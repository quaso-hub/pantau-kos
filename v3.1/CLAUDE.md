# GOD EYE — Master Blueprint v2
> Instruksi LENGKAP dan FINAL untuk GitHub Copilot Agent.
> Baca SELURUHNYA sebelum menulis satu baris kode.
> Jangan downgrade model. Implement semua fitur.

---

## ⚠️ KOREKSI DARI VERSI SEBELUMNYA

1. **SDK Gemini**: Pakai `google-genai` (BUKAN `google-generativeai` yang deprecated)
2. **Model Gemini**: `gemini-3.1-pro-preview` — BUKAN 2.0-flash.
   Gemini 3.1 Pro Preview sudah LIVE di Gemini API per Februari 2026.
   Referensi: https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview
3. **Routes API**: BUKAN Distance Matrix API (lebih akurat, mendukung traffic realtime)
4. **Domain Cloud Run**: Gunakan fitur Custom Domains di Cloud Run UI, BUKAN A record biasa
   karena Cloud Run tidak punya IP statis.

---

## KONTEKS PROYEK

Sistem pencari kos-kosan cerdas, personal use untuk 1 mahasiswa UBAYA Tenggilis Surabaya.
- Referensi: UBAYA Tenggilis (-7.3275, 112.7858)
- Target harga: Rp 500.000–650.000/bulan
- Filter scraper: Rp 300.000–800.000/bulan (toleransi lebar)
- Radius: ≤15km dari UBAYA

---

## ARSITEKTUR SISTEM LENGKAP

```
┌────────────────── DATA SOURCES ──────────────────────────────┐
│                                                               │
│  mamikos.com        ─┐                                        │
│  olx.co.id          ─┤                                        │
│  rumah123.com       ─┤  Scraper di n8n (VM: n8n.ikrn.engineer)│
│  sewakost.com       ─┤  Schedule tiap 2-6 jam                 │
│  kost.com           ─┤  → POST /monitor ke Cloud Run          │
│  99.co              ─┘                                        │
│                                                               │
│  IG / Twitter / Threads / Forum / Berita                      │
│  → TIDAK di-scrape langsung (risiko block)                    │
│  → Diakses via Gemini Google Search grounding saat analisis   │
└───────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────── CLOUD RUN ──────────────────────────────────┐
│  god-eye-XXX.asia-southeast1.run.app                          │
│  (custom domain: god-eye.ikrn.engineer via Cloud Run UI)      │
│                                                               │
│  /webhook    ← Telegram bot (user kirim screenshot/teks)      │
│  /monitor    ← n8n scraper (listing baru, auth X-Secret)      │
│  /dashboard  ← Web dashboard (browser)                        │
│  /health     ← uptime check                                   │
│                                                               │
│  ANALYSIS ENGINE (asyncio.gather — semua paralel):            │
│  ├── Gemini 3.1 Pro Preview + Google Search grounding         │
│  │   → Vision analisis foto kamar                            │
│  │   → Search nomor WA (GetContact, laporan penipuan)        │
│  │   → Search IG/Twitter/Threads/forum untuk listing ini     │
│  │   → Search harga pasar kos area 2026                      │
│  │   → Search reputasi area (berita kriminal, banjir, dll)   │
│  ├── DeepSeek v3 (deepseek-chat)                              │
│  │   → Analisis risiko bahasa Indonesia                       │
│  │   → Rekomendasi final + pertanyaan survei                  │
│  ├── Routes API → jarak + waktu 3 scenario                    │
│  ├── Places API (New) → fasilitas sekitar 1km                 │
│  ├── Air Quality API → AQI area kos                           │
│  └── Address Validation + Geocoding API                       │
│                                                               │
│  FIRESTORE BRAIN:                                             │
│  ├── kos_listings      (semua yang pernah dianalisis)         │
│  ├── user_preferences  (dipelajari dari feedback 👍👎)        │
│  ├── area_cache        (data area, update 24 jam)             │
│  └── blacklist         (nomor/akun penipu teridentifikasi)    │
└───────────────────────────────────────────────────────────────┘
              │                          │
              ▼                          ▼
     Telegram Bot                 Web Dashboard
     (notif realtime,             god-eye.ikrn.engineer
      inline buttons,             (history semua listing,
      analisis manual)            stats, filter, map view)
```

---

## STACK TEKNIS

