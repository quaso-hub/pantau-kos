"""
services/analysis_service.py  (v4.1 — Multi-Agent Chain)

4-Agent orchestration pipeline:

  ┌─────────────────────────────────────────────────────────────────────────┐
  │  Agent 1 · Vision & Extractor (Gemini)                                  │
  │  → Extracts hard facts from image+text: price, phones, address,         │
  │    room specs, fraud signals. Returns structured JSON.                   │
  ├─────────────────────────────────────────────────────────────────────────┤
  │  Agent 2 · Geospatial Evaluator (MapsGateway)                           │
  │  → Takes Agent 1's address, runs geocode + routes + places + AQI.      │
  │    Returns exact distances and routing viability.                        │
  ├─────────────────────────────────────────────────────────────────────────┤
  │  Agent 3 · Risk & Financial Analyst (DeepSeek) — cynical fraud investigator │
  │  → Receives Agent 1 facts + Agent 2 geospatial data + user prefs.      │
  │    Evaluates budget, flags inconsistencies, assigns 0-100 score.        │
  ├─────────────────────────────────────────────────────────────────────────┤
  │  Agent 4 · Synthesizer (Gemini lightweight)                              │
  │  → Receives all context from Agents 1-3.                                │
  │    Formats final narrative recommendation + verdict.                    │
  └─────────────────────────────────────────────────────────────────────────┘

Key pattern from multi-agent-patterns skill:
- Each agent operates in a CLEAN, isolated context window.
- Agents do NOT share chat history — they receive exactly what they need.
- Agent 1 & 2 run in parallel where possible.
- Agent 3 waits for both 1 & 2 before starting (depends on geospatial).
- Agent 4 waits for 3 (full synthesis).
- Context isolation prevents the "lost-in-middle" degradation of a monolith.
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

log = logging.getLogger("god-eye.analysis-service")

# ── Agent system prompts — each is self-contained ────────────────────────────

_AGENT1_SYSTEM = textwrap.dedent("""
    Kamu adalah INVESTIGATOR kos-kosan Surabaya. Lakukan pencarian Google untuk:

    1. Nomor telepon dari iklan — SEARCH: "{nomor} getcontact penipuan kos surabaya"
       - Tersimpan sebagai apa di GetContact/Truecaller? Ada laporan penipuan?

    2. Nama jalan/kelurahan — verifikasi keberadaan di Surabaya

    3. Harga pasar kos di area tersebut — SEARCH: "harga kos {kelurahan} surabaya 2026"
       - Kisaran harga normal vs harga di iklan

    4. Reputasi area — SEARCH: "keamanan {area} surabaya 2026"
       - Aman pulang malam? Risiko banjir?

    5. Listing di platform lain — ada di Mamikos/OLX/Facebook dengan info berbeda?

    Analisis juga foto yang dikirimkan (jika ada):
    - Ukuran kamar, kondisi, kamar mandi dalam/luar, furnitur
    - Foto asli atau stock photo?

    Tulis SEMUA temuan dalam teks bebas yang lengkap dan faktual.
    Jika tidak ada data, tulis "Tidak ditemukan."
""").strip()

_AGENT3_SYSTEM = textwrap.dedent("""
    Kamu adalah CYNICAL FRAUD INVESTIGATOR dan FINANCIAL ANALYST untuk mahasiswa UBAYA Surabaya.
    Kamu SANGAT skeptis. Kamu selalu mengasumsikan iklan berpotensi penipuan sampai terbukti sebaliknya.
    Bias kamu: melindungi mahasiswa dari kehilangan uang sewa.

    INPUT yang akan kamu terima:
    - FACTS dari Vision Agent (Agent 1): fakta keras dari iklan
    - GEOSPATIAL dari Maps Agent (Agent 2): jarak, rute, fasilitas sekitar
    - USER PREFS: preferensi dan budget user

    TUGAS:
    1. FRAUD SCORE (0-100, makin tinggi makin curiga):
       Pertimbangkan: harga vs pasar, foto autentik/tidak, nomor phone intel,
       template scammer, akun baru, duplikat foto, inkonsistensi info.

    2. KELAYAKAN HARGA:
       Bandingkan harga dengan pasar (dari fakta Agent 1 + pengetahuanmu).
       Berikan skor 1-10 (10 = sangat murah untuk kualitasnya).

    3. RISK FLAGS (maksimal 5, paling kritis):
       Setiap flag: teks singkat < 100 karakter, actionable.

    4. SKOR AKHIR (0-100):
       Nilai investasi/keputusan menyewa. 100 = sempurna.
       Pertimbangkan: jarak, harga, fasilitas, fraud risk, keamanan area.

    5. REKOMENDASI (2 kalimat, Bahasa Indonesia):
       Kesimpulan langsung: apakah layak survei?

    OUTPUT: JSON murni tanpa markdown.
    {
      "fraud_score": 0,
      "fraud_level": "LOW|MEDIUM|HIGH",
      "price_score": 7,
      "price_verdict": "murah|sesuai|mahal|mencurigakan",
      "risk_flags": [],
      "composite_score": 75,
      "recommendation": "Teks rekomendasi.",
      "analyst_notes": "Catatan tambahan investigator."
    }
