"""
adapters/controllers/telegram_handlers.py  (v4.1)

Thin PTB handler functions — delegate all business logic to the service layer.
Each handler:
  1. Extracts input from Update/Context
  2. Guards against duplicate processing via idempotency cache
  3. Gets the Container from bot_data
  4. Calls the appropriate service
  5. Formats and sends the response

Architecture note:
  Container is stored in application.bot_data["container"] and injected
  by main.py at startup.  Handlers never import repositories or gateways.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Optional

import httpx
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest as TgBadRequest
from telegram.ext import CallbackContext, ContextTypes, ConversationHandler

from adapters.controllers.formatter import (
    LOADING_STEPS,
    escape_md,
    format_loading,
    format_report,
    split_message,
)
from adapters.controllers.keyboards import confirm_keyboard, report_keyboard
from infrastructure.container import Container

log = logging.getLogger("god-eye.handlers")

# ── ConversationHandler state constants ──────────────────────────────────────
STATE_BUDGET = 0
STATE_RADIUS = 1
STATE_CONFIRM = 2

# ── Settings rate-limit ──────────────────────────────────────────────────────
_settings_ratelimit: dict[int, list[float]] = {}
_RATELIMIT_WINDOW = 60.0
_RATELIMIT_MAX_CALLS = 3

# ── Per-chat analysis lock + update-id idempotency ───────────────────────────
#
# ROOT CAUSE of duplicate analyses:
#   Telegram retries do NOT always use the same update_id.
#   A single user message can produce retries with DIFFERENT update_ids
#   when Telegram doesn't receive HTTP 200 fast enough.
#   Per-update_id dedup is therefore insufficient.
#
# CORRECT APPROACH: per-chat_id lock
#   If chat_id already has an analysis in-flight → drop all new messages
#   until the current analysis finishes (or times out).
#
# Secondary: per-update_id dedup (still useful when same update_id IS retried)

# Per-chat asyncio.Lock — only one analysis per chat at a time
_chat_locks: dict[int, asyncio.Lock] = {}

# Per-update_id dedup — catches identical update_id retries (secondary guard)
_processed_updates: dict[int, float] = {}
_IDEMPOTENCY_TTL = 300.0  # 5 min eviction window

# Track which chat_ids currently have an analysis running
_chat_busy: set[int] = set()


def _get_chat_lock(chat_id: int) -> asyncio.Lock:
    """Return (creating if needed) the asyncio.Lock for this chat_id."""
    if chat_id not in _chat_locks:
        _chat_locks[chat_id] = asyncio.Lock()
    return _chat_locks[chat_id]


def _is_chat_busy(chat_id: int) -> bool:
    """True if chat_id already has an analysis task running."""
    return chat_id in _chat_busy


def _mark_chat_busy(chat_id: int) -> None:
    _chat_busy.add(chat_id)


def _mark_chat_free(chat_id: int) -> None:
    _chat_busy.discard(chat_id)


def _claim_update(update_id: int) -> bool:
    """
    Per-update_id dedup (secondary guard for identical-id retries).
    Returns True → first time seen, proceed.
    Returns False → already seen, drop.
    """
    now = time.monotonic()
    stale = [uid for uid, ts in _processed_updates.items() if now - ts > _IDEMPOTENCY_TTL]
    for uid in stale:
        del _processed_updates[uid]
    if update_id in _processed_updates:
        log.warning("Idempotency: duplicate update_id=%s — dropped", update_id)
        return False
    _processed_updates[update_id] = now
    return True


# Alias for non-analysis handlers (callbacks/commands)
def _is_duplicate_update(update_id: int) -> bool:
    return not _claim_update(update_id)





def _get_container(context: CallbackContext) -> Container:
    """Retrieve the DI container from bot_data."""
    return context.bot_data["container"]


def _check_ratelimit(chat_id: int) -> bool:
    now = time.monotonic()
    bucket = _settings_ratelimit.setdefault(chat_id, [])
    _settings_ratelimit[chat_id] = [t for t in bucket if now - t < _RATELIMIT_WINDOW]
    if len(_settings_ratelimit[chat_id]) >= _RATELIMIT_MAX_CALLS:
        return False
    _settings_ratelimit[chat_id].append(now)
    return True


async def _download_photo(bot: Bot, file_id: str) -> Optional[bytes]:
    try:
        file = await bot.get_file(file_id)
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(file.file_path)
            return resp.content
    except Exception as exc:
        log.warning("Failed to download file %s: %s", file_id, exc)
        return None


# ── Core analysis flow ────────────────────────────────────────────────────────

async def _run_analysis_with_progress(
    bot: Bot,
    chat_id: int,
    text: str,
    image_bytes: Optional[bytes],
    source_link: str,
    source: str,
    container: Container,
) -> None:
    """5-checkpoint progressive-edit analysis via service layer."""
    session_repo = container.session_repo
    analysis_svc = container.analysis_service
    msg_id: Optional[int] = None

    try:
        msg_id = await session_repo.get_message_id(chat_id)
        if not msg_id:
            boot = await bot.send_message(
                chat_id=chat_id,
                text=format_loading(1, 5, "SYSTEM: Booting God Eye Engine"),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            msg_id = boot.message_id
            await session_repo.save_message_id(chat_id, msg_id)

        start_time = time.monotonic()
        spinner = 0
        result = None

        for step, tag, label in LOADING_STEPS:
            if time.monotonic() - start_time > 60.0:
                await _send_timeout_warning(bot, chat_id, msg_id)
                await session_repo.clear(chat_id)
                return

            try:
                await bot.edit_message_text(
                    text=format_loading(step, 5, f"{tag}: {label}", spinner),
                    chat_id=chat_id,
                    message_id=msg_id,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            except TgBadRequest as e:
                if "message is not modified" in str(e).lower():
                    pass  # identical content — safe to ignore
                else:
                    raise
            spinner = (spinner + 1) % 4

            if step == 3:
                try:
                    result = await asyncio.wait_for(
                        analysis_svc.analyze(
                            text=text,
                            image_bytes=image_bytes,
                            source_link=source_link,
                            source=source,
                            chat_id=chat_id,
                        ),
                        timeout=55.0,
                    )
                except asyncio.TimeoutError:
                    await _send_timeout_warning(bot, chat_id, msg_id)
                    await session_repo.clear(chat_id)
                    return

        if result is None:
            raise RuntimeError("Analysis returned no result")

        report = format_report(result)
        chunks = split_message(report)
        keyboard = report_keyboard(
            listing_id=result.listing_id,
            phone=result.phones[0] if result.phones else None,
        )

        await bot.edit_message_text(
            text=chunks[0],
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=keyboard if len(chunks) == 1 else None,
            disable_web_page_preview=True,
        )

        for idx in range(1, len(chunks)):
            markup = keyboard if idx == len(chunks) - 1 else None
            await bot.send_message(
                chat_id=chat_id,
                text=chunks[idx],
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=markup,
                disable_web_page_preview=True,
            )

        await session_repo.clear(chat_id)

    except TgBadRequest as exc:
        # Silently ignore "Message is not modified" — it's a Telegram API quirk,
        # not a real error. All other BadRequest errors still bubble up.
        if "message is not modified" in str(exc).lower():
            log.debug("Skipped duplicate edit for chat_id=%s", chat_id)
            await session_repo.clear(chat_id)
            return
        log.error("Telegram BadRequest for chat_id=%s: %s", chat_id, exc, exc_info=True)
        err_text = (
            "*\\[ERROR\\]*\n"
            f"`code: {escape_md(type(exc).__name__)}`\n"
            f"`msg:  {escape_md(str(exc)[:200])}`"
        )
        try:
            if msg_id:
                await bot.edit_message_text(
                    err_text,
                    chat_id=chat_id,
                    message_id=msg_id,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            else:
                await bot.send_message(chat_id=chat_id, text=err_text, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as send_exc:
            log.error("Failed to deliver error message: %s", send_exc)
        await session_repo.clear(chat_id)

    except Exception as exc:
        log.error("Analysis failed for chat_id=%s: %s", chat_id, exc, exc_info=True)
        err_text = (
            "*\\[WARNING\\]*\n"
            f"`code: {escape_md(type(exc).__name__)}`\n"
            f"`msg:  {escape_md(str(exc)[:200])}`"
        )
        try:
            if msg_id:
                await bot.edit_message_text(
                    err_text,
                    chat_id=chat_id,
                    message_id=msg_id,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=err_text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
        except Exception as send_exc:
            log.error("Failed to deliver error message: %s", send_exc)
        await session_repo.clear(chat_id)


async def _send_timeout_warning(bot: Bot, chat_id: int, msg_id: int) -> None:
    timeout_text = (
        "*\\[WARNING\\]*\n"
        "`code: ANALYSIS_TIMEOUT`\n\n"
        "Analysis exceeded 60s\\. Select an option:"
    )
    try:
        await bot.edit_message_text(
            text=timeout_text,
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Retry", callback_data="reanalyze"),
                    InlineKeyboardButton("Queue", callback_data="queue"),
                ],
                [InlineKeyboardButton("Manual Check", callback_data="manual")],
            ]),
        )
    except Exception as exc:
        log.warning("Failed to send timeout warning: %s", exc)


# ── Message handler ───────────────────────────────────────────────────────────

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    allowed_chat_id: int,
) -> None:
    """
    PTB entry-point for all user messages.

    CRITICAL PATH — must return to PTB in milliseconds so the next update
    can be dequeued before Telegram's webhook timeout fires a retry.

    Duplicate-suppression strategy (two guards, innermost wins):
      Guard 1 — per-update_id dedup: drops retries with identical update_id.
      Guard 2 — per-chat_id busy flag: drops retries with different update_ids
                for the same chat while an analysis is already running.
                This is the PRIMARY guard that stops the 3× spam in the screenshot.

    Flow:
      1. Guard 1 check  → drop identical-id retries
      2. Guard 2 check  → drop if chat already busy
      3. Mark chat busy
      4. Download image (fast, Telegram CDN, <1 s)
      5. asyncio.create_task(_run_analysis_with_progress)
      6. return immediately
    """
    update_id = update.update_id

    # Guard 1 — per-update_id (catches Telegram sending exact same update_id)
    if not _claim_update(update_id):
        return

    msg = update.message
    if not msg:
        return
    if msg.chat_id != allowed_chat_id:
        await msg.reply_text("Access denied.")
        return

    chat_id = allowed_chat_id

    # Guard 2 — per-chat busy flag (PRIMARY: catches different-update_id retries)
    if _is_chat_busy(chat_id):
        log.warning(
            "Chat %s busy: dropping update_id=%s (analysis already running)",
            chat_id, update_id,
        )
        return

    # Mark this chat as busy BEFORE any await — no concurrency gap
    _mark_chat_busy(chat_id)

    container = _get_container(context)
    text = msg.text or msg.caption or ""
    image_bytes: Optional[bytes] = None

    # Image download is cheap (Telegram CDN) — do it here, not in the Task
    if msg.photo:
        image_bytes = await _download_photo(context.bot, msg.photo[-1].file_id)
    elif (msg.document
          and msg.document.mime_type
          and msg.document.mime_type.startswith("image/")):
        image_bytes = await _download_photo(context.bot, msg.document.file_id)

    if not text and not image_bytes:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "*\\[SYSTEM\\]*\n"
                "Send listing text, a URL, a room photo, or a screenshot\\."
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        _mark_chat_free(chat_id)   # nothing to analyse — unlock immediately
        return

    links = re.findall(r"https?://[^\s]+", text)
    source_link = links[0] if links else ""

    # ── Spawn background Task — handler returns immediately after this ──────
    async def _analysis_task() -> None:
        try:
            await _run_analysis_with_progress(
                bot=context.bot,
                chat_id=chat_id,
                text=text,
                image_bytes=image_bytes,
                source_link=source_link,
                source="manual",
                container=container,
            )
        finally:
            # Always release the lock — even on exception or cancellation
            _mark_chat_free(chat_id)
            log.info("Chat %s unlocked after analysis (update_id=%s)", chat_id, update_id)

    task = asyncio.create_task(_analysis_task(), name=f"analysis-chat{chat_id}-uid{update_id}")
    log.info(
        "Analysis task spawned: chat_id=%s update_id=%s task=%s",
        chat_id, update_id, task.get_name(),
    )
    # Handler returns here — PTB immediately processes the next queued update






# ── Callback query handler ───────────────────────────────────────────────────

async def handle_callback_query(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    allowed_chat_id: int,
) -> None:
    # ── Idempotency guard ──────────────────────────────────────────────────
    if update.update_id and _is_duplicate_update(update.update_id):
        return

    query = update.callback_query
    if not query:
        return
    await query.answer()
    if query.message.chat_id != allowed_chat_id:
        return

    container = _get_container(context)
    data = query.data or ""
    log.info("Callback: %r", data)

    # ── Bare actions ──────────────────────────────────────────────────────
    if data == "queue":
        await context.bot.send_message(
            chat_id=allowed_chat_id,
            text="*\\[SYSTEM\\]* Analysis queued\\.\nResend the listing when ready to retry\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if data == "manual":
        await context.bot.send_message(
            chat_id=allowed_chat_id,
            text="*\\[SYSTEM\\]* Manual review mode\\.\nForward the listing to proceed without AI analysis\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if data == "reanalyze":
        await context.bot.send_message(
            chat_id=allowed_chat_id,
            text="*\\[SYSTEM\\]* Resend the listing to trigger a fresh analysis\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if ":" not in data:
        return

    action, listing_id = data.split(":", 1)

    if action == "open_dashboard":
        return

    if action == "reanalyze":
        await context.bot.send_message(
            chat_id=allowed_chat_id,
            text=(
                f"*\\[SYSTEM\\]* Resend listing `{escape_md(listing_id)}` "
                "to trigger a fresh analysis\\."
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    # ── Feedback actions (delegated to service) ───────────────────────────
    listing_doc = await container.listing_repo.get(listing_id)
    location = listing_doc.get("location", "") if listing_doc else ""
    price_value = listing_doc.get("price_value") if listing_doc else None

    try:
        await container.feedback_service.process(
            chat_id=allowed_chat_id,
            listing_id=listing_id,
            action=action,
            location=location,
            price_value=float(price_value) if price_value is not None else None,
            listing=listing_doc,
        )
    except Exception as exc:
        log.warning("feedback non-fatal: %s", exc)

    feedback_map: dict[str, str] = {
        "survey": f"Listing `{escape_md(listing_id)}` marked for survey\\. Preferences updated\\.",
        "skip": f"Listing `{escape_md(listing_id)}` skipped\\. Area noted for avoidance\\.",
        "save": f"Listing `{escape_md(listing_id)}` saved to watchlist\\.",
        "save_watchlist": f"Listing `{escape_md(listing_id)}` saved to watchlist\\.",
        "blacklist": f"Phone from listing `{escape_md(listing_id)}` reported and blacklisted\\.",
    }
    reply = feedback_map.get(action, f"Feedback `{escape_md(action)}` recorded\\.")
    await context.bot.send_message(
        chat_id=allowed_chat_id,
        text=f"*\\[SYSTEM\\]* {reply}",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "*\\[SYSTEM\\]* God Eye Engine — online\n\n"
            "Send any kos listing to begin analysis:\n"
            "  `text`  — paste raw ad copy\n"
            "  `URL`   — Mamikos / FB / Instagram link\n"
            "  `photo` — room or location screenshot\n\n"
            "Use /help for full command reference\\."
        ),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "*\\[SYSTEM\\]* Command Reference\n\n"
            "`/start`    — system status and input guide\n"
            "`/help`     — this message\n"
            "`/history`  — last 3 analyzed listings with scores\n"
            "`/stats`    — session stats and active preferences\n"
            "`/settings` — configure budget and search radius\n"
            "`/clear`    — reset all learned area preferences\n\n"
            "*Input formats accepted:*\n"
            "  Plain text, URL, photo, or document image\\.\n\n"
            "*Analysis pipeline:*\n"
            "  Gemini Vision \\+ DeepSeek scoring \\+ Maps \\+ AQI\n"
            "  Fraud detection via phone blacklist \\+ pattern scoring\\."
        ),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    container = _get_container(context)
    try:
        history = await container.listing_repo.get_recent(limit=3)
    except Exception as exc:
        log.error("get_recent failed: %s", exc)
        history = []

    if not history:
        await context.bot.send_message(
            chat_id=chat_id,
            text="*\\[HISTORY\\]* No listings analyzed yet\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    lines = ["*\\[HISTORY\\]* Last analyzed listings\n"]
    for idx, item in enumerate(history, 1):
        lid = escape_md(item.get("listing_id", "unknown"))
        price = escape_md(item.get("price_text", "—"))
        score = escape_md(str(item.get("price_score", "—")))
        rec = escape_md(item.get("recommendation", "—"))
        loc = escape_md(item.get("location", "—"))
        lines.append(
            f"{idx}\\. `{lid}`\n"
            f"   price: `{price}`  score: `{score}/100`\n"
            f"   location: {loc}\n"
            f"   verdict: {rec}"
        )
    await context.bot.send_message(
        chat_id=chat_id,
        text="\n\n".join(lines),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    container = _get_container(context)
    try:
        total = await container.listing_repo.count_all()
        flagged = await container.listing_repo.count_high_risk()
        prefs = await container.preferences_repo.get(chat_id)
    except Exception as exc:
        log.error("stats failed: %s", exc)
        total, flagged = 0, 0
        from domain.models import UserPreferences
        prefs = UserPreferences()

    budget = escape_md(str(prefs.max_price))
    radius = escape_md(str(prefs.max_distance_km))
    p_str = escape_md(", ".join(prefs.preferred_areas) or "none")
    a_str = escape_md(", ".join(prefs.avoided_areas) or "none")

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "*\\[STATS\\]* Session overview\n\n"
            f"`total analyzed  :` {escape_md(str(total))}\n"
            f"`flagged high risk:` {escape_md(str(flagged))}\n\n"
            "*Active preferences:*\n"
            f"`budget max     :` Rp{budget}\n"
            f"`search radius  :` {radius} km\n"
            f"`preferred areas:` {p_str}\n"
            f"`avoided areas  :` {a_str}"
        ),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    container = _get_container(context)
    try:
        await container.preferences_repo.clear_areas(chat_id)
        text = (
            "*\\[SYSTEM\\]* Preferences cleared\\.\n"
            "`preferred_areas` and `avoided_areas` reset to empty\\."
        )
    except Exception as exc:
        log.error("clear_areas failed: %s", exc)
        text = (
            "*\\[WARNING\\]*\n"
            f"`code: {escape_md(type(exc).__name__)}`\n"
            "Failed to clear preferences\\."
        )
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_newchat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    container = _get_container(context)
    await container.session_repo.clear(chat_id)

    separator = (
        "\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n"
        "\n\n\n\n\n\n\n\n\n\n"
        "\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-"
    )
    await context.bot.send_message(chat_id=chat_id, text=separator, parse_mode=ParseMode.MARKDOWN_V2)
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "*\\[SYSTEM\\]* \\-\\- New Session Started \\-\\-\n\n"
            "God Eye Engine is ready\\.\n"
            "Send a listing \\(text, URL, or photo\\) to begin\\."
        ),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# ── /settings ConversationHandler ────────────────────────────────────────────

async def settings_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    if not _check_ratelimit(chat_id):
        await context.bot.send_message(
            chat_id=chat_id,
            text="*\\[SYSTEM\\]* Rate limit reached\\.\nTry again in 60 seconds\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return ConversationHandler.END

    container = _get_container(context)
    try:
        prefs = await container.preferences_repo.get(chat_id)
        budget = escape_md(str(prefs.max_price))
    except Exception:
        budget = "650000"

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "*\\[SETTINGS\\]* Configure search parameters\n\n"
            f"Current budget max: `Rp{budget}`\n\n"
            "Enter new monthly budget maximum \\(integer, in Rupiah\\):\n"
            "Example: `1500000`\n\n"
            "Send /cancel to abort\\."
        ),
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return STATE_BUDGET


async def settings_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    raw = (update.message.text or "").strip()
    raw_clean = raw.replace(".", "").replace(",", "").replace("_", "")

    if not raw_clean.isdigit() or int(raw_clean) <= 0:
        await context.bot.send_message(
            chat_id=chat_id,
            text="*\\[SETTINGS\\]* Invalid input\\.\nEnter a positive integer\\. Example: `1500000`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return STATE_BUDGET

    context.user_data["settings_budget"] = int(raw_clean)

    container = _get_container(context)
    try:
        prefs = await container.preferences_repo.get(chat_id)
        radius = escape_md(str(prefs.max_distance_km))
    except Exception:
        radius = "5"

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"Budget set to `Rp{escape_md(raw_clean)}`\\.\n\n"
            f"Current search radius: `{radius} km`\n\n"
            "Enter new search radius \\(km, decimal allowed\\):\n"
            "Example: `3\\.5`\n\n"
            "Send /cancel to abort\\."
        ),
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return STATE_RADIUS


async def settings_radius(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    raw = (update.message.text or "").strip().replace(",", ".")
    try:
        radius_val = float(raw)
        if radius_val <= 0:
            raise ValueError("non-positive")
    except ValueError:
        await context.bot.send_message(
            chat_id=chat_id,
            text="*\\[SETTINGS\\]* Invalid input\\.\nEnter a positive number\\. Example: `3\\.5`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return STATE_RADIUS

    context.user_data["settings_radius"] = radius_val
    budget_val = context.user_data.get("settings_budget", "—")
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "*\\[SETTINGS\\]* Confirm new settings:\n\n"
            f"`budget max    :` Rp{escape_md(str(budget_val))}\n"
            f"`search radius :` {escape_md(str(radius_val))} km\n\n"
            "Save these settings?"
        ),
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=confirm_keyboard(),
    )
    return STATE_CONFIRM


async def settings_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    chat_id = update.effective_chat.id
    await query.answer()

    if query.data == "settings_yes":
        container = _get_container(context)
        budget_val = context.user_data.get("settings_budget")
        radius_val = context.user_data.get("settings_radius")
        patch: dict = {}
        if budget_val is not None:
            patch["max_price"] = budget_val
        if radius_val is not None:
            patch["max_distance_km"] = radius_val
        try:
            await container.preferences_repo.update(chat_id, patch)
            text = (
                "*\\[SETTINGS\\]* Preferences saved\\.\n"
                f"`budget max    :` Rp{escape_md(str(budget_val))}\n"
                f"`search radius :` {escape_md(str(radius_val))} km"
            )
        except Exception as exc:
            log.error("update_preferences failed: %s", exc)
            text = (
                "*\\[WARNING\\]*\n"
                f"`code: {escape_md(type(exc).__name__)}`\n"
                "Failed to save preferences\\."
            )
    else:
        text = "*\\[SETTINGS\\]* Cancelled\\. No changes made\\."

    context.user_data.pop("settings_budget", None)
    context.user_data.pop("settings_radius", None)
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2)
    return ConversationHandler.END


async def settings_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("settings_budget", None)
    context.user_data.pop("settings_radius", None)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="*\\[SETTINGS\\]* Cancelled\\. No changes made\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return ConversationHandler.END
