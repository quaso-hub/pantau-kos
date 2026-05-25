"""
monitor/receiver.py
Handler untuk POST /monitor dari n8n scraper.
Schema JSON yang diterima:
{
  "source":      "mamikos" | "olx" | "99co" | ...,
  "title":       "Kos ...",
  "price":       500000,          # int, bisa null
  "location":    "Jl. ...",
  "url":         "https://...",
  "description": "...",
  "images":      ["url1", ...],   # opsional
  "scraped_at":  "2026-03-07T..."
}
"""
import logging

import httpx
from telegram import Bot
from telegram.constants import ParseMode

from engine.analyzer import full_analysis
from bot.formatter import format_report, split_message
from bot.keyboards import report_keyboard
from memory.firestore import listing_exists, get_preferences

log = logging.getLogger("god-eye.monitor")

# Batas filter harga (luar range ini → skip)
PRICE_MIN = 300_000
PRICE_MAX = 800_000

# Kota yang diperbolehkan (lowercase)
ALLOWED_CITIES = ["surabaya", "sidoarjo"]


async def handle_monitor_post(data: dict, bot: Bot, allowed_chat_id: int) -> None:
    """
    Proses satu listing baru dari n8n:
    1. Validasi dan filter kasar (harga + kota)
    2. Cek duplikat di Firestore
    3. Jalankan full analysis pipeline
    4. Cek score vs threshold preferensi user → kirim notif jika lolos
    """
    source      = data.get("source", "unknown")
    title       = data.get("title", "")
    price_raw   = data.get("price")          # bisa int atau None
    location    = data.get("location", "")
    url         = data.get("url", "")
    description = data.get("description", "")
    image_urls  = data.get("images", [])

    log.info(f"Monitor post: source={source}, url={url}, price={price_raw}")

    # ── 1. Filter kasar: harga ────────────────────────────────────────────────
    if price_raw is not None:
        try:
            price_int = int(price_raw)
            if not (PRICE_MIN <= price_int <= PRICE_MAX):
                log.info(f"Skipped (price out of range): {price_int}")
                return
        except (ValueError, TypeError):
            pass  # Harga tidak valid → tetap lanjut, biarkan analyzer tangani

    # ── 2. Filter kasar: kota ─────────────────────────────────────────────────
    location_lower = location.lower()
    if not any(city in location_lower for city in ALLOWED_CITIES):
        log.info(f"Skipped (city not allowed): {location!r}")
        return

    # ── 3. Cek duplikat ───────────────────────────────────────────────────────
    if url and await listing_exists(url):
        log.info(f"Skipped (duplicate): {url}")
        return

    # ── 4. Download gambar pertama (jika ada) ─────────────────────────────────
    image_bytes: bytes | None = None
    if image_urls:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(image_urls[0])
                if r.status_code == 200:
                    image_bytes = r.content
        except Exception as exc:
            log.warning(f"Failed to download monitor image: {exc}")

    # ── 5. Susun teks gabungan ────────────────────────────────────────────────
    price_text = f"Rp {int(price_raw):,}/bulan" if price_raw else ""
    combined_text = "\n".join(filter(None, [title, price_text, location, description]))

    # ── 6. Full analysis ──────────────────────────────────────────────────────
    try:
        result = await full_analysis(
            text=combined_text,
            image_bytes=image_bytes,
            source_link=url,
            source=source,
            chat_id=allowed_chat_id,
        )
    except Exception as exc:
        log.error(f"Monitor analysis failed: {exc}", exc_info=True)
        await bot.send_message(
            allowed_chat_id,
            f"❌ Error monitor ({source}): {str(exc)[:200]}",
        )
        return

    # ── 7. Cek threshold preferensi user ──────────────────────────────────────
    try:
        prefs = await get_preferences(allowed_chat_id)
        threshold = prefs.get("notification_threshold", 70)
    except Exception:
        threshold = 70

    if result.score < threshold:
        log.info(
            f"Score {result.score} < threshold {threshold}, skipping notification "
            f"(listing saved to Firestore)"
        )
        return

    # ── 8. Kirim notif ke Telegram ────────────────────────────────────────────
    header = (
        f"🔔 *LISTING BARU — {source.upper()}*\n"
        f"Score: {result.score}/100\n\n"
    )
    report = header + format_report(result)
    parts  = split_message(report)
    phone  = result.phones[0] if result.phones else None
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
        f"Monitor notification sent: listing_id={result.listing_id}, "
        f"score={result.score}, source={source}"
    )
