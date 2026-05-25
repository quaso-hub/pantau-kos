# n8n Ultimate Hunter Agent 🕵️

Dua file JSON ini siap di-import ke n8n (`n8n.ikrn.engineer`) sebagai **6 workflow terpisah** — 3 dari Tier 1, 3 dari Tier 2.

---

## Cara Import

1. Buka n8n → **Workflows** → **Import from file**
2. Import `n8n-scraper-tier1.json` → pilih semua 3 workflows
3. Import `n8n-scraper-tier2.json` → pilih semua 3 workflows
4. Aktifkan tiap workflow dengan toggle **Active**

---

## Arsitektur Per Workflow

```
Schedule → [Random UA] → HTTP Fetch → Parse+Filter+Dedup → IF (has results?) → Split 1-by-1 → POST /monitor
```

---

## Tier 1 — API-Based (Lebih Reliable)

| Workflow | Platform | Interval | Method |
|----------|----------|----------|--------|
| `Tier1 — Mamikos Hunter` | mamikos.com | Setiap 2 jam | JSON API |
| `Tier1 — OLX Hunter` | olx.co.id | Setiap 3 jam | REST API |
| `Tier1 — 99co Hunter` | 99.co | Setiap 5 jam | REST API |

## Tier 2 — HTML Scraping (Fallback + Extra Coverage)

| Workflow | Platform | Interval | Method |
|----------|----------|----------|--------|
| `Tier2 — Rumah123 Hunter` | rumah123.com | Setiap 4 jam | HTML (Next.js data → regex) |
| `Tier2 — Sewakost Hunter` | sewakost.com | Setiap 4 jam | HTML (JSON-LD → regex) |
| `Tier2 — Kost.com Hunter` | kost.com | Setiap 6 jam | HTML (embedded JSON → regex) |

---

## Fitur Tiap Workflow

### 🔄 Anti-Bot: User-Agent Rotation
- 5 UA pool per workflow: Chrome Windows, Safari macOS, Chrome Linux, Firefox, Mobile Chrome
- Dirotasi random setiap eksekusi
- Header tambahan: `Referer`, `Accept-Language`, `X-Requested-With`

### 🔍 Triple Pre-Filter
Sebelum dikirim ke God Eye, setiap listing dicheck:
1. **Harga**: Rp 300.000 – 800.000/bulan
2. **Lokasi**: harus mengandung kata "surabaya", "sby", atau "jawa timur"
3. **Foto**: minimal 1 URL gambar valid (http/https)

### 🧠 Deduplication (24-jam TTL)
- Menggunakan `$getWorkflowStaticData('global')` — persisten lintas eksekusi
- Key unik: `{source}_{id/slug}`
- Auto-cleanup entry yang lebih dari 24 jam → tidak ada memory leak

### 📦 Kirim Satu-per-Satu
- `splitInBatches` dengan batchSize=1
- Rate limiting natural → tidak spam /monitor
- `neverError: true` → workflow tidak berhenti jika satu listing gagal dikirim

---

## Payload Format ke /monitor

```json
{
  "source": "mamikos",
  "title": "Kos Putra Dekat UBAYA",
  "price": 550000,
  "location": "Jl. Raya Tenggilis, Tenggilis Mejoyo, Surabaya",
  "url": "https://mamikos.com/kamar/kos-putra-ubaya-123",
  "description": "Kamar 3x4m, AC, WiFi...",
  "images": ["https://cdn.mamikos.com/photo1.jpg", "..."],
  "scraped_at": "2026-03-07T10:30:00.000Z"
}
```

---

## Environment Variable yang Dibutuhkan

Di n8n Settings → **Environment Variables** (atau `.env`):
```
N8N_SECRET=<nilai_sama_dengan_SECRET_KEY_di_Cloud_Run>
```

---

## Tier 2 — HTML Parsing Strategy

Karena Tier 2 adalah website biasa (bukan API), parser menggunakan **strategi berlapis**:

1. **Layer 1 — Embedded JSON**: Cek `__NEXT_DATA__`, `__INITIAL_STATE__`, JSON-LD structured data  
   → Lebih akurat, dapat semua field
2. **Layer 2 — Regex Fallback**: Jika tidak ada embedded JSON, scan HTML  
   → Extract URL (`href`), harga (`Rp xxx.xxx`), gambar (`src=`), judul (`<h2>/<h3>`)
3. **Layer 3 — Best-effort pairing**: Pasangkan URL + harga + gambar dari halaman

> **Note**: Tier 2 lebih rentan terhadap perubahan struktur HTML. Jika tiba-tiba 0 hasil, cek apakah website berubah template dan update regex di Code node.

---

## Troubleshooting

| Gejala | Kemungkinan Penyebab | Solusi |
|--------|---------------------|--------|
| Workflow error di HTTP node | Website block / rate limit | Cek log, tambah delay atau rotate IP |
| 0 hasil terus dari Tier 2 | Template HTML berubah | Buka console.log, lihat raw HTML, update regex |
| Listing sama muncul terus | Static data ter-reset (n8n restart) | Normal — akan clear setelah 24h |
| /monitor HTTP 401 | N8N_SECRET tidak cocok | Sync value dengan Cloud Run env |
| /monitor HTTP 422 | Payload field kurang | Pastikan semua field wajib ada |
