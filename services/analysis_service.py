"""
services/analysis_service.py
Use Case: Full kos listing analysis pipeline.
Orchestrates Gemini + Maps (parallel) + DeepSeek → scoring → persist.
Depends only on domain interfaces — zero knowledge of Telegram, Flask, or Firestore.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from domain.interfaces import (
    AIGateway,
    ListingRepository,
    MapsGateway,
    PreferencesRepository,
)
from domain.models import AnalysisResult, MapsResult, UserPreferences
from domain.scoring import calculate_score
from domain.text_extractors import (
    budget_status,
    extract_fraud_risk,
    extract_links,
    extract_location_from_gemini,
    extract_phone,
    extract_price,
    extract_price_score,
    extract_recommendation,
    jarak_status,
    parse_price_value,
)

log = logging.getLogger("god-eye.analysis-service")


async def _safe(coro, fallback=None, name: str = ""):
    """Run coroutine with 15s timeout. Return fallback on failure (non-fatal)."""
    try:
        return await asyncio.wait_for(coro, timeout=15.0)
    except Exception as exc:
        log.warning("%s failed: %s", name or "safe()", exc)
        return fallback


class AnalysisService:
    """
    Application-level use case: analyze a kos listing end-to-end.
    
    This is the core business orchestrator — it replaces the old
    engine/analyzer.py::full_analysis() monolith while keeping the
    same pipeline stages:
    
    1. Text extraction (phones, prices, links)
    2. Gemini Vision analysis → JSON dict
    3. Maps geocode + Routes + Places + AQI (parallel, safe)
    4. DeepSeek scoring + fraud risk
    5. Composite scoring
    6. Persist to repository
    """

    def __init__(
        self,
        gemini: AIGateway,
        deepseek: AIGateway,
        maps: MapsGateway,
        listing_repo: ListingRepository,
        preferences_repo: PreferencesRepository,
    ) -> None:
        self._gemini = gemini
        self._deepseek = deepseek
        self._maps = maps
        self._listing_repo = listing_repo
        self._preferences_repo = preferences_repo

    async def analyze(
        self,
        text: str = "",
        image_bytes: Optional[bytes] = None,
        source_link: str = "",
        source: str = "manual",
        chat_id: Optional[int] = None,
    ) -> AnalysisResult:
        listing_id = AnalysisResult.new_id()
        phones = extract_phone(text)
        prices = extract_price(text)
        links = extract_links(text)
        phone_str = ", ".join(phones) if phones else "Tidak ditemukan"
        price_str = ", ".join(prices) if prices else "Tidak disebutkan"
        price_val = parse_price_value(prices[0]) if prices else None

        # ── 1. Gemini ────────────────────────────────────────────────────────
        gemini_prompt = (
            f"TEKS POST:\n{text or '(hanya gambar)'}\n\n"
            f"LINK SUMBER: {source_link or '(tidak ada)'}\n\n"
            f"NOMOR KONTAK: {phone_str}\n\n"
            "Analisis kos-kosan ini sesuai instruksi sistem. "
            "Kembalikan JSON lengkap dengan semua field yang diminta."
        )
        gemini_data: dict = await _safe(
            self._gemini.analyze(gemini_prompt, image_bytes),
            fallback={},
            name="Gemini",
        ) or {}
        gemini_raw = gemini_data.get("summary", str(gemini_data)) if gemini_data else ""

        # ── 2. Location extraction ───────────────────────────────────────────
        location_hint = extract_location_from_gemini(gemini_data, gemini_raw, text)

        # ── 3. Maps (parallel, safe) ─────────────────────────────────────────
        maps_result = MapsResult()
        location_query = location_hint or text[:80]
        if location_query.strip():
            maps_result = (
                await _safe(self._maps.full_lookup(location_query), fallback=MapsResult(), name="Maps")
                or MapsResult()
            )

        km_val = self._maps.primary_distance_km(maps_result)

        # ── Load user preferences ────────────────────────────────────────────
        prefs = UserPreferences()
        if chat_id:
            prefs = await _safe(
                self._preferences_repo.get(chat_id), fallback=UserPreferences(), name="Prefs"
            ) or UserPreferences()

        # ── 4. DeepSeek ──────────────────────────────────────────────────────
        nearby_str = "\n".join(
            f"{p.place_type.title()}: {p.name}" for p in maps_result.nearby if p.found
        ) or "Tidak tersedia"

        air_str = "Tidak tersedia"
        if maps_result.air_quality:
            air_str = f"AQI {maps_result.air_quality.aqi} — {maps_result.air_quality.category}"

        jarak_text = f"{km_val:.1f} km" if km_val is not None else "belum diketahui"
        preferred_areas = ", ".join(prefs.preferred_areas) or "belum ada"

        deepseek_prompt = (
            "Kamu adalah konsultan properti sewa + analis keamanan untuk mahasiswa di Surabaya.\n\n"
            f"Teks postingan: {text[:500] if text else '(hanya gambar)'}\n"
            f"Harga: {price_str} | Kontak: {phone_str} | Jarak ke UBAYA: {jarak_text}\n"
            f"Kualitas udara: {air_str}\nFasilitas sekitar (1km):\n{nearby_str}\n"
            f"Preferensi user: area favorit={preferred_areas}, budget max=Rp{prefs.max_price:,}\n\n"
            "Berikan analisis SINGKAT:\n"
            "1. SKOR KEWAJARAN HARGA (1-10)\n"
            "2. RISIKO PENIPUAN (LOW/MEDIUM/HIGH + alasan singkat)\n"
            "3. KEAMANAN LINGKUNGAN malam hari\n"
            "4. REKOMENDASI AKHIR (2 kalimat)\n"
            "Jawab ringkas, poin-poin, Bahasa Indonesia."
        )
        deepseek_raw: str = (
            await _safe(self._deepseek.analyze(deepseek_prompt), fallback="", name="DeepSeek")
            or ""
        )

        fraud_risk = extract_fraud_risk(deepseek_raw)
        price_score = extract_price_score(deepseek_raw)
        recommendation = (
            gemini_data.get("authenticity", {}).get("recommendation")
            or extract_recommendation(deepseek_raw)
        )

        # ── 5. Composite scoring ─────────────────────────────────────────────
        nearby_count = sum(1 for p in maps_result.nearby if p.found)
        score = calculate_score(
            price_value=price_val,
            km=km_val,
            location=location_hint,
            fraud_risk=fraud_risk,
            nearby_count=nearby_count,
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
            budget_status=budget_status(price_val),
            jarak_status=jarak_status(km_val),
        )

        # ── 6. Persist ──────────────────────────────────────────────────────
        try:
            await self._listing_repo.save(result)
        except Exception as exc:
            log.warning("Listing save failed (non-fatal): %s", exc)

        return result
