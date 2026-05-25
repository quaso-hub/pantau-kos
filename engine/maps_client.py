"""
engine/maps_client.py
Semua Google Maps API calls:
  - Geocoding API         -> koordinat dari nama lokasi
  - Routes API v2         -> rute + traffic 3 scenario (BUKAN Distance Matrix)
  - Places API (New)      -> fasilitas sekitar 1km via searchNearby
  - Air Quality API       -> AQI area kos
  - Address Validation API -> normalize alamat
Semua async, parallel via asyncio.gather() + safe() wrapper di analyzer.
"""
import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger("god-eye.maps")

MAPS_API_KEY = os.environ["MAPS_API_KEY"]

UBAYA_LAT = -7.3275
UBAYA_LNG = 112.7858

_ROUTES_ENDPOINT  = "https://routes.googleapis.com/directions/v2:computeRoutes"
_PLACES_ENDPOINT  = "https://places.googleapis.com/v1/places:searchNearby"
_AQI_ENDPOINT     = "https://airquality.googleapis.com/v1/currentConditions:lookup"
_GEOCODE_ENDPOINT = "https://maps.googleapis.com/maps/api/geocode/json"
_ADDRVAL_ENDPOINT = "https://addressvalidation.googleapis.com/v1:validateAddress"

TRAVEL_SCENARIOS = [
    {"label": "pagi_06:00",  "hour": 6,  "minute": 0},
    {"label": "siang_12:30", "hour": 12, "minute": 30},
    {"label": "malam_21:00", "hour": 21, "minute": 0},
]

_PLACE_TYPES = ["supermarket", "hospital", "police", "atm", "mosque", "laundry"]


@dataclass
class MapsResult:
    geocode: dict | None = None
    routes: list = field(default_factory=list)   # [{label, duration_minutes, distance_km}]
    nearby: list = field(default_factory=list)   # [{type, name, found}]
    air_quality: dict | None = None
    address_validated: str | None = None


# -- Geocoding -----------------------------------------------------------------

