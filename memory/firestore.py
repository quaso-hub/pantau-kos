"""
memory/firestore.py
CRUD async Firestore untuk 4 collections:
  - kos_listings      : semua kos yang pernah dianalisis
  - user_preferences  : preferensi yang dipelajari dari feedback
  - area_cache        : cache data area (TTL 24 jam)
  - blacklist         : nomor/akun penipu

Graceful-degradation:
  If the Firestore database does not exist (404 NotFound) or any other
  connectivity error occurs, all public functions catch the exception,
  log a warning, and return safe defaults.  The bot keeps working without
  persistence until Firestore is provisioned.
"""
import logging
import os
from datetime import datetime, timezone

from google.cloud import firestore
from google.cloud.firestore_v1.async_client import AsyncClient
from google.api_core.exceptions import GoogleAPICallError, NotFound

log = logging.getLogger("god-eye.firestore")

_PROJECT     = os.environ.get("GOOGLE_CLOUD_PROJECT", "kos-monitor")
_DATABASE_ID = os.environ.get("FIRESTORE_DATABASE_ID", "kos-monitor-firestore")
_db: AsyncClient | None = None

# Circuit-breaker: after the first NotFound we skip all DB calls until restart.
# This avoids 60-second retry storms on every single update.
_db_unavailable: bool = False


def _get_db() -> AsyncClient:
    global _db
    if _db is None:
        _db = firestore.AsyncClient(project=_PROJECT, database=_DATABASE_ID)
    return _db


def _mark_unavailable(exc: Exception) -> None:
    """Log the error and flip the circuit-breaker flag."""
    global _db_unavailable
    if isinstance(exc, NotFound) and "does not exist" in str(exc):
        if not _db_unavailable:
            log.error(
                "Firestore database '%s' not found in project '%s'. "
                "All persistence disabled until DB is provisioned. "
                "Visit https://console.cloud.google.com/datastore/setup?project=%s",
                _DATABASE_ID, _PROJECT, _PROJECT,
            )
        _db_unavailable = True
    else:
        log.warning("Firestore call failed (non-fatal): %s", exc)


# ── kos_listings ──────────────────────────────────────────────────────────────

async def save_listing(result) -> None:
    """Simpan AnalysisResult ke Firestore collection kos_listings."""
    if _db_unavailable:
        return
    try:
        db = _get_db()
        maps = result.maps
        doc = {
            "listing_id":   result.listing_id,
            "source":       result.source,
            "source_link":  result.source_link,
            "text_snippet": result.text[:500],
            "location":     result.location_hint,
            "price_value":  result.price_value,
            "phones":       result.phones,
            "score":        result.score,
            "fraud_risk":   result.fraud_risk,
            "distance_km":  result.distance_km_val,
            "geocode":      maps.geocode,
            "air_quality":  maps.air_quality,
            "recommendation": result.recommendation,
            "timestamp":    result.timestamp,
            "created_at":   firestore.SERVER_TIMESTAMP,
        }
        await db.collection("kos_listings").document(result.listing_id).set(doc)
        log.info(f"Saved listing {result.listing_id} to Firestore")
    except Exception as exc:
        _mark_unavailable(exc)


async def get_listing(listing_id: str) -> dict | None:
    """Ambil satu listing by ID."""
    if _db_unavailable:
        return None
    try:
        db = _get_db()
        doc = await db.collection("kos_listings").document(listing_id).get()
        return doc.to_dict() if doc.exists else None
    except Exception as exc:
        _mark_unavailable(exc)
        return None


async def listing_exists(source_link: str) -> bool:
    """Cek apakah link sudah pernah dianalisis (hindari duplikat dari scraper)."""
    if not source_link or _db_unavailable:
        return False
    try:
        db = _get_db()
        query = (
            db.collection("kos_listings")
            .where("source_link", "==", source_link)
            .limit(1)
        )
        docs = [d async for d in query.stream()]
        return len(docs) > 0
    except Exception as exc:
        _mark_unavailable(exc)
        return False


# ── user_preferences ──────────────────────────────────────────────────────────

_DEFAULT_PREFS: dict = {
    "preferred_areas":       [],
    "avoided_areas":         [],
    "max_distance_km":       15,
    "max_price":             650_000,
    "required_facilities":   [],
    "feedback_history":      [],
    "notification_threshold": 70,
}


async def get_preferences(chat_id: int) -> dict:
    """Ambil preferensi user. Return default jika belum ada atau DB unavailable."""
    if _db_unavailable:
        return dict(_DEFAULT_PREFS)
    try:
        db = _get_db()
        doc = await db.collection("user_preferences").document(str(chat_id)).get()
        if doc.exists:
            return {**_DEFAULT_PREFS, **doc.to_dict()}
        return dict(_DEFAULT_PREFS)
    except Exception as exc:
        _mark_unavailable(exc)
        return dict(_DEFAULT_PREFS)


async def update_preferences(chat_id: int, patch: dict) -> None:
    """Update (merge) preferensi user."""
    if _db_unavailable:
        return
    try:
        db = _get_db()
        await db.collection("user_preferences").document(str(chat_id)).set(
            patch, merge=True
        )
        log.info(f"Updated preferences for chat_id={chat_id}")
    except Exception as exc:
        _mark_unavailable(exc)


