"""
adapters/repositories/postgres_repo.py
PostgreSQL implementations of all repository interfaces (replacing Firestore).
Uses asyncpg for async operations.
"""
from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Optional, Any

import asyncpg
from asyncpg import Pool, Record

from domain.interfaces import (
    AreaCacheRepository,
    BlacklistRepository,
    ListingRepository,
    PreferencesRepository,
    SessionRepository,
)
from domain.models import AnalysisResult, UserPreferences
from infrastructure.config import PostgresConfig

log = logging.getLogger("god-eye.postgres")

# Global connection pool
_pool: Optional[Pool] = None


async def init_pool(db_url: str) -> Pool:
    """Initialize asyncpg connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            db_url,
            min_size=1,
            max_size=5,
            command_timeout=60,
        )
        log.info("PostgreSQL connection pool initialized")
    return _pool


async def close_pool() -> None:
    """Close connection pool on shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        log.info("PostgreSQL connection pool closed")


def _get_pool() -> Pool:
    """Get current pool or raise error."""
    if _pool is None:
        raise RuntimeError("PostgreSQL pool not initialized. Call init_pool() first.")
    return _pool


# ── ListingRepository ─────────────────────────────────────────────────────────

class PostgresListingRepo(ListingRepository):
    def __init__(self, config: PostgresConfig) -> None:
        self._url = config.url

    async def save(self, result: AnalysisResult) -> None:
        """Save listing to kos_listings table."""
        try:
            pool = _get_pool()
            maps = result.maps
            
            # Serialize phones array, geocode, air_quality as JSON
            phones_json = json.dumps(result.phones or [])
            geocode_data = None
            if maps.geocode:
                geocode_data = {
                    "lat": float(maps.geocode.latitude),
                    "lng": float(maps.geocode.longitude),
                }
            
            aqi_data = None
            if maps.air_quality:
                aqi_data = {
                    "aqi": maps.air_quality.aqi,
                    "category": maps.air_quality.category,
                }
            
            query = """
                INSERT INTO kos_listings (
                    id, source, source_link, text_snippet, location,
                    price, phones, score, fraud_risk, distance_km,
                    geocode, air_quality, recommendation, timestamp, created_at
                ) VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, NOW()
                )
                ON CONFLICT (id) DO UPDATE SET
                    score = $8,
                    fraud_risk = $9,
                    recommendation = $13,
                    timestamp = $14
            """
            
            async with pool.acquire() as conn:
                await conn.execute(
                    query,
                    result.listing_id,
                    result.source,
                    result.source_link,
                    result.text[:500],
                    result.location_hint,
                    result.price_value,
                    phones_json,
                    result.score,
                    result.fraud_risk,
                    result.distance_km_val,
                    json.dumps(geocode_data) if geocode_data else None,
                    json.dumps(aqi_data) if aqi_data else None,
                    result.recommendation,
                    result.timestamp,
                )
            log.info("Saved listing %s", result.listing_id)
        except Exception as exc:
            log.error("PostgreSQL save failed for %s: %s", result.listing_id, exc)
            raise

    async def get(self, listing_id: str) -> Optional[dict]:
        """Get listing by ID."""
        try:
            pool = _get_pool()
            query = "SELECT * FROM kos_listings WHERE id = $1"
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, listing_id)
            return dict(row) if row else None
        except Exception as exc:
            log.warning("PostgreSQL get failed for %s: %s", listing_id, exc)
            return None

    async def exists_by_link(self, source_link: str) -> bool:
        """Check if listing exists by source link."""
        if not source_link:
            return False
        try:
            pool = _get_pool()
            query = "SELECT 1 FROM kos_listings WHERE source_link = $1 LIMIT 1"
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, source_link)
            return row is not None
        except Exception as exc:
            log.warning("PostgreSQL exists_by_link failed: %s", exc)
            return False

    async def get_recent(self, limit: int = 3) -> list[dict]:
        """Get recent listings."""
        try:
            pool = _get_pool()
            query = """
                SELECT * FROM kos_listings
                ORDER BY created_at DESC
                LIMIT $1
            """
            async with pool.acquire() as conn:
                rows = await conn.fetch(query, limit)
            return [dict(row) for row in rows]
        except Exception as exc:
            log.warning("PostgreSQL get_recent failed: %s", exc)
            return []

    async def count_all(self) -> int:
        """Count all listings."""
        try:
            pool = _get_pool()
            query = "SELECT COUNT(*) as cnt FROM kos_listings"
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query)
            return row["cnt"] if row else 0
        except Exception as exc:
            log.warning("PostgreSQL count_all failed: %s", exc)
            return 0

    async def count_high_risk(self) -> int:
        """Count high-risk listings."""
        try:
            pool = _get_pool()
            query = "SELECT COUNT(*) as cnt FROM kos_listings WHERE fraud_risk = 'HIGH'"
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query)
            return row["cnt"] if row else 0
        except Exception as exc:
            log.warning("PostgreSQL count_high_risk failed: %s", exc)
            return 0

    async def delete(self, listing_id: str) -> None:
        """Delete listing by ID."""
        try:
            pool = _get_pool()
            query = "DELETE FROM kos_listings WHERE id = $1"
            async with pool.acquire() as conn:
                await conn.execute(query, listing_id)
            log.info("Deleted listing %s", listing_id)
        except Exception as exc:
            log.error("PostgreSQL delete failed for %s: %s", listing_id, exc)
            raise


# ── PreferencesRepository ─────────────────────────────────────────────────────

