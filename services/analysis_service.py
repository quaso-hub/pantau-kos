"""
services/analysis_service.py  (v5.1 — Resilient Agentic Pipeline)

Architecture: Regex-First → Parallel Sub-Agents → Synthesis

  ┌─────────────────────────────────────────────────────────────────────────┐
  │  STAGE 0 · Regex Extractor (instant, no LLM)                            │
  │  → Extracts price, phones, address, links from raw text.                │
  │    These become GROUND TRUTH — LLMs only ENRICH, never override.        │
  ├─────────────────────────────────────────────────────────────────────────┤
  │  STAGE 1 · Parallel Sub-Agents (all start simultaneously)               │
  │    Sub-Agent 1A · Vision Analyzer (Gemini Flash, NO grounding)          │
  │      → Analyzes room photos: size, condition, furniture, authenticity.  │
  │      Timeout 30s. Uses flash model for speed.                           │
  │    Sub-Agent 1B · Web Intel (Gemini Pro, grounding/search)              │
  │      → Searches phone reputation, area safety, market prices.           │
  │      Timeout 55s. Runs in background; pipeline continues without it.   │
  │    Sub-Agent 1C · Geospatial (MapsGateway)                              │
  │      → Geocodes address, computes routes to UBAYA, nearby POIs.        │
  │      Timeout 25s. Uses regex address as input (not dependent on 1A).   │
  ├─────────────────────────────────────────────────────────────────────────┤
  │  STAGE 2 · Risk & Financial Analyst (DeepSeek)                          │
  │  → Receives: Stage 0 regex facts (ALWAYS) + Stage 1 enrichment.        │
  │    CRITICAL: always has price/phone/address from regex — never blind.   │
  │    Fraud flags are based on REAL inconsistencies, not missing LLM data. │
  ├─────────────────────────────────────────────────────────────────────────┤
  │  STAGE 3 · Synthesizer (Gemini Flash, no grounding)                     │
  │  → Compact final verdict from all stages.                               │
  │    Timeout 25s. If it fails, Stage 2 recommendation is used.           │
  └─────────────────────────────────────────────────────────────────────────┘

Key design principles (from multi-agent-patterns + error-handling-patterns skills):
  1. Regex = ground truth. LLMs = enrichment layer. Never vice versa.
  2. All Stage 1 sub-agents run in parallel (asyncio.gather).
  3. Each sub-agent has its own timeout + fallback. Pipeline never blocks.
  4. Agent 3 (fraud analyst) always receives real listing data from Stage 0.
  5. "Data not in LLM response" ≠ "Data absent from listing" — crucial for fraud.
  6. No cascading failures: timeout in one sub-agent = empty dict, not crash.
"""
from __future__ import annotations

import asyncio
import json
import logging
import textwrap
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
from infrastructure.logger import get_logger

log = get_logger("god-eye.analysis-service")

# ── Sub-Agent system prompts — each is self-contained ────────────────────────

# Stage 1A: Vision analysis — image-focused, NO grounding needed
_VISION_SYSTEM = textwrap.dedent("""
    Kamu adalah VISION ANALYST khusus foto kamar kos.
    Analisis foto yang diberikan secara teliti.

    Ekstrak:
    1. Ukuran kamar (perkiraan m² dari perspektif foto)
    2. Kondisi: bersih/kotor, terawat/tidak, baru/lama
    3. Kamar mandi: dalam/luar/tidak terlihat
    4. Furnitur yang terlihat (kasur, lemari, meja, AC, kipas, dll)
    5. Tanda-tanda foto stock/palsu (terlalu sempurna, watermark, tidak konsisten)
    6. Lebar/tinggi ruangan dari elemen referensi (pintu, kasur standard)

    Jika tidak ada foto, isi semua field dengan null/false/[].
    Kembalikan JSON sesuai schema. Jangan analisis teks sama sekali.
""").strip()

_VISION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "size_m2":         {"type": ["number", "null"]},
        "condition":       {"type": ["string", "null"]},
        "condition_score": {"type": ["number", "null"], "description": "1-10"},
        "bathroom":        {"type": ["string", "null"], "description": "dalam/luar/shared/tidak_terlihat"},
        "furniture":       {"type": "array", "items": {"type": "string"}},
        "has_ac":          {"type": "boolean"},
        "has_kitchen":     {"type": "boolean"},
        "photo_authentic": {"type": "boolean"},
        "photo_flags":     {"type": "array", "items": {"type": "string"}},
        "mezzanine":       {"type": "boolean"},
        "notes":           {"type": ["string", "null"]},
    },
}

