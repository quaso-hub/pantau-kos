# POSTMORTEM — God Eye Kos-Bot: Catatan Kebodohan AI

> Ini catatan jujur setiap kesalahan, asumsi salah, shortcut bebal, dan insiden blunder
> yang dilakukan oleh AI (GitHub Copilot) selama development project ini.
> Tujuan: transparansi penuh, bahan pembelajaran, dan cegah blunder serupa.

---

## 📋 Index

| # | Tanggal | Insiden | Severity |
|---|---------|---------|----------|
| 1 | 2026-03-07 | Dashboard stub data tidak pernah diketahui | Medium |
| 2 | 2026-03-07 | Navigation bug: `listing_id` vs `id` field | High |
| 3 | 2026-03-08 | 500 error: 3 penyebab berbeda, fix bertahap | High |
| 4 | 2026-03-08 | Fix hotfix (fc55ba8) tidak menyelesaikan 500 | Critical |
| 5 | 2026-03-08 | Cloud Build auto-trigger — tidak disadari gagal | Medium |
| 6 | 2026-03-08 | Region Cloud Run salah disebut (southeast2 vs southeast1) | Low |
| 7 | 2026-03-08 | Push terakhir (`2697e22`) tertunda oleh summarization | Low |

---

## Insiden #1 — Dashboard Stub Data Tidak Pernah Diketahui

**Tanggal:** 2026-03-07
**Severity:** Medium

### Apa yang Terjadi
AI mengimplementasikan `web/dashboard.py` dengan fungsi `_get_listings()` dan `_get_stats()`
yang mengembalikan **data hardcoded/stub** — bukan query Firestore nyata. Dashboard "berhasil"
ditampilkan, loading, kelihatan bagus, tapi semua data palsu.

### Mengapa Bisa Terjadi
AI fokus pada struktur template dan UI, menunda koneksi Firestore dengan asumsi
"ini bisa diisi nanti." Tidak ada tes end-to-end yang memvalidasi apakah data nyata muncul.

### Dampak
User tidak tahu dashboard tidak menampilkan data asli. Butuh commit tambahan (`f07b8a7`)
hanya untuk hal yang seharusnya ada dari awal.

### Pelajaran
Jangan pernah ship stub data ke production tanpa komentar eksplisit `# TODO: STUB`.
Selalu sambungkan ke data source nyata, atau fail fast dengan error message.

---

## Insiden #2 — Navigation Bug: `listing_id` vs `id` Field

**Tanggal:** 2026-03-07
**Severity:** High

### Apa yang Terjadi
User klik listing card di dashboard → tidak bisa navigate ke halaman detail.
URL yang dihasilkan: `/dashboard/undefined` — karena `l.id` undefined di JS.

### Root Cause
`_get_listings()` fetch dari Firestore dan mengembalikan dict dengan key `listing_id`
(dari document field). Template HTML dan JS mengakses `l.id` yang tidak ada.

### Mengapa Bisa Terjadi
AI menulis template dengan asumsi field bernama `id`, padahal Firestore document
menggunakan `listing_id` sebagai field name. Tidak ada tes navigasi end-to-end.

### Dampak
Dashboard tidak berfungsi sama sekali untuk navigasi. Harus fix di commit terpisah.

### Fix
- Python: `item['id'] = item.get('listing_id')` di `_get_listings()`
- Jinja: `{{ l.listing_id or l.id }}`
- JS: `l.listing_id || l.id`

### Pelajaran
Selalu audit field names antara apa yang Firestore kembalikan vs apa yang template ekspektasikan.
Cek dengan query sederhana sebelum menulis template.

---

## Insiden #3 — 500 Error: 3 Penyebab Berbeda

**Tanggal:** 2026-03-08
**Severity:** High

### Apa yang Terjadi
Setelah deploy `3983ddd`, semua halaman detail (`/dashboard/<id>`) mengembalikan 500 error.

### Root Causes (3 sekaligus)

**3a. Geocode sebagai GeoPoint object**
Firestore menyimpan geocode sebagai `google.cloud.firestore.GeoPoint` object.
Template mencoba akses `listing.geocode.lat` — GeoPoint punya `.latitude` dan `.longitude`,
bukan `.lat` dan `.lng`. Crash: `AttributeError`.

**3b. air_quality dot-access**
`listing.air_quality` adalah Python `dict`. Di Jinja2, `listing.air_quality.aqi` tidak sama
dengan `listing.air_quality['aqi']` — Jinja2 mencoba attribute access dulu, lalu key.
Tapi `dict` tidak punya attribute `aqi`. Crash: `UndefinedError`.

**3c. Price formatting None**
`"{:,}".format(None)` → `TypeError`. Beberapa listing di Firestore tidak punya field `price`.

### Mengapa Bisa Terjadi
AI menulis template dengan asumsi struktur data yang "idealized" — tidak mengecek
bentuk asli data Firestore. GeoPoint adalah tipe spesifik Firestore, bukan dict biasa.

### Fix
Normalisasi semua nested fields di `dashboard.py` sebelum kirim ke template:
- GeoPoint → `has_geo`, `geo_lat`, `geo_lng` (flat float)
- air_quality dict → `aqi_value`, `aqi_category` (flat scalar)
- price → default 0 jika None

### Pelajaran
Selalu flatten/normalize Firestore objects sebelum kirim ke template.
GeoPoint, Timestamp, DocumentReference — semua perlu explicit conversion.

---

## Insiden #4 — Hotfix `fc55ba8` Tidak Menyelesaikan 500 Error

**Tanggal:** 2026-03-08
**Severity:** Critical