```
requirements.txt:
  google-genai>=1.0.0           # SDK terbaru — WAJIB, bukan google-generativeai
  google-cloud-firestore>=2.19.0
  flask>=3.0.0
  python-telegram-bot>=21.6
  httpx>=0.27.0
  Pillow>=10.0.0
```

---

## ENV VARIABLES

```bash
TELEGRAM_TOKEN          # @BotFather
GEMINI_API_KEY          # Google AI Studio — untuk gemini-3.1-pro-preview
MAPS_API_KEY            # Google Maps Platform
DEEPSEEK_API_KEY        # platform.deepseek.com
ALLOWED_CHAT_ID         # Telegram chat ID pemilik bot
GOOGLE_CLOUD_PROJECT    # GCP project ID (untuk Firestore)
N8N_WEBHOOK_SECRET      # Secret untuk auth request dari n8n
PORT                    # 8080 (Cloud Run default)
GEMINI_MODEL            # gemini-3.1-pro-preview (configurable via env)
```

---

## FILE STRUCTURE

```
god-eye/
├── main.py
├── requirements.txt
├── Dockerfile
├── deploy.cmd
│
├── bot/
│   ├── __init__.py
│   ├── handlers.py       # Telegram message handlers
│   ├── keyboards.py      # Inline keyboard buttons
│   └── formatter.py      # Format laporan Markdown Telegram
│
├── engine/
│   ├── __init__.py
│   ├── analyzer.py       # Orchestrate pipeline, asyncio.gather
│   ├── gemini_client.py  # Gemini 3.1 Pro + Google Search grounding
│   ├── deepseek_client.py
│   └── maps_client.py    # Routes, Places, AirQuality, Address Validation
│
├── memory/
│   ├── __init__.py
│   ├── firestore.py      # Async Firestore CRUD
│   ├── learning.py       # Self-learning dari feedback
│   └── scoring.py        # Scoring 0-100
│
├── monitor/
│   ├── __init__.py
│   └── receiver.py       # /monitor endpoint dari n8n
│
└── web/
    ├── dashboard.py      # Flask routes web dashboard
    └── templates/
        ├── base.html
        ├── index.html    # Daftar listing + filter
        └── detail.html   # Detail satu listing
```

---

## GEMINI CLIENT — CARA BENAR PAKAI SDK BARU

```python
# engine/gemini_client.py
import os
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview")

async def analyze(text: str, image_bytes: bytes | None, phones: list[str]) -> dict:
    parts = []

    if image_bytes:
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))

    parts.append(types.Part.from_text(text=build_prompt(text, phones)))

    response = client.models.generate_content(
        model=MODEL,
        contents=[types.Content(role="user", parts=parts)],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[types.Tool(google_search=types.GoogleSearch())],
            thinking_config=types.ThinkingConfig(thinking_level="high"),
            response_mime_type="application/json",
        ),
    )

    import json
    return json.loads(response.text)
```

---

## GEMINI SYSTEM PROMPT

```python
SYSTEM_PROMPT = """
Kamu analis properti + investigator penipuan untuk mahasiswa UBAYA Surabaya 2026.
UBAYA Tenggilis: Jl. Raya Kalirungkut (-7.3275, 112.7858).

GUNAKAN Google Search untuk semua poin yang butuh info realtime:

1. EKSTRAKSI LOKASI
   - Nama jalan/kelurahan dari teks atau foto
   - Estimasi koordinat (lat, lng)

2. ANALISIS FOTO (jika ada gambar)
   - Estimasi ukuran kamar (m²)
   - Kondisi: bersih/sedang/buruk
   - Kamar mandi: dalam/luar/tidak terlihat
   - Furnitur yang terlihat
   - Foto asli atau stock photo? (cek watermark, shadow, metadata visual)
   - Red flags visual

3. CEK NOMOR TELEPON — SEARCH: "{nomor} getcontact penipuan kos surabaya"
   - Tersimpan sebagai apa di GetContact/Truecaller?
   - Ada laporan penipuan?
   - Ditemukan di forum/grup kos Surabaya?
   - Cek juga di IG/Twitter/Threads apakah nomor ini pernah dilaporkan

4. CEK LISTING INI DI INTERNET — SEARCH: foto/harga/lokasi spesifik
   - Apakah listing ini muncul di platform lain dengan info berbeda?
   - Ada yang pernah review/komplain tentang kos ini di media sosial?
   - Foto ini pernah dipakai untuk penipuan sebelumnya?

5. REPUTASI AREA — SEARCH: "keamanan {area} surabaya 2026" + "kriminal {area}"
   - Tingkat kriminalitas area
   - Aman pulang malam jam 21.00?
   - Ada masalah banjir, macet parah?
   - Karakter area: hunian mahasiswa/industri/campuran

6. HARGA PASAR — SEARCH: "harga kos {area} surabaya 2026"
   - Kisaran harga pasar normal di area ini
   - Harga yang ditawarkan: murah/sesuai/mahal?

7. RED FLAGS POSTINGAN
   - Harga terlalu murah dibanding pasar
   - Copy-paste template
   - Akun baru, tidak ada history

Kembalikan JSON murni, tanpa markdown:
{
  "location_text": "nama lokasi",
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
```

