"""
adapters/gateways/gemini_gateway.py
Concrete Gemini implementation of AIGateway.
Preserves: vision, Google Search grounding, thinking_level=high, JSON response, 3x retry.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from google import genai
from google.genai import types

from domain.interfaces import AIGateway
from infrastructure.config import GeminiConfig

log = logging.getLogger("god-eye.gemini")

SYSTEM_PROMPT = """
Kamu analis properti + investigator penipuan untuk mahasiswa UBAYA Surabaya 2026.
UBAYA Tenggilis: Jl. Raya Kalirungkut (-7.3275, 112.7858).

GUNAKAN Google Search untuk semua poin yang butuh info realtime:

1. EKSTRAKSI LOKASI — nama jalan/kelurahan dari teks atau foto, estimasi koordinat

2. ANALISIS FOTO (jika ada gambar)
   - Estimasi ukuran kamar (m²), kondisi, kamar mandi dalam/luar
   - Furnitur yang terlihat, foto asli atau stock photo?

3. CEK NOMOR TELEPON — SEARCH: "{nomor} getcontact penipuan kos surabaya"
   - Tersimpan sebagai apa di GetContact/Truecaller?
   - Ada laporan penipuan? Ada di IG/Twitter/Threads?

4. CEK LISTING DI INTERNET — SEARCH: foto/harga/lokasi spesifik
   - Listing muncul di platform lain dengan info berbeda?
   - Foto pernah dipakai untuk penipuan?

5. REPUTASI AREA — SEARCH: "keamanan {area} surabaya 2026"
   - Tingkat kriminalitas, aman pulang malam 21.00, risiko banjir

6. HARGA PASAR — SEARCH: "harga kos {area} surabaya 2026"
   - Kisaran normal dan verdict: murah/sesuai/mahal

7. RED FLAGS — harga terlalu murah, template scammer, akun baru

Kembalikan JSON murni tanpa markdown:
{
  "location_text": "nama lokasi",
  "location_kelurahan": "nama kelurahan saja",
  "location_coords": {"lat": -7.xxx, "lng": 112.xxx},
  "room": {
    "size_m2": null,
    "condition": "baik|sedang|buruk",
    "bathroom": "dalam|luar|tidak_terlihat",
    "furniture": [],
    "photo_authentic": true,
    "photo_flags": []
  },
  "phone_check": {
    "number": "",
    "getcontact_name": "",
    "fraud_reports": "",
    "trusted": true,
    "social_media_findings": ""
  },
  "listing_web_check": {
    "found_elsewhere": false,
    "social_complaints": "",
    "duplicate_photos": false
  },
  "area": {
    "crime_level": "rendah|sedang|tinggi",
    "safe_night": true,
    "flood_risk": false,
    "notes": ""
  },
  "price_market": {
    "market_range": "Rp X - Y",
    "verdict": "murah|sesuai|mahal"
  },
  "post_flags": [],
  "authenticity": "tinggi|sedang|rendah"
}
"""


class GeminiGateway(AIGateway):
    """Concrete Gemini Vision adapter."""

    def __init__(self, config: GeminiConfig) -> None:
        self._model = config.model
        self._client = genai.Client(api_key=config.api_key)

    async def analyze(
        self,
        prompt: str,
        image_bytes: Optional[bytes] = None,
    ) -> dict | str:
        parts: list = []
        if image_bytes:
            mime = (
                "image/png"
                if image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
                else "image/jpeg"
            )
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
        parts.append(types.Part.from_text(text=prompt))

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[types.Tool(google_search=types.GoogleSearch())],
            thinking_config=types.ThinkingConfig(thinking_level="high"),
            response_mime_type="application/json",
        )

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                resp = await asyncio.to_thread(
                    lambda: self._client.models.generate_content(
                        model=self._model,
                        contents=[types.Content(role="user", parts=parts)],
                        config=config,
                    )
                )
                raw_text = getattr(resp, "text", "") or ""
                try:
                    return json.loads(raw_text)
                except json.JSONDecodeError:
                    log.warning("Gemini returned non-JSON, wrapping as raw")
                    return {"raw": raw_text}
            except Exception as exc:
                last_exc = exc
                wait = 2 ** attempt
                log.warning("Gemini attempt %d failed: %s. Retry in %ds", attempt + 1, exc, wait)
                await asyncio.sleep(wait)

        log.error("Gemini failed after 3 attempts: %s", last_exc)
        return {"error": str(last_exc)[:200]}