""").strip()

_AGENT4_SYSTEM = textwrap.dedent("""
    Kamu adalah SYNTHESIS AGENT — tugasmu adalah menulis ringkasan eksekutif FINAL
    dari laporan intelijen kos-kosan.

    Kamu menerima output dari 3 agent sebelumnya:
    - Agent 1 (Vision & Extractor): fakta keras
    - Agent 2 (Geospatial): data jarak dan fasilitas
    - Agent 3 (Risk & Financial Analyst): skor risiko dan rekomendasi

    Tugas: Tulis rekomendasi akhir yang:
    - Langsung, tegas, 2-3 kalimat
    - Bahasa Indonesia natural
    - Menyebutkan angka konkret (jarak km, harga, skor)
    - Actionable: harus jelas apakah "SURVEI SEKARANG", "SURVEI DENGAN HATI-HATI", atau "HINDARI"

    OUTPUT: Teks plain (bukan JSON, bukan markdown), maksimal 250 karakter.
""").strip()


class AnalysisService:
    """
    Multi-Agent analysis pipeline — 4 specialized agents chained in sequence.

    Pattern: Supervisor/Orchestrator (this class) → specialist agents.
    Context isolation: each agent receives only what it needs, not full history.
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

        # Pre-extract phones/prices/links from raw text (fast, no LLM needed)
        phones_raw = extract_phone(text)
        prices_raw = extract_price(text)
        links_raw = extract_links(text)
        phone_str = ", ".join(phones_raw) if phones_raw else "Tidak ditemukan"
        price_str = ", ".join(prices_raw) if prices_raw else "Tidak disebutkan"
        price_val_raw = parse_price_value(prices_raw[0]) if prices_raw else None

        # Load user preferences (parallel with agents, non-blocking)
        prefs_task = asyncio.ensure_future(self._load_prefs(chat_id))

        # ── Agent 1: Vision & Extractor ──────────────────────────────────────
        # PERFORMANCE: start Agent1 AND Agent2 in parallel.
        # Agent2 launches immediately with the best location hint we can derive
        # from raw text alone (no LLM). Once Agent1 returns, if it produced a
        # better address we re-run Agent2 with the improved hint.
        log.info("[Agent1] Starting Vision & Extraction | listing_id=%s", listing_id)

        # Best-effort location from raw text — used as Agent2 early hint
        text_location_hint = _extract_location_from_text(text)
        log.info("[Agent2-early] Using text hint: %r", text_location_hint)

        agent1_task = asyncio.ensure_future(
            self._run_agent1(text, image_bytes, source_link, phone_str, price_str)
        )
        # Fire Agent2 in parallel ONLY if we have a usable hint
        if text_location_hint:
            agent2_early_task = asyncio.ensure_future(self._run_agent2(text_location_hint))
        else:
            agent2_early_task = None

        # Wait for Agent1 to finish
        agent1_data = await agent1_task

        log.info("[Agent1] Done | address_raw=%r | flags=%s",
                 agent1_data.get("extracted_address_raw", ""),
                 agent1_data.get("raw_red_flags", []))

        # Extract the best location hint now that Agent1 has finished
        location_hint = _best_location(agent1_data, text)

        # Decide whether to use early Agent2 result or re-run with better hint
        if agent2_early_task is not None and not location_hint:
            # No better hint from Agent1 — just wait for the early run
            maps_result = await agent2_early_task
        elif location_hint and _hints_differ(location_hint, text_location_hint):
            # Agent1 gave a significantly better address — re-run Agent2 with it
            if agent2_early_task is not None and not agent2_early_task.done():
                agent2_early_task.cancel()   # cancel the stale early run
            log.info("[Agent2] Re-running with Agent1 address: %r", location_hint)
            maps_result = await self._run_agent2(location_hint)
        elif agent2_early_task is not None:
            # Same or similar hint — reuse the early parallel result
            maps_result = await agent2_early_task
        else:
            # No hint at all — run Agent2 now with whatever we have
            log.warning("[Agent2] No location hint from text or Agent1 — trying raw text")
            maps_result = await self._run_agent2(location_hint or text[:120])

        km_val = self._maps.primary_distance_km(maps_result)
        log.info("[Agent2] Done | km=%s | nearby=%d | geocode=%s",
                 km_val, sum(1 for p in maps_result.nearby if p.found),
                 bool(maps_result.geocode))

        # Agent 1 may provide better price/phone data
        phone_str_a1 = (
            ", ".join(agent1_data.get("extracted_phones", []))
            or phone_str
        )
        price_val = (
            agent1_data.get("extracted_price_numeric")
            or price_val_raw
        )

        # ── Await prefs (should be ready by now) ──────────────────────────────
        prefs = await prefs_task

        # ── Agent 3: Risk & Financial Analyst ─────────────────────────────────
        log.info("[Agent3] Starting Risk & Financial analysis")
        agent3_data = await self._run_agent3(
            agent1_data=agent1_data,
            maps_result=maps_result,
            km_val=km_val,
            prefs=prefs,
            text=text,
        )
        log.info("[Agent3] Done | fraud=%s | score=%s | price_score=%s",
                 agent3_data.get("fraud_level"),
                 agent3_data.get("composite_score"),
                 agent3_data.get("price_score"))

        # ── Agent 4: Synthesizer ───────────────────────────────────────────────
        log.info("[Agent4] Starting Synthesis")
        final_recommendation = await self._run_agent4(
            agent1_data=agent1_data,
            maps_result=maps_result,
            km_val=km_val,
            agent3_data=agent3_data,
        )
        log.info("[Agent4] Done | recommendation=%r", final_recommendation[:80])

        # ── Compose final AnalysisResult ───────────────────────────────────────
        fraud_risk = agent3_data.get("fraud_level") or "UNKNOWN"
        price_score = agent3_data.get("price_score")
        composite_score = agent3_data.get("composite_score")

        # Fallback: re-calculate score if Agent 3 didn't return one
        nearby_count = sum(1 for p in maps_result.nearby if p.found)
        if composite_score is None:
            composite_score = calculate_score(
                price_value=price_val,
                km=km_val,
                location=location_hint,
                fraud_risk=fraud_risk,
                nearby_count=nearby_count,
                preferences=prefs,
            )

        # Build deepseek_raw from Agent 3 for backward-compat with formatter
        agent3_risk_flags = agent3_data.get("risk_flags", [])
        deepseek_raw = "\n".join(
            [f"- {flag}" for flag in agent3_risk_flags]
            + [agent3_data.get("analyst_notes", "")]
        )

        # gemini_data from Agent 1 for backward-compat with formatter
        gemini_data = {
            **agent1_data,
            "authenticity": {
                "recommendation": final_recommendation,
            },
            # map to old keys formatter expects
            "summary": agent1_data.get("extracted_address_raw", ""),
        }

        result = AnalysisResult(
            listing_id=listing_id,
            source=source,
            text=text,
            source_link=source_link,
            phones=phones_raw or agent1_data.get("extracted_phones", []),
            prices=prices_raw,
            price_value=price_val,
            gemini_raw=json.dumps(agent1_data, ensure_ascii=False)[:500],
            gemini_data=gemini_data,
            location_hint=location_hint,
            maps=maps_result,
            distance_km_val=km_val,
            deepseek_raw=deepseek_raw,
            fraud_risk=fraud_risk,
            price_score=price_score,
            recommendation=final_recommendation,
            score=composite_score,
            budget_status=budget_status(price_val),
            jarak_status=jarak_status(km_val),
        )

        # ── Persist ───────────────────────────────────────────────────────────
        try:
            await self._listing_repo.save(result)
        except Exception as exc:
            log.warning("Listing save failed (non-fatal): %s", exc)

        return result

    # ── Agent 1: Vision & Extractor ──────────────────────────────────────────

    async def _run_agent1(
        self,
        text: str,
        image_bytes: Optional[bytes],
        source_link: str,
        phone_str: str,
        price_str: str,
    ) -> dict:
        """
        Agent 1 context window contains ONLY:
        - System prompt defining its extraction role
        - Raw listing text + detected phones/prices
        - Image bytes if available
        Clean context = focused extraction without noise.
        """
        prompt = (
            f"TEKS IKLAN:\n{text[:2000] if text else '(hanya gambar)'}\n\n"
            f"LINK SUMBER: {source_link or '(tidak ada)'}\n"
            f"NOMOR TERDETEKSI (regex): {phone_str}\n"
            f"HARGA TERDETEKSI (regex): {price_str}\n\n"
            "Ekstrak semua fakta keras dari iklan ini. Kembalikan JSON sesuai schema."
        )

        # Temporarily swap system prompt for Agent 1's focused role
        # use_thinking=False: extraction doesn't need deep reasoning — saves 15-20s
        result = await _safe_agent(
            self._gemini.analyze(
                prompt,
                image_bytes,
                system_prompt=_AGENT1_SYSTEM,
                use_grounding=True,
                use_thinking=False,    # FAST: extraction only, no thinking needed
            ),
            fallback={},
            agent_name="Agent1-Vision",
            timeout=45.0,
        )
        if not isinstance(result, dict):
            return {}
        return result

    # ── Agent 2: Geospatial Evaluator ─────────────────────────────────────────

    async def _run_agent2(self, location_hint: str) -> MapsResult:
        """
        Agent 2 context is the Maps APIs — not an LLM.
        Takes Agent 1's address output, returns structured geospatial data.
        """
        if not location_hint or not location_hint.strip():
            log.warning("[Agent2] No location hint — skipping geospatial lookup")
            return MapsResult()
        result = await _safe_agent(
            self._maps.full_lookup(location_hint),
            fallback=MapsResult(),
            agent_name="Agent2-Geospatial",
            timeout=25.0,   # Maps APIs are fast; 25s is plenty
        )
        return result or MapsResult()

    # ── Agent 3: Risk & Financial Analyst ─────────────────────────────────────

    async def _run_agent3(
        self,
        agent1_data: dict,
        maps_result: MapsResult,
        km_val: Optional[float],
        prefs: UserPreferences,
        text: str,
    ) -> dict:
        """
        Agent 3 context window contains ONLY:
        - System prompt: cynical fraud investigator role
        - Distilled facts from Agent 1 (NOT raw listing text)
        - Distilled geospatial from Agent 2 (NOT full MapsResult object)
        - User preferences
        Context isolation: Agent 3 never sees original listing text.
        """
        # Distill Agent 1 into compact facts (avoid token bloat)
        a1_facts = {
            "price_raw": agent1_data.get("extracted_price_raw", "tidak ada"),
            "price_numeric": agent1_data.get("extracted_price_numeric"),
            "phones": agent1_data.get("extracted_phones", []),
            "address": agent1_data.get("extracted_address_raw", "tidak diketahui"),
            "room_condition": agent1_data.get("room", {}).get("condition", "tidak_diketahui"),
            "room_size_m2": agent1_data.get("room", {}).get("size_m2"),
            "bathroom": agent1_data.get("room", {}).get("bathroom", "tidak_terlihat"),
            "furniture": agent1_data.get("room", {}).get("furniture", []),
            "photo_authentic": agent1_data.get("room", {}).get("photo_authentic", True),
            "photo_flags": agent1_data.get("room", {}).get("photo_flags", []),
            "phone_intel": agent1_data.get("phone_intel", {}),
            "listing_intel": agent1_data.get("listing_intel", {}),
            "red_flags_raw": agent1_data.get("raw_red_flags", []),
        }

        # Distill Agent 2 geospatial
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
        a2_geo = {
            "distance_to_ubaya_km": km_val,
            "routes": routes_str,
            "nearby_facilities": nearby_str,
            "air_quality": air_str,
            "geocode_found": bool(maps_result.geocode),
        }

        prompt = (
            "=== FAKTA DARI VISION AGENT ===\n"
            f"{json.dumps(a1_facts, ensure_ascii=False, indent=2)}\n\n"
            "=== DATA GEOSPATIAL ===\n"
            f"{json.dumps(a2_geo, ensure_ascii=False, indent=2)}\n\n"
            "=== PREFERENSI USER ===\n"
            f"Budget max: Rp{prefs.max_price:,}\n"
            f"Area favorit: {', '.join(prefs.preferred_areas) or 'belum ada'}\n"
            f"Radius max ke UBAYA: {prefs.max_distance_km} km\n\n"
            "Lakukan analisis forensik lengkap. Kembalikan JSON sesuai schema."
        )

        result = await _safe_agent(
            self._deepseek.analyze(
                prompt,
                system_prompt=_AGENT3_SYSTEM,
            ),
            fallback={},
            agent_name="Agent3-RiskAnalyst",
            timeout=40.0,   # DeepSeek 3x45s retry would blow budget; cap at 40s
        )
        if isinstance(result, str):
            # DeepSeek returned plain text — try parse JSON from it
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

    # ── Agent 4: Synthesizer ───────────────────────────────────────────────────

    async def _run_agent4(
        self,
        agent1_data: dict,
        maps_result: MapsResult,
        km_val: Optional[float],
        agent3_data: dict,
    ) -> str:
        """
        Agent 4 context contains a compact summary of all prior agents.
        Returns a plain-text final recommendation sentence.
        Uses Gemini lightweight (no vision, no grounding tools needed).
        """
        summary = (
            "=== RINGKASAN DARI 3 AGENT SEBELUMNYA ===\n"
            f"Lokasi: {agent1_data.get('extracted_address_raw', 'tidak diketahui')}\n"
            f"Harga: {agent1_data.get('extracted_price_raw', '?')}"
            f" (numeric: Rp{agent1_data.get('extracted_price_numeric') or '?'})\n"
            f"Jarak ke UBAYA: {f'{km_val:.1f} km' if km_val else 'tidak diketahui'}\n"
            f"Kondisi kamar: {agent1_data.get('room', {}).get('condition', '?')}\n"
            f"Fraud level: {agent3_data.get('fraud_level', '?')}"
            f" (fraud score: {agent3_data.get('fraud_score', '?')}/100)\n"
            f"Skor investasi: {agent3_data.get('composite_score', '?')}/100\n"
            f"Price verdict: {agent3_data.get('price_verdict', '?')}\n"
            f"Risk flags: {'; '.join(agent3_data.get('risk_flags', []))}\n"
            f"Catatan investigator: {agent3_data.get('analyst_notes', '')}\n\n"
            "Tulis rekomendasi akhir (2-3 kalimat, langsung, Bahasa Indonesia, max 250 karakter):"
        )

        result = await _safe_agent(
            self._gemini.analyze(
                summary,
                system_prompt=_AGENT4_SYSTEM,
                use_grounding=False,   # No search needed for synthesis
                use_thinking=False,    # Speed over depth for final formatting
            ),
            fallback=None,
            agent_name="Agent4-Synthesizer",
            timeout=20.0,   # Synthesis is short — 20s is generous
        )
        # Agent 4 may return dict (JSON-mode Gemini) or plain text
        if isinstance(result, dict):
            return (
                result.get("raw")
                or result.get("recommendation")
                or agent3_data.get("recommendation", "Analisis tidak tersedia.")
            )
        if isinstance(result, str) and len(result) > 10:
            return result[:250]
        return agent3_data.get("recommendation", "Analisis tidak tersedia.")

    # ── Shared helpers ─────────────────────────────────────────────────────────

    async def _load_prefs(self, chat_id: Optional[int]) -> UserPreferences:
        if not chat_id:
            return UserPreferences()
        try:
            prefs = await asyncio.wait_for(self._preferences_repo.get(chat_id), timeout=5.0)
            return prefs or UserPreferences()
        except Exception as exc:
            log.warning("Prefs load failed (using defaults): %s", exc)
            return UserPreferences()


