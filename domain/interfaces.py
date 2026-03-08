"""
domain/interfaces.py
Abstract interfaces (Ports) for the Clean Architecture boundary.
All adapters (Firestore, Gemini, Maps, etc.) implement these ABCs.
Domain and Service layers depend ONLY on these interfaces — never on concrete adapters.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from domain.models import (
    AnalysisResult,
    MapsResult,
    UserPreferences,
)


# ═══════════════════════════════════════════════════════════════════════════════
# REPOSITORIES  (data persistence ports)
# ═══════════════════════════════════════════════════════════════════════════════

class ListingRepository(ABC):
    """Port for kos_listings persistence."""

    @abstractmethod
    async def save(self, result: AnalysisResult) -> None: ...

    @abstractmethod
    async def get(self, listing_id: str) -> Optional[dict]: ...

    @abstractmethod
    async def exists_by_link(self, source_link: str) -> bool: ...

    @abstractmethod
    async def get_recent(self, limit: int = 3) -> list[dict]: ...

    @abstractmethod
    async def count_all(self) -> int: ...

    @abstractmethod
    async def count_high_risk(self) -> int: ...


class PreferencesRepository(ABC):
    """Port for user_preferences persistence."""

    @abstractmethod
    async def get(self, chat_id: int) -> UserPreferences: ...

    @abstractmethod
    async def update(self, chat_id: int, patch: dict) -> None: ...

    @abstractmethod
    async def append_feedback(self, chat_id: int, listing_id: str, action: str) -> None: ...

    @abstractmethod
    async def clear_areas(self, chat_id: int) -> None: ...


class BlacklistRepository(ABC):
    """Port for phone blacklist persistence."""

    @abstractmethod
    async def is_blacklisted(self, phone: str) -> bool: ...

    @abstractmethod
    async def add(self, phone: str, reason: str = "") -> None: ...


class AreaCacheRepository(ABC):
    """Port for area data cache (24h TTL)."""

    @abstractmethod
    async def get(self, area_key: str) -> Optional[dict]: ...

    @abstractmethod
    async def set(self, area_key: str, data: dict) -> None: ...


class SessionRepository(ABC):
    """Port for active analysis session tracking (idempotency)."""

    @abstractmethod
    async def save_message_id(self, chat_id: int, message_id: int) -> None: ...

    @abstractmethod
    async def get_message_id(self, chat_id: int) -> Optional[int]: ...

    @abstractmethod
    async def save_context(self, chat_id: int, text: str, source_link: str) -> None:
        """Persist the last user input so Retry callbacks can replay it."""
        ...

    @abstractmethod
    async def get_context(self, chat_id: int) -> Optional[dict]:
        """Return {'text': ..., 'source_link': ...} or None."""
        ...

    @abstractmethod
    async def clear(self, chat_id: int) -> None: ...


# ═══════════════════════════════════════════════════════════════════════════════
# GATEWAYS  (external service ports)
# ═══════════════════════════════════════════════════════════════════════════════

class AIGateway(ABC):
    """Port for AI analysis services (Gemini, DeepSeek, etc.)."""

    @abstractmethod
    async def analyze(
        self,
        prompt: str,
        image_bytes: Optional[bytes] = None,
        system_prompt: Optional[str] = None,
        use_grounding: bool = True,
        use_thinking: bool = False,
        json_schema: Optional[dict] = None,
    ) -> dict | str:
        """
        Send prompt (+ optional image) to the AI service.
        - system_prompt: override default system instruction per-call (for multi-agent)
        - use_grounding: enable Google Search grounding (Gemini only)
          NOTE: two-phase approach used — Phase 1 grounding (plain text), Phase 2 JSON extraction
        - use_thinking: enable thinking_level=high (Gemini only)
        - json_schema: pin output schema for Phase 2 / single-phase JSON calls
        Return parsed dict (Gemini) or raw string (DeepSeek).
        """
        ...


class MapsGateway(ABC):
    """Port for Maps/Geolocation services."""

    @abstractmethod
    async def geocode(self, address: str) -> Optional[dict]: ...

    @abstractmethod
    async def full_lookup(self, location_hint: str) -> MapsResult: ...

    @abstractmethod
    def primary_distance_km(self, maps_result: MapsResult) -> Optional[float]: ...
