#!/usr/bin/env python3
"""
GOD EYE -- Main entry point (v5.0 — Resilient & Observable System)

Architecture:
  ┌─────────────────────────────────────────────────────────────────┐
  │  main.py  (Composition Root)                                    │
  │  ┌─────────┐   ┌──────────────┐   ┌─────────────────────────┐ │
  │  │ Flask   │──▶│ PTB App      │──▶│ Container (DI)          │ │
  │  │ WSGI    │   │ daemon thread│   │ ├─ services (use cases) │ │
  │  └─────────┘   └──────────────┘   │ ├─ repositories         │ │
  │                                    │ └─ gateways             │ │
  │                                    └─────────────────────────┘ │
  └─────────────────────────────────────────────────────────────────┘

v5.0 changes:
  - Structured JSON logging (GCP Cloud Logging compatible)
  - Graceful shutdown: SIGTERM → wait for background tasks → clean exit
  - All logging now structured with trace IDs
"""
import asyncio
import logging
import os
import signal
import sys
import threading
from typing import Optional

from flask import Flask, jsonify, redirect, request
from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from infrastructure.config import AppConfig
from infrastructure.container import Container
from infrastructure.logger import setup_logging, get_logger
from infrastructure.migrations import init_database
from adapters.controllers.telegram_handlers import (
    STATE_BUDGET,
    STATE_CONFIRM,
    STATE_RADIUS,
    cmd_clear,
    cmd_help,
    cmd_history,
    cmd_newchat,
    cmd_start,
    cmd_stats,
    handle_callback_query,
    handle_message,
    settings_budget,
    settings_cancel,
    settings_confirm,
    settings_radius,
    settings_start,
)
from adapters.controllers.monitor_handler import handle_monitor_post
from web.dashboard import dashboard_bp

# -- Structured Logging (must be before any logger usage) ----------------------
setup_logging(level=logging.INFO)
log = get_logger("god-eye")

# -- Config (single source of truth) ------------------------------------------
config = AppConfig.from_env()

TELEGRAM_TOKEN  = config.telegram.token
ALLOWED_CHAT_ID = config.telegram.allowed_chat_id
N8N_SECRET      = config.telegram.n8n_webhook_secret

# -- Initialize PostgreSQL Database -------------------------------------------
async def _init_db() -> None:
    """Initialize PostgreSQL connection pool and run migrations."""
    try:
        db_url = config.postgres.url
        if not db_url:
            log.error("DATABASE_URL not configured -- cannot initialize database")
            raise RuntimeError("DATABASE_URL environment variable not set")
        
        pool = await init_database(db_url)
        log.info("✅ PostgreSQL database initialized successfully")
    except Exception as exc:
        log.critical(f"❌ Failed to initialize database: {exc}", exc_info=True)
        raise


# Initialize database at startup
try:
    asyncio.run(_init_db())
except Exception as exc:
    log.critical(f"Cannot start without database: {exc}")
    sys.exit(1)


_BOT_COMMANDS = [
    BotCommand("start",    "Initialize God Eye -- system status"),
    BotCommand("help",     "Show input guide and command reference"),
    BotCommand("history",  "Last 3 analyzed listings with scores"),
    BotCommand("stats",    "Current session stats and preferences"),
    BotCommand("settings", "Configure budget and search radius"),
    BotCommand("clear",    "Reset all learned area preferences"),
    BotCommand("newchat",  "Clear chat view and start a fresh session"),
]

# -- Build DI Container -------------------------------------------------------
container = Container.build(config)

# -- PTB Application globals ---------------------------------------------------
_ptb_app:    Optional[Application]               = None
_ptb_loop:   Optional[asyncio.AbstractEventLoop] = None
_ptb_thread: Optional[threading.Thread]          = None


async def _post_init(application: Application) -> None:
    try:
        await application.bot.set_my_commands(_BOT_COMMANDS)
        log.info("Bot commands registered.")
    except Exception as exc:
        log.warning("set_my_commands failed (non-fatal): %s", exc)


def _build_application() -> Application:
    settings_conv = ConversationHandler(
        entry_points=[CommandHandler("settings", settings_start)],
        states={
            STATE_BUDGET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, settings_budget),
            ],
            STATE_RADIUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, settings_radius),
            ],
            STATE_CONFIRM: [
                CallbackQueryHandler(settings_confirm, pattern="^settings_(yes|no)$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", settings_cancel)],
        per_user=True,
        per_chat=False,
    )

    allowed = filters.Chat(chat_id=ALLOWED_CHAT_ID)

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .updater(None)
        .post_init(_post_init)
        .concurrent_updates(True)   # ← PTB processes next update immediately,
        .build()                    #   even while a previous handler is awaited.
                                    #   Safe because handle_message returns < 1 s
                                    #   (analysis runs in a background Task).
    )

    # ── Inject container into bot_data for all handlers to access ─────────
    app.bot_data["container"] = container

    app.add_handler(settings_conv, group=-1)
    app.add_handler(CommandHandler("start",   cmd_start,   filters=allowed))
    app.add_handler(CommandHandler("help",    cmd_help,    filters=allowed))
    app.add_handler(CommandHandler("history", cmd_history, filters=allowed))
    app.add_handler(CommandHandler("stats",   cmd_stats,   filters=allowed))
    app.add_handler(CommandHandler("clear",   cmd_clear,   filters=allowed))
    app.add_handler(CommandHandler("newchat", cmd_newchat, filters=allowed))
    app.add_handler(
        CallbackQueryHandler(
            lambda update, ctx: handle_callback_query(update, ctx, ALLOWED_CHAT_ID)
        )
    )
    app.add_handler(
        MessageHandler(
            allowed & (filters.TEXT | filters.PHOTO | filters.Document.IMAGE),
            lambda update, ctx: handle_message(update, ctx, ALLOWED_CHAT_ID),
        )
    )
    return app