---

## MAPS CLIENT — ROUTES API (bukan Distance Matrix)

```python
# engine/maps_client.py
import httpx, os

MAPS_KEY = os.environ["MAPS_API_KEY"]
UBAYA = {"latitude": -7.3275, "longitude": 112.7858}

SCENARIOS = [
    {"label": "🌅 Pagi 06.00",  "hour": 6,  "minute": 0},
    {"label": "🌞 Siang 12.30", "hour": 12, "minute": 30},
    {"label": "🌙 Malam 21.00", "hour": 21, "minute": 0},
]

async def get_routes(destination_coords: dict) -> list[dict]:
    """Pakai Routes API v2 dengan traffic awareness."""
    from datetime import datetime, timezone

    results = []
    async with httpx.AsyncClient() as client:
        for scenario in SCENARIOS:
            # Construct departure time untuk hari kerja Senin depan
            now = datetime.now(timezone.utc)
            # ... logic set weekday departure time

            body = {
                "origin": {"location": {"latLng": UBAYA}},
                "destination": {"location": {"latLng": destination_coords}},
                "travelMode": "DRIVE",
                "routingPreference": "TRAFFIC_AWARE",
                "departureTime": now.isoformat(),  # set sesuai scenario
                "computeAlternativeRoutes": False,
                "languageCode": "id",
            }

            resp = await client.post(
                "https://routes.googleapis.com/directions/v2:computeRoutes",
                json=body,
                headers={
                    "X-Goog-Api-Key": MAPS_KEY,
                    "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.legs.steps.navigationInstruction",
                },
                timeout=10,
            )
            data = resp.json()
            route = data.get("routes", [{}])[0]
            results.append({
                "label": scenario["label"],
                "duration_minutes": int(route.get("duration", "0s").rstrip("s")) // 60,
                "distance_km": round(route.get("distanceMeters", 0) / 1000, 1),
            })

    return results

async def get_aqi(coords: dict) -> dict:
    """Air Quality API."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://airquality.googleapis.com/v1/currentConditions:lookup",
            json={"location": {"latitude": coords["lat"], "longitude": coords["lng"]}},
            params={"key": MAPS_KEY},
            timeout=10,
        )
        data = resp.json()
        indexes = data.get("indexes", [{}])
        aqi = indexes[0].get("aqi", 0) if indexes else 0
        category = indexes[0].get("category", "") if indexes else ""
        return {"aqi": aqi, "category": category}

async def get_nearby_places(coords: dict) -> list[dict]:
    """Places API (New)."""
    place_types = ["supermarket", "hospital", "police", "atm", "mosque", "laundry"]
    results = []
    async with httpx.AsyncClient() as client:
        for ptype in place_types:
            resp = await client.post(
                "https://places.googleapis.com/v1/places:searchNearby",
                json={
                    "includedTypes": [ptype],
                    "locationRestriction": {
                        "circle": {
                            "center": {"latitude": coords["lat"], "longitude": coords["lng"]},
                            "radius": 1000.0,
                        }
                    },
                    "maxResultCount": 1,
                },
                headers={
                    "X-Goog-Api-Key": MAPS_KEY,
                    "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating",
                },
                timeout=10,
            )
            places = resp.json().get("places", [])
            if places:
                results.append({"type": ptype, "name": places[0].get("displayName", {}).get("text", ""), "found": True})
            else:
                results.append({"type": ptype, "found": False})
    return results
```

---

## SCORING (0-100)

