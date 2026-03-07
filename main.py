#!/usr/bin/env python3
"""
GOD EYE -- Main entry point (v4.0 — Clean Architecture)

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

Changes from v3.3:
  - DI Container wires all dependencies; handlers read from bot_data["container"]
  - /monitor returns 202 Accepted immediately, processes in background
  - All imports point to v2/ clean architecture modules
  - Handlers are thin adapters; business logic lives in services/
"""
import asyncio
import logging
import os
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

# -- Logging -------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("god-eye")

# -- Config (single source of truth) ------------------------------------------
config = AppConfig.from_env()

TELEGRAM_TOKEN  = config.telegram.token
ALLOWED_CHAT_ID = config.telegram.allowed_chat_id
N8N_SECRET      = config.telegram.n8n_webhook_secret

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

# -- Flask app -----------------------------------------------------------------
flask_app = Flask(__name__)
flask_app.register_blueprint(dashboard_bp)


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
