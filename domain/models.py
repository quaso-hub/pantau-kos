"""
domain/models.py
Pure domain models — zero external dependencies.
All business entities are plain dataclasses; no ORM, no SDK types.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ── Value Objects ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GeoCoord:
    lat: float
    lng: float


@dataclass(frozen=True)
class RouteInfo:
    label: str                          # e.g. "pagi_06:00"
    duration_minutes: Optional[int]
    distance_km: Optional[float]


@dataclass(frozen=True)
class NearbyPlace:
    place_type: str                     # e.g. "supermarket", "hospital"
    name: str
    found: bool


@dataclass(frozen=True)
class AirQuality:
    aqi: int
    category: str


# ── Aggregate: MapsResult ────────────────────────────────────────────────────

@dataclass
class MapsResult:
    geocode: Optional[dict] = None      # {lat, lng, formatted}
    routes: list[RouteInfo] = field(default_factory=list)
    nearby: list[NearbyPlace] = field(default_factory=list)
    air_quality: Optional[AirQuality] = None
    address_validated: Optional[str] = None


# ── Aggregate: AnalysisResult ────────────────────────────────────────────────

@dataclass
class AnalysisResult:
    listing_id: str
    source: str
    text: str
    source_link: str

    phones: list[str]
    prices: list[str]
    price_value: Optional[float]

    gemini_raw: str
    gemini_data: dict
    location_hint: str
    maps: MapsResult
    distance_km_val: Optional[float]

    deepseek_raw: str
    fraud_risk: str                     # LOW / MEDIUM / HIGH
    price_score: int                    # 1-10
    recommendation: str

    score: int                          # 0-100 composite
    budget_status: str
    jarak_status: str

    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())[:8]


# ── Entity: UserPreferences ──────────────────────────────────────────────────

@dataclass
class UserPreferences:
    preferred_areas: list[str] = field(default_factory=list)
    avoided_areas: list[str] = field(default_factory=list)
    max_distance_km: float = 15.0
    max_price: int = 650_000
    required_facilities: list[str] = field(default_factory=list)
    feedback_history: list[dict] = field(default_factory=list)
    notification_threshold: float = 70.0
    skip_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "preferred_areas": self.preferred_areas,
            "avoided_areas": self.avoided_areas,
            "max_distance_km": self.max_distance_km,
            "max_price": self.max_price,
            "required_facilities": self.required_facilities,
            "feedback_history": self.feedback_history,
            "notification_threshold": self.notification_threshold,
            "skip_counts": self.skip_counts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UserPreferences":
        defaults = cls()
        return cls(
            preferred_areas=d.get("preferred_areas", defaults.preferred_areas),
            avoided_areas=d.get("avoided_areas", defaults.avoided_areas),
            max_distance_km=d.get("max_distance_km", defaults.max_distance_km),
            max_price=d.get("max_price", defaults.max_price),
            required_facilities=d.get("required_facilities", defaults.required_facilities),
            feedback_history=d.get("feedback_history", defaults.feedback_history),
            notification_threshold=d.get("notification_threshold", defaults.notification_threshold),
            skip_counts=d.get("skip_counts", defaults.skip_counts),
        )


# ── Entity: MonitorPayload (incoming scraper data) ───────────────────────────

@dataclass
class MonitorPayload:
    source: str = "unknown"
    title: str = ""
    price: Optional[int] = None
    location: str = ""
    url: str = ""
    description: str = ""
    images: list[str] = field(default_factory=list)
    scraped_at: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "MonitorPayload":
        price_raw = d.get("price")
        price_int: Optional[int] = None
        if price_raw is not None:
            try:
                price_int = int(price_raw)
            except (ValueError, TypeError):
                pass
        return cls(
            source=d.get("source", "unknown"),
            title=d.get("title", ""),
            price=price_int,
            location=d.get("location", ""),
            url=d.get("url", ""),
            description=d.get("description", ""),
            images=d.get("images", []),
            scraped_at=d.get("scraped_at", ""),
        )