```python
def calculate(price, distance_km, gemini, prefs) -> int:
    score = 50

    # Harga ±20
    if 450_000 <= price <= 550_000: score += 20
    elif 550_001 <= price <= 650_000: score += 15
    elif 300_000 <= price < 450_000: score += 8
    elif 650_001 <= price <= 800_000: score += 5
    else: score -= 20

    # Jarak ±20
    if distance_km <= 5: score += 20
    elif distance_km <= 8: score += 15
    elif distance_km <= 12: score += 8
    elif distance_km <= 15: score += 3
    else: score -= 20

    # Keaslian ±25
    if gemini["authenticity"] == "tinggi": score += 15
    elif gemini["authenticity"] == "rendah": score -= 25
    if not gemini["phone_check"]["trusted"]: score -= 10

    # Post red flags
    score -= len(gemini.get("post_flags", [])) * 5

    # Listing ditemukan di tempat lain dengan info berbeda
    if gemini["listing_web_check"].get("duplicate_photos"): score -= 20

    # Kamar ±10
    if gemini["room"]["bathroom"] == "dalam": score += 8
    if gemini["room"]["condition"] == "baik": score += 5

    # Area ±15
    crime = gemini["area"]["crime_level"]
    if crime == "rendah": score += 10
    elif crime == "tinggi": score -= 15
    if gemini["area"].get("flood_risk"): score -= 10
    if gemini["area"].get("safe_night"): score += 5

    # Preferensi user ±15
    loc = gemini.get("location_text", "")
    if any(a in loc for a in prefs.get("preferred_areas", [])): score += 15
    if any(a in loc for a in prefs.get("avoided_areas", [])): score -= 15

    return max(0, min(100, score))
```

---

## SELF-LEARNING

```python
# memory/learning.py
async def on_feedback(listing_id: str, action: str):
    """Dipanggil setiap kali user tap inline button."""
    listing = await firestore.get_listing(listing_id)
    prefs = await firestore.get_preferences()

    kelurahan = listing.get("location_kelurahan", "")

    if action == "survey":
        # Pelajari area yang disukai
        if kelurahan and kelurahan not in prefs["preferred_areas"]:
            prefs["preferred_areas"].append(kelurahan)
        # Turunkan threshold (lebih banyak notif)
        prefs["notification_threshold"] = max(50, prefs["notification_threshold"] - 1)

    elif action == "skip":
        # Track berapa kali skip area ini
        skip_counts = prefs.setdefault("skip_counts", {})
        skip_counts[kelurahan] = skip_counts.get(kelurahan, 0) + 1
        # Setelah skip 3x area yang sama → masuk avoided
        if skip_counts[kelurahan] >= 3 and kelurahan not in prefs["avoided_areas"]:
            prefs["avoided_areas"].append(kelurahan)
        # Naikkan threshold (lebih selektif)
        prefs["notification_threshold"] = min(85, prefs["notification_threshold"] + 0.5)

    elif action == "blacklist_phone":
        phone = listing.get("phone")
        if phone:
            await firestore.add_blacklist(phone, reason=f"Dilaporkan dari listing {listing_id}")

    await firestore.save_preferences(prefs)
```

---

## TELEGRAM REPORT FORMAT

```
🔍 *GOD EYE* · Score: {score}/100 {emoji}
━━━━━━━━━━━━━━━━━━━━━━
📌 {source} · {short_url}

💰 *HARGA*
Rp {price:,}/bln {budget_icon}
{price_vs_market}

📍 *LOKASI*
{address}
[🗺️ Lihat Rute ke UBAYA]({maps_url})

🚗 *PERJALANAN*
🌅 Pagi 06.00 → {pagi} mnt
🌞 Siang 12.30 → {siang} mnt
🌙 Malam 21.00 → {malam} mnt

🌬️ AQI {aqi} — {aqi_label}

🏪 *FASILITAS 1KM*
{nearby_list}

🛏️ *KAMAR*
{room_summary}

🛡️ *AREA*
Kriminalitas: {crime} | Aman malam: {safe_night}
{area_notes}

⚠️ *RISIKO: {fraud_level}*
{fraud_detail}

📱 {phone} → {getcontact_name}
{social_findings}

🤖 *REKOMENDASI*
{recommendation}
━━━━━━━━━━━━━━━━━━━━━━
```

Buttons:
```python
[[InlineKeyboardButton("✅ Mau Survey", callback_data=f"survey_{id}")],
 [InlineKeyboardButton("❌ Skip", callback_data=f"skip_{id}")],
 [InlineKeyboardButton("📞 WA", url=f"https://wa.me/{phone}")],
 [InlineKeyboardButton("🚫 Laporkan Penipuan", callback_data=f"blacklist_{id}")]]
```

