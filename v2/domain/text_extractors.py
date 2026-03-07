"""
domain/text_extractors.py
Pure text extraction functions — zero I/O, zero external dependencies.
Moved from engine/analyzer.py into the domain layer.
"""
from __future__ import annotations

import re
from typing import Optional


def extract_phone(text: str) -> list[str]:
    return re.findall(r'(?:\+62|62|0)[\s\-]?8[\d\s\-]{8,12}', text)


def extract_price(text: str) -> list[str]:
    return re.findall(
        r'[Rr][pP]\.?\s?[\d.,]+(?:\s?[Jj][Tt][Aa]?)?(?:\s?[Kk])?', text
    )


def extract_links(text: str) -> list[str]:
    return re.findall(r'https?://[^\s]+', text)


def parse_price_value(price_str: str) -> Optional[float]:
    """Parse Rp price string to float. Return None on failure."""
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


def extract_fraud_risk(deepseek_text: str) -> str:
    upper = deepseek_text.upper()
    if "HIGH" in upper or "TINGGI" in upper:
        return "HIGH"
    if "MEDIUM" in upper or "SEDANG" in upper:
        return "MEDIUM"
    return "LOW"


def extract_price_score(deepseek_text: str) -> int:
    m = re.search(r'(?:skor|score)[^\d]*(\d{1,2})', deepseek_text, re.IGNORECASE)
    if m:
        return max(1, min(10, int(m.group(1))))
    return 5


def extract_recommendation(deepseek_text: str) -> str:
    m = re.search(
        r'(?:rekomendasi akhir|rekomendasi)[:\s]+(.+?)(?:\n\n|\Z)',
        deepseek_text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1).strip()[:300]
    sentences = [s.strip() for s in deepseek_text.split('.') if s.strip()]
    if len(sentences) >= 2:
        return ". ".join(sentences[-2:])[:300]
    return deepseek_text[-300:] if deepseek_text else ""


def extract_location_from_gemini(gemini_data: dict, gemini_raw: str, text: str) -> str:
    """Extract location hint from Gemini output or raw text."""
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
    return location_hint


def budget_status(price_value: Optional[float]) -> str:
    if price_value is None:
        return "❓ Harga tidak ditemukan"
    if 300_000 <= price_value <= 650_000:
        return f"✅ Rp {price_value:,.0f}/bulan — dalam budget"
    if price_value < 300_000:
        return f"⚠️ Rp {price_value:,.0f}/bulan — sangat murah, waspada"
    return f"❌ Rp {price_value:,.0f}/bulan — di atas budget"


def jarak_status(km: Optional[float]) -> str:
    if km is None:
        return "❓ Jarak belum diketahui"
    if km <= 10:
        return f"✅ {km:.1f} km — dalam radius 10km"
    if km <= 15:
        return f"⚠️ {km:.1f} km — radius 10-15km, agak jauh"
    return f"❌ {km:.1f} km — lebih dari 15km, terlalu jauh"


def normalize_area(location: str) -> str:
    """Extract area/kecamatan name from location string."""
    parts = [p.strip() for p in location.split(",")]
    for part in parts:
        if any(kw in part.lower() for kw in ["jl.", "no.", "kav", "surabaya", "jawa"]):
            continue
        if len(part) >= 4:
            return part
    words = location.split()
    return " ".join(words[:2]) if len(words) >= 2 else location[:30]
