"""
adapters/controllers/formatter.py  (v4.0)
MarkdownV2 format for Telegram — intelligence-brief tone.
Now imports domain models instead of engine.analyzer / engine.maps_client.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from domain.models import AnalysisResult, MapsResult

UBAYA_LAT = -7.3275
UBAYA_LNG = 112.7858
DASHBOARD_BASE = "https://god-eye.ikrn.engineer/dashboard"
_SPINNERS = ["[-]", "[|]", "[/]", "[\\]"]

LOADING_STEPS = [
    (1, "SYSTEM", "Booting God Eye Engine"),
    (2, "SYSTEM", "Initializing models"),
    (3, "VISION", "Gemini analyzing imagery"),
    (4, "DATA", r"Aggregating sources \(Maps\, Scrapers\, Firestore\)"),
    (5, "ANALYSIS", "DeepSeek scoring & correlation"),
]


def escape_md(s: object) -> str:
    text = str(s) if s is not None else ""
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!\\])', r'\\\1', text)


def format_loading(step: int, total: int, label: str, spinner_idx: int = 0) -> str:
    spinner = _SPINNERS[spinner_idx % len(_SPINNERS)]
    return f"`{spinner} Step {step}/{total} -- {label}`"


def _fmt_price(val: Optional[float], raw_prices: list) -> str:
    if val:
        formatted = f"Rp{int(val):,}".replace(",", ".")
        return f"`price: {formatted} \\(scraper\\)`"
    if raw_prices:
        return f"`price: {escape_md(raw_prices[0])} \\(raw\\)`"
    return "`price: N/A`"


def _score_label(score: Optional[int]) -> str:
    if score is None:
        return "UNSCORED"
    if score >= 75:
        return "GREEN"
    if score >= 50:
        return "CAUTION"
    return "AVOID"


def _fraud_label(risk: Optional[str]) -> str:
    if not risk:
        return "UNKNOWN"
    r = risk.upper().strip()
    if "HIGH" in r:
        return "HIGH"
    if "MEDIUM" in r or "MED" in r:
        return "MEDIUM"
    return "LOW"


def _financials_section(result: AnalysisResult) -> str:
    lines = ["*\\[FINANCIALS\\]*"]
    lines.append(_fmt_price(result.price_value, result.prices or []))
    budget = escape_md(result.budget_status or "unknown")
    lines.append(f"`budget\\_status: {budget}`")
    if result.price_score is not None:
        ps = escape_md(str(result.price_score))
        lines.append(f"`price\\_score: {ps}/10 \\(deepseek\\)`")
    return "\n".join(lines)


def _logistics_section(result: AnalysisResult) -> str:
    lines = ["*\\[LOGISTICS\\]*"]
    maps: MapsResult = result.maps or MapsResult()
    if result.distance_km_val is not None:
        km = escape_md(f"{result.distance_km_val:.1f}")
        lines.append(f"\\- `distance: {km} km to UBAYA \\(maps\\)`")
    else:
        lines.append("\\- `distance: unavailable`")
    jarak = escape_md(result.jarak_status or "unknown")
    lines.append(f"\\- `jarak\\_status: {jarak}`")
    if result.location_hint:
        lines.append(f"\\- `location: {escape_md(result.location_hint)}`")
    if maps.geocode and isinstance(maps.geocode, dict):
        addr = maps.geocode.get("formatted_address") or maps.geocode.get("address", "")
        if addr:
            lines.append(f"\\- `geocode: {escape_md(addr)}`")
    nearby_found = [p for p in (maps.nearby or []) if p.found]
    if nearby_found:
        poi_parts = []
        for poi in nearby_found[:4]:
            t = escape_md(poi.place_type)
            n = escape_md(poi.name)
            poi_parts.append(f"{t}:{n}")
        lines.append(f"\\- `nearby: {', '.join(poi_parts)}`")
    if maps.air_quality:
        aqi = escape_md(str(maps.air_quality.aqi))
        cat = escape_md(maps.air_quality.category)
        lines.append(f"\\- `air: AQI {aqi} -- {cat}`")
    return "\n".join(lines)


def _risk_section(result: AnalysisResult) -> str:
    lines = ["*\\[RISK ASSESSMENT\\]*"]
    fraud = _fraud_label(result.fraud_risk)
    score = result.score or 0
    verdict = _score_label(score)
    lines.append(
        f"`fraud: {escape_md(fraud)}` \\| "
        f"`score: {escape_md(str(score))}/100` \\| "
        f"`verdict: {escape_md(verdict)}`"
    )
    flags = []
    if result.deepseek_raw:
        for line in result.deepseek_raw.splitlines():
            stripped = line.strip()
            if stripped and (
                stripped[0].isdigit()
                or stripped.startswith("-")
                or any(
                    stripped.lower().startswith(kw)
                    for kw in ("risiko", "flag", "peringatan", "warning")
                )
            ):
                clean = re.sub(r'^[\d\.\-\*\s]+', '', stripped).strip()
                if len(clean) > 10:
                    flags.append(clean[:120])
            if len(flags) >= 4:
                break
    for i, flag in enumerate(flags, 1):
        lines.append(f"{i}\\. {escape_md(flag)}")
    if result.phones:
        phones_str = escape_md(", ".join(result.phones[:3]))
        lines.append(f"`phones: {phones_str}`")
    return "\n".join(lines)


def _verdict_section(result: AnalysisResult) -> str:
    lines = ["*\\[VERDICT\\]*"]
    rec = result.recommendation or "Analisis tidak tersedia."
    lines.append(escape_md(rec[:200]))
    lid = result.listing_id or ""
    if lid:
        url = f"{DASHBOARD_BASE}/{lid}"
        lines.append(f"[Open Dashboard]({url})")
    return "\n".join(lines)


def _build_warnings(result: AnalysisResult) -> list:
    warnings = []
    maps: MapsResult = result.maps or MapsResult()
    if not maps.geocode:
        warnings.append("MAPS_GEOCODE_UNAVAILABLE")
    if not result.gemini_data:
        warnings.append("GEMINI_VISION_FAILED")
    if not result.deepseek_raw:
        warnings.append("DEEPSEEK_SCORING_FAILED")
    return warnings


def format_report(result: AnalysisResult) -> str:
    divider = "\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-"
    ts = result.timestamp
    if isinstance(ts, datetime):
        ts_str = ts.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    elif ts:
        ts_str = str(ts)[:19]
    else:
        ts_str = "--"
    lid = escape_md(result.listing_id or "unknown")
    src = escape_md(result.source or "manual")
    ts_esc = escape_md(ts_str)
    header = "\n".join([
        "`[GOD EYE] Intelligence Brief`",
        f"`id:{lid}` \\| `src:{src}` \\| `{ts_esc}`",
        divider,
    ])
    sections = [
        header,
        _financials_section(result),
        divider,
        _logistics_section(result),
        divider,
        _risk_section(result),
        divider,
        _verdict_section(result),
    ]
    warnings = _build_warnings(result)
    if warnings:
        warn_lines = ["*\\[WARNING\\]*"]
        for w in warnings:
            warn_lines.append(f"`code: {escape_md(w)}`")
        sections.append(divider)
        sections.append("\n".join(warn_lines))
    return "\n\n".join(sections)


def split_message(text: str, max_len: int = 4000) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, max_len)
        if cut <= 0:
            cut = max_len
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks
