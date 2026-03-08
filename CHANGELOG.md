# CHANGELOG — God Eye Kos-Bot

Semua perubahan signifikan dicatat di sini, termasuk yang **merusak** dan yang **memperbaiki**.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

---

## [Unreleased]

---

## [5.5-dashboard.3] — 2026-03-08
**Commit:** `2697e22` — *fix(detail): fix Jinja TemplateSyntaxError - extra endif causing 500*

### Fixed
- **500 error pada SEMUA halaman detail** — root cause: `{% endif %}{% endif %}` ganda sebelum
  delete modal, membuat `{% else %}` (not-found branch) tidak punya pasangan `{% if %}`.
  Jinja2 melempar `TemplateSyntaxError` saat render template pertama kali.
- Struktur block Jinja di `detail.html` diperbaiki: delete modal dipindah ke DALAM blok
  `{% if listing %}` (sebelum `{% else %}`), bukan setelah `{% endif %}` utama.
- Python balance check: `Final depth: 0 — No unbalanced blocks found` ✅

### Notes
- Cloud Build auto-trigger tidak firing untuk push ini — di-trigger manual
- Build `34513ad8` → SUCCESS → deployed revision `god-eye-00025-xxx`

---

## [5.5-dashboard.2] — 2026-03-08
**Commit:** `fc55ba8` — *fix(dashboard): hotfix 500 error on detail page*

### Fixed
- `listing.geocode.lat/lng` crash — Firestore menyimpan geocode sebagai `GeoPoint` object,
  bukan dict. Template melakukan dot-access yang crash. Fix: normalisasi di `dashboard.py`
  detail() ke flat keys `has_geo`, `geo_lat`, `geo_lng`.
- `listing.air_quality.aqi` crash — `air_quality` adalah `dict`, tidak bisa dot-access
  key-nya di Jinja. Fix: di-extract ke `aqi_value` dan `aqi_category`.
- `"{:,}".format(None)` crash — `price` bisa `None` di Firestore.
  Fix: `listing.setdefault("price", listing.get("price_value") or 0)`.
- `phones` normalisasi: `None` → `[]`, `str` → `[str]`, list tetap list.

### Notes
- Commit ini **tidak** menyelesaikan 500 error — masih ada bug Jinja block di `detail.html`
  yang baru ditemukan setelah hotfix ini di-commit (lihat `2697e22`).
- Cloud Build auto-trigger tidak firing → di-trigger manual (build `b7b114f1`)

---

## [5.5-dashboard.1] — 2026-03-07
**Commit:** `3983ddd` — *feat(dashboard): fix navigation + delete + sound + richer detail page*

### Added
- **Delete listing**: `FirestoreListingRepo.delete()` di `v2/adapters/repositories/firestore_repo.py`
- **Delete endpoint**: `DELETE /dashboard/api/delete/<id>` di `web/dashboard.py`
- **Inline delete** di `index.html`: trash icon muncul saat hover → konfirmasi inline → animasi collapse
- **Toast notification** setelah delete
- **Sound effects engine** di `base.html` — Web Audio API pure JS:
  - `SFX.click()`, `SFX.nav()`, `SFX.delete()`, `SFX.success()`, `SFX.error()`, `SFX.toggle()`
  - Preference disimpan di `localStorage` key `sfx_muted`
- **Sound toggle button** 🔊/🔇 di navbar
- **Detail page richer**:
  - Phones section
  - AQI card (color-coded)
  - Google Maps link dari geocode
  - Delete button + modal di hero section
  - Gemini raw / DeepSeek raw analysis sections

### Fixed
- **Navigasi listing card rusak** — `_get_listings()` mengembalikan dict dengan key `listing_id`
  tapi tidak `id`; template pakai `l.id` yang undefined.
  Fix: normalisasi `item['id'] = item.get('listing_id')` + template gunakan `l.listing_id or l.id`
- JS `renderCard()` di `index.html`: `l.id` → `l.listing_id || l.id`
- SSR card di `index.html`: `{{ l.id }}` → `{{ l.listing_id or l.id }}`
- `index.html` AQI badge: gunakan `l.air_quality.get('aqi')` dengan guard `is mapping`

---

## [5.5-dashboard.0] — 2026-03-07
**Commit:** `f07b8a7` — *fix(dashboard): connect Firestore — stub replaced with real queries*

### Fixed
- Dashboard sebelumnya pakai **stub data hardcoded** — tidak pernah fetch Firestore.
  `_get_listings()` dan `_get_stats()` di `web/dashboard.py` diganti dengan
  query Firestore asli via `v2` container.
- Stats (total, avg_score, surveyed) sekarang real-time dari Firestore.

---

## [5.5] — 2026-02
**Commit:** `556e602` — *fix(v5.5): resolve all 4 production failures*

