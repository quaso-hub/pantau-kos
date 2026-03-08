"""
adapters/controllers/keyboards.py  (v5.0)
Inline keyboard builders with optional "View Logs" for observability.
"""
from __future__ import annotations
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

DASHBOARD_BASE = "https://god-eye.ikrn.engineer/dashboard"


def report_keyboard(
    listing_id: str,
    phone: str | None = None,
    trace_id: str | None = None,
) -> InlineKeyboardMarkup:
    dashboard_url = f"{DASHBOARD_BASE}/{listing_id}"
    rows = [
        [
            InlineKeyboardButton("Open Dashboard", url=dashboard_url),
            InlineKeyboardButton("Re-analyze", callback_data=f"reanalyze:{listing_id}"),
        ],
        [
            InlineKeyboardButton("Survey", callback_data=f"survey:{listing_id}"),
            InlineKeyboardButton("Skip", callback_data=f"skip:{listing_id}"),
        ],
        [
            InlineKeyboardButton("Save to Watchlist", callback_data=f"save_watchlist:{listing_id}"),
        ],
        [
            InlineKeyboardButton("Report Fraud", callback_data=f"blacklist:{listing_id}"),
        ],
    ]
    if phone:
        normalized = phone.strip().replace(" ", "").replace("-", "")
        if normalized.startswith("0"):
            normalized = "62" + normalized[1:]
        elif not normalized.startswith("62"):
            normalized = "62" + normalized
        rows[2].insert(0, InlineKeyboardButton("Contact WA", url=f"https://wa.me/{normalized}"))
    if trace_id:
        rows.append([
            InlineKeyboardButton("📋 View Logs", callback_data=f"view_logs:{trace_id}"),
        ])
    return InlineKeyboardMarkup(rows)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Yes, save", callback_data="settings_yes"),
            InlineKeyboardButton("Cancel", callback_data="settings_no"),
        ]
    ])
