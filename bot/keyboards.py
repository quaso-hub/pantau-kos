"""
bot/keyboards.py  (v3.2)
Inline keyboard builders for kos analysis reports and settings confirmation.
Callback data format: "<action>:<listing_id>"
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

DASHBOARD_BASE = "https://god-eye.ikrn.engineer/dashboard"


def report_keyboard(listing_id: str, phone: str | None = None) -> InlineKeyboardMarkup:
    """
    Report action keyboard:

    Row 0: [Open Dashboard]  [Re-analyze]
    Row 1: [Survey]  [Skip]
    Row 2: [Contact WA]  [Save to Watchlist]   (WA only if phone present)
    Row 3: [Report Fraud]
    """
    dashboard_url = f"{DASHBOARD_BASE}/{listing_id}"

    rows = [
        [
            InlineKeyboardButton("Open Dashboard",    url=dashboard_url),
            InlineKeyboardButton("Re-analyze",        callback_data=f"reanalyze:{listing_id}"),
        ],
        [
            InlineKeyboardButton("Survey",            callback_data=f"survey:{listing_id}"),
            InlineKeyboardButton("Skip",              callback_data=f"skip:{listing_id}"),
        ],
        [
            InlineKeyboardButton("Save to Watchlist", callback_data=f"save_watchlist:{listing_id}"),
        ],
        [
            InlineKeyboardButton("Report Fraud",      callback_data=f"blacklist:{listing_id}"),
        ],
    ]

    # Insert WhatsApp button next to Save if phone is available
    if phone:
        normalized = phone.strip().replace(" ", "").replace("-", "")
        if normalized.startswith("0"):
            normalized = "62" + normalized[1:]
        elif not normalized.startswith("62"):
            normalized = "62" + normalized
        rows[2].insert(0, InlineKeyboardButton("Contact WA", url=f"https://wa.me/{normalized}"))

    return InlineKeyboardMarkup(rows)


def confirm_keyboard() -> InlineKeyboardMarkup:
    """
    Yes / Cancel confirmation keyboard for /settings ConversationHandler.
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Yes, save", callback_data="settings_yes"),
            InlineKeyboardButton("Cancel",    callback_data="settings_no"),
        ]
    ])
