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

            # Flatten risk_flags from deepseek_raw or gemini_data
            risk_flags: list[str] = []
            if result.gemini_data:
                risk_flags = result.gemini_data.get("risk_flags", []) or []
            if not risk_flags and result.deepseek_raw:
                for line in result.deepseek_raw.splitlines():
                    stripped = line.lstrip("-• ").strip()
                    if stripped and not stripped.startswith("Catatan"):
                        risk_flags.append(stripped)

            doc = {
                # ── Core identity ────────────────────────────────────────────
                "listing_id":       result.listing_id,
                "source":           result.source,
                "source_link":      result.source_link,
                "text_snippet":     result.text[:500] if result.text else "",

                # ── Location ─────────────────────────────────────────────────
                "location":         result.location_hint or "",
                "geocode":          maps.geocode if maps else None,

                # ── Price ─────────────────────────────────────────────────────
                "price_value":      result.price_value,
                "price_text":       result.prices[0] if result.prices else None,
                "price_score":      result.price_score,
                "budget_status":    result.budget_status or "",

                # ── Contact ───────────────────────────────────────────────────
                "phones":           result.phones or [],

                # ── Scoring & Risk ────────────────────────────────────────────
                "score":            result.score,
                "fraud_risk":       result.fraud_risk or "UNKNOWN",
                "risk_flags":       risk_flags,

                # ── Distance ──────────────────────────────────────────────────
                "distance_km":      result.distance_km_val,
                "jarak_status":     result.jarak_status or "",

                # ── Air quality ───────────────────────────────────────────────
                "air_quality":  (
                    {"aqi": maps.air_quality.aqi, "category": maps.air_quality.category}
                    if maps and maps.air_quality else None
                ),

                # ── Recommendation ────────────────────────────────────────────
                "recommendation":   result.recommendation or "",

                # ── Agent data for dashboard detail view ──────────────────────
                "agent_data": {
                    "vision": {k: v for k, v in (result.gemini_data or {}).items()
                               if k in ("size_m2", "condition", "condition_score",
                                        "bathroom", "furniture", "has_ac",
                                        "mezzanine", "photo_authentic", "photo_flags")},
                    "web_intel_summary": (result.gemini_data or {}).get("web_intel_summary", "")[:500],
                    "extracted_price_raw": (result.gemini_data or {}).get("extracted_price_raw", ""),
                    "extracted_address":   (result.gemini_data or {}).get("extracted_address_raw", ""),
                    "analyst_notes":       result.deepseek_raw[:300] if result.deepseek_raw else "",
                },

                # ── Timestamps ────────────────────────────────────────────────
                "timestamp":        result.timestamp,
                "created_at":       firestore.SERVER_TIMESTAMP,
            }
            await db.collection("kos_listings").document(result.listing_id).set(doc)
            log.info(
                "Saved listing %s | price=%s | score=%s | fraud=%s | km=%s",
                result.listing_id, result.price_value, result.score,
                result.fraud_risk, result.distance_km_val,
            )
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

    async def save_context(self, chat_id: int, text: str, source_link: str) -> None:
        """Persist last user input for Retry replay."""
        if _db_unavailable:
            return
        try:
            db = _get_db(self._cfg)
            await db.collection("active_sessions").document(str(chat_id)).set(
                {
                    "last_text": text[:2000],
                    "last_source_link": source_link,
                    "context_saved_at": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
        except Exception as exc:
            _mark_unavailable(exc)

    async def get_context(self, chat_id: int) -> Optional[dict]:
        """Return {'text': ..., 'source_link': ...} or None."""
        if _db_unavailable:
            return None
        try:
            db = _get_db(self._cfg)
            doc = await db.collection("active_sessions").document(str(chat_id)).get()
            if doc.exists:
                data = doc.to_dict()
                text = data.get("last_text")
                if text:
                    return {
                        "text": text,
                        "source_link": data.get("last_source_link", ""),
                    }
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
