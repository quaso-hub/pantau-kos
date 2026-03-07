"""
infrastructure/container.py
Dependency Injection container — simple dataclass that holds all concrete
instances.  Built once in main.py, then passed to handlers/services.

Why not a DI framework?
  For a scalable monolith on Cloud Run, a plain dataclass is simpler,
  debuggable, and has zero magic.  If we ever need scoped lifetimes,
  we can swap in `dependency-injector` or `inject` later.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from infrastructure.config import AppConfig
from domain.interfaces import (
    ListingRepository,
    PreferencesRepository,
    BlacklistRepository,
    AreaCacheRepository,
    SessionRepository,
    AIGateway,
    MapsGateway,
)
from services.analysis_service import AnalysisService
from services.feedback_service import FeedbackService
from services.monitor_service import MonitorService

log = logging.getLogger("god-eye.container")


@dataclass
class Container:
    """
    Holds all wired dependencies.  Constructed once in main.py.

    Usage in handlers:
        container: Container = context.bot_data["container"]
        result = await container.analysis_service.analyze(...)
    """
    config: AppConfig

    # ── Repositories (adapters → domain interfaces) ──────────────────────
    listing_repo: ListingRepository = field(default=None)      # type: ignore[assignment]
    preferences_repo: PreferencesRepository = field(default=None)  # type: ignore[assignment]
    blacklist_repo: BlacklistRepository = field(default=None)   # type: ignore[assignment]
    area_cache_repo: AreaCacheRepository = field(default=None)  # type: ignore[assignment]
    session_repo: SessionRepository = field(default=None)       # type: ignore[assignment]

    # ── Gateways (adapters → domain interfaces) ──────────────────────────
    gemini_gateway: AIGateway = field(default=None)             # type: ignore[assignment]
    deepseek_gateway: AIGateway = field(default=None)           # type: ignore[assignment]
    maps_gateway: MapsGateway = field(default=None)             # type: ignore[assignment]

    # ── Services (use cases) ─────────────────────────────────────────────
    analysis_service: AnalysisService = field(default=None)     # type: ignore[assignment]
    feedback_service: FeedbackService = field(default=None)     # type: ignore[assignment]
    monitor_service: MonitorService = field(default=None)       # type: ignore[assignment]

    @classmethod
    def build(cls, config: AppConfig) -> "Container":
        """Wire all concrete implementations."""
        # Lazy imports to avoid circular dependencies
        from adapters.repositories.firestore_repo import (
            FirestoreListingRepo,
            FirestorePreferencesRepo,
            FirestoreBlacklistRepo,
            FirestoreAreaCacheRepo,
            FirestoreSessionRepo,
        )
        from adapters.gateways.gemini_gateway import GeminiGateway
        from adapters.gateways.deepseek_gateway import DeepSeekGateway
        from adapters.gateways.maps_gateway import GoogleMapsGateway

        # 1. Repositories
        listing_repo = FirestoreListingRepo(config.firestore)
        preferences_repo = FirestorePreferencesRepo(config.firestore)
        blacklist_repo = FirestoreBlacklistRepo(config.firestore)
        area_cache_repo = FirestoreAreaCacheRepo(config.firestore)
        session_repo = FirestoreSessionRepo(config.firestore)

        # 2. Gateways
        gemini_gw = GeminiGateway(config.gemini)
        deepseek_gw = DeepSeekGateway(config.deepseek)
        maps_gw = GoogleMapsGateway(config.maps)

        # 3. Services (depend on repos + gateways — no circular deps)
        analysis_svc = AnalysisService(
            gemini=gemini_gw,
            deepseek=deepseek_gw,
            maps=maps_gw,
            listing_repo=listing_repo,
            preferences_repo=preferences_repo,
        )
        feedback_svc = FeedbackService(
            preferences_repo=preferences_repo,
            blacklist_repo=blacklist_repo,
            listing_repo=listing_repo,
        )
        monitor_svc = MonitorService(
            analysis_service=analysis_svc,
            listing_repo=listing_repo,
            preferences_repo=preferences_repo,
            config=config.monitor,
        )

        container = cls(
            config=config,
            listing_repo=listing_repo,
            preferences_repo=preferences_repo,
            blacklist_repo=blacklist_repo,
            area_cache_repo=area_cache_repo,
            session_repo=session_repo,
            gemini_gateway=gemini_gw,
            deepseek_gateway=deepseek_gw,
            maps_gateway=maps_gw,
            analysis_service=analysis_svc,
            feedback_service=feedback_svc,
            monitor_service=monitor_svc,
        )
        log.info("DI Container wired successfully.")
        return container
