# 🛰️ KOS-BOT "GOD EYE" — v5.5 + Web Dashboard

> Bot Telegram + Web Dashboard untuk memantau, menganalisis, dan mengelola iklan kos di Surabaya.
> Deployed di **[god-eye.ikrn.engineer](https://god-eye.ikrn.engineer)** · Cloud Run `asia-southeast1` · Project `kos-monitor`

---

## 🧠 AI Stack

| Model | SDK | Peran |
|-------|-----|-------|
| `gemini-3.1-pro-preview` | `google-genai` | Analisis teks+gambar, JSON terstruktur, `thinking_level="high"`, Google Search grounding |
| `deepseek-chat` | OpenAI-compat REST | Skor harga, risiko penipuan (Naive Bayes), rekomendasi |

**Google APIs:**
- Routes API v2 — rute + traffic 3 scenario (pagi/siang/malam), bukan Distance Matrix
- Places API (New) — fasilitas 1 km: supermarket, RS, ATM, masjid, laundry
- Air Quality API — AQI real-time area kos
- Geocoding API + Address Validation API
- Cloud Firestore (AsyncClient) — `kos_listings`, `user_preferences`, `area_cache`, `blacklist`

**Scraping (via n8n):** Mamikos · OLX · Rumah123 · Sewakost · 99.co · Kost.com

---

## 🏗️ Arsitektur

```
main.py  (Flask entry point — register blueprints, set webhook)
├── bot/
│   ├── handlers.py        → Telegram update handler + callback query
│   ├── keyboards.py       → Inline keyboards (tombol Laporkan Penipuan)
│   └── formatter.py       → Format laporan Markdown, split >4096 char
├── engine/
│   ├── analyzer.py        → Pipeline orchestrator — safe() wrapper, asyncio.gather
│   │                        dual-model strategy, jitter backoff, circuit breaker
│   ├── gemini_client.py   → Gemini 3.1 Pro Preview, JSON extraction
│   ├── deepseek_client.py → DeepSeek Chat, retry 3x, Naive Bayes fraud scoring
│   └── maps_client.py     → Routes v2 + Places + AQI + Geocoding
├── memory/
│   ├── firestore.py       → AsyncClient CRUD (4 collections)
│   ├── scoring.py         → Scoring komposit 0-100
│   ├── learning.py        → Self-learning dari feedback + skip_counts + blacklist
│   └── cache.py           → Area cache 24h TTL
├── monitor/
│   └── receiver.py        → POST /monitor dari n8n (6 sumber)
└── web/
    ├── dashboard.py       → Flask Blueprint /dashboard
    └── templates/
        ├── base.html      → Tailwind CDN layout + Web Audio SFX engine
        ├── index.html     → Grid listing + filter + stats + inline delete
        └── detail.html    → Detail page: hero, AQI, phones, geocode map, delete
```

---

## 🌐 Endpoint

| Method | Path | Keterangan |
|--------|------|------------|
| `GET` | `/` | Health check |
| `POST` | `/webhook` | Telegram webhook |
| `POST` | `/monitor` | n8n scraper — header `X-Secret` wajib |
| `GET` | `/dashboard` | Web dashboard |
| `GET` | `/dashboard/<id>` | Detail satu listing |
| `DELETE` | `/dashboard/api/delete/<id>` | Hapus listing dari Firestore |
| `GET` | `/dashboard/api/listings` | JSON endpoint listing (dipakai JS dashboard) |

**Custom domain:** `god-eye.ikrn.engineer` via Cloud Run Integrations → Custom Domains

---

## ⚙️ Environment Variables

| Variabel | Wajib | Keterangan |
|----------|-------|------------|
| `TELEGRAM_TOKEN` | ✅ | Token Bot Telegram |
| `GEMINI_API_KEY` | ✅ | API key google-genai SDK |
| `MAPS_API_KEY` | ✅ | Google Maps (Routes, Places, AQI, Geocoding) |
| `DEEPSEEK_API_KEY` | ✅ | DeepSeek API |
| `ALLOWED_CHAT_ID` | ✅ | Chat ID Telegram yang diizinkan |
| `GOOGLE_CLOUD_PROJECT` | ✅ | GCP Project ID (untuk Firestore) |
| `N8N_WEBHOOK_SECRET` | ➖ | Secret header /monitor |
| `GEMINI_MODEL` | ➖ | Override model (default: gemini-3.1-pro-preview) |

Deploy script defaults: `PROJECT_ID=kos-monitor` · `REGION=asia-southeast1` · `SERVICE_NAME=god-eye`

---

## 🚀 Deploy ke Cloud Run

```cmd
deploy.cmd          # Windows
bash deploy.sh      # Linux / macOS
```

Script otomatis: load `.env` → validasi → `docker build` → `docker push` → `gcloud run deploy`

### ⚠️ Cloud Build Auto-Trigger Kadang Silent-Fail
Jika deploy tidak muncul setelah push, trigger manual:
```bash
gcloud builds triggers run rmgpgab-god-eye-asia-southeast1-quaso-hub-pantau-kos--mabje --branch=main
```

---

## 🖥️ Web Dashboard Features

- Grid listing real-time (polling 30s)
- Filter & sort: harga, jarak, area, status
- Stats header: total, avg score, surveyed
- Inline delete dengan animasi collapse + toast
- **Sound effects** — Web Audio API: click, nav, delete, success, error + toggle 🔊
- **Detail page**: hero + skor, phones, AQI card, Google Maps link, raw AI analysis

---

## 📦 Catatan Teknis Penting

| ⚠️ | Pesan |
|----|-------|
| Package | Gunakan `google-genai`, BUKAN `google-generativeai` — beda SDK |
| Firestore | Selalu `AsyncClient`, jangan sync |
| GeoPoint | Geocode bisa `GeoPoint` object ATAU dict — normalize dulu |
| air_quality | Selalu `dict` — akses via `.get()`, bukan dot-access |
| Telegram | Max 4096 char — `split_message()` di `bot/formatter.py` |
| Cloud Build | Auto-trigger bisa silent-fail — trigger manual jika perlu |
| Region | `asia-southeast1` (bukan southeast2) |

---

## 🗓️ Track Record

| Versi | Tanggal | Highlight |
|-------|---------|-----------|
| v1.0 | 2025 | Bot Telegram dasar + Gemini + DeepSeek + Distance Matrix |
| v2.0 | 2025 | /monitor + n8n + logging + service account |
| v3.1 | 2025 | Gemini 3.1 Pro + Routes API v2 + Places (New) + Dashboard awal |
| v4.0 | 2025 | Clean Architecture refactor (domain/services/adapters) |
| v5.0 | 2025 | Pipeline fix + structured logging + resilience |
| v5.1 | 2025 | Agentic redesign — regex-first, no false fraud flags |
| v5.2 | 2025 | Address extraction fix, formatter cleanup |
| v5.3 | 2026 | Dual-model + jitter backoff + circuit breaker |
| v5.4 | 2026 | Naive Bayes fraud scoring + confidence-weighted evidence |
| v5.5 | 2026-02 | Resolve 4 production failures (geocode/timeout/false-positive/score) |
| v5.5+ | 2026-03 | Dashboard: Firestore real queries, nav fix, delete, sound, AQI, detail |

→ [`CHANGELOG.md`](./CHANGELOG.md) — detail tiap commit
→ [`POSTMORTEM.md`](./POSTMORTEM.md) — catatan kesalahan AI selama development
