"""
adapters/repositories/firestore_repo.py
Concrete Firestore implementations of all repository interfaces.
Preserves the circuit-breaker pattern from v1.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from google.cloud import firestore
from google.cloud.firestore_v1.async_client import AsyncClient
from google.api_core.exceptions import NotFound

from domain.interfaces import (
    AreaCacheRepository,
    BlacklistRepository,
    ListingRepository,
    PreferencesRepository,
    SessionRepository,
)
from domain.models import AnalysisResult, UserPreferences
from infrastructure.config import FirestoreConfig

log = logging.getLogger("god-eye.firestore")


# ── Shared circuit-breaker + client singleton ────────────────────────────────

_db: Optional[AsyncClient] = None
_db_unavailable: bool = False


def _get_db(cfg: FirestoreConfig) -> AsyncClient:
    global _db
    if _db is None:
        _db = firestore.AsyncClient(project=cfg.project, database=cfg.database_id)
    return _db


def _mark_unavailable(exc: Exception) -> None:
    global _db_unavailable
    if isinstance(exc, NotFound) and "does not exist" in str(exc):
        if not _db_unavailable:
            log.error(
                "Firestore database not found. "
                "All persistence disabled until restart."
            )
        _db_unavailable = True
    else:
        log.warning("Firestore call failed (non-fatal): %s", exc)


# ── ListingRepository ─────────────────────────────────────────────────────────

class FirestoreListingRepo(ListingRepository):
    def __init__(self, config: FirestoreConfig) -> None:
        self._cfg = config

    async def save(self, result: AnalysisResult) -> None:
        if _db_unavailable:
            return
        try:
            db = _get_db(self._cfg)
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
                "air_quality":  (
                    {"aqi": maps.air_quality.aqi, "category": maps.air_quality.category}
                    if maps.air_quality else None
                ),
                "recommendation": result.recommendation,
                "timestamp":    result.timestamp,
                "created_at":   firestore.SERVER_TIMESTAMP,
            }
            await db.collection("kos_listings").document(result.listing_id).set(doc)
            log.info("Saved listing %s", result.listing_id)
        except Exception as exc:
            _mark_unavailable(exc)

    async def get(self, listing_id: str) -> Optional[dict]:
        if _db_unavailable:
            return None
        try:
            db = _get_db(self._cfg)
            doc = await db.collection("kos_listings").document(listing_id).get()
            return doc.to_dict() if doc.exists else None
        except Exception as exc:
            _mark_unavailable(exc)
            return None

    async def exists_by_link(self, source_link: str) -> bool:
        if not source_link or _db_unavailable:
            return False
        try:
            db = _get_db(self._cfg)
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

    async def get_recent(self, limit: int = 3) -> list[dict]:
        if _db_unavailable:
            return []
        try:
            db = _get_db(self._cfg)
            query = (
                db.collection("kos_listings")
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
            )
            return [d.to_dict() async for d in query.stream()]
        except Exception as exc:
            _mark_unavailable(exc)
            return []

    async def count_all(self) -> int:
        if _db_unavailable:
            return 0
        try:
            db = _get_db(self._cfg)
            docs = [d.to_dict() async for d in db.collection("kos_listings").limit(100).stream()]
            return len(docs)
        except Exception as exc:
            _mark_unavailable(exc)
            return 0

    async def count_high_risk(self) -> int:
        if _db_unavailable:
            return 0
        try:
            db = _get_db(self._cfg)
            docs = [d.to_dict() async for d in db.collection("kos_listings").limit(100).stream()]
            return sum(1 for d in docs if d.get("fraud_risk") == "HIGH")
        except Exception as exc:
            _mark_unavailable(exc)
            return 0

    async def delete(self, listing_id: str) -> None:
        """Hard-delete a listing document from Firestore."""
        if _db_unavailable:
            return
        try:
            db = _get_db(self._cfg)
            await db.collection("kos_listings").document(listing_id).delete()
            log.info("Deleted listing %s", listing_id)
        except Exception as exc:
            log.warning("Firestore delete failed for %s: %s", listing_id, exc)
            raise


# ── PreferencesRepository ─────────────────────────────────────────────────────

class FirestorePreferencesRepo(PreferencesRepository):
    def __init__(self, config: FirestoreConfig) -> None:
        self._cfg = config

    async def get(self, chat_id: int) -> UserPreferences:
        if _db_unavailable:
            return UserPreferences()
        try:
            db = _get_db(self._cfg)
            doc = await db.collection("user_preferences").document(str(chat_id)).get()
            if doc.exists:
                return UserPreferences.from_dict(doc.to_dict())
            return UserPreferences()
        except Exception as exc:
            _mark_unavailable(exc)
            return UserPreferences()

    async def update(self, chat_id: int, patch: dict) -> None:
        if _db_unavailable:
            return
        try:
            db = _get_db(self._cfg)
            await db.collection("user_preferences").document(str(chat_id)).set(
                patch, merge=True,
            )
            log.info("Updated preferences for chat_id=%s", chat_id)
        except Exception as exc:
            _mark_unavailable(exc)

    async def append_feedback(self, chat_id: int, listing_id: str, action: str) -> None:
        if _db_unavailable:
            return
        try:
            db = _get_db(self._cfg)
            entry = {
                "listing_id": listing_id,
                "action": action,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await db.collection("user_preferences").document(str(chat_id)).set(
                {"feedback_history": firestore.ArrayUnion([entry])},
                merge=True,
            )
        except Exception as exc:
            _mark_unavailable(exc)

    async def clear_areas(self, chat_id: int) -> None:
        if _db_unavailable:
            return
        try:
            db = _get_db(self._cfg)
            await db.collection("user_preferences").document(str(chat_id)).set(
                {"preferred_areas": [], "avoided_areas": []},
                merge=True,
            )
            log.info("Cleared area preferences for chat_id=%s", chat_id)
        except Exception as exc:
            _mark_unavailable(exc)


# ── BlacklistRepository ───────────────────────────────────────────────────────

class FirestoreBlacklistRepo(BlacklistRepository):
    def __init__(self, config: FirestoreConfig) -> None:
        self._cfg = config

    async def is_blacklisted(self, phone: str) -> bool:
        if _db_unavailable:
            return False
        try:
            normalized = re.sub(r'[\s\-]', '', phone)
            db = _get_db(self._cfg)
            doc = await db.collection("blacklist").document(normalized).get()
            return doc.exists
        except Exception as exc:
            _mark_unavailable(exc)
            return False

    async def add(self, phone: str, reason: str = "") -> None:
        if _db_unavailable:
            return
        try:
            normalized = re.sub(r'[\s\-]', '', phone)
            db = _get_db(self._cfg)
            await db.collection("blacklist").document(normalized).set({
                "phone": normalized,
                "reason": reason,
                "added_at": firestore.SERVER_TIMESTAMP,
            })
            log.info("Blacklisted %s", normalized)
        except Exception as exc:
            _mark_unavailable(exc)


# ── AreaCacheRepository ───────────────────────────────────────────────────────

class FirestoreAreaCacheRepo(AreaCacheRepository):
    def __init__(self, config: FirestoreConfig) -> None:
        self._cfg = config

    async def get(self, area_key: str) -> Optional[dict]:
        if _db_unavailable:
            return None
        try:
            db = _get_db(self._cfg)
            doc = await db.collection("area_cache").document(area_key).get()
            if not doc.exists:
                return None
            data = doc.to_dict()
            cached_at = data.get("cached_at")
            if cached_at:
                now = datetime.now(timezone.utc)
                if hasattr(cached_at, "timestamp"):
                    age = now - datetime.fromtimestamp(cached_at.timestamp(), tz=timezone.utc)
                else:
                    age = now - datetime.fromisoformat(str(cached_at))
                if age > timedelta(hours=24):
                    return None
            return data
        except Exception as exc:
            _mark_unavailable(exc)
            return None

    async def set(self, area_key: str, data: dict) -> None:
        if _db_unavailable:
            return
        try:
            db = _get_db(self._cfg)
            await db.collection("area_cache").document(area_key).set({
                **data,
                "cached_at": firestore.SERVER_TIMESTAMP,
            })
        except Exception as exc:
            _mark_unavailable(exc)


# ── SessionRepository ─────────────────────────────────────────────────────────

class FirestoreSessionRepo(SessionRepository):
    def __init__(self, config: FirestoreConfig) -> None:
        self._cfg = config

    async def save_message_id(self, chat_id: int, message_id: int) -> None:
        if _db_unavailable:
            return
        try:
            db = _get_db(self._cfg)
            await db.collection("active_sessions").document(str(chat_id)).set(
                {"message_id": message_id, "updated_at": firestore.SERVER_TIMESTAMP},
                merge=True,
            )
        except Exception as exc:
            _mark_unavailable(exc)

    async def get_message_id(self, chat_id: int) -> Optional[int]:
        if _db_unavailable:
            return None
        try:
            db = _get_db(self._cfg)
            doc = await db.collection("active_sessions").document(str(chat_id)).get()
            if doc.exists:
                return doc.to_dict().get("message_id")
            return None
        except Exception as exc:
            _mark_unavailable(exc)
            return None

    async def clear(self, chat_id: int) -> None:
        if _db_unavailable:
            return
        try:
            db = _get_db(self._cfg)
            await db.collection("active_sessions").document(str(chat_id)).delete()
        except Exception as exc:
            _mark_unavailable(exc)