async def _safe_agent(coro, fallback, agent_name: str = "Agent", timeout: float = 50.0):
    """Run agent coroutine with configurable timeout. Log failure and return fallback."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        log.error("[%s] TIMEOUT after %.0fs — returning fallback", agent_name, timeout)
        return fallback
    except Exception as exc:
        log.error(
            "[%s] EXCEPTION | type=%s | detail=%s",
            agent_name,
            type(exc).__name__,
            repr(exc),
        )
        return fallback


# ── Location extraction helpers ───────────────────────────────────────────────

import re as _re  # noqa: E402 — kept at module bottom to avoid circular issues

_SURABAYA_AREAS = [
    # Kecamatan / kelurahan populer Surabaya
    "Rungkut", "Tenggilis", "Kalirungkut", "Gunung Anyar", "Sukolilo",
    "Mulyorejo", "Gubeng", "Wonokromo", "Wonocolo", "Gayungan",
    "Wiyung", "Karangpilang", "Dukuh Pakis", "Sawahan", "Tegalsari",
    "Bubutan", "Genteng", "Simokerto", "Kenjeran", "Bulak",
    "Semampir", "Pabean Cantikan", "Krembangan", "Asemrowo", "Benowo",
    "Sambikerep", "Lakarsantri", "Tandes", "Sukomanunggal", "Jambangan",
    "Gayung", "Menanggal", "Pakuwon", "Citraland", "Darmo",
    "Menganti", "Driyorejo", "Waru", "Gedangan", "Sidoarjo",
]


def _extract_location_from_text(text: str) -> str:
    """
    Extract the best possible location hint from raw listing text.

    Priority order:
    1. Explicit street/kelurahan patterns (Jl., Kel., Kec., etc.)
    2. Known Surabaya area names mentioned in text
    3. Empty string (caller will skip Agent2 early launch)

    Never returns raw prose — only clean location-like strings.
    """
    if not text:
        return ""

    # 1. Street address pattern
    m = _re.search(
        r'((?:Jl\.|Jalan|Jln\.?)\s+[A-Za-z0-9][^\n,]{3,80})',
        text, _re.IGNORECASE
    )
    if m:
        return m.group(1).strip()[:120]

    # 2. Kelurahan / Kecamatan explicit label
    m = _re.search(
        r'(?:Kel(?:urahan)?\.?|Kec(?:amatan)?\.?)\s+([A-Za-z ]{4,60})',
        text, _re.IGNORECASE
    )
    if m:
        return m.group(1).strip()

    # 3. "dekat / area / kawasan X" pattern
    m = _re.search(
        r'(?:dekat|deket|area|kawasan|di|lokasi)[^a-zA-Z]{0,5}'
        r'([A-Z][a-zA-Z](?:[a-zA-Z ]){3,50})',
        text
    )
    if m:
        candidate = m.group(1).strip()
        if len(candidate) >= 4:
            return candidate

    # 4. Known Surabaya area name directly in text
    for area in _SURABAYA_AREAS:
        if _re.search(r'\b' + _re.escape(area) + r'\b', text, _re.IGNORECASE):
            return area

    return ""


def _best_location(agent1_data: dict, text: str) -> str:
    """
    Return the cleanest location string from Agent1 output.
    Falls back to text extraction if Agent1 gave nothing useful.
    """
    candidates = [
        agent1_data.get("extracted_address_kelurahan", ""),
        agent1_data.get("extracted_address_raw", ""),
    ]
    for c in candidates:
        if c and isinstance(c, str) and len(c.strip()) >= 4:
            return c.strip()
    # Agent1 gave nothing — fall back to text extraction
    return _extract_location_from_text(text)


def _hints_differ(a: str, b: str) -> bool:
    """
    True if two location hints are meaningfully different —
    i.e. Agent1 gave us something better than the text fallback.
    """
    if not a or not b:
        return bool(a)  # if one is empty, they "differ" only if a is non-empty
    return a.strip().lower() != b.strip().lower()

