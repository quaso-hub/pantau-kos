"""
memory/cache.py
Cache data area di Firestore dengan TTL 24 jam.
Digunakan untuk menghindari re-fetch data yang sama dalam waktu singkat.
"""
import logging

from memory.firestore import get_area_cache, set_area_cache

log = logging.getLogger("god-eye.cache")


def _area_key(area: str) -> str:
    """Normalize area string menjadi Firestore document key."""
    return area.lower().strip().replace(" ", "_").replace(",", "")[:100]


async def get_cached_area(area: str) -> dict | None:
    """Ambil data area dari cache jika masih valid (< 24 jam)."""
    key = _area_key(area)
    data = await get_area_cache(key)
    if data:
        log.debug(f"Cache HIT for area: {area!r}")
    return data


async def set_cached_area(area: str, data: dict) -> None:
    """Simpan data area ke cache."""
    key = _area_key(area)
    await set_area_cache(key, data)
    log.debug(f"Cache SET for area: {area!r}")
