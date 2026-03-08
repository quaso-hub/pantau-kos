"""
adapters/gateways/gemini_gateway.py  (v4.2)
Concrete Gemini implementation of AIGateway.

KEY FIX (v4.2):
  response_mime_type="application/json" is INCOMPATIBLE with google_search grounding.
  When grounding tools are active, the model returns narrative text (not JSON) and
  json.loads() fails silently → {"raw": ...} is returned → all extraction fields are
  missing → price/address/fraud-score all wrong.

  SOLUTION — two-phase approach:
    Phase 1 (grounding): google_search enabled, plain text response → collects web facts
    Phase 2 (extraction): NO tools, response_mime_type=JSON + response_json_schema → structured output

  Non-grounded calls (Agent4 synthesis) use single-phase JSON directly.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional

from google import genai
from google.genai import types

from domain.interfaces import AIGateway
from infrastructure.config import GeminiConfig

log = logging.getLogger("god-eye.gemini")

# ── Legacy / fallback system prompt (used by Agent4 single-phase calls) ────────
SYSTEM_PROMPT = """
Kamu analis properti + investigator penipuan untuk mahasiswa UBAYA Surabaya 2026.
UBAYA Tenggilis: Jl. Raya Kalirungkut (-7.3275, 112.7858).
Kembalikan JSON sesuai schema yang diminta. Isi SETIAP field yang datanya tersedia.
"""

# ── Agent1 Phase 1: grounding/search — free-form text, tools enabled ──────────
_AGENT1_SEARCH_SYSTEM = """
Kamu adalah INVESTIGATOR kos-kosan Surabaya. Lakukan pencarian Google untuk:

1. Nomor telepon dari iklan — SEARCH: "{nomor} getcontact penipuan kos surabaya"
   - Tersimpan sebagai apa di GetContact/Truecaller? Ada laporan penipuan?

2. Nama jalan/kelurahan — SEARCH: verifikasi keberadaan di Surabaya

3. Harga pasar kos di area tersebut — SEARCH: "harga kos {kelurahan} surabaya 2026"
   - Kisaran harga normal, verdict murah/sesuai/mahal

4. Reputasi area — SEARCH: "keamanan {area} surabaya 2026"
   - Aman pulang malam? Risiko banjir?

5. Cek foto/listing di internet — ada di platform lain dengan info berbeda?

Tulis SEMUA temuan dalam teks bebas yang lengkap dan faktual.
Jika tidak ada data, tulis "Tidak ditemukan."
"""

# ── Agent1 Phase 2: structured extraction — JSON mode, no tools ───────────────
_AGENT1_EXTRACT_SYSTEM = """
Kamu adalah DATA EXTRACTION ENGINE. Baca iklan dan hasil investigasi lalu ekstrak semua fakta.

ATURAN WAJIB:
- Isi SETIAP field yang datanya ada. JANGAN biarkan field kosong jika data tersedia.
- extracted_price_raw: kutip harga persis dari teks (contoh: "950rb/bulan")
- extracted_price_numeric: konversi ke angka (950rb → 950000, 1.2jt → 1200000)
- extracted_address_raw: alamat persis dari iklan (contoh: "Medayu Utara VIIIA/No.146A Pagar Hitam")
- extracted_address_kelurahan: kelurahan/kecamatan saja (contoh: "Rungkut")
- extracted_phones: SEMUA nomor HP yang ditemukan
- room.photo_authentic: false jika foto terlihat stock-photo atau terlalu sempurna
- raw_red_flags: [] jika normal, isi jika ada tanda bahaya