async def append_feedback(
    chat_id: int, listing_id: str, action: str
) -> None:
    """Append satu entry ke feedback_history."""
    if _db_unavailable:
        return
    try:
        db = _get_db()
        ref = db.collection("user_preferences").document(str(chat_id))
        entry = {
            "listing_id": listing_id,
            "action": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await ref.set(
            {"feedback_history": firestore.ArrayUnion([entry])},
            merge=True,
        )
    except Exception as exc:
        _mark_unavailable(exc)


# ── blacklist ─────────────────────────────────────────────────────────────────

async def is_blacklisted(phone: str) -> bool:
    """Cek apakah nomor ada di blacklist."""
    if _db_unavailable:
        return False
    try:
        normalized = re.sub(r'[\s\-]', '', phone)
        db = _get_db()
        doc = await db.collection("blacklist").document(normalized).get()
        return doc.exists
    except Exception as exc:
        _mark_unavailable(exc)
        return False


async def add_to_blacklist(phone: str, reason: str = "") -> None:
    """Tambah nomor ke blacklist."""
    if _db_unavailable:
        return
    try:
        import re as _re
        normalized = _re.sub(r'[\s\-]', '', phone)
        db = _get_db()
        await db.collection("blacklist").document(normalized).set({
            "phone": normalized,
            "reason": reason,
            "added_at": firestore.SERVER_TIMESTAMP,
        })
        log.info(f"Added {normalized} to blacklist")
    except Exception as exc:
        _mark_unavailable(exc)


# ── area_cache ────────────────────────────────────────────────────────────────

async def get_area_cache(area_key: str) -> dict | None:
    """Ambil cache area. Return None jika tidak ada atau expired (> 24 jam)."""
    if _db_unavailable:
        return None
    try:
        db = _get_db()
        doc = await db.collection("area_cache").document(area_key).get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        cached_at = data.get("cached_at")
        if cached_at:
            from datetime import timedelta
            now = datetime.now(timezone.utc)
            if hasattr(cached_at, "timestamp"):
                age = now - datetime.fromtimestamp(cached_at.timestamp(), tz=timezone.utc)
            else:
                age = now - datetime.fromisoformat(str(cached_at))
            if age.total_seconds() > 86400:
                return None
        return data
    except Exception as exc:
        _mark_unavailable(exc)
        return None


async def set_area_cache(area_key: str, data: dict) -> None:
    """Simpan cache area dengan timestamp."""
    if _db_unavailable:
        return
    try:
        db = _get_db()
        await db.collection("area_cache").document(area_key).set({
            **data,
            "cached_at": firestore.SERVER_TIMESTAMP,
        })
    except Exception as exc:
        _mark_unavailable(exc)


import re  # noqa: E402 — dibutuhkan oleh is_blacklisted


# ── Session message-id (idempotency) ─────────────────────────────────────────

async def save_session_message_id(chat_id: int, message_id: int) -> None:
    """Store active analysis message_id for idempotent restart handling."""
    if _db_unavailable:
        return
    try:
        db = _get_db()
        await db.collection("active_sessions").document(str(chat_id)).set(
            {
                "message_id": message_id,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
    except Exception as exc:
        _mark_unavailable(exc)


async def get_session_message_id(chat_id: int) -> int | None:
    """Retrieve stored message_id for a chat session, or None."""
    if _db_unavailable:
        return None
    try:
        db = _get_db()
        doc = await db.collection("active_sessions").document(str(chat_id)).get()
        if doc.exists:
            return doc.to_dict().get("message_id")
        return None
    except Exception as exc:
        _mark_unavailable(exc)
        return None


async def clear_session(chat_id: int) -> None:
    """Delete active session record after analysis completes."""
    if _db_unavailable:
        return
    try:
        db = _get_db()
        await db.collection("active_sessions").document(str(chat_id)).delete()
    except Exception as exc:
        _mark_unavailable(exc)


# ── User history ──────────────────────────────────────────────────────────────

async def get_user_history(chat_id: int, limit: int = 3) -> list[dict]:
    """
    Return last `limit` analyzed listings associated with a chat_id.
    Returns empty list if DB unavailable.
    """
    if _db_unavailable:
        return []
    try:
        db = _get_db()
        query = (
            db.collection("kos_listings")
            .order_by("created_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        docs = [d.to_dict() async for d in query.stream()]
        return docs
    except Exception as exc:
        _mark_unavailable(exc)
        return []


# ── User stats ────────────────────────────────────────────────────────────────

async def get_user_stats(chat_id: int) -> dict:
    """
    Return aggregate stats for a user.
    Returns zero-stats if DB unavailable.
    """
    if _db_unavailable:
        return {
            "total_analyzed": 0,
            "flagged_high_risk": 0,
            "preferences": dict(_DEFAULT_PREFS),
        }
    try:
        db = _get_db()
        prefs = await get_preferences(chat_id)

        query_all = db.collection("kos_listings").limit(100)
        all_docs  = [d.to_dict() async for d in query_all.stream()]
        total     = len(all_docs)
        flagged   = sum(1 for d in all_docs if d.get("fraud_risk") == "HIGH")

        return {
            "total_analyzed": total,
            "flagged_high_risk": flagged,
            "preferences": prefs,
        }
    except Exception as exc:
        _mark_unavailable(exc)
        return {
            "total_analyzed": 0,
            "flagged_high_risk": 0,
            "preferences": dict(_DEFAULT_PREFS),
        }


# ── Clear preferences (soft reset) ───────────────────────────────────────────

async def clear_user_preferences(chat_id: int) -> None:
    """Reset learned areas to empty lists, keep budget/radius settings."""
    if _db_unavailable:
        return
    try:
        db = _get_db()
        await db.collection("user_preferences").document(str(chat_id)).set(
            {"preferred_areas": [], "avoided_areas": []},
            merge=True,
        )
        log.info(f"Cleared area preferences for chat_id={chat_id}")
    except Exception as exc:
        _mark_unavailable(exc)