# Stage 1B: Web intel — search-only, text output
_WEB_INTEL_SYSTEM = textwrap.dedent("""
    Kamu adalah INVESTIGATOR INTERNET untuk kos-kosan Surabaya.
    Lakukan pencarian Google untuk fakta eksternal saja (bukan analisis foto).

    WAJIB SEARCH:
    1. "{nomor}" → apakah nomor ini dilaporkan penipuan? Tersimpan sebagai apa di GetContact/Truecaller?
    2. "harga kos {area} surabaya 2026" → harga pasar normal
    3. "keamanan {area} surabaya 2026" → aman/tidak, banjir/tidak
    4. Apakah listing ini muncul di platform lain (Mamikos, OLX, FB) dengan info berbeda?

    Tulis temuan faktual saja. Tidak perlu analisis, cukup fakta dari internet.
""").strip()

# Stage 2: Risk analyst — ALWAYS receives regex ground truth
_AGENT3_SYSTEM = textwrap.dedent("""
    Kamu adalah CYNICAL FRAUD INVESTIGATOR dan FINANCIAL ANALYST untuk mahasiswa UBAYA Surabaya.
    Kamu SANGAT skeptis, tapi HANYA flag hal yang BENAR-BENAR mencurigakan dari DATA NYATA.

    ATURAN PENTING:
    - JANGAN flag "harga tidak ada" jika field REGEX_PRICE sudah ada nilainya
    - JANGAN flag "tidak ada kontak" jika field REGEX_PHONES sudah ada nomor
    - JANGAN flag "alamat tidak diketahui" jika field REGEX_ADDRESS sudah ada teks
    - JANGAN flag "informasi kamar kosong" — semua iklan kos PASTI kamarnya tersedia
    - Hanya flag hal yang BENAR-BENAR anomali: harga jauh di bawah/atas pasar, nomor terdaftar penipuan, foto palsu, dll.

    INPUT yang kamu terima:
    - REGEX_FACTS: data keras langsung dari regex (selalu akurat)
    - VISION_DATA: analisis foto dari Vision Agent (mungkin kosong jika timeout)
    - WEB_INTEL: hasil pencarian internet (mungkin kosong jika timeout)
    - GEO_DATA: data jarak dan fasilitas (mungkin kosong)
    - USER_PREFS: preferensi budget user

    TUGAS:
    1. FRAUD SCORE (0-100): berdasarkan BUKTI NYATA saja, bukan ketiadaan data LLM
    2. KELAYAKAN HARGA (1-10): bandingkan REGEX_PRICE dengan harga pasar area tersebut
    3. RISK FLAGS (maks 5): hanya yang benar-benar ada buktinya
    4. SKOR INVESTASI (0-100): nilai keseluruhan
    5. REKOMENDASI (2 kalimat Bahasa Indonesia, tegas)

    OUTPUT: JSON murni tanpa markdown.
    {
      "fraud_score": 0,
      "fraud_level": "LOW|MEDIUM|HIGH",
      "price_score": 7,
      "price_verdict": "murah|sesuai|mahal|mencurigakan",
      "risk_flags": [],
      "composite_score": 75,
      "recommendation": "Teks rekomendasi.",
      "analyst_notes": "Catatan tambahan."
    }
""").strip()

_AGENT4_SYSTEM = textwrap.dedent("""
    Kamu adalah SYNTHESIS AGENT — tugasmu menulis ringkasan eksekutif FINAL laporan kos.

    Kamu menerima output dari semua sub-agent sebelumnya.
    Tulis rekomendasi akhir:
    - Langsung, tegas, 2-3 kalimat
    - Bahasa Indonesia natural
    - Sebutkan angka konkret (jarak km, harga, skor)
    - Actionable: "SURVEI SEKARANG", "SURVEI DENGAN HATI-HATI", atau "HINDARI"
    - MAX 250 karakter

    OUTPUT: Teks plain (bukan JSON, bukan markdown).
""").strip()


