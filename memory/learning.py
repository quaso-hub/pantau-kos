"""
memory/learning.py  (v3.1)
Self-learning: update user preferences dari feedback tombol Telegram.
Fungsi calculate_score() dipindah ke memory/scoring.py.
"""
import logging

from memory.firestore import (
    get_preferences, update_preferences, append_feedback,
    add_to_blacklist,
)
from memory.scoring import calculate_score  # re-export agar kode lama tidak rusak

log = logging.getLogger("god-eye.learning")

__all__ = ["process_feedback", "calculate_score"]


# ── Update preferences dari feedback tombol ───────────────────────────────────

async def process_feedback(
    chat_id: int,
    listing_id: str,
    action: str,          # "survey" | "skip" | "save" | "blacklist"
    location: str = "",
    price_value: float | None = None,
    listing: dict | None = None,   # full listing doc (untuk blacklist_phone)
) -> None:
    """
    Proses feedback dari inline button dan update user_preferences di Firestore.

    Actions:
      survey    → preferred_areas += area, threshold -= 1 (min 50)
      skip      → skip_counts[area] += 1, setelah 3x → avoided_areas
                  threshold += 0.5 (max 85)
      save      → catat saja, tidak ubah preferensi
      blacklist → blacklist nomor telepon di Firestore
    """
    prefs = await get_preferences(chat_id)
    patch: dict = {}
    kelurahan = _normalize_area(location)

    if action == "survey":
        preferred = list(prefs.get("preferred_areas", []))
        if kelurahan and kelurahan not in preferred:
            preferred.append(kelurahan)
            patch["preferred_areas"] = preferred
        # Perketat max_price jika yang dipilih lebih murah
        if price_value and price_value < prefs.get("max_price", 650_000):
            patch["max_price"] = int(price_value)
        # Turunkan threshold → lebih banyak notif
        patch["notification_threshold"] = max(50, prefs.get("notification_threshold", 65) - 1)

    elif action == "skip":
        # Track skip per area
        skip_counts: dict = dict(prefs.get("skip_counts", {}))
        skip_counts[kelurahan] = skip_counts.get(kelurahan, 0) + 1 if kelurahan else 0
        patch["skip_counts"] = skip_counts
        # Setelah 3x skip area yang sama → masuk avoided
        avoided = list(prefs.get("avoided_areas", []))
        if kelurahan and skip_counts.get(kelurahan, 0) >= 3 and kelurahan not in avoided:
            avoided.append(kelurahan)
            patch["avoided_areas"] = avoided
        # Naikkan threshold → lebih selektif
        patch["notification_threshold"] = min(85, prefs.get("notification_threshold", 65) + 0.5)

    elif action == "blacklist":
        # Blacklist nomor telepon
        phone = None
        if listing:
            phone = listing.get("phone") or listing.get("phones", [None])[0]
        if phone:
            await add_to_blacklist(phone, reason=f"Dilaporkan dari listing {listing_id}")
            log.info(f"Blacklisted phone {phone} from listing {listing_id}")
        # Tidak update prefs — hanya Firestore blacklist

    if patch:
        await update_preferences(chat_id, patch)

    await append_feedback(chat_id, listing_id, action)
    log.info(f"Feedback '{action}' processed | listing={listing_id} | chat={chat_id}")


def _normalize_area(location: str) -> str:
    """
    Ambil nama area / kecamatan dari string lokasi.
    Contoh: "Jl. Prapen Indah No.12, Wonocolo, Surabaya" → "Wonocolo"
    """
    parts = [p.strip() for p in location.split(",")]
    for part in parts:
        if any(kw in part.lower() for kw in ["jl.", "no.", "kav", "surabaya", "jawa"]):
            continue
        if len(part) >= 4:
            return part
    words = location.split()
    return " ".join(words[:2]) if len(words) >= 2 else location[:30]