### Apa yang Terjadi
AI mengidentifikasi 3 penyebab 500 error (insiden #3), commit hotfix `fc55ba8`, trigger build.
Build SUCCESS. Deploy. **Masih 500.** AI bingung.

Investigasi lebih lanjut menemukan penyebab SEBENARNYA yang terlewat:
**Extra `{% endif %}` di `detail.html`** — delete modal yang ditambahkan di commit `3983ddd`
disisipkan SETELAH `{% endif %}` penutup blok utama, lalu diikuti `{% else %}` (not-found branch).
Hasil: `{% else %}` punya `{% endif %}` tapi tidak punya `{% if %}` — Jinja2 `TemplateSyntaxError`.

### Mengapa Terlewat
AI melakukan insert kode baru (delete modal) dengan `replace_string_in_file` tanpa
memverifikasi balance tag Jinja setelahnya. AI percaya diri template "pasti benar"
karena logika HTML-nya sudah benar.

### Dampak
- Satu commit hotfix ekstra (`fc55ba8`) yang tidak perlu jika root cause sudah benar dari awal
- Satu manual Cloud Build trigger yang sia-sia
- Downtime lebih lama dari seharusnya

### Fix
Commit `2697e22`: delete modal dipindah ke dalam blok `{% if listing %}`, sebelum `{% else %}`.

### Cara Deteksi
```python
import re
depth = 0
for tag in re.findall(r'{%-?\s*(if|else|elif|endif|for|endfor)[^}]*-?%}', template):
    keyword = tag.strip().split()[0]
    if keyword in ('if', 'for'): depth += 1
    elif keyword in ('endif', 'endfor'): depth -= 1
print(f"Final depth: {depth}")  # harus 0
```

### Pelajaran
**Setelah setiap insert/edit di Jinja template: jalankan balance check.**
Jangan trust HTML structure tanpa verifikasi Jinja block depth.

---

## Insiden #5 — Cloud Build Auto-Trigger Tidak Disadari Gagal

**Tanggal:** 2026-03-07 s/d 2026-03-08
**Severity:** Medium

### Apa yang Terjadi
Push `3983ddd` ke `main` → Cloud Build trigger tidak firing.
Push `fc55ba8` → sama, tidak firing.
AI tidak menyadari ini sampai user melaporkan perubahan tidak tampak di production.

### Mengapa Bisa Terjadi
AI tidak memonitor Cloud Build setelah `git push`. Asumsi: push → auto-build → auto-deploy
selalu berjalan. Tidak ada validasi "apakah build sedang berjalan?"

### Dampak
Beberapa push stuck di origin tanpa deploy. User melihat UI lama terus.

### Workaround
```bash
gcloud builds triggers run rmgpgab-god-eye-asia-southeast1-quaso-hub-pantau-kos--mabje --branch=main
```

### Pelajaran
Setelah setiap push yang penting, selalu verifikasi:
```bash
gcloud builds list --limit=3 --project=kos-monitor
```
Jangan assume auto-trigger berjalan.

---

## Insiden #6 — Region Cloud Run Salah Disebut

**Tanggal:** 2026-03-08
**Severity:** Low

### Apa yang Terjadi
Di satu titik dalam conversation, AI menyebut region Cloud Run sebagai `asia-southeast2`
padahal yang benar adalah `asia-southeast1`. Beberapa command gcloud yang digenerate
bisa saja salah region jika tidak dicross-check.

### Pelajaran
Selalu verifikasi region dengan:
```bash
gcloud run services describe god-eye --format="value(metadata.labels['cloud.googleapis.com/location'])"
```

---

## Insiden #7 — Push Terakhir Tertunda oleh Summarization

**Tanggal:** 2026-03-08
**Severity:** Low

### Apa yang Terjadi
Commit `2697e22` sudah di-commit. AI akan menjalankan `git push` sebagai langkah berikutnya.
Persis sebelum tool call `git push`, conversation summarization triggered — konteks di-compress.
Session baru dimulai tanpa mengetahui push belum dilakukan.

### Dampak
Minimal — push diselesaikan di awal session berikutnya. Tidak ada data loss.

### Pelajaran
Untuk operasi critical (push, deploy, database migration), idealnya lakukan dalam satu
tool call bersama commit:
```bash
git add . && git commit -m "..." && git push
```
Jangan pisahkan commit dan push ke dua langkah berbeda jika bisa dihindari.

---

## Ringkasan Pola Kesalahan

| Pola | Frekuensi | Contoh |
|------|-----------|--------|
| Asumsi struktur data tanpa verifikasi | ⭐⭐⭐⭐ | GeoPoint, listing_id vs id |
| Tidak verifikasi setelah edit | ⭐⭐⭐⭐ | Jinja balance, build status |
| Ship stub/placeholder ke production | ⭐⭐⭐ | Dashboard stub data |
| Identifikasi root cause tidak tuntas | ⭐⭐⭐ | fc55ba8 tidak fix 500 |
| Asumsi infrastruktur berjalan otomatis | ⭐⭐ | Cloud Build auto-trigger |

---

## Checklist Post-Edit (untuk masa depan)

Setelah edit Jinja template:
- [ ] Python balance check (if/endif depth = 0)
- [ ] Semua nested Firestore objects sudah di-flatten di Python, bukan di template

Setelah `git push`:
- [ ] `gcloud builds list --limit=3` — verifikasi build firing
- [ ] Tunggu build SUCCESS sebelum test di production

Setelah add feature baru ke dashboard:
- [ ] Smoke test: `Invoke-WebRequest https://god-eye.ikrn.engineer/dashboard/<id>`
- [ ] Check field names antara Firestore output dan template

---

*Last updated: 2026-03-08*