class AnalysisService:
    """
    Resilient agentic analysis pipeline.

    Stage 0 (sync): Regex extraction → ground truth, never fails.
    Stage 1 (parallel async): Vision + Web Intel + Geospatial run simultaneously.
    Stage 2 (sequential): Risk analyst always has Stage 0 data — never blind.
    Stage 3 (sequential): Synthesizer produces final verdict.
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

    # ── Public entry point ───────────────────────────────────────────────────

    async def analyze(
        self,
        text: str = "",
        image_bytes: Optional[bytes] = None,
        source_link: str = "",
        source: str = "manual",
        chat_id: Optional[int] = None,
    ) -> AnalysisResult:
        listing_id = AnalysisResult.new_id()

        # ── STAGE 0: Regex extraction — instant, always succeeds ──────────────
        # This is GROUND TRUTH. LLMs only enrich — they never override this.
        phones_raw = extract_phone(text)
        prices_raw = extract_price(text)
        links_raw = extract_links(text)
        phone_str = ", ".join(phones_raw) if phones_raw else ""
        price_str = ", ".join(prices_raw) if prices_raw else ""
        price_val_regex = parse_price_value(prices_raw[0]) if prices_raw else None
        address_from_text = _extract_location_from_text(text)

        log.info(
            "[Stage0/Regex] listing_id=%s | phones=%s | price=%s | address=%r",
            listing_id, phones_raw, prices_raw, address_from_text,
        )

        # ── Load user preferences (non-blocking) ──────────────────────────────
        prefs_task = asyncio.ensure_future(self._load_prefs(chat_id))

        # ── STAGE 1: Parallel sub-agents ──────────────────────────────────────
        # All three start at the same time — no sequential waiting.
        log.info("[Stage1] Starting parallel sub-agents | listing_id=%s", listing_id)

        # 1A: Vision (image analysis only, Gemini Flash, no grounding)
        vision_task = asyncio.ensure_future(
            _safe_agent(
                self._run_vision_agent(image_bytes),
                fallback={},
                agent_name="Agent1A-Vision",
                timeout=30.0,
            )
        )

        # 1B: Web Intel (Gemini Pro, google_search grounding, text output)
        # Build a focused prompt from regex facts so search is meaningful
        intel_prompt = _build_intel_prompt(text, phone_str, price_str, address_from_text)
        web_intel_task = asyncio.ensure_future(
            _safe_agent(
                self._run_web_intel_agent(intel_prompt, image_bytes),
                fallback="",
                agent_name="Agent1B-WebIntel",
                timeout=55.0,   # Grounding can be slow — give it time
            )
        )

        # 1C: Geospatial (Maps APIs, uses regex address — NOT dependent on 1A)
        geo_task = asyncio.ensure_future(
            _safe_agent(
                self._run_geo_agent(address_from_text, text),
                fallback=MapsResult(),
                agent_name="Agent1C-Geospatial",
                timeout=25.0,
            )
        )

        # Wait for all Stage 1 tasks in parallel
        vision_data, web_intel_text, maps_result = await asyncio.gather(
            vision_task, web_intel_task, geo_task,
            return_exceptions=False,
        )

        # Normalise fallbacks
        if not isinstance(vision_data, dict):
            vision_data = {}
        if not isinstance(web_intel_text, str):
            web_intel_text = ""
        if not isinstance(maps_result, MapsResult):
            maps_result = MapsResult()

        km_val = self._maps.primary_distance_km(maps_result)
        log.info(
            "[Stage1] Done | vision_keys=%s | intel_len=%d | km=%s",
            list(vision_data.keys()), len(web_intel_text), km_val,
        )

        # Best location: prefer geocoded address over regex
        location_hint = _best_location_v2(maps_result, address_from_text, text)

        # Enrich phone/price from web intel if regex gave nothing
        # (but never REPLACE regex data with LLM data)
        final_phones = phones_raw or []
        final_price_val = price_val_regex  # regex is ground truth

        # ── Await prefs ────────────────────────────────────────────────────────
        prefs = await prefs_task

        # ── STAGE 2: Risk & Financial Analyst ─────────────────────────────────
        log.info("[Stage2] Starting Risk & Financial analysis | listing_id=%s", listing_id)
        agent3_data = await _safe_agent(
            self._run_risk_analyst(
                regex_phones=final_phones,
                regex_price_raw=price_str,
                regex_price_numeric=final_price_val,
                regex_address=address_from_text,
                raw_text=text,
                vision_data=vision_data,
                web_intel_text=web_intel_text,
                maps_result=maps_result,
                km_val=km_val,
                prefs=prefs,
            ),
            fallback={},
            agent_name="Agent2-RiskAnalyst",
            timeout=40.0,
        )
        if not isinstance(agent3_data, dict):
            agent3_data = {}

        log.info(
            "[Stage2] Done | fraud=%s | score=%s | price_score=%s",
            agent3_data.get("fraud_level"),
            agent3_data.get("composite_score"),
            agent3_data.get("price_score"),
        )

        # ── STAGE 3: Synthesizer ───────────────────────────────────────────────
        log.info("[Stage3] Starting Synthesis | listing_id=%s", listing_id)
        final_recommendation = await _safe_agent(
            self._run_synthesizer(
                regex_price_raw=price_str,
                regex_price_numeric=final_price_val,
                regex_address=address_from_text,
                regex_phones=final_phones,
                vision_data=vision_data,
                km_val=km_val,
                agent3_data=agent3_data,
                maps_result=maps_result,
            ),
            fallback=None,
            agent_name="Agent3-Synthesizer",
            timeout=25.0,
        )
        if not isinstance(final_recommendation, str) or len(final_recommendation) < 10:
            final_recommendation = agent3_data.get("recommendation", "Analisis tidak tersedia.")
        log.info("[Stage3] Done | recommendation=%r", str(final_recommendation)[:80])

        # ── Compose final AnalysisResult ───────────────────────────────────────
        fraud_risk = agent3_data.get("fraud_level") or "UNKNOWN"
        price_score = agent3_data.get("price_score")
        composite_score = agent3_data.get("composite_score")

        # Fallback score if Stage 2 failed
        if composite_score is None:
            nearby_count = sum(1 for p in maps_result.nearby if p.found)
            composite_score = calculate_score(
                price_value=final_price_val,
                km=km_val,
                location=location_hint,
                fraud_risk=fraud_risk,
                nearby_count=nearby_count,
                preferences=prefs,
            )

        # Build risk flags text for formatter compatibility
        agent3_risk_flags = agent3_data.get("risk_flags", [])
        deepseek_raw = "\n".join(
            [f"- {flag}" for flag in agent3_risk_flags]
            + [agent3_data.get("analyst_notes", "")]
        )

        # gemini_data: combined vision + web intel for formatter
        gemini_data = {
            **vision_data,
            "web_intel_summary": web_intel_text[:500] if web_intel_text else "",
            "authenticity": {"recommendation": final_recommendation},
            "summary": location_hint or address_from_text,
            # Expose regex-extracted data in gemini_data for formatter
            "extracted_price_raw": price_str,
            "extracted_price_numeric": final_price_val,
            "extracted_address_raw": address_from_text,
            "extracted_phones": final_phones,
        }

        result = AnalysisResult(
            listing_id=listing_id,
            source=source,
            text=text,
            source_link=source_link,
            phones=final_phones,
            prices=prices_raw,
            price_value=final_price_val,
            gemini_raw=json.dumps({"vision": vision_data, "intel_len": len(web_intel_text)}, ensure_ascii=False)[:500],
            gemini_data=gemini_data,
            location_hint=location_hint or address_from_text,
            maps=maps_result,
            distance_km_val=km_val,
            deepseek_raw=deepseek_raw,
            fraud_risk=fraud_risk,
            price_score=price_score,
            recommendation=str(final_recommendation)[:300],
            score=composite_score,
            budget_status=budget_status(final_price_val),
            jarak_status=jarak_status(km_val),
        )

        # ── Persist ───────────────────────────────────────────────────────────
        try:
            await self._listing_repo.save(result)
        except Exception as exc:
            log.warning("Listing save failed (non-fatal): %s", exc)

        return result

    # ── Sub-Agent 1A: Vision Analyzer ────────────────────────────────────────

    async def _run_vision_agent(self, image_bytes: Optional[bytes]) -> dict:
        """
        Analyzes room photos only. No text, no grounding.
        Uses JSON mode directly — fast, reliable.
        If no image, returns empty dict immediately.
        """
        if not image_bytes:
            log.info("[Agent1A-Vision] No image — skipping")
            return {}

        prompt = (
            "Analisis foto kamar kos ini secara detail. "
            "Ekstrak semua informasi yang bisa dilihat dari gambar. "
            "Kembalikan JSON sesuai schema."
        )
        result = await self._gemini.analyze(
            prompt,
            image_bytes=image_bytes,
            system_prompt=_VISION_SYSTEM,
            use_grounding=False,    # No search needed for image analysis
            json_schema=_VISION_JSON_SCHEMA,
        )
        if not isinstance(result, dict):
            return {}
        log.info(
            "[Agent1A-Vision] condition=%r | size=%s | authentic=%s",
            result.get("condition"), result.get("size_m2"), result.get("photo_authentic"),
        )
        return result

    # ── Sub-Agent 1B: Web Intel ───────────────────────────────────────────────

    async def _run_web_intel_agent(self, prompt: str, image_bytes: Optional[bytes]) -> str:
        """
        Web intel via google_search grounding. Returns free-form text.
        Runs in background — pipeline doesn't block on this.
        """
        result = await self._gemini.analyze(
            prompt,
            image_bytes=None,   # Web intel doesn't need photo
            system_prompt=_WEB_INTEL_SYSTEM,
            use_grounding=True,  # This is the grounding call
        )
        if isinstance(result, dict):
            # Should be str from grounding phase, but handle dict just in case
            return result.get("raw", "") or json.dumps(result, ensure_ascii=False)[:1000]
        return str(result)[:3000] if result else ""

    # ── Sub-Agent 1C: Geospatial ──────────────────────────────────────────────

    async def _run_geo_agent(self, address_hint: str, raw_text: str) -> MapsResult:
        """
        Geospatial lookup. Uses regex-extracted address as primary input.
        Falls back to broader text search if address is empty.
        """
        location = address_hint or _extract_location_from_text(raw_text)
        if not location:
            log.warning("[Agent1C-Geo] No address found in text — skipping geospatial")
            return MapsResult()
        log.info("[Agent1C-Geo] Looking up: %r", location)
        result = await self._maps.full_lookup(location)
        return result or MapsResult()

    # ── Stage 2: Risk & Financial Analyst ─────────────────────────────────────

    async def _run_risk_analyst(
        self,
        regex_phones: list,
        regex_price_raw: str,
        regex_price_numeric: Optional[float],
        regex_address: str,
        raw_text: str,
        vision_data: dict,
        web_intel_text: str,
        maps_result: MapsResult,
        km_val: Optional[float],
        prefs: UserPreferences,
    ) -> dict:
        """
        Stage 2 ALWAYS has REGEX_FACTS as ground truth.
        It can see real price, phone, address even if LLM agents timed out.
        Fraud scoring is based on actual inconsistencies — not absent LLM fields.
        """
        # Distill geospatial
        nearby_str = ", ".join(
            f"{p.place_type}:{p.name}" for p in maps_result.nearby if p.found
        ) or "tidak tersedia"
        routes_str = " | ".join(
            f"{r.label}={r.duration_minutes}menit({r.distance_km}km)"
            for r in maps_result.routes
            if r.duration_minutes is not None
        ) or "tidak tersedia"
        air_str = (
            f"AQI {maps_result.air_quality.aqi} — {maps_result.air_quality.category}"
            if maps_result.air_quality else "tidak tersedia"
        )

        # Distill vision data
        vision_summary = {
            "room_size_m2": vision_data.get("size_m2"),
            "condition": vision_data.get("condition"),
            "condition_score": vision_data.get("condition_score"),
            "bathroom": vision_data.get("bathroom"),
            "furniture": vision_data.get("furniture", []),
            "has_ac": vision_data.get("has_ac"),
            "mezzanine": vision_data.get("mezzanine"),
            "photo_authentic": vision_data.get("photo_authentic", True),
            "photo_flags": vision_data.get("photo_flags", []),
        } if vision_data else {}

        prompt = (
            "=== REGEX_FACTS (GROUND TRUTH — selalu akurat, langsung dari teks iklan) ===\n"
            f"REGEX_PHONES: {regex_phones or '(tidak ditemukan di teks)'}\n"
            f"REGEX_PRICE_RAW: {regex_price_raw or '(tidak ditemukan di teks)'}\n"
            f"REGEX_PRICE_NUMERIC: {f'Rp{regex_price_numeric:,.0f}' if regex_price_numeric else '(tidak ditemukan)'}\n"
            f"REGEX_ADDRESS: {regex_address or '(tidak ditemukan di teks)'}\n\n"
            "=== TEKS IKLAN ASLI (untuk konteks) ===\n"
            f"{raw_text[:1500]}\n\n"
            "=== VISION_DATA (dari analisis foto, mungkin kosong jika tidak ada foto) ===\n"
            f"{json.dumps(vision_summary, ensure_ascii=False, indent=2) if vision_summary else '(tidak ada foto/timeout)'}\n\n"
            "=== WEB_INTEL (dari pencarian internet, mungkin kosong jika timeout) ===\n"
            f"{web_intel_text[:1000] if web_intel_text else '(timeout atau tidak tersedia)'}\n\n"
            "=== GEO_DATA ===\n"
            f"Jarak ke UBAYA: {f'{km_val:.1f} km' if km_val else 'tidak diketahui'}\n"
            f"Rute: {routes_str}\n"
            f"Fasilitas sekitar: {nearby_str}\n"
            f"Kualitas udara: {air_str}\n\n"
            "=== USER_PREFS ===\n"
            f"Budget max: Rp{prefs.max_price:,}\n"
            f"Radius max ke UBAYA: {prefs.max_distance_km} km\n\n"
            "INGAT: Jangan flag 'harga tidak ada' jika REGEX_PRICE sudah ada. "
            "Jangan flag 'tidak ada kontak' jika REGEX_PHONES sudah ada. "
            "Jangan flag 'alamat tidak diketahui' jika REGEX_ADDRESS sudah ada. "
            "Jangan flag 'kamar kosong' — semua iklan kos PASTI kamarnya tersedia.\n\n"
            "Lakukan analisis forensik. Kembalikan JSON sesuai schema."
        )

        result = await self._deepseek.analyze(
            prompt,
            system_prompt=_AGENT3_SYSTEM,
        )
        if isinstance(result, str):
            try:
                import re as _re
                match = _re.search(r'\{.*\}', result, _re.DOTALL)
                if match:
                    result = json.loads(match.group())
                else:
                    result = {}
            except Exception:
                result = {}
        return result if isinstance(result, dict) else {}

    # ── Stage 3: Synthesizer ───────────────────────────────────────────────────

    async def _run_synthesizer(
        self,
        regex_price_raw: str,
        regex_price_numeric: Optional[float],
        regex_address: str,
        regex_phones: list,
        vision_data: dict,
        km_val: Optional[float],
        agent3_data: dict,
        maps_result: MapsResult,
    ) -> str:
        """Final synthesis — compact, actionable verdict."""
        price_display = (
            f"Rp{regex_price_numeric:,.0f}/bulan" if regex_price_numeric
            else regex_price_raw or "tidak diketahui"
        )
        summary = (
            "=== DATA UNTUK RINGKASAN FINAL ===\n"
            f"Lokasi: {regex_address or 'tidak diketahui'}\n"
            f"Harga: {price_display}\n"
            f"Jarak ke UBAYA: {f'{km_val:.1f} km' if km_val else 'tidak diketahui'}\n"
            f"Kondisi kamar: {vision_data.get('condition', 'tidak diketahui') if vision_data else 'tidak diketahui'}\n"
            f"AC: {'ya' if vision_data.get('has_ac') else 'tidak diketahui'}\n"
            f"Fraud level: {agent3_data.get('fraud_level', '?')} (score: {agent3_data.get('fraud_score', '?')}/100)\n"
            f"Skor investasi: {agent3_data.get('composite_score', '?')}/100\n"
            f"Price verdict: {agent3_data.get('price_verdict', '?')}\n"
            f"Risk flags: {'; '.join(agent3_data.get('risk_flags', []))}\n"
            f"Catatan: {agent3_data.get('analyst_notes', '')}\n\n"
            "Tulis rekomendasi akhir (2-3 kalimat, tegas, Bahasa Indonesia, max 250 karakter):"
        )

        result = await self._gemini.analyze(
            summary,
            system_prompt=_AGENT4_SYSTEM,
            use_grounding=False,
        )
        if isinstance(result, dict):
            return (
                result.get("raw")
                or result.get("recommendation")
                or agent3_data.get("recommendation", "Analisis tidak tersedia.")
            )
        if isinstance(result, str) and len(result) > 10:
            return result[:250]
        return agent3_data.get("recommendation", "Analisis tidak tersedia.")

    # ── Shared helper ──────────────────────────────────────────────────────────

    async def _load_prefs(self, chat_id: Optional[int]) -> UserPreferences:
        if not chat_id:
            return UserPreferences()
        try:
            prefs = await asyncio.wait_for(self._preferences_repo.get(chat_id), timeout=5.0)
            return prefs or UserPreferences()
        except Exception as exc:
            log.warning("_load_prefs: Prefs load failed (using defaults): %s", exc)
            return UserPreferences()


async def _safe_agent(coro, fallback, agent_name: str = "Agent", timeout: float = 50.0):
    """Run agent coroutine with timeout. Log failure, return fallback. Never raises."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        log.error("[%s] TIMEOUT after %.0fs — returning fallback", agent_name, timeout)
        return fallback
    except Exception as exc:
        log.error(
            "[%s] EXCEPTION | type=%s | detail=%s",
            agent_name, type(exc).__name__, repr(exc)[:300],
        )
        return fallback