# -- Background thread runner --------------------------------------------------
def _run_ptb_in_thread(app: Application) -> None:
    global _ptb_loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _ptb_loop = loop
    log.info("PTB event loop started in background thread.")

    async def _runner() -> None:
        async with app:
            await app.start()
            log.info("PTB Application started -- ready to process updates.")
            await asyncio.Event().wait()

    try:
        loop.run_until_complete(_runner())
    except Exception as exc:
        log.critical("PTB background thread crashed: %s", exc, exc_info=True)


# -- Thread-safe helpers -------------------------------------------------------
def _enqueue_update(update: Update) -> None:
    if _ptb_loop is None or _ptb_app is None:
        log.error("PTB not ready -- dropping update %s", update.update_id)
        return
    asyncio.run_coroutine_threadsafe(
        _ptb_app.update_queue.put(update),
        _ptb_loop,
    )


def _schedule(coro) -> None:
    """Schedule a coroutine on the PTB event loop (fire-and-forget)."""
    if _ptb_loop is None:
        log.error("PTB loop not ready -- dropping coroutine.")
        return
    asyncio.run_coroutine_threadsafe(coro, _ptb_loop)


# -- Start PTB at import time --------------------------------------------------
def _start_ptb() -> None:
    global _ptb_app, _ptb_thread
    _ptb_app    = _build_application()
    _ptb_thread = threading.Thread(
        target=_run_ptb_in_thread,
        args=(_ptb_app,),
        daemon=True,
        name="ptb-event-loop",
    )
    _ptb_thread.start()
    log.info("PTB daemon thread launched.")


_start_ptb()

# -- Graceful Shutdown ---------------------------------------------------------
_shutdown_event = threading.Event()


def _graceful_shutdown(signum, frame):
    """
    Handle SIGTERM from Cloud Run.
    Cloud Run gives ~10s after SIGTERM before SIGKILL.
    Wait for running analysis tasks, then exit cleanly.
    """
    sig_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
    log.warning("Received %s — initiating graceful shutdown", sig_name)

    if _ptb_loop:
        import concurrent.futures
        future = asyncio.run_coroutine_threadsafe(
            _wait_for_analysis_tasks(timeout=8.0), _ptb_loop
        )
        try:
            future.result(timeout=9.0)
        except (concurrent.futures.TimeoutError, Exception) as exc:
            log.warning("Graceful wait interrupted: %s", exc)

    _shutdown_event.set()
    log.info("Graceful shutdown complete.")
    sys.exit(0)


async def _wait_for_analysis_tasks(timeout: float = 8.0) -> None:
    """Wait for running analysis asyncio tasks to complete before shutdown."""
    tasks = [
        t for t in asyncio.all_tasks()
        if t.get_name().startswith("analysis-") or t.get_name().startswith("retry-")
    ]
    if not tasks:
        log.info("No running analysis tasks — immediate shutdown OK.")
        return
    log.info("Waiting for %d analysis task(s) (timeout=%.0fs)", len(tasks), timeout)
    done, pending = await asyncio.wait(tasks, timeout=timeout)
    if pending:
        log.warning("Cancelling %d task(s) still running after timeout", len(pending))
        for t in pending:
            t.cancel()


signal.signal(signal.SIGTERM, _graceful_shutdown)
signal.signal(signal.SIGINT, _graceful_shutdown)

# -- Flask app -----------------------------------------------------------------
flask_app = Flask(__name__)
flask_app.register_blueprint(dashboard_bp)
flask_app.config["CONTAINER"] = container  # inject untuk dashboard


@flask_app.route("/", methods=["GET"])
def root():
    return redirect("/dashboard/", code=302)


@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok":   True,
        "ptb":  _ptb_thread.is_alive() if _ptb_thread else False,
        "loop": _ptb_loop is not None,
    })


@flask_app.route("/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"ok": False, "error": "empty body"}), 400
    if _ptb_app is None:
        log.error("PTB app not ready")
        return jsonify({"ok": False, "error": "ptb not ready"}), 503
    try:
        update = Update.de_json(data, _ptb_app.bot)
        _enqueue_update(update)
        return jsonify({"ok": True})
    except Exception as exc:
        log.error("Failed to parse/enqueue update: %s", exc, exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@flask_app.route("/monitor", methods=["POST"])
def n8n_monitor():
    """
    Decoupled webhook: validates auth + payload, then fires-and-forgets
    the processing coroutine on the PTB event loop.
    Returns 202 Accepted immediately — n8n gets a fast response,
    analysis + notification happen asynchronously.
    """
    if N8N_SECRET:
        auth = request.headers.get("X-Webhook-Secret", "")
        if auth != N8N_SECRET:
            return jsonify({"ok": False, "error": "forbidden"}), 403
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"ok": False, "error": "empty body"}), 400
    if _ptb_app is None:
        return jsonify({"ok": False, "error": "ptb not ready"}), 503

    # ── Fire-and-forget: schedule on PTB event loop, return 202 ──────────
    _schedule(handle_monitor_post(data, _ptb_app.bot, ALLOWED_CHAT_ID, container))
    return jsonify({"ok": True, "status": "accepted"}), 202


if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=8080, debug=True)
