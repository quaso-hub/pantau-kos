"""
adapters/gateways/deepseek_gateway.py
Concrete DeepSeek implementation of AIGateway.
Preserves: 3x retry with exponential backoff, 45s timeout.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from domain.interfaces import AIGateway
from infrastructure.config import DeepSeekConfig

log = logging.getLogger("god-eye.deepseek")


class DeepSeekGateway(AIGateway):
    """Concrete DeepSeek Chat adapter."""

    def __init__(self, config: DeepSeekConfig) -> None:
        self._endpoint = config.endpoint
        self._model = config.model
        self._headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }

    async def analyze(
        self,
        prompt: str,
        image_bytes: Optional[bytes] = None,  # DeepSeek is text-only; ignored
        system_prompt: Optional[str] = None,   # Injected into messages[0] as system role
        use_grounding: bool = True,            # Not applicable for DeepSeek
        use_thinking: bool = True,             # Not applicable for DeepSeek
        json_schema: Optional[dict] = None,    # Not applicable for DeepSeek
    ) -> dict | str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._model,
            "temperature": 0,
            "max_tokens": 1500,
            "messages": messages,
        }

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=45) as c:
                    r = await c.post(self._endpoint, headers=self._headers, json=payload)
                    r.raise_for_status()
                    return r.json()["choices"][0]["message"]["content"]
            except Exception as exc:
                last_exc = exc
                wait = 2 ** attempt
                log.warning(
                    "DeepSeek attempt %d/%d FAILED | type=%s | detail=%s | retry_in=%ds",
                    attempt + 1, 3,
                    type(exc).__name__,
                    repr(exc),
                    wait,
                )
                await asyncio.sleep(wait)

        log.error(
            "DeepSeek EXHAUSTED 3 attempts | model=%s | last_error=%s | detail=%s",
            self._model,
            type(last_exc).__name__,
            repr(last_exc),
        )
        return f"[DeepSeek error: {str(last_exc)[:400]}]"
