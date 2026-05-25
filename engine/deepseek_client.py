"""
engine/deepseek_client.py
DeepSeek v3 async client dengan retry + exponential backoff.
"""
import asyncio
import logging
import os

import httpx

log = logging.getLogger("god-eye.deepseek")

DEEPSEEK_KEY      = os.environ["DEEPSEEK_API_KEY"]
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL    = "deepseek-chat"


async def deepseek_analyze(prompt: str, max_tokens: int = 1500) -> str:
    """
    Kirim prompt ke DeepSeek Chat API.
    Retry hingga 3x dengan exponential backoff.
    """
    payload = {
        "model": DEEPSEEK_MODEL,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_KEY}",
        "Content-Type": "application/json",
    }

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=45) as c:
                r = await c.post(DEEPSEEK_ENDPOINT, headers=headers, json=payload)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            last_exc = exc
            wait = 2 ** attempt
            log.warning(f"DeepSeek attempt {attempt + 1} failed: {exc}. Retry in {wait}s")
            await asyncio.sleep(wait)

    log.error(f"DeepSeek failed after 3 attempts: {last_exc}")
    return f"[DeepSeek error: {str(last_exc)[:200]}]"