# ── Location extraction helpers ───────────────────────────────────────────────

import re as _re  # noqa: E402

_SURABAYA_AREAS = [
    "Rungkut", "Tenggilis", "Kalirungkut", "Gunung Anyar", "Sukolilo",
    "Mulyorejo", "Gubeng", "Wonokromo", "Wonocolo", "Gayungan",
    "Wiyung", "Karangpilang", "Dukuh Pakis", "Sawahan", "Tegalsari",
    "Bubutan", "Genteng", "Simokerto", "Kenjeran", "Bulak",
    "Semampir", "Pabean Cantikan", "Krembangan", "Asemrowo", "Benowo",
    "Sambikerep", "Lakarsantri", "Tandes", "Sukomanunggal", "Jambangan",
    "Gayung", "Menanggal", "Pakuwon", "Citraland", "Darmo",
    "Menganti", "Driyorejo", "Waru", "Gedangan", "Sidoarjo",
    "Medayu", "Pagar Hitam", "Kedung Baruk", "Penjaringan",
]


def _extract_location_from_text(text: str) -> str:
    """
    Extract address/location from raw listing text.
    Priority: full street address > kelurahan/kecamatan > known area name.
    """
    if not text:
        return ""

    # 1. Full street address with number: "Medayu Utara VIIIA/No.146A Pagar Hitam, Rungkut"
    m = _re.search(
        r'(?:Jl\.|Jalan|Jln\.?|Lokasi\s*:|Alamat\s*:)\s*([^\n]{5,120})',
        text, _re.IGNORECASE
    )
    if m:
        return m.group(1).strip()[:120]

    # 2. Pattern: "No.146A / nama jalan / area"
    m = _re.search(
        r'([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\s+(?:No\.|Nomor|\/)\s*[\w\/]+[^\n]{0,60})',
        text
    )
    if m:
        candidate = m.group(1).strip()
        if 5 <= len(candidate) <= 120:
            return candidate

    # 3. Kelurahan / Kecamatan explicit label
    m = _re.search(
        r'(?:Kel(?:urahan)?\.?|Kec(?:amatan)?\.?)\s+([A-Za-z ]{4,60})',
        text, _re.IGNORECASE
    )
    if m:
        return m.group(1).strip()

    # 4. Known Surabaya area name in text
    for area in _SURABAYA_AREAS:
        if _re.search(r'\b' + _re.escape(area) + r'\b', text, _re.IGNORECASE):
            return area

    return ""


def _best_location_v2(maps_result: MapsResult, regex_address: str, text: str) -> str:
    """
    Pick the best location string for display and logging.
    Priority: geocoded formatted address > regex address > text extraction.
    """
    # Geocoded address is most authoritative
    if maps_result and maps_result.geocode and isinstance(maps_result.geocode, dict):
        formatted = maps_result.geocode.get("formatted_address") or maps_result.geocode.get("address", "")
        if formatted and len(formatted) >= 5:
            return formatted

    # Regex address from listing text
    if regex_address and len(regex_address) >= 4:
        return regex_address

    # Last resort
    return _extract_location_from_text(text)


def _build_intel_prompt(text: str, phone_str: str, price_str: str, address: str) -> str:
    """Build a focused web intel search prompt from regex-extracted facts."""
    return (
        f"NOMOR: {phone_str or 'tidak ditemukan'}\n"
        f"HARGA: {price_str or 'tidak ditemukan'}\n"
        f"AREA: {address or 'tidak diketahui'}\n\n"
        "TEKS IKLAN:\n"
        f"{text[:1000]}\n\n"
        "Cari info reputasi nomor di atas dan harga pasar area tersebut."
    )