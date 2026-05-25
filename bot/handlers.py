"""
bot/handlers.py  (v3.3)

Handler functions registered on the PTB Application in main.py.
All handlers receive a real telegram.ext.CallbackContext — no stubs needed.

Architecture note
─────────────────
The old handle_update() + asyncio.run() pattern caused httpx.PoolTimeout because
the Bot's connection pool was bound to the import-time event loop while each
Flask request created a new one.  This file now contains only pure handler
functions; the Application and its event loop live in main.py.
"""
import asyncio
import logging
import re
import time
from typing import Optional

import httpx
from telegram import Bot, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, ContextTypes, ConversationHandler

from bot.formatter import (
    LOADING_STEPS,
    escape_md,
    format_loading,
    format_report,
    split_message,
)
from bot.keyboards import confirm_keyboard, report_keyboard
from engine.analyzer import full_analysis
from memory.firestore import (
    clear_session,
    clear_user_preferences,
    get_listing,
    get_preferences,
    get_session_message_id,
    get_user_history,
    get_user_stats,
    save_session_message_id,
    update_preferences,
)
from memory.learning import process_feedback

log = logging.getLogger("god-eye.handlers")

# ── ConversationHandler state constants ──────────────────────────────────────
STATE_BUDGET  = 0
STATE_RADIUS  = 1
STATE_CONFIRM = 2

# ── Settings rate-limit: {chat_id: [timestamp, ...]} ─────────────────────────
_settings_ratelimit: dict[int, list[float]] = {}
_RATELIMIT_WINDOW    = 60.0
_RATELIMIT_MAX_CALLS = 3


# ── Internal helpers ──────────────────────────────────────────────────────────

