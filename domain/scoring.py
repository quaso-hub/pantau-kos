"""
domain/scoring.py
Pure scoring function — zero I/O, zero external dependencies.
Moved from memory/scoring.py into the domain layer where it belongs.
"""
from __future__ import annotations

from domain.models import UserPreferences

# ── Tier tables ───────────────────────────────────────────────────────────────

PRICE_TIERS: list[tuple[int, int, int]] = [
    (450_000, 550_000, +20),
    (550_000, 650_000, +15),
    (650_000, 750_000, +5),
    (0,       450_000, +10),
    (750_000, 10_000_000, -15),
]

DISTANCE_TIERS: list[tuple[float, float, int]] = [
    (0, 3,   +20),
    (3, 5,   +15),
    (5, 10,  +10),
    (10, 15,  +0),
    (15, 999, -20),
]


def _price_delta(price: float) -> int:
    for lo, hi, delta in PRICE_TIERS:
        if lo <= price < hi:
            return delta
    return 0


def _distance_delta(km: float) -> int:
    for lo, hi, delta in DISTANCE_TIERS:
        if lo <= km < hi:
            return delta
    return -20


def calculate_score(
    price_value: float | None,
    km: float | None,
    location: str,
    fraud_risk: str,
    nearby_count: int,
    preferences: UserPreferences,
) -> int:
    """
    Composite score 0-100.
    Base 50 + Harga(±20) + Jarak(±20) + Area(±15) + Fraud(-30) + Fasilitas(+15).
    """
    score = 50

    if price_value is not None:
        score += _price_delta(price_value)

    if km is not None:
        score += _distance_delta(km)

    loc_lower = location.lower()
    preferred = [a.lower() for a in preferences.preferred_areas]
    avoided = [a.lower() for a in preferences.avoided_areas]

    if any(a in loc_lower for a in preferred):
        score += 15
    if any(a in loc_lower for a in avoided):
        score -= 15

    # Soft penalty for repeatedly-skipped areas
    for area_key, count in preferences.skip_counts.items():
        if loc_lower in area_key.lower() and count >= 3:
            score -= 10
            break

    score += {"HIGH": -30, "MEDIUM": -10, "LOW": 0}.get(fraud_risk, 0)

    score += min(nearby_count * 3, 15)

    return max(0, min(100, score))
