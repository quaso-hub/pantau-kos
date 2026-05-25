# 🚀 PythonAnywhere Deployment - Simple Checklist

Berikut adalah instruksi yang sudah disederhanakan untuk Anda. Ikuti satu per satu.

---

## ✅ CHECKLIST DEPLOYMENT

### Step 1: Clone Repository (3 menit)
**Di PythonAnywhere Bash Console:**

```bash
cd ~
git clone https://github.com/quaso-hub/pantau-kos.git kost-bot
cd kost-bot
ls
```

**Expected:** Anda lihat `main.py`, `requirements.txt`, folder `v2`

---

### Step 2: Create Virtual Environment (2 menit)
**Di PythonAnywhere Bash Console:**

```bash
mkvirtualenv --python=/usr/bin/python3.11 kos_bot
```

**Expected:** Prompt berubah jadi `(kos_bot) ...`

---

### Step 3: Install Packages (5 menit)
**Di PythonAnywhere Bash Console:**

```bash
workon kos_bot
pip install --upgrade pip
pip install -r ~/kost-bot/requirements.txt
```

**Expected:** Selesai tanpa error

---

### Step 4: Update WSGI File (3 menit)
**Di PythonAnywhere Web Tab:**

1. Klik **Web** tab
2. Klik domain Anda `sadas.pythonanywhere.com`
3. Scroll ke **WSGI configuration file**
4. Klik file link (biasanya: `/var/www/sadas_pythonanywhere_com_wsgi.py`)
5. **Delete semua isi**, ganti dengan ini:

```python
import sys
import os
project_home = os.path.expanduser('~/kost-bot')
if project_home not in sys.path:
    sys.path.insert(0, project_home)
os.chdir(project_home)
from infrastructure.logger import setup_logging
setup_logging()
from main import app as application
```

6. Klik **Save**

---

### Step 5: Set Virtual Environment Path (1 menit)
**Di PythonAnywhere Web Tab (sama window):**

1. Cari section **Virtualenv**
2. Isi path ini:
   ```
   /home/sadas/.virtualenvs/kos_bot
   ```
3. Tekan **Enter**

---

### Step 6: Add Environment Variables (3 menit)
**Di PythonAnywhere Account Settings:**

1. Klik username di atas kanan
2. Pilih **Account**
3. Scroll ke **Environment variables**
4. Klik **Add a new variable**
5. Tambah ketiga variable ini:

```
DATABASE_URL = postgresql://neondb_owner:npg_PASSWORD@ep-withered-feather-aotbugls.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
TELEGRAM_BOT_TOKEN = your_bot_token
GEMINI_API_KEY = your_gemini_api_key
```

(Ganti `PASSWORD`, `your_bot_token`, `your_gemini_api_key` dengan nilai asli Anda)

---

### Step 7: Reload Web App (2 menit)
**Di PythonAnywhere Web Tab:**

1. Kembali ke Web tab
2. Klik tombol hijau **Reload** di atas
3. Tunggu 10 detik

**Expected:** Tombol berubah jadi gray untuk sebentar, lalu green lagi

---

### Step 8: Test Health Endpoint (1 menit)
**Di browser:**

Buka: `https://sadas.pythonanywhere.com/health`

**Expected output:**
```json
{"status": "ok"}
```

**Jika error 502 atau error lain:**
- Klik **Error log** di Web tab
- Lihat pesan error
- Kembali ke step 4-7 dan check lagi

---

### Step 9: Configure Telegram Webhook (2 menit)
**Di komputer lokal Anda (terminal):**

```bash
curl -X POST https://api.telegram.org/bot<TOKEN>/setWebhook \
     -H "Content-Type: application/json" \
     -d '{"url": "https://sadas.pythonanywhere.com/webhook"}'
```

**Ganti `<TOKEN>` dengan token bot asli Anda!**

**Expected response:**
```json
{"ok":true,"result":true}
```

---

### Step 10: Test Telegram Bot (1 menit)
**Di Telegram:**

1. Buka aplikasi Telegram
2. Cari bot Anda (misal: @YourBotName)
3. Kirim command: `/start`
4. Bot seharusnya reply dengan pesan welcome

**Jika tidak ada response:**
- Tunggu 30 detik
- Coba lagi
- Check error log di PythonAnywhere

---

### Step 11: Test Dashboard (1 menit)
**Di browser:**

Buka: `https://sadas.pythonanywhere.com/dashboard`

**Expected:** Tampil halaman dashboard dengan table kos listings (mungkin masih kosong kalau belum ada data)

---

## 📊 Status Checklist

```
[✓] Clone repository
[✓] Create virtual environment
[✓] Install packages
[✓] Update WSGI file
[✓] Set virtualenv path
[✓] Add environment variables
[✓] Reload web app
[✓] Test health endpoint
[✓] Configure Telegram webhook
[✓] Test Telegram bot
[✓] Test dashboard
```

---

## 🎉 SELESAI!

Jika semua berhasil, sistem Anda sudah LIVE!

- Website: `https://sadas.pythonanywhere.com`
- Bot: Aktif di Telegram
- Dashboard: Bisa diakses
- Database: Connected ke Neon PostgreSQL

---

## ⚠️ Jika Ada Error

**Error 502 Bad Gateway:**
- Klik Error log
- Lihat pesan error
- Paling sering: path salah atau dependency missing
- Solusi: reload web app lagi

**Bot tidak merespons:**
- Pastikan DATABASE_URL benar di environment variables
- Pastikan TELEGRAM_BOT_TOKEN benar
- Cek error log
- Tunggu 1 menit, coba lagi

**Dashboard tidak muncul:**
- Pastikan /health endpoint bisa diakses
- Check error log
- Reload web app

---

## 📞 Support

Jika stuck di mana:
1. Check PythonAnywhere error log (paling penting!)
2. Verify environment variables sudah di-set
3. Reload web app
4. Check path-path sudah benar

Good luck! 🚀