def _check_ratelimit(chat_id: int) -> bool:
    now    = time.monotonic()
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
) -> None:
    """
    5-checkpoint progressive-edit analysis engine.
    Sends a single boot message, edits it through each LOADING_STEP,
    then replaces the final loading message with the full formatted report.
    """
    msg_id: Optional[int] = None

    try:
        # Idempotency: reuse existing session message on restart
        msg_id = await get_session_message_id(chat_id)
        if not msg_id:
            boot = await bot.send_message(
                chat_id=chat_id,
                text=format_loading(1, 5, "SYSTEM: Booting God Eye Engine"),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            msg_id = boot.message_id
            await save_session_message_id(chat_id, msg_id)

        start_time = time.monotonic()
        spinner    = 0
        result     = None

        for step, tag, label in LOADING_STEPS:
            # Timeout guard
            if time.monotonic() - start_time > 60.0:
                await _send_timeout_warning(bot, chat_id, msg_id)
                await clear_session(chat_id)
                return

            await bot.edit_message_text(
                text=format_loading(step, 5, f"{tag}: {label}", spinner),
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            spinner = (spinner + 1) % 4

            if step == 3:
                try:
                    result = await asyncio.wait_for(
                        full_analysis(
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
                    await clear_session(chat_id)
                    return

        if result is None:
            raise RuntimeError("Analysis returned no result")

        report   = format_report(result)
        chunks   = split_message(report)
        keyboard = report_keyboard(
            listing_id=result.listing_id,
            phone=result.phones[0] if result.phones else None,
        )

        # Edit first chunk in place (replaces the loading message)
        await bot.edit_message_text(
            text=chunks[0],
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=keyboard if len(chunks) == 1 else None,
            disable_web_page_preview=True,
        )

        # Overflow chunks as new messages
        for idx in range(1, len(chunks)):
            markup = keyboard if idx == len(chunks) - 1 else None
            await bot.send_message(
                chat_id=chat_id,
                text=chunks[idx],
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=markup,
                disable_web_page_preview=True,
            )

        await clear_session(chat_id)

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
                    err_text, chat_id=chat_id, message_id=msg_id,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            else:
                await bot.send_message(chat_id=chat_id, text=err_text,
                                       parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as send_exc:
            log.error("Failed to deliver error message: %s", send_exc)
        await clear_session(chat_id)


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
                    InlineKeyboardButton("Retry",        callback_data="reanalyze"),
                    InlineKeyboardButton("Queue",        callback_data="queue"),
                ],
                [
                    InlineKeyboardButton("Manual Check", callback_data="manual"),
                ],
            ]),
        )
    except Exception as exc:
        log.warning("Failed to send timeout warning: %s", exc)


# ── PTB-registered message handler ───────────────────────────────────────────

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    allowed_chat_id: int,
) -> None:
    """
    Handles all non-command text, photo, and image-document messages.
    Registered on Application in main.py with an `allowed` Chat filter,
    so the auth check below is a belt-and-suspenders guard.
    """
    msg = update.message
    if not msg:
        return
    if msg.chat_id != allowed_chat_id:
        await msg.reply_text("Access denied.")
        return

    text        = msg.text or msg.caption or ""
    image_bytes: Optional[bytes] = None

    if msg.photo:
        image_bytes = await _download_photo(context.bot, msg.photo[-1].file_id)
    elif (
        msg.document
        and msg.document.mime_type
        and msg.document.mime_type.startswith("image/")
    ):
        image_bytes = await _download_photo(context.bot, msg.document.file_id)

    if not text and not image_bytes:
        await context.bot.send_message(
            chat_id=allowed_chat_id,
            text=(
                "*\\[SYSTEM\\]*\n"
                "Send listing text, a URL, a room photo, or a screenshot\\."
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    links       = re.findall(r"https?://[^\s]+", text)
    source_link = links[0] if links else ""

    await _run_analysis_with_progress(
        bot=context.bot,
        chat_id=allowed_chat_id,
        text=text,
        image_bytes=image_bytes,
        source_link=source_link,
        source="manual",
    )


# ── PTB-registered callback query handler ────────────────────────────────────

async def handle_callback_query(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    allowed_chat_id: int,
) -> None:
    """
    Dispatch inline button callbacks.

    Patterns handled:
      reanalyze                   — bare retry (post-timeout)
      queue                       — bare queue action
      manual                      — bare manual action
      open_dashboard:<listing_id> — URL button (server-side no-op)
      reanalyze:<listing_id>
      save_watchlist:<listing_id>
      survey:<listing_id>
      skip:<listing_id>
      save:<listing_id>
      blacklist:<listing_id>
    """
    query = update.callback_query
    if not query:
        return
    await query.answer()

    if query.message.chat_id != allowed_chat_id:
        return

    data = query.data or ""
    log.info("Callback: %r", data)

    # ── Bare actions ──────────────────────────────────────────────────────
    if data == "queue":
        await context.bot.send_message(
            chat_id=allowed_chat_id,
            text=(
                "*\\[SYSTEM\\]* Analysis queued\\.\n"
                "Resend the listing when ready to retry\\."
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    if data == "manual":
        await context.bot.send_message(
            chat_id=allowed_chat_id,
            text=(
                "*\\[SYSTEM\\]* Manual review mode\\.\n"
                "Forward the listing to proceed without AI analysis\\."
            ),
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

    # ── Actions with listing_id ───────────────────────────────────────────
    if ":" not in data:
        log.debug("Unhandled callback (no colon): %r", data)
        return

    action, listing_id = data.split(":", 1)

    if action == "open_dashboard":
        # URL buttons are handled client-side
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

    # ── Feedback actions ──────────────────────────────────────────────────
    listing_doc = await get_listing(listing_id)
    location    = listing_doc.get("location", "")    if listing_doc else ""
    price_value = listing_doc.get("price_value")     if listing_doc else None

    try:
        await process_feedback(
            chat_id=allowed_chat_id,
            listing_id=listing_id,
            action=action,
            location=location,
            price_value=float(price_value) if price_value is not None else None,
            listing=listing_doc,
        )
    except Exception as exc:
        log.warning("process_feedback non-fatal: %s", exc)

    feedback_map: dict[str, str] = {
        "survey":         f"Listing `{escape_md(listing_id)}` marked for survey\\. Preferences updated\\.",
        "skip":           f"Listing `{escape_md(listing_id)}` skipped\\. Area noted for avoidance\\.",
        "save":           f"Listing `{escape_md(listing_id)}` saved to watchlist\\.",
        "save_watchlist": f"Listing `{escape_md(listing_id)}` saved to watchlist\\.",
        "blacklist":      f"Phone from listing `{escape_md(listing_id)}` reported and blacklisted\\.",
    }
    reply = feedback_map.get(action, f"Feedback `{escape_md(action)}` recorded\\.")

    await context.bot.send_message(
        chat_id=allowed_chat_id,
        text=f"*\\[SYSTEM\\]* {reply}",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
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
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
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
    try:
        history = await get_user_history(chat_id, limit=3)
    except Exception as exc:
        log.error("get_user_history failed: %s", exc)
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
        lid   = escape_md(item.get("listing_id", "unknown"))
        price = escape_md(item.get("price_text", "—"))
        score = escape_md(str(item.get("price_score", "—")))
        rec   = escape_md(item.get("recommendation", "—"))
        loc   = escape_md(item.get("location", "—"))
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
    try:
        stats = await get_user_stats(chat_id)
    except Exception as exc:
        log.error("get_user_stats failed: %s", exc)
        stats = {}

    total   = escape_md(str(stats.get("total_analyzed", 0)))
    flagged = escape_md(str(stats.get("flagged_high_risk", 0)))
    prefs   = stats.get("preferences", {})
    budget  = escape_md(str(prefs.get("max_price", "not set")))
    radius  = escape_md(str(prefs.get("max_distance_km", "not set")))
    p_str   = escape_md(", ".join(prefs.get("preferred_areas", [])) or "none")
    a_str   = escape_md(", ".join(prefs.get("avoided_areas", [])) or "none")

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "*\\[STATS\\]* Session overview\n\n"
            f"`total analyzed  :` {total}\n"
            f"`flagged high risk:` {flagged}\n\n"
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
    try:
        await clear_user_preferences(chat_id)
        text = (
            "*\\[SYSTEM\\]* Preferences cleared\\.\n"
            "`preferred_areas` and `avoided_areas` reset to empty\\."
        )
    except Exception as exc:
        log.error("clear_user_preferences failed: %s", exc)
        text = (
            "*\\[WARNING\\]*\n"
            f"`code: {escape_md(type(exc).__name__)}`\n"
            "Failed to clear preferences\\."
        )
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_newchat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Visual 'clear chat' — Telegram has no API to delete messages in bulk,
    so we push a large separator block to visually bury prior history,
    then send a fresh session banner.

    Also clears any stuck in-memory analysis session (message_id) so the
    next listing starts a clean progress message.
    """
    chat_id = update.effective_chat.id

    # Clear any stale analysis session
    await clear_session(chat_id)

    # Visual separator: a block of blank lines pushes old messages out of view
    separator = (
        "\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n"
        "\n\n\n\n\n\n\n\n\n\n"
        "\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-"
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=separator,
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    # Fresh session banner
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

async def settings_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    chat_id = update.effective_chat.id

    if not _check_ratelimit(chat_id):
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "*\\[SYSTEM\\]* Rate limit reached\\.\n"
                "Try again in 60 seconds\\."
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return ConversationHandler.END

    try:
        prefs  = await get_preferences(chat_id)
        budget = escape_md(str(prefs.get("max_price", 650000)))
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


async def settings_budget(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    chat_id   = update.effective_chat.id
    raw       = (update.message.text or "").strip()
    raw_clean = raw.replace(".", "").replace(",", "").replace("_", "")

    if not raw_clean.isdigit() or int(raw_clean) <= 0:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "*\\[SETTINGS\\]* Invalid input\\.\n"
                "Enter a positive integer\\. Example: `1500000`"
            ),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return STATE_BUDGET

    context.user_data["settings_budget"] = int(raw_clean)

    try:
        prefs  = await get_preferences(chat_id)
        radius = escape_md(str(prefs.get("max_distance_km", 5)))
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


async def settings_radius(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    chat_id = update.effective_chat.id
    raw     = (update.message.text or "").strip().replace(",", ".")

    try:
        radius_val = float(raw)
        if radius_val <= 0:
            raise ValueError("non-positive")
    except ValueError:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "*\\[SETTINGS\\]* Invalid input\\.\n"
                "Enter a positive number\\. Example: `3\\.5`"
            ),
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


async def settings_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query   = update.callback_query
    chat_id = update.effective_chat.id
    await query.answer()

    if query.data == "settings_yes":
        budget_val = context.user_data.get("settings_budget")
        radius_val = context.user_data.get("settings_radius")
        patch: dict = {}
        if budget_val is not None:
            patch["max_price"] = budget_val
        if radius_val is not None:
            patch["max_distance_km"] = radius_val

        try:
            await update_preferences(chat_id, patch)
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

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return ConversationHandler.END


async def settings_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    context.user_data.pop("settings_budget", None)
    context.user_data.pop("settings_radius", None)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="*\\[SETTINGS\\]* Cancelled\\. No changes made\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return ConversationHandler.END
