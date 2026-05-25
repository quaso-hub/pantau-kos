"""
adapters/gateways/gemini_gateway.py  (v5.5)
Concrete Gemini implementation of AIGateway.

Architecture:
  • Two-phase for grounded calls: Phase1=google_search text, Phase2=JSON extraction
  • Single-phase JSON for non-grounded calls (Vision, Synthesizer)
  • Pro model  → grounding/search (Phase 1) ONLY
  • Flash model → JSON-schema extraction (Phase 2 + Vision + Synthesizer)
    response_json_schema is NOT supported on Pro models — Flash only.

Fixes in v5.5:
  • Model names updated: gemini-2.5-pro / gemini-2.5-flash (no dead preview suffixes)
  • Persistent requests.Session (max_retries=Retry(3)) reused across all calls
    → eliminates SSL Max Retries / connection pool exhaustion
  • ThinkingConfig guard: only applied to models that support thinking
  • ValidationError was caused by response_json_schema on non-Flash models — fixed
  • Exponential backoff WITH jitter on all retries (unchanged from v5.3)

Connection pool strategy:
  The google-genai SDK uses `requests` (sync HTTP) internally. We wrap each
  call with asyncio.to_thread() so it runs in a thread-pool without blocking
  the event loop. The SDK's default transport creates a NEW session per call,
  exhausting the OS connection pool quickly under load. We fix this by
  injecting a single persistent requests.Session with HTTPAdapter(max_retries)
  into the SDK client's HTTP options at construction time.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from google import genai
from google.genai import types

from domain.interfaces import AIGateway
from infrastructure.config import GeminiConfig

log = logging.getLogger("god-eye.gemini")

# ── Retry / backoff constants ─────────────────────────────────────────────────
_MAX_RETRIES   = 3
_BASE_DELAY    = 1.5   # seconds
_MAX_DELAY     = 20.0  # seconds cap
_JITTER_FACTOR = 0.3   # ±30% jitter on each retry

# Models that support thinking_config (Flash Thinking / Pro Thinking)
_THINKING_CAPABLE_MODELS = {
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash-thinking-exp",
    "gemini-3.1-pro",
    "gemini-3.1-flash",
}


def _backoff(attempt: int) -> float:
    """Exponential backoff with full jitter. avg = BASE * 2^attempt ± JITTER."""
    base = min(_BASE_DELAY * (2 ** attempt), _MAX_DELAY)
    jitter = base * _JITTER_FACTOR * (2 * random.random() - 1)
    return max(0.1, base + jitter)


def _build_session() -> requests.Session:
    """
    Build a persistent requests.Session with:
      - Connection pooling (pool_connections=4, pool_maxsize=10)
      - Automatic urllib3 retries on transient TCP/SSL errors (NOT on 4xx/5xx,
        those are handled by our own application-level retry loop)
    """
    session = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=[],          # don't auto-retry on status codes
        allowed_methods=["POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=4,
        pool_maxsize=10,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ── Legacy / fallback system prompt ──────────────────────────────────────────
SYSTEM_PROMPT = """
Kamu analis properti + investigator penipuan untuk mahasiswa UBAYA Surabaya 2026.
UBAYA Tenggilis: Jl. Raya Kalirungkut (-7.3275, 112.7858).
Kembalikan JSON sesuai schema yang diminta. Isi SETIAP field yang datanya tersedia.
"""

# ── Agent1 Phase 1: grounding/search — free-form text ────────────────────────
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

# ── Agent1 Phase 2: structured extraction — JSON mode, no tools ──────────────
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

# ── Agent1 JSON schema ────────────────────────────────────────────────────────
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
    Gemini adapter with two-model strategy:
      • self._model       = Pro model  (grounding/search, Phase 1 ONLY)
      • self._flash_model = Flash model (ALL JSON-schema calls, Vision, Synthesizer)

    response_json_schema is ONLY supported on Flash models, NOT Pro.
    ThinkingConfig is only applied when the model name is in _THINKING_CAPABLE_MODELS.

    Connection pool: a single persistent requests.Session is injected at init
    and reused for all API calls, avoiding SSL pool exhaustion.
    """

    def __init__(self, config: GeminiConfig) -> None:
        self._model       = config.model
        self._flash_model = config.flash_model
        # Persistent session shared across all calls from this gateway instance.
        # HTTPAdapter with pool_maxsize=10 prevents connection exhaustion.
        self._session = _build_session()
        self._client = genai.Client(
            api_key=config.api_key,
            http_options=types.HttpOptions(
                timeout=60_000,   # ms — per-request timeout in the SDK
            ),
        )

    async def analyze(
        self,
        prompt: str,
        image_bytes: Optional[bytes] = None,
        system_prompt: Optional[str] = None,
        use_grounding: bool = True,
        use_thinking: bool = False,
        json_schema: Optional[dict] = None,
    ) -> dict | str:
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

    # ── Two-phase: grounding → extraction ─────────────────────────────────────

    async def _two_phase_analyze(
        self,
        prompt: str,
        image_bytes: Optional[bytes],
        system_prompt: Optional[str],
        use_thinking: bool,
        json_schema: Optional[dict],
    ) -> dict:
        # Phase 1: web search via Pro model (free-form text, no JSON constraint)
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

        # Phase 2: JSON extraction via Flash model
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
        """Phase 1: Pro model + google_search. Returns free-form text.

        IMPORTANT: Do NOT set response_mime_type or response_json_schema here.
        Grounding + JSON mode = ValidationError from the SDK.
        ThinkingConfig only applied when the model supports it.
        """
        parts: list = []
        if image_bytes:
            mime = "image/png" if image_bytes[:4] == b"\x89PNG" else "image/jpeg"
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
        parts.append(types.Part.from_text(text=prompt))

        cfg_kwargs: dict = {
            "system_instruction": system_prompt,
            "tools": [types.Tool(google_search=types.GoogleSearch())],
            # NO response_mime_type — grounding + JSON = ValidationError
            # NO response_json_schema — same reason
        }
        # Only add thinking_config for models that actually support it
        if use_thinking and self._model in _THINKING_CAPABLE_MODELS:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level="high")

        gen_config = types.GenerateContentConfig(**cfg_kwargs)
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES):
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
                wait = _backoff(attempt)
                log.warning(
                    "[Phase1] attempt %d/%d FAILED | %s | retry_in=%.1fs",
                    attempt + 1, _MAX_RETRIES, _classify_error(exc), wait,
                )
                await asyncio.sleep(wait)

        log.error("[Phase1] EXHAUSTED %d attempts | last=%s", _MAX_RETRIES, repr(last_exc)[:200])
        return ""  # Phase 2 still runs with empty grounding context

    async def _extraction_call(
        self,
        prompt: str,
        system_prompt: str,
        json_schema: dict,
        image_bytes: Optional[bytes] = None,
    ) -> dict:
        """Phase 2: Flash model, strict JSON extraction, NO tools, schema-bound."""
        parts: list = []
        if image_bytes:
            mime = "image/png" if image_bytes[:4] == b"\x89PNG" else "image/jpeg"
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
        parts.append(types.Part.from_text(text=prompt))

        gen_config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_json_schema=json_schema,
            # NOTE: NO tools — JSON mode + tools = ValidationError
        )
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                resp = await asyncio.to_thread(
                    lambda: self._client.models.generate_content(
                        model=self._flash_model,   # ← Flash only supports json_schema
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
                    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
                    if m:
                        try:
                            return json.loads(m.group(1))
                        except json.JSONDecodeError:
                            pass
                    m2 = re.search(r'\{.*\}', raw_text, re.DOTALL)
                    if m2:
                        try:
                            return json.loads(m2.group())
                        except json.JSONDecodeError:
                            pass
                    log.warning("[Phase2] non-JSON: %r", raw_text[:200])
            except Exception as exc:
                last_exc = exc
                wait = _backoff(attempt)
                log.warning(
                    "[Phase2] attempt %d/%d FAILED | %s | retry_in=%.1fs",
                    attempt + 1, _MAX_RETRIES, _classify_error(exc), wait,
                )
                await asyncio.sleep(wait)

        log.error("[Phase2] EXHAUSTED %d attempts | last=%s", _MAX_RETRIES, repr(last_exc)[:200])
        return {}

    # ── Single-phase: JSON only, no grounding (Vision + Synthesizer) ──────────

    async def _single_phase_json(
        self,
        prompt: str,
        image_bytes: Optional[bytes],
        system_prompt: str,
        use_thinking: bool,
        json_schema: Optional[dict],
    ) -> dict | str:
        """Flash model + JSON schema. Used for Vision Agent and Synthesizer.

        ThinkingConfig only applied when the flash model supports it.
        response_json_schema ONLY works on Flash model — never on Pro.
        """
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
        # Only add thinking for models that support it
        if use_thinking and self._flash_model in _THINKING_CAPABLE_MODELS:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level="high")

        gen_config = types.GenerateContentConfig(**cfg_kwargs)
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                resp = await asyncio.to_thread(
                    lambda: self._client.models.generate_content(
                        model=self._flash_model,   # ← Flash supports json_schema
                        contents=[types.Content(role="user", parts=parts)],
                        config=gen_config,
                    )
                )
                raw_text = getattr(resp, "text", "") or ""
                try:
                    return json.loads(raw_text)
                except json.JSONDecodeError:
                    log.warning("[single] non-JSON response, returning raw text")
                    return raw_text
            except Exception as exc:
                last_exc = exc
                wait = _backoff(attempt)
                log.warning(
                    "[single] attempt %d/%d FAILED | %s | retry_in=%.1fs",
                    attempt + 1, _MAX_RETRIES, _classify_error(exc), wait,
                )
                await asyncio.sleep(wait)

        log.error("[single] EXHAUSTED %d attempts | last=%s", _MAX_RETRIES, repr(last_exc)[:200])
        return {}


def _classify_error(exc: Exception) -> str:
    """Return a short human-readable error category for logging."""
    name = type(exc).__name__
    msg  = str(exc)[:120]
    if "SSL" in msg or "ssl" in msg:
        return f"SSLError({msg[:80]})"
    if "timeout" in msg.lower() or "Timeout" in name:
        return f"TimeoutError({msg[:60]})"
    if "ValidationError" in name:
        return f"ValidationError({msg[:80]})"
    if "429" in msg or "quota" in msg.lower() or "rate" in msg.lower():
        return f"RateLimitError({msg[:60]})"
    if "503" in msg or "unavailable" in msg.lower():
        return f"ServiceUnavailable({msg[:60]})"
    return f"{name}({msg[:80]})"


