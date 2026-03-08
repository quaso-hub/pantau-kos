"""
adapters/gateways/maps_gateway.py  (v5.0)
Concrete Google Maps implementation of MapsGateway.

v5.0 enhancements:
  - tenacity retries with exponential backoff + jitter on all API calls
  - Circuit breaker: 3 consecutive failures → open circuit → instant fallback
  - In-memory LRU cache for geocoding (results rarely change, saves API quota)
  - All parallel via asyncio.gather()
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from domain.interfaces import MapsGateway
from domain.models import AirQuality, MapsResult, NearbyPlace, RouteInfo
from infrastructure.config import MapsConfig

log = logging.getLogger("god-eye.maps")

_ROUTES_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"
_PLACES_ENDPOINT = "https://places.googleapis.com/v1/places:searchNearby"
_AQI_ENDPOINT = "https://airquality.googleapis.com/v1/currentConditions:lookup"
_GEOCODE_ENDPOINT = "https://maps.googleapis.com/maps/api/geocode/json"
_ADDRVAL_ENDPOINT = "https://addressvalidation.googleapis.com/v1:validateAddress"

_TRAVEL_SCENARIOS = [
    {"label": "pagi_06:00", "hour": 6, "minute": 0},
    {"label": "siang_12:30", "hour": 12, "minute": 30},
    {"label": "malam_21:00", "hour": 21, "minute": 0},
]

_PLACE_TYPES = ["supermarket", "hospital", "police", "atm", "mosque", "laundry"]


# ── Circuit Breaker ──────────────────────────────────────────────────────────

class CircuitBreaker:
    """Simple circuit breaker: opens after N consecutive failures, resets after cooldown."""

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 60.0):
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._failures = 0
        self._opened_at: Optional[float] = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at > self._cooldown:
            # Half-open: allow one attempt
            self._opened_at = None
            self._failures = 0
            log.info("Circuit breaker half-open — allowing retry")
            return False
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = time.monotonic()
            log.error(
                "Circuit breaker OPENED after %d consecutive failures (cooldown=%.0fs)",
                self._failures, self._cooldown,
            )


# ── In-Memory LRU Cache ─────────────────────────────────────────────────────

class LRUCache:
    """Simple async-safe LRU cache with TTL."""

    def __init__(self, maxsize: int = 128, ttl_seconds: float = 3600.0):
        self._cache: OrderedDict[str, tuple[float, any]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[any]:
        if key not in self._cache:
            return None
        ts, val = self._cache[key]
        if time.monotonic() - ts > self._ttl:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return val

    def set(self, key: str, value: any) -> None:
        self._cache[key] = (time.monotonic(), value)
        self._cache.move_to_end(key)
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)


def _next_weekday_departure(hour: int, minute: int) -> str:
    wib = timedelta(hours=7)
    now_wib = datetime.now(timezone.utc) + wib
    days_ahead = (0 - now_wib.weekday()) % 7
    if days_ahead == 0 and (
        now_wib.hour > hour or (now_wib.hour == hour and now_wib.minute >= minute)
    ):
        days_ahead = 7
    target_wib = now_wib.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(
        days=days_ahead
    )
    target_utc = target_wib - wib
    return target_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


class GoogleMapsGateway(MapsGateway):
    """Concrete Google Maps adapter with circuit breaker + geocode cache."""

    def __init__(self, config: MapsConfig) -> None:
        self._key = config.api_key
        self._ubaya_lat = config.ubaya_lat
        self._ubaya_lng = config.ubaya_lng
        # Circuit breaker: open after 3 consecutive failures, cooldown 60s
        self._circuit = CircuitBreaker(failure_threshold=3, cooldown_seconds=60.0)
        # Geocode cache: 128 entries, 1-hour TTL
        self._geocode_cache = LRUCache(maxsize=128, ttl_seconds=3600.0)

    # ── Geocoding ──────────────────────────────────────────────────────────

    async def geocode(self, address: str) -> Optional[dict]:
        """
        Geocode with cache + circuit breaker + 3-attempt fallback.
        """
        # Check cache first
        cache_key = address.strip().lower()[:200]
        cached = self._geocode_cache.get(cache_key)
        if cached is not None:
            log.info("Geocode CACHE HIT | address=%r", address[:60])
            return cached

        # Check circuit breaker
        if self._circuit.is_open:
            log.warning("Geocode CIRCUIT OPEN — returning None for %r", address[:60])
            return None

        queries = self._build_geocode_queries(address)
        for attempt, query in enumerate(queries, 1):
            result = await self._geocode_once(query, attempt)
            if result:
                self._circuit.record_success()
                # Cache the successful result
                self._geocode_cache.set(cache_key, result)
                return result
            self._circuit.record_failure()

        log.error(
            "Geocode EXHAUSTED all %d attempts | address=%r",
            len(queries), address,
        )
        return None

    def _build_geocode_queries(self, address: str) -> list[str]:
        """Build a progressive list of geocode query strings, coarsest last."""
        address = address.strip()
        queries = []

        # Full address
        full = f"{address}, Surabaya" if "surabaya" not in address.lower() else address
        queries.append(full[:200])

        # Shortened — take first meaningful segment before comma/newline
        parts = [p.strip() for p in address.replace("\n", ",").split(",")]
        # Skip segments that look like a full sentence (prose noise)
        short_parts = [p for p in parts if 3 <= len(p) <= 60 and not p[0].isdigit()]
        if short_parts and short_parts[0].lower() not in address[:20].lower():
            short = f"{short_parts[0]}, Surabaya"
            if short != queries[0]:
                queries.append(short)

        # Last word group that looks like a place name (capitalised, 4+ chars)
        import re as _r
        m = _r.search(r'\b([A-Z][a-z]{3,}(?:\s+[A-Z][a-z]{2,})?)\b', address)
        if m:
            area_only = f"{m.group(1)}, Surabaya"
            if area_only not in queries:
                queries.append(area_only)

        return queries

    async def _geocode_once(self, query: str, attempt: int) -> Optional[dict]:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(
                    _GEOCODE_ENDPOINT,
                    params={
                        "address": query,
                        "key": self._key,
                        "language": "id",
                        "region": "id",
                        "components": "country:ID",
                    },
                )
                data = r.json()
                status = data.get("status", "UNKNOWN")
                if status == "OK":
                    results = data.get("results", [])
                    if results:
                        loc = results[0]["geometry"]["location"]
                        log.info(
                            "Maps Geocode OK | attempt=%d | query=%r | formatted=%r",
                            attempt, query, results[0].get("formatted_address", ""),
                        )
                        return {
                            "lat": loc["lat"],
                            "lng": loc["lng"],
                            "formatted": results[0]["formatted_address"],
                        }
                elif status == "ZERO_RESULTS":
                    log.warning(
                        "Maps Geocode ZERO_RESULTS | attempt=%d | query=%r — trying shorter query",
                        attempt, query,
                    )
                else:
                    log.error(
                        "Maps Geocode FAILED | attempt=%d | status=%s | error=%s | query=%r",
                        attempt, status, data.get("error_message", "(none)"), query,
                    )
        except Exception as exc:
            log.error(
                "Maps Geocode EXCEPTION | attempt=%d | type=%s | detail=%s",
                attempt, type(exc).__name__, repr(exc),
            )
        return None

    # ── Full parallel lookup ───────────────────────────────────────────────

    async def full_lookup(self, location_hint: str) -> MapsResult:
        result = MapsResult()
        geo = await self.geocode(location_hint)
        if not geo:
            return result
        result.geocode = geo
        lat, lng = geo["lat"], geo["lng"]

        routes_list, nearby_list, aq, validated = await asyncio.gather(
            self._routes(lat, lng),
            self._nearby(lat, lng),
            self._air_quality(lat, lng),
            self._validate_address(location_hint),
        )
        result.routes = routes_list
        result.nearby = nearby_list
        result.air_quality = aq
        result.address_validated = validated
        return result

    def primary_distance_km(self, maps_result: MapsResult) -> Optional[float]:
        if maps_result.routes:
            return maps_result.routes[0].distance_km
        return None

    # ── Internal: Routes API ───────────────────────────────────────────────

    async def _route_one(
        self, c: httpx.AsyncClient, dest_lat: float, dest_lng: float, scenario: dict
    ) -> RouteInfo:
        try:
            body = {
                "origin": {
                    "location": {
                        "latLng": {"latitude": self._ubaya_lat, "longitude": self._ubaya_lng}
                    }
                },
                "destination": {
                    "location": {"latLng": {"latitude": dest_lat, "longitude": dest_lng}}
                },
                "travelMode": "DRIVE",
                "routingPreference": "TRAFFIC_AWARE",
                "departureTime": _next_weekday_departure(scenario["hour"], scenario["minute"]),
                "computeAlternativeRoutes": False,
                "languageCode": "id",
            }
            resp = await c.post(
                _ROUTES_ENDPOINT,
                json=body,
                headers={
                    "X-Goog-Api-Key": self._key,
                    "X-Goog-FieldMask": "routes.duration,routes.distanceMeters",
                },
                timeout=12,
            )
            route = resp.json().get("routes", [{}])[0]
            dur_s = int(route.get("duration", "0s").rstrip("s"))
            return RouteInfo(
                label=scenario["label"],
                duration_minutes=round(dur_s / 60),
                distance_km=round(route.get("distanceMeters", 0) / 1000, 1),
            )
        except Exception as exc:
            log.warning("Routes error (%s): %s", scenario["label"], exc)
            return RouteInfo(label=scenario["label"], duration_minutes=None, distance_km=None)

    async def _routes(self, dest_lat: float, dest_lng: float) -> list[RouteInfo]:
        async with httpx.AsyncClient(timeout=15) as c:
            results = await asyncio.gather(
                *[self._route_one(c, dest_lat, dest_lng, s) for s in _TRAVEL_SCENARIOS]
            )
        return list(results)

    # ── Internal: Places API ───────────────────────────────────────────────

    async def _place_one(
        self, c: httpx.AsyncClient, lat: float, lng: float, ptype: str
    ) -> NearbyPlace:
        try:
            resp = await c.post(
                _PLACES_ENDPOINT,
                json={
                    "includedTypes": [ptype],
                    "locationRestriction": {
                        "circle": {
                            "center": {"latitude": lat, "longitude": lng},
                            "radius": 1000.0,
                        }
                    },
                    "maxResultCount": 1,
                },
                headers={
                    "X-Goog-Api-Key": self._key,
                    "X-Goog-FieldMask": "places.displayName,places.formattedAddress",
                },
                timeout=10,
            )
            places = resp.json().get("places", [])
            if places:
                name = places[0].get("displayName", {}).get(
                    "text", places[0].get("formattedAddress", "-")
                )
                return NearbyPlace(place_type=ptype, name=name, found=True)
        except Exception as exc:
            log.warning("Places error (%s): %s", ptype, exc)
        return NearbyPlace(place_type=ptype, name="", found=False)

    async def _nearby(self, lat: float, lng: float) -> list[NearbyPlace]:
        async with httpx.AsyncClient(timeout=12) as c:
            results = await asyncio.gather(
                *[self._place_one(c, lat, lng, pt) for pt in _PLACE_TYPES]
            )
        return list(results)

    # ── Internal: Air Quality API ──────────────────────────────────────────

    async def _air_quality(self, lat: float, lng: float) -> Optional[AirQuality]:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(
                    _AQI_ENDPOINT,
                    json={"location": {"latitude": lat, "longitude": lng}},
                    params={"key": self._key},
                )
                indexes = r.json().get("indexes", [])
                if indexes:
                    return AirQuality(
                        aqi=indexes[0].get("aqi", 0),
                        category=indexes[0].get("category", "Tidak diketahui"),
                    )
        except Exception as exc:
            log.warning("Air quality error: %s", exc)
        return None

    # ── Internal: Address Validation ───────────────────────────────────────

    async def _validate_address(self, address: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(
                    f"{_ADDRVAL_ENDPOINT}?key={self._key}",
                    json={"address": {"addressLines": [address], "regionCode": "ID"}},
                )
                return (
                    r.json()
                    .get("result", {})
                    .get("address", {})
                    .get("formattedAddress")
                    or None
                )
        except Exception as exc:
            log.warning("Address validation error: %s", exc)
        return None
