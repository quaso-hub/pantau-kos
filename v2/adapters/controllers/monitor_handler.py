"""
adapters/controllers/monitor_handler.py  (v4.0)

Thin handler for the /monitor webhook.
Receives notification result from MonitorService and dispatches Telegram messages.
This is the controller-level adapter — MonitorService handles all business logic.
"""
from __future__ import annotations

import logging

from telegram import Bot
from telegram.constants import ParseMode

from adapters.controllers.formatter import format_report, split_message
from adapters.controllers.keyboards import report_keyboard
from domain.models import MonitorPayload
from infrastructure.container import Container

log = logging.getLogger("god-eye.monitor-handler")


async def handle_monitor_post(data: dict, bot: Bot, allowed_chat_id: int, container: Container) -> None:
    """
    Thin adapter: parse payload → delegate to MonitorService → send notification.
    """
    payload = MonitorPayload.from_dict(data)
    log.info("Monitor post: source=%s, url=%s, price=%s", payload.source, payload.url, payload.price)

    notification = await container.monitor_service.ingest(payload, allowed_chat_id)

    if notification is None:
        return  # filtered out

    if not notification.should_notify:
        if notification.skip_reason and "error" in notification.skip_reason.lower():
            await bot.send_message(
                allowed_chat_id,
                f"❌ Error monitor ({notification.source}): {notification.skip_reason}",
            )
        return

    result = notification.result
    header = (
        f"🔔 *LISTING BARU — {notification.source.upper()}*\n"
        f"Score: {result.score}/100\n\n"
    )
    report = header + format_report(result)
    parts = split_message(report)
    phone = result.phones[0] if result.phones else None
    keyboard = report_keyboard(result.listing_id, phone)

    for i, part in enumerate(parts):
        markup = keyboard if i == len(parts) - 1 else None
        await bot.send_message(
            allowed_chat_id,
            part,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False,
            reply_markup=markup,
        )

    log.info(
        "Monitor notification sent: listing_id=%s, score=%s, source=%s",
        result.listing_id,
        result.score,
        notification.source,
    )