---

## WEB DASHBOARD

Route `/dashboard` — Flask + Jinja2 + Tailwind CDN (tidak perlu React/Vue).

Fitur:
- Tabel listing dengan kolom: Score, Harga, Jarak, Area, Tanggal, Status
- Filter: range harga, range jarak, area, status (pending/survey/skip)
- Sort: score ↓, date ↓, price ↑, distance ↑
- Klik row → halaman detail dengan full report
- Stats header: Total analyzed, Average score, Total surveyed
- Map embed (Maps JavaScript API): titik-titik kos warna sesuai score

Custom domain: `god-eye.ikrn.engineer`
Cara set: Cloud Run UI → Integrations → Custom Domains → tambah domain → Google guide DNS setup → Bukan A record manual.

---

## N8N WORKFLOWS — 6 SUMBER

Semua di `n8n.ikrn.engineer`. Import JSON via Settings → Import.

Struktur tiap workflow:
```
Schedule → HTTP Request (scrape) → Code (parse + filter) → Split → POST /monitor
```

Header POST ke bot:
```json
{ "X-Secret": "{{$env.N8N_SECRET}}" }
```

Body JSON tiap listing:
```json
{
  "source": "mamikos",
  "title": "...",
  "price": 500000,
  "location": "Jl. ...",
  "url": "https://...",
  "description": "...",
  "images": ["url1"],
  "scraped_at": "2026-03-07T..."
}
```

**Sumber dan jadwal:**

| Sumber | URL Scrape | Jadwal |
|--------|-----------|--------|
| Mamikos | `https://mamikos.com/cari/surabaya?sort=latest&price_max=700000` | tiap 2 jam |
| OLX | `https://www.olx.co.id/items/q-kos-surabaya?search[order]=created_at:desc` | tiap 3 jam |
| Rumah123 | `https://www.rumah123.com/properti/surabaya/kost/?sort=recent` | tiap 4 jam |
| Sewakost | `https://www.sewakost.com/kost/surabaya/?sort=new` | tiap 4 jam |
| 99.co | `https://www.99.co/id/sewa/kamar-kos?city_name=surabaya&price_max=800000&sort_by=created_at` | tiap 5 jam |
| Kost.com | `https://www.kost.com/cari-kost/surabaya/` | tiap 6 jam |

IG / Twitter / Threads / forum TIDAK di-scrape langsung — diakses via Gemini Google Search grounding saat proses analisis per listing.

---

## ERROR HANDLING WAJIB

```python
async def safe(coro, fallback=None, name=""):
    try:
        return await asyncio.wait_for(coro, timeout=15.0)
    except Exception as e:
        import logging
        logging.getLogger("god-eye").warning(f"{name} failed: {e}")
        return fallback

# Pakai:
routes, aqi, nearby = await asyncio.gather(
    safe(maps.get_routes(coords), fallback=[], name="Routes"),
    safe(maps.get_aqi(coords), fallback={}, name="AirQuality"),
    safe(maps.get_nearby(coords), fallback=[], name="Places"),
)
# Kalau 1 gagal, report tetap terkirim dengan data yang ada
```

---

## GOOGLE APIs — AKTIFKAN DI GCP CONSOLE

| API | Kegunaan |
|-----|---------|
| Routes API | Rute + traffic (BUKAN Distance Matrix) |
| Places API (New) | Fasilitas 1km |
| Geocoding API | Nama → koordinat |
| Address Validation API | Validasi alamat |
| Air Quality API | AQI |
| Maps JavaScript API | Web dashboard peta |
| Maps Static API | Gambar peta di Telegram |

---

## CATATAN FINAL UNTUK COPILOT

1. `google-genai` bukan `google-generativeai` — install package berbeda
2. Model: `gemini-3.1-pro-preview` — sudah live, tidak perlu fallback ke 2.0
3. `thinking_level="high"` untuk analisis terdalam
4. Google Search grounding aktif di SETIAP Gemini call
5. Routes API bukan Distance Matrix — endpoint berbeda, struktur response berbeda
6. Semua Firestore pakai AsyncClient
7. Telegram message max 4096 char — split kalau lebih
8. `/monitor` wajib cek `X-Secret` sebelum proses apapun
9. Web dashboard: Flask + Jinja2 + Tailwind CDN saja, tidak perlu SPA
10. Gunakan `asyncio.gather()` untuk semua API yang tidak saling dependent