### Fixed (4 production failures)
1. **Geocode timeout** — geocoding tidak diparallelkan, blocking pipeline 30s+
2. **False positive fraud** — Naive Bayes terlalu sensitif pada nomor telepon valid
3. **Score out of range** — komposit score bisa >100 atau <0 pada edge case
4. **Circuit breaker stuck open** — tidak pernah reset ke half-open setelah recovery

---

## [5.4] — 2026-02
**Commit:** `c96a8d9` — *feat(v5.4): Naive Bayes fraud scoring + confidence-weighted evidence*

### Added
- **Naive Bayes classifier** di `engine/deepseek_client.py` untuk fraud scoring
- Confidence-weighted evidence aggregation
- Prior probability dari historical data di Firestore

---

## [5.3] — 2026-01
**Commit:** `24c4fae` — *fix(v5.3): dual-model strategy + jitter backoff + circuit breaker*

### Added
- **Dual-model strategy**: fallback Gemini → DeepSeek jika satu model gagal
- **Jitter backoff**: exponential backoff + random jitter untuk retry API
- **Circuit breaker**: auto-open setelah N consecutive failures, half-open probe

---

## [5.2] — 2025
**Commit:** `7f79674` — *fix(v5.2): address extraction, false flags, formatter cleanup*

### Fixed
- Address extraction dari teks bebas — regex lebih akurat
- False fraud flags pada nomor telepon legitimate
- Formatter: section yang kosong tidak lagi muncul di laporan

---

## [5.1] — 2025
**Commit:** `ee698e3` — *fix(v5.1): agentic pipeline redesign — regex-first, no false fraud flags*

### Changed
- Pipeline redesign: regex-first untuk ekstraksi data struktur (price, phone, location)
  sebelum kirim ke LLM — mengurangi hallucination dan false positive

---

## [5.0] — 2025
**Commit:** `5376387` — *fix+feat(v5.0): fix pipeline bugs + structured logging + resilience + View Logs*

### Added
- Structured logging (structlog-style)
- "View Logs" link di laporan Telegram → Cloud Run log URL
- Pipeline resilience: semua API call dibungkus `safe()` wrapper

---

## [4.x — Interim Fixes] — 2025

### Commits (kronologis)
- `0ef2420` — Gemini two-phase analyze: separate grounding dari JSON extraction
- `405ccb7` — Maps geocode 3-attempt fallback, smarter location extraction
- `2f9be40` — Parallelisasi Agent1+Agent2, timeout 60s→120s, fix stale msg_id
- `252e2c7` — Per-chat_id busy lock — fix Telegram retry spam dengan update_id berbeda
- `158359f` — Async decouple analysis via create_task + 2-level idempotency lock
- `82adc59` — Dashboard dark cyber UI overhaul: glassmorphism, Three.js particles, animated rings
- `bf731c1` — Fix `prefs.max_radius_km` → `max_distance_km` AttributeError
- `85de594` — Multi-agent 4-chain pipeline + idempotency dedup + verbose API error logging
- `5dbfa0f` — Suppress BadRequest 'message is not modified' spam

---

## [4.0] — 2025
**Commits:** `c9e629f` + `1d982b1`

### Changed
- **Clean Architecture refactor** — domain/services/adapters/infrastructure layers
  (tersimpan di `v2/` dan `v3.1/` sebagai arsip)
- Merge ke project root

---

## [3.1.0] — 2025

### Added
- **Gemini 3.1 Pro Preview** (`gemini-3.1-pro-preview`) → `thinking_level="high"`
- JSON response terstruktur: `location_text`, `room`, `phone_check`, `area`, `price_market`, `post_flags`, `authenticity`
- **Google Routes API v2** (3 scenario traffic: pagi/siang/malam)
- **Google Places API (New)** — 6 tipe fasilitas
- **Web Dashboard** Flask + Jinja2 + Tailwind CDN
- Tombol **Laporkan Penipuan** di Telegram keyboard
- `memory/scoring.py` — scoring komposit dipisah dari learning
- `safe()` wrapper di `engine/analyzer.py`
- Skip counts + auto-avoided area

---

## [3.0.0] — 2025

### Added
- Arsitektur modular penuh: `bot/`, `engine/`, `memory/`, `monitor/`
- Gemini 2.0 Flash + Google Search grounding
- DeepSeek Chat API, retry 3x
- Routes API + Places + AQI + Geocoding
- Firestore AsyncClient (4 collections)
- Self-learning dari feedback inline button

---

## [2.0.0] — 2025

### Added
- `/monitor` endpoint untuk n8n
- `N8N_WEBHOOK_SECRET` env var
- Service account di deploy script
- Structured logging

---

## [1.0.0] — 2025

### Added
- Bot Telegram dasar: analisis kos teks/foto/link
- Gemini + DeepSeek dual AI
- Google Maps Distance Matrix + Places
- Flask webhook endpoint
- Deploy ke Cloud Run (manual)

---

*Lihat [POSTMORTEM.md](./POSTMORTEM.md) untuk catatan bugs dan kesalahan AI.*
