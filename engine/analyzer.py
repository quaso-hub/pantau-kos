"""
engine/analyzer.py
Pipeline orchestrator: terima input (teks + gambar opsional) →
jalankan Gemini + Maps (parallel) + DeepSeek → scoring → simpan Firestore.
Return AnalysisResult dataclass.
"""
import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from engine.gemini_client import gemini_analyze
from engine.deepseek_client import deepseek_analyze
from engine.maps_client import maps_full, primary_distance_km, MapsResult
from memory.firestore import save_listing, get_preferences
from memory.scoring import calculate_score

log = logging.getLogger("god-eye.analyzer")


# ── Regex helpers (dipreserve dari root) ─────────────────────────────────────

def extract_phone(text: str) -> list[str]:
    return re.findall(r'(?:\+62|62|0)[\s\-]?8[\d\s\-]{8,12}', text)


def extract_price(text: str) -> list[str]:
    return re.findall(
        r'[Rr][pP]\.?\s?[\d.,]+(?:\s?[Jj][Tt][Aa]?)?(?:\s?[Kk])?', text
    )


def extract_links(text: str) -> list[str]:
    return re.findall(r'https?://[^\s]+', text)


def parse_price_value(price_str: str) -> float | None:
    """Parse string harga Rp ke nilai float. Return None jika gagal."""
    nums = re.findall(r'[\d.,]+', price_str)
    if not nums:
        return None
    try:
        val_str = nums[0].replace(".", "").replace(",", "")
        val = float(val_str)
        if val < 10:
            val *= 1_000_000
        elif val < 10_000:
            val *= 1_000
        if "jt" in price_str.lower() or "juta" in price_str.lower():
            if val < 100:
                val *= 1_000_000
        return val
    except Exception:
        return None


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class AnalysisResult:
    listing_id: str
    source: str
    text: str
    source_link: str

    phones: list[str]
    prices: list[str]
    price_value: float | None

    gemini_raw: str
    gemini_data: dict           # dict hasil Gemini (v3.1) — keys: location_text, room, phone_check, area, price_market, post_flags, authenticity
    location_hint: str
    maps: MapsResult
    distance_km_val: float | None

    deepseek_raw: str
    fraud_risk: str          # LOW / MEDIUM / HIGH
    price_score: int         # 1-10
    recommendation: str

    score: int               # 0-100 composite
    budget_status: str       # text status harga
    jarak_status: str        # text status jarak

    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ── Budget & jarak status ─────────────────────────────────────────────────────

def _budget_status(price_value: float | None) -> str:
    if price_value is None:
        return "❓ Harga tidak ditemukan"
    if 300_000 <= price_value <= 650_000:
        return f"✅ Rp {price_value:,.0f}/bulan — dalam budget"
    if price_value < 300_000:
        return f"⚠️ Rp {price_value:,.0f}/bulan — sangat murah, waspada"
    return f"❌ Rp {price_value:,.0f}/bulan — di atas budget"


def _jarak_status(km: float | None) -> str:
    if km is None:
        return "❓ Jarak belum diketahui"
    if km <= 10:
        return f"✅ {km:.1f} km — dalam radius 10km"
    if km <= 15:
        return f"⚠️ {km:.1f} km — radius 10-15km, agak jauh"
    return f"❌ {km:.1f} km — lebih dari 15km, terlalu jauh"


# ── Extract fraud risk dari teks DeepSeek ────────────────────────────────────

def _extract_fraud_risk(deepseek_text: str) -> str:
    upper = deepseek_text.upper()
    if "HIGH" in upper or "TINGGI" in upper:
        return "HIGH"
    if "MEDIUM" in upper or "SEDANG" in upper:
        return "MEDIUM"
    return "LOW"


def _extract_price_score(deepseek_text: str) -> int:
    m = re.search(r'(?:skor|score)[^\d]*(\d{1,2})', deepseek_text, re.IGNORECASE)
    if m:
        return max(1, min(10, int(m.group(1))))
    return 5


def _extract_recommendation(deepseek_text: str) -> str:
    """Ambil bagian rekomendasi akhir dari teks DeepSeek."""
    m = re.search(
        r'(?:rekomendasi akhir|rekomendasi)[:\s]+(.+?)(?:\n\n|\Z)',
        deepseek_text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1).strip()[:300]
    # fallback: 2 kalimat terakhir
    sentences = [s.strip() for s in deepseek_text.split('.') if s.strip()]
# ── safe() wrapper ────────────────────────────────────────────────────────────

async def safe(coro, fallback=None, name: str = ""):
    """Jalankan coroutine dengan timeout 15s. Return fallback jika gagal (non-fatal)."""
    try:
        return await asyncio.wait_for(coro, timeout=15.0)
    except Exception as exc:
        log.warning(f"{name or 'safe()'} failed: {exc}")
        return fallback


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def full_analysis(
    text: str = "",
    image_bytes: bytes | None = None,
    source_link: str = "",
    source: str = "manual",
    chat_id: int | None = None,
) -> AnalysisResult:
    """
    Pipeline v3.1:
    1. Extract telepon, harga, link dari teks
    2. Gemini (gemini-3.1-pro-preview): analisis → JSON dict
    3. Maps: geocode → Routes + Places + AQI + AddressValidation (parallel, safe)
    4. DeepSeek: skor harga, risiko penipuan, rekomendasi
    5. Scoring komposit (memory.scoring)
    6. Simpan ke Firestore
    """
    listing_id = str(uuid.uuid4())[:8]
    phones    = extract_phone(text)
    prices    = extract_price(text)
    links     = extract_links(text)
    phone_str = ", ".join(phones) if phones else "Tidak ditemukan"
    price_str = ", ".join(prices) if prices else "Tidak disebutkan"
    price_val = parse_price_value(prices[0]) if prices else None

    # ── 1. Gemini → dict ──────────────────────────────────────────────────────
    gemini_prompt = (
        f"TEKS POST:\n{text or '(hanya gambar)'}\n\n"
        f"LINK SUMBER: {source_link or '(tidak ada)'}\n\n"
        f"NOMOR KONTAK: {phone_str}\n\n"
        "Analisis kos-kosan ini sesuai instruksi sistem. "
        "Kembalikan JSON lengkap dengan semua field yang diminta."
    )
    gemini_data: dict = await safe(
        gemini_analyze(gemini_prompt, image_bytes),
        fallback={},
        name="Gemini",
    )
    # Fallback raw string untuk kompatibilitas formatter lama
    gemini_raw = gemini_data.get("summary", str(gemini_data)) if gemini_data else ""

    # ── 2. Extract lokasi dari Gemini dict atau teks mentah ───────────────────
    location_hint: str = gemini_data.get("location_text", "") if gemini_data else ""
    if not location_hint:
        for pattern in [
            r'(?:Lokasi|Alamat|Jalan)[:\s]+([^\n]{5,100})',
            r'(?:di|area|kawasan)\s+([A-Z][a-zA-Z\s]{4,60}(?:,\s*Surabaya)?)',
        ]:
            m = re.search(pattern, gemini_raw, re.IGNORECASE)
            if m:
                location_hint = m.group(1).strip()
                break
    if not location_hint and text:
        m = re.search(r'(?:Jl\.|Jalan|Kel\.|Kec\.)[^\n,]{5,80}', text, re.IGNORECASE)
        if m:
            location_hint = m.group(0).strip()

    # ── 3. Maps (parallel, safe) ──────────────────────────────────────────────
    maps_result = MapsResult()
    location_query = location_hint or text[:80]
    if location_query.strip():
        maps_result = await safe(maps_full(location_query), fallback=MapsResult(), name="Maps")

    km_val = primary_distance_km(maps_result)

    # ── Load user preferences ─────────────────────────────────────────────────
    prefs: dict = {}
    if chat_id:
        prefs = await safe(get_preferences(chat_id), fallback={}, name="Prefs") or {}

    # ── 4. DeepSeek ───────────────────────────────────────────────────────────
    nearby_str = "\n".join(
        f"{i['type'].title()}: {i.get('name', '-')}"
        for i in maps_result.nearby if i.get("found")
    ) or "Tidak tersedia"

    air_str = "Tidak tersedia"
    if maps_result.air_quality:
        aq = maps_result.air_quality
        air_str = f"AQI {aq['aqi']} — {aq['category']}"

    jarak_text      = f"{km_val:.1f} km" if km_val is not None else "belum diketahui"
    preferred_areas = ", ".join(prefs.get("preferred_areas", [])) or "belum ada"
    max_price       = prefs.get("max_price", 650_000)

    deepseek_prompt = (
        "Kamu adalah konsultan properti sewa + analis keamanan untuk mahasiswa di Surabaya.\n\n"
        f"Teks postingan: {text[:500] if text else '(hanya gambar)'}\n"
        f"Harga: {price_str} | Kontak: {phone_str} | Jarak ke UBAYA: {jarak_text}\n"
        f"Kualitas udara: {air_str}\nFasilitas sekitar (1km):\n{nearby_str}\n"
        f"Preferensi user: area favorit={preferred_areas}, budget max=Rp{max_price:,}\n\n"
        "Berikan analisis SINGKAT:\n"
        "1. SKOR KEWAJARAN HARGA (1-10)\n"
        "2. RISIKO PENIPUAN (LOW/MEDIUM/HIGH + alasan singkat)\n"
        "3. KEAMANAN LINGKUNGAN malam hari\n"
        "4. REKOMENDASI AKHIR (2 kalimat)\n"
        "Jawab ringkas, poin-poin, Bahasa Indonesia."
    )
    deepseek_raw: str = await safe(deepseek_analyze(deepseek_prompt), fallback="", name="DeepSeek") or ""

    fraud_risk     = _extract_fraud_risk(deepseek_raw)
    price_score    = _extract_price_score(deepseek_raw)
    recommendation = (
        gemini_data.get("authenticity", {}).get("recommendation")
        or _extract_recommendation(deepseek_raw)
    )

    # ── 5. Scoring komposit ───────────────────────────────────────────────────
    score = calculate_score(
        price_value=price_val,
        km=km_val,
        location=location_hint,
        fraud_risk=fraud_risk,
        nearby_count=sum(1 for i in maps_result.nearby if i.get("found")),
        preferences=prefs,
    )

    result = AnalysisResult(
        listing_id=listing_id,
        source=source,
        text=text,
        source_link=source_link,
        phones=phones,
        prices=prices,
        price_value=price_val,
        gemini_raw=gemini_raw,
        gemini_data=gemini_data,
        location_hint=location_hint,
        maps=maps_result,
        distance_km_val=km_val,
        deepseek_raw=deepseek_raw,
        fraud_risk=fraud_risk,
        price_score=price_score,
        recommendation=recommendation,
        score=score,
        budget_status=_budget_status(price_val),
        jarak_status=_jarak_status(km_val),
    )

    # ── 6. Simpan ke Firestore ────────────────────────────────────────────────
    try:
        await save_listing(result)
    except Exception as exc:
        log.warning(f"Firestore save failed (non-fatal): {exc}")

    return result