async def maps_geocode(address: str) -> dict | None:
    """Ubah nama lokasi -> {lat, lng, formatted}."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                _GEOCODE_ENDPOINT,
                params={"address": f"{address}, Surabaya", "key": MAPS_API_KEY, "language": "id"},
            )
            results = r.json().get("results", [])
            if results:
                loc = results[0]["geometry"]["location"]
                return {"lat": loc["lat"], "lng": loc["lng"], "formatted": results[0]["formatted_address"]}
    except Exception as exc:
        log.warning(f"Geocode error: {exc}")
    return None


# -- Routes API ----------------------------------------------------------------

def _next_weekday_departure(hour: int, minute: int) -> str:
    """Return ISO8601 UTC timestamp untuk hari Senin depan jam HH:MM WIB (UTC+7)."""
    wib = timedelta(hours=7)
    now_wib = datetime.now(timezone.utc) + wib
    days_ahead = (0 - now_wib.weekday()) % 7
    if days_ahead == 0 and (now_wib.hour > hour or (now_wib.hour == hour and now_wib.minute >= minute)):
        days_ahead = 7
    target_wib = now_wib.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
    target_utc = target_wib - wib
    return target_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


async def _route_one(c: httpx.AsyncClient, dest_lat: float, dest_lng: float, scenario: dict) -> dict:
    try:
        body = {
            "origin":      {"location": {"latLng": {"latitude": UBAYA_LAT, "longitude": UBAYA_LNG}}},
            "destination": {"location": {"latLng": {"latitude": dest_lat,  "longitude": dest_lng}}},
            "travelMode":  "DRIVE",
            "routingPreference": "TRAFFIC_AWARE",
            "departureTime": _next_weekday_departure(scenario["hour"], scenario["minute"]),
            "computeAlternativeRoutes": False,
            "languageCode": "id",
        }
        resp = await c.post(
            _ROUTES_ENDPOINT,
            json=body,
            headers={
                "X-Goog-Api-Key": MAPS_API_KEY,
                "X-Goog-FieldMask": "routes.duration,routes.distanceMeters",
            },
            timeout=12,
        )
        route = resp.json().get("routes", [{}])[0]
        dur_s = int(route.get("duration", "0s").rstrip("s"))
        return {
            "label":            scenario["label"],
            "duration_minutes": round(dur_s / 60),
            "distance_km":      round(route.get("distanceMeters", 0) / 1000, 1),
        }
    except Exception as exc:
        log.warning(f"Routes error ({scenario['label']}): {exc}")
        return {"label": scenario["label"], "duration_minutes": None, "distance_km": None}


async def maps_routes(dest_lat: float, dest_lng: float) -> list:
    """Hitung rute + traffic 3 scenario secara parallel."""
    async with httpx.AsyncClient(timeout=15) as c:
        results = await asyncio.gather(*[
            _route_one(c, dest_lat, dest_lng, s) for s in TRAVEL_SCENARIOS
        ])
    return list(results)


# -- Places API (New) ----------------------------------------------------------

async def _place_one(c: httpx.AsyncClient, lat: float, lng: float, ptype: str) -> dict:
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
                "X-Goog-Api-Key": MAPS_API_KEY,
                "X-Goog-FieldMask": "places.displayName,places.formattedAddress",
            },
            timeout=10,
        )
        places = resp.json().get("places", [])
        if places:
            name = places[0].get("displayName", {}).get("text", places[0].get("formattedAddress", "-"))
            return {"type": ptype, "name": name, "found": True}
    except Exception as exc:
        log.warning(f"Places error ({ptype}): {exc}")
    return {"type": ptype, "found": False}


async def maps_nearby(lat: float, lng: float) -> list:
    """Cari fasilitas sekitar 1km secara parallel."""
    async with httpx.AsyncClient(timeout=12) as c:
        results = await asyncio.gather(*[_place_one(c, lat, lng, pt) for pt in _PLACE_TYPES])
    return list(results)


# -- Air Quality API -----------------------------------------------------------

async def maps_air_quality(lat: float, lng: float) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                _AQI_ENDPOINT,
                json={"location": {"latitude": lat, "longitude": lng}},
                params={"key": MAPS_API_KEY},
            )
            indexes = r.json().get("indexes", [])
            if indexes:
                return {"aqi": indexes[0].get("aqi", 0), "category": indexes[0].get("category", "Tidak diketahui")}
    except Exception as exc:
        log.warning(f"Air quality error: {exc}")
    return None


# -- Address Validation --------------------------------------------------------

async def maps_validate_address(address: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{_ADDRVAL_ENDPOINT}?key={MAPS_API_KEY}",
                json={"address": {"addressLines": [address], "regionCode": "ID"}},
            )
            return r.json().get("result", {}).get("address", {}).get("formattedAddress") or None
    except Exception as exc:
        log.warning(f"Address validation error: {exc}")
    return None


# -- Full parallel fetch -------------------------------------------------------

async def maps_full(location_hint: str) -> MapsResult:
    """Geocode lokasi, lalu jalankan Routes + Places + AQI + AddressValidation secara parallel."""
    result = MapsResult()
    geocode = await maps_geocode(location_hint)
    if not geocode:
        return result

    result.geocode = geocode
    lat, lng = geocode["lat"], geocode["lng"]

    result.routes, result.nearby, result.air_quality, result.address_validated = (
        await asyncio.gather(
            maps_routes(lat, lng),
            maps_nearby(lat, lng),
            maps_air_quality(lat, lng),
            maps_validate_address(location_hint),
        )
    )
    return result


def primary_distance_km(maps_result: MapsResult) -> float | None:
    """Ambil jarak km dari scenario pagi (index 0). Return None jika gagal."""
    if maps_result.routes:
        return maps_result.routes[0].get("distance_km")
    return None