Kembalikan JSON sesuai schema. WAJIB isi semua field yang datanya ada dalam teks.
"""

# ── Agent1 JSON schema — pins Phase 2 extraction output ───────────────────────
_AGENT1_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "extracted_price_raw":         {"type": ["string", "null"]},
        "extracted_price_numeric":     {"type": ["number", "null"]},
        "extracted_phones":            {"type": "array", "items": {"type": "string"}},
        "extracted_address_raw":       {"type": ["string", "null"]},
        "extracted_address_kelurahan": {"type": ["string", "null"]},
        "extracted_address_coords": {
            "type": "object",
            "properties": {
                "lat": {"type": ["number", "null"]},
                "lng": {"type": ["number", "null"]},
            },
        },
        "room": {
            "type": "object",
            "properties": {
                "size_m2":         {"type": ["number", "null"]},
                "condition":       {"type": ["string", "null"]},
                "bathroom":        {"type": ["string", "null"]},
                "furniture":       {"type": "array", "items": {"type": "string"}},
                "photo_authentic": {"type": "boolean"},
                "photo_flags":     {"type": "array", "items": {"type": "string"}},
            },
        },
        "phone_intel": {
            "type": "object",
            "properties": {
                "number":              {"type": ["string", "null"]},
                "getcontact_saved_as": {"type": ["string", "null"]},
                "fraud_report_found":  {"type": "boolean"},
                "fraud_report_detail": {"type": ["string", "null"]},
                "social_media_flags":  {"type": ["string", "null"]},
            },
        },
        "listing_intel": {
            "type": "object",
            "properties": {
                "found_on_other_platforms": {"type": "boolean"},
                "contradictory_info_found": {"type": "boolean"},
                "duplicate_photo_found":    {"type": "boolean"},
                "details":                  {"type": ["string", "null"]},
            },
        },
        "raw_red_flags": {"type": "array", "items": {"type": "string"}},
        "source_link":   {"type": ["string", "null"]},
    },
}


class GeminiGateway(AIGateway):
    """
    Concrete Gemini Vision adapter.

    Two-phase strategy for grounded calls (Agent1):
      Phase 1: google_search tools enabled, plain-text response  → collects web facts
      Phase 2: NO tools, response_mime_type=JSON + schema         → structured extraction

    Single-phase strategy for non-grounded calls (Agent4 synthesis).
    """

    def __init__(self, config: GeminiConfig) -> None:
        self._model = config.model
        self._client = genai.Client(api_key=config.api_key)

    async def analyze(
        self,
        prompt: str,
        image_bytes: Optional[bytes] = None,
        system_prompt: Optional[str] = None,
        use_grounding: bool = True,
        use_thinking: bool = False,
        json_schema: Optional[dict] = None,
    ) -> dict | str:
        """
        Entry point for all Gemini calls.
          use_grounding=True  → two-phase (search → extract)
          use_grounding=False → single-phase JSON (Agent4 synthesis)
        """
        if use_grounding:
            return await self._two_phase_analyze(
                prompt=prompt,
                image_bytes=image_bytes,
                system_prompt=system_prompt,
                use_thinking=use_thinking,
                json_schema=json_schema,
            )
        else:
            return await self._single_phase_json(
                prompt=prompt,
                image_bytes=image_bytes,
                system_prompt=system_prompt or SYSTEM_PROMPT,
                use_thinking=use_thinking,
                json_schema=json_schema,
            )

    # ── Two-phase: grounding → extraction ───────────────────────────────────

    async def _two_phase_analyze(
        self,
        prompt: str,
        image_bytes: Optional[bytes],
        system_prompt: Optional[str],
        use_thinking: bool,
        json_schema: Optional[dict],
    ) -> dict:
        # Phase 1: web search + vision (free-form text)
        grounded_text = await self._grounding_call(
            prompt=prompt,
            image_bytes=image_bytes,
            system_prompt=system_prompt or _AGENT1_SEARCH_SYSTEM,
            use_thinking=use_thinking,
        )
        log.info(
            "[Phase1] grounded_text=%d chars | preview=%r",
            len(grounded_text), grounded_text[:120],
        )

        # Phase 2: structured JSON extraction (no tools, schema-bound)
        # CRITICAL: image_bytes MUST be passed to Phase 2 — the extraction model
        # needs to see the photo to extract room condition, size, furniture, etc.
        extract_prompt = (
            "=== TEKS IKLAN ASLI ===\n"
            f"{prompt}\n\n"
            "=== HASIL INVESTIGASI INTERNET ===\n"
            f"{grounded_text[:3000]}\n\n"
            "Ekstrak semua fakta keras dari iklan, foto, dan hasil investigasi di atas. "
            "Kembalikan JSON sesuai schema. WAJIB isi setiap field yang datanya tersedia."
        )
        result = await self._extraction_call(
            prompt=extract_prompt,
            image_bytes=image_bytes,
            system_prompt=_AGENT1_EXTRACT_SYSTEM,
            json_schema=json_schema or _AGENT1_JSON_SCHEMA,
        )
        log.info(
            "[Phase2] keys=%s | price=%s | address=%r | phone=%s",
            list(result.keys()) if isinstance(result, dict) else type(result).__name__,
            result.get("extracted_price_numeric") if isinstance(result, dict) else "?",
            result.get("extracted_address_raw")   if isinstance(result, dict) else "?",
            result.get("extracted_phones")         if isinstance(result, dict) else "?",
        )
        return result if isinstance(result, dict) else {}

    async def _grounding_call(
        self,
        prompt: str,
        image_bytes: Optional[bytes],
        system_prompt: str,
        use_thinking: bool,
    ) -> str:
        """Phase 1: google_search enabled, returns free-form text (NO JSON constraint)."""
        parts: list = []
        if image_bytes:
            mime = "image/png" if image_bytes[:4] == b"\x89PNG" else "image/jpeg"
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
        parts.append(types.Part.from_text(text=prompt))

        cfg_kwargs: dict = {
            "system_instruction": system_prompt,
            "tools": [types.Tool(google_search=types.GoogleSearch())],
            # NOTE: intentionally NO response_mime_type here — grounding + JSON = conflict
        }
        if use_thinking:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level="high")

        gen_config = types.GenerateContentConfig(**cfg_kwargs)
        last_exc: Exception | None = None

        for attempt in range(3):
            try:
                resp = await asyncio.to_thread(
                    lambda: self._client.models.generate_content(
                        model=self._model,
                        contents=[types.Content(role="user", parts=parts)],
                        config=gen_config,
                    )
                )
                raw = getattr(resp, "text", "") or ""
                if raw:
                    return raw
                log.warning("[Phase1] attempt %d returned empty text", attempt + 1)
            except Exception as exc:
                last_exc = exc
                wait = 2 ** attempt
                log.warning(
                    "[Phase1] attempt %d/3 FAILED | %s | retry_in=%ds",
                    attempt + 1, repr(exc)[:200], wait,
                )
                await asyncio.sleep(wait)

        log.error("[Phase1] EXHAUSTED 3 attempts | last=%s", repr(last_exc)[:200])
        return ""  # Phase 2 still runs with empty grounding context

    async def _extraction_call(
        self,
        prompt: str,
        system_prompt: str,
        json_schema: dict,
        image_bytes: Optional[bytes] = None,
    ) -> dict:
        """Phase 2: strict JSON extraction — NO tools, schema-bound response.
        Optionally includes image for vision-based extraction."""
        parts: list = []
        if image_bytes:
            mime = "image/png" if image_bytes[:4] == b"\x89PNG" else "image/jpeg"
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
        parts.append(types.Part.from_text(text=prompt))

        gen_config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_json_schema=json_schema,
            # NOTE: intentionally NO tools here — JSON mode + tools = conflict
        )
        last_exc: Exception | None = None

        for attempt in range(3):
            try:
                resp = await asyncio.to_thread(
                    lambda: self._client.models.generate_content(
                        model=self._model,
                        contents=[types.Content(role="user", parts=parts)],
                        config=gen_config,
                    )
                )
                raw_text = getattr(resp, "text", "") or ""
                log.debug("[Phase2] raw=%r", raw_text[:300])
                try:
                    parsed = json.loads(raw_text)
                    if isinstance(parsed, dict):
                        return parsed
                    log.warning("[Phase2] JSON not a dict: %s", type(parsed))
                except json.JSONDecodeError:
                    # Try rescue from markdown code block
                    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
                    if m:
                        try:
                            return json.loads(m.group(1))
                        except json.JSONDecodeError:
                            pass
                    # Last resort: grab first {...} block
                    m2 = re.search(r'\{.*\}', raw_text, re.DOTALL)
                    if m2:
                        try:
                            return json.loads(m2.group())
                        except json.JSONDecodeError:
                            pass
                    log.warning("[Phase2] non-JSON: %r", raw_text[:200])
            except Exception as exc:
                last_exc = exc
                wait = 2 ** attempt
                log.warning(
                    "[Phase2] attempt %d/3 FAILED | %s | retry_in=%ds",
                    attempt + 1, repr(exc)[:200], wait,
                )
                await asyncio.sleep(wait)

        log.error("[Phase2] EXHAUSTED 3 attempts | last=%s", repr(last_exc)[:200])
        return {}

    # ── Single-phase: JSON only, no grounding (Agent4 synthesis) ────────────

    async def _single_phase_json(
        self,
        prompt: str,
        image_bytes: Optional[bytes],
        system_prompt: str,
        use_thinking: bool,
        json_schema: Optional[dict],
    ) -> dict | str:
        """Single call: no tools, JSON mode. Used for Agent4 synthesis / scoring."""
        parts: list = []
        if image_bytes:
            mime = "image/png" if image_bytes[:4] == b"\x89PNG" else "image/jpeg"
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
        parts.append(types.Part.from_text(text=prompt))

        cfg_kwargs: dict = {
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
        }
        if json_schema:
            cfg_kwargs["response_json_schema"] = json_schema
        if use_thinking:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level="high")

        gen_config = types.GenerateContentConfig(**cfg_kwargs)
        last_exc: Exception | None = None

        for attempt in range(3):
            try:
                resp = await asyncio.to_thread(
                    lambda: self._client.models.generate_content(
                        model=self._model,
                        contents=[types.Content(role="user", parts=parts)],
                        config=gen_config,
                    )
                )
                raw_text = getattr(resp, "text", "") or ""
                try:
                    return json.loads(raw_text)
                except json.JSONDecodeError:
                    log.warning("[single] non-JSON response, returning raw text")
                    return raw_text  # Agent4 formatter can handle plain text too
            except Exception as exc:
                last_exc = exc
                wait = 2 ** attempt
                log.warning(
                    "[single] attempt %d/3 FAILED | %s | retry_in=%ds",
                    attempt + 1, repr(exc)[:200], wait,
                )
                await asyncio.sleep(wait)

        log.error("[single] EXHAUSTED | last=%s", repr(last_exc)[:200])
        return {"error": str(last_exc)[:400]}