class PostgresPreferencesRepo(PreferencesRepository):
    def __init__(self, config: PostgresConfig) -> None:
        self._url = config.url

    async def get_or_create(self, chat_id: int) -> UserPreferences:
        """Get or create user preferences."""
        try:
            pool = _get_pool()
            query = "SELECT * FROM user_preferences WHERE chat_id = $1"
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, chat_id)
            
            if row:
                return UserPreferences(
                    chat_id=row["chat_id"],
                    max_distance_km=row["max_distance_km"],
                    budget_min=row["budget_min"],
                    budget_max=row["budget_max"],
                    area_preferences=row["area_preferences"] or [],
                    skip_counts=row["skip_counts"] or {},
                    avoided_areas=row["avoided_areas"] or [],
                )
            else:
                # Create default
                prefs = UserPreferences(
                    chat_id=chat_id,
                    max_distance_km=15.0,
                    budget_min=300_000,
                    budget_max=800_000,
                )
                await self.save(prefs)
                return prefs
        except Exception as exc:
            log.error("PostgreSQL get_or_create failed: %s", exc)
            raise

    async def save(self, prefs: UserPreferences) -> None:
        """Save user preferences."""
        try:
            pool = _get_pool()
            query = """
                INSERT INTO user_preferences (
                    chat_id, max_distance_km, budget_min, budget_max,
                    area_preferences, skip_counts, avoided_areas, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, NOW()
                )
                ON CONFLICT (chat_id) DO UPDATE SET
                    max_distance_km = $2,
                    budget_min = $3,
                    budget_max = $4,
                    area_preferences = $5,
                    skip_counts = $6,
                    avoided_areas = $7,
                    updated_at = NOW()
            """
            async with pool.acquire() as conn:
                await conn.execute(
                    query,
                    prefs.chat_id,
                    prefs.max_distance_km,
                    prefs.budget_min,
                    prefs.budget_max,
                    json.dumps(prefs.area_preferences),
                    json.dumps(prefs.skip_counts),
                    json.dumps(prefs.avoided_areas),
                )
            log.info("Saved preferences for chat_id %s", prefs.chat_id)
        except Exception as exc:
            log.error("PostgreSQL save preferences failed: %s", exc)
            raise


# ── BlacklistRepository ───────────────────────────────────────────────────────

class PostgresBlacklistRepo(BlacklistRepository):
    def __init__(self, config: PostgresConfig) -> None:
        self._url = config.url

    async def add(self, phone: str, reason: str = "") -> None:
        """Add phone to blacklist."""
        try:
            pool = _get_pool()
            query = """
                INSERT INTO blacklist (phone, reason, added_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (phone) DO UPDATE SET reason = $2
            """
            async with pool.acquire() as conn:
                await conn.execute(query, phone, reason)
            log.info("Blacklisted phone %s: %s", phone, reason)
        except Exception as exc:
            log.error("PostgreSQL blacklist add failed: %s", exc)
            raise

    async def is_blocked(self, phone: str) -> bool:
        """Check if phone is blacklisted."""
        try:
            pool = _get_pool()
            query = "SELECT 1 FROM blacklist WHERE phone = $1 LIMIT 1"
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, phone)
            return row is not None
        except Exception as exc:
            log.warning("PostgreSQL blacklist check failed: %s", exc)
            return False


# ── AreaCacheRepository ───────────────────────────────────────────────────────

class PostgresAreaCacheRepo(AreaCacheRepository):
    def __init__(self, config: PostgresConfig) -> None:
        self._url = config.url

    async def get_cache(self, area_name: str) -> Optional[dict]:
        """Get cached area stats (24h TTL)."""
        try:
            pool = _get_pool()
            query = """
                SELECT * FROM area_cache
                WHERE area_name = $1
                AND cached_at > NOW() - INTERVAL '24 hours'
            """
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, area_name)
            return dict(row) if row else None
        except Exception as exc:
            log.warning("PostgreSQL area cache get failed: %s", exc)
            return None

    async def set_cache(self, area_name: str, data: dict) -> None:
        """Cache area stats."""
        try:
            pool = _get_pool()
            query = """
                INSERT INTO area_cache (area_name, skip_count, survey_count, avg_score, cached_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (area_name) DO UPDATE SET
                    skip_count = $2,
                    survey_count = $3,
                    avg_score = $4,
                    cached_at = NOW()
            """
            async with pool.acquire() as conn:
                await conn.execute(
                    query,
                    area_name,
                    data.get("skip_count", 0),
                    data.get("survey_count", 0),
                    data.get("avg_score", 0.0),
                )
        except Exception as exc:
            log.error("PostgreSQL area cache set failed: %s", exc)
            raise


# ── SessionRepository ─────────────────────────────────────────────────────────

class PostgresSessionRepo(SessionRepository):
    def __init__(self, config: PostgresConfig) -> None:
        self._url = config.url

    async def get(self, chat_id: int) -> Optional[dict]:
        """Get session data."""
        try:
            pool = _get_pool()
            query = "SELECT * FROM sessions WHERE chat_id = $1"
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, chat_id)
            return dict(row) if row else None
        except Exception as exc:
            log.warning("PostgreSQL session get failed: %s", exc)
            return None

    async def set(self, chat_id: int, data: dict) -> None:
        """Set session data."""
        try:
            pool = _get_pool()
            query = """
                INSERT INTO sessions (chat_id, state, current_listing_id, created_at, last_activity)
                VALUES ($1, $2, $3, NOW(), NOW())
                ON CONFLICT (chat_id) DO UPDATE SET
                    state = $2,
                    current_listing_id = $3,
                    last_activity = NOW()
            """
            async with pool.acquire() as conn:
                await conn.execute(
                    query,
                    chat_id,
                    data.get("state", "idle"),
                    data.get("current_listing_id"),
                )
        except Exception as exc:
            log.error("PostgreSQL session set failed: %s", exc)
            raise
