"""
services/monitor_service.py
Use Case: Process incoming n8n scraper webhook payloads.
Filter → deduplicate → analyze → decide notification threshold.
Depends only on domain interfaces + AnalysisService.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from domain.interfaces import ListingRepository, PreferencesRepository
from domain.models import AnalysisResult, MonitorPayload
from infrastructure.config import MonitorConfig
from services.analysis_service import AnalysisService

log = logging.getLogger("god-eye.monitor-service")


class MonitorNotification:
    """Value object returned to the controller layer for notification dispatch."""

    def __init__(
        self,
        result: AnalysisResult,
        source: str,
        should_notify: bool,
        skip_reason: str = "",
    ) -> None:
        self.result = result
        self.source = source
        self.should_notify = should_notify
        self.skip_reason = skip_reason


class MonitorService:
    """
    Application-level use case: ingest a scraper payload.

    Pipeline:
    1. Coarse filter (price range, city whitelist)
    2. Deduplication check
    3. Download first image
    4. Delegate to AnalysisService
    5. Check notification threshold
    6. Return MonitorNotification (controller decides how to send)
    """

    def __init__(
        self,
        analysis_service: AnalysisService,
        listing_repo: ListingRepository,
        preferences_repo: PreferencesRepository,
        config: MonitorConfig,
    ) -> None:
        self._analysis = analysis_service
        self._listings = listing_repo
        self._prefs = preferences_repo
        self._cfg = config

    async def ingest(
        self,
        payload: MonitorPayload,
        chat_id: int,
    ) -> Optional[MonitorNotification]:
        """
        Process one scraper payload.
        Returns MonitorNotification if analysis succeeded, else None.
        """
        # ── 1. Price filter ──────────────────────────────────────────────────
        if payload.price is not None:
            if not (self._cfg.price_min <= payload.price <= self._cfg.price_max):
                log.info("Skipped (price out of range): %s", payload.price)
                return None

        # ── 2. City filter ───────────────────────────────────────────────────
        loc_lower = payload.location.lower()
        if not any(city in loc_lower for city in self._cfg.allowed_cities):
            log.info("Skipped (city not allowed): %r", payload.location)
            return None

        # ── 3. Deduplication ─────────────────────────────────────────────────
        if payload.url and await self._listings.exists_by_link(payload.url):
            log.info("Skipped (duplicate): %s", payload.url)
            return None

        # ── 4. Download first image ──────────────────────────────────────────
        image_bytes: Optional[bytes] = None
        if payload.images:
            try:
                async with httpx.AsyncClient(timeout=10) as c:
                    r = await c.get(payload.images[0])
                    if r.status_code == 200:
                        image_bytes = r.content
            except Exception as exc:
                log.warning("Failed to download monitor image: %s", exc)

        # ── 5. Build combined text ───────────────────────────────────────────
        price_text = f"Rp {payload.price:,}/bulan" if payload.price else ""
        combined = "\n".join(
            filter(None, [payload.title, price_text, payload.location, payload.description])
        )

        # ── 6. Full analysis ─────────────────────────────────────────────────
        try:
            result = await self._analysis.analyze(
                text=combined,
                image_bytes=image_bytes,
                source_link=payload.url,
                source=payload.source,
                chat_id=chat_id,
            )
        except Exception as exc:
            log.error("Monitor analysis failed: %s", exc, exc_info=True)
            return MonitorNotification(
                result=None,  # type: ignore[arg-type]
                source=payload.source,
                should_notify=False,
                skip_reason=f"Analysis error: {str(exc)[:200]}",
            )

        # ── 7. Threshold check ───────────────────────────────────────────────
        try:
            prefs = await self._prefs.get(chat_id)
            threshold = prefs.notification_threshold
        except Exception:
            threshold = 70

        if result.score < threshold:
            log.info(
                "Score %d < threshold %s, skipping notification",
                result.score,
                threshold,
            )
            return MonitorNotification(
                result=result,
                source=payload.source,
                should_notify=False,
                skip_reason=f"Score {result.score} < threshold {threshold}",
            )

        return MonitorNotification(
            result=result,
            source=payload.source,
            should_notify=True,
        )
