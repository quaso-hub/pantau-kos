"""
services/feedback_service.py
Use Case: Process user feedback from inline buttons.
Updates preferences, manages blacklist.
Depends only on domain interfaces — zero Telegram knowledge.
"""
from __future__ import annotations

import logging

from domain.interfaces import (
    BlacklistRepository,
    ListingRepository,
    PreferencesRepository,
)
from domain.text_extractors import normalize_area

log = logging.getLogger("god-eye.feedback-service")


class FeedbackService:
    """
    Application-level use case: process feedback action on a listing.

    Actions:
      survey    → preferred_areas += area, threshold -= 1 (min 50)
      skip      → skip_counts[area] += 1, after 3x → avoided_areas
      save      → record only, no pref changes
      blacklist → add phone to blacklist
    """

    def __init__(
        self,
        preferences_repo: PreferencesRepository,
        blacklist_repo: BlacklistRepository,
        listing_repo: ListingRepository,
    ) -> None:
        self._prefs = preferences_repo
        self._blacklist = blacklist_repo
        self._listings = listing_repo

    async def process(
        self,
        chat_id: int,
        listing_id: str,
        action: str,
        location: str = "",
        price_value: float | None = None,
        listing: dict | None = None,
    ) -> None:
        prefs = await self._prefs.get(chat_id)
        patch: dict = {}
        kelurahan = normalize_area(location)

        if action == "survey":
            preferred = list(prefs.preferred_areas)
            if kelurahan and kelurahan not in preferred:
                preferred.append(kelurahan)
                patch["preferred_areas"] = preferred
            if price_value and price_value < prefs.max_price:
                patch["max_price"] = int(price_value)
            patch["notification_threshold"] = max(50, prefs.notification_threshold - 1)

        elif action == "skip":
            skip_counts = dict(prefs.skip_counts)
            skip_counts[kelurahan] = skip_counts.get(kelurahan, 0) + 1 if kelurahan else 0
            patch["skip_counts"] = skip_counts
            avoided = list(prefs.avoided_areas)
            if kelurahan and skip_counts.get(kelurahan, 0) >= 3 and kelurahan not in avoided:
                avoided.append(kelurahan)
                patch["avoided_areas"] = avoided
            patch["notification_threshold"] = min(85, prefs.notification_threshold + 0.5)

        elif action == "blacklist":
            phone = None
            if listing:
                phone = listing.get("phone") or (listing.get("phones") or [None])[0]
            if phone:
                await self._blacklist.add(phone, reason=f"Reported from listing {listing_id}")
                log.info("Blacklisted phone %s from listing %s", phone, listing_id)

        if patch:
            await self._prefs.update(chat_id, patch)

        await self._prefs.append_feedback(chat_id, listing_id, action)
        log.info("Feedback '%s' processed | listing=%s | chat=%s", action, listing_id, chat_id)
