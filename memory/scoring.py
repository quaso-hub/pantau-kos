"""
memory/scoring.py  (v3.1)
Fungsi scoring komposit 0-100 untuk satu listing kos.
Dipisah dari learning.py agar bisa diimport dari analyzer dan learning.

Formula:
  Base 50
  + Harga     (max +20 / min -15)
  + Jarak     (max +20 / min -20)
  + Area pref (±15)
  + Fraud     (max -30)
  + Fasilitas (max +15)
  Clamp [0, 100]
"""

PRICE_TIERS: list[tuple[int, int, int]] = [
    # (batas_bawah, batas_atas, delta_score)
    (450_000, 550_000, +20),
    (550_000, 650_000, +15),
    (650_000, 750_000,  +5),
    (0,       450_000, +10),   # sangat murah → tambah tapi tidak maks (waspada)
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
    preferences: dict,
) -> int:
    """
    Hitung skor komposit 0-100 untuk satu listing.
    Dipanggil dari engine/analyzer.py dan memory/learning.py.

    Args:
        price_value:  harga bulanan (Rupiah), atau None
        km:           jarak ke UBAYA dalam km, atau None
        location:     string lokasi/area (untuk cek preferensi)
        fraud_risk:   "LOW" | "MEDIUM" | "HIGH"
        nearby_count: jumlah fasilitas ditemukan dalam 1km
        preferences:  dict preferensi user dari Firestore

    Returns:
        skor integer 0-100
    """
    score = 50

    # ── Harga ─────────────────────────────────────────────────────────────────
    if price_value is not None:
        score += _price_delta(price_value)

    # ── Jarak ─────────────────────────────────────────────────────────────────
    if km is not None:
        score += _distance_delta(km)

    # ── Area preferensi user (±15) ────────────────────────────────────────────
    loc_lower  = location.lower()
    preferred  = [a.lower() for a in preferences.get("preferred_areas", [])]
    avoided    = [a.lower() for a in preferences.get("avoided_areas",   [])]
    if any(a in loc_lower for a in preferred):
        score += 15
    if any(a in loc_lower for a in avoided):
        score -= 15

    # ── Blacklist area dari skip_counts ───────────────────────────────────────
    skip_counts: dict = preferences.get("skip_counts", {})
    if any(
        loc_lower in k.lower() and v >= 3
        for k, v in skip_counts.items()
    ):
        score -= 10  # soft penalty — lebih ringan dari avoided_areas

    # ── Fraud risk (max -30) ──────────────────────────────────────────────────
    score += {"HIGH": -30, "MEDIUM": -10, "LOW": 0}.get(fraud_risk, 0)

    # ── Fasilitas sekitar (max +15) ───────────────────────────────────────────
    score += min(nearby_count * 3, 15)

    return max(0, min(100, score))
