# 🚀 LANGSUNG JAM! - Copy-Paste di PythonAnywhere Bash Console

## STEP 1: Clone Repository (jalankan satu per satu)

```bash
cd ~
git clone https://github.com/quaso-hub/pantau-kos.git kost-bot
```

Tunggu selesai sampai prompt kembali. Harus lihat:
```
✓ Repository sudah ter-clone
✓ Folder kost-bot ada di /home/sadas/
```

---

## STEP 2: Buat Virtual Environment

```bash
mkvirtualenv --python=/usr/bin/python3.11 kos_bot
```

Tunggu sampai prompt berubah jadi:
```
(kos_bot) sadas@...~$
```

---

## STEP 3: Install Packages

```bash
workon kos_bot
pip install --upgrade pip
```

Tunggu selesai, terus:

```bash
pip install -r ~/kost-bot/requirements.txt
```

Ini ambil waktu 5-10 menit. Tunggu sampai selesai.

---

## STEP 4: Verify (pastikan OK)

```bash
python -c "import flask; import asyncpg; import telegram; print('✓ All packages OK!')"
```

Seharusnya output: `✓ All packages OK!`

---

## 🎯 Selesai Bash Console!

Sekarang pergi ke **Web Tab** di PythonAnywhere dan ikuti di bawah:

---

# 📝 WEB TAB CONFIGURATION

## 1. Klik tab "Web"

---

## 2. Click di domain: sadas.pythonanywhere.com

---

## 3. Scroll ke "Source code"

Ganti dari:
```
/home/sadas/mysite
```

Menjadi:
```
/home/sadas/kost-bot
```

---

## 4. Scroll ke "Working directory"

Ganti dari:
```
/home/sadas/
```

Menjadi:
```
/home/sadas/kost-bot
```

---

## 5. Scroll ke "WSGI configuration file"

Klik link file: `/var/www/sadas_pythonanywhere_com_wsgi.py`

---

## 6. Di WSGI Editor (yang terbuka):

**Delete SEMUA isi**, terus paste ini:

```python
import sys
import os

project_home = os.path.expanduser('~/kost-bot')
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.chdir(project_home)

try:
    from infrastructure.logger import setup_logging
    setup_logging()
except Exception as e:
    print(f"Warning: Could not setup logging: {e}")

from main import app as application
```

Klik **Save** (tombol di atas)

---

## 7. Kembali ke Web Tab

---

## 8. Scroll ke "Virtualenv"

Isi dengan:
```
/home/sadas/.virtualenvs/kos_bot
```

Press **Enter**

---

## 9. Scroll ke bawah, klik **Reload** (tombol hijau)

Tunggu sampai tombol jadi abu-abu terus hijau lagi (15 detik)

---

## 10. Add Environment Variables

Klik **Account** (top right)

---

## 11. Click menu > Environment variables

---

## 12. Add 3 variables:

### Variable 1:
```
Name: DATABASE_URL
Value: postgresql://neondb_owner:npg_PASSWORD@ep-withered-feather-aotbugls.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
```
(Ganti PASSWORD dengan password database Neon kamu)

### Variable 2:
```
Name: TELEGRAM_BOT_TOKEN
Value: YOUR_BOT_TOKEN
```
(Ganti YOUR_BOT_TOKEN dengan token dari @BotFather)

### Variable 3:
```
Name: GEMINI_API_KEY
Value: YOUR_GEMINI_API_KEY
```
(Ganti YOUR_GEMINI_API_KEY dengan API key kamu)

---

## 13. Back to Web Tab > Click Reload lagi

---

## ✅ SELESAI!

---

# 🧪 TEST

## Test 1: Health Endpoint
Buka browser, pergi ke:
```
https://sadas.pythonanywhere.com/health
```

Seharusnya lihat:
```json
{"status": "ok"}
```

Jika error 502:
1. Check error log (link orange di Web tab)
2. Baca error message
3. Fix dan reload lagi

## Test 2: Dashboard
```
https://sadas.pythonanywhere.com/dashboard
```

Seharusnya lihat halaman HTML

## Test 3: Telegram Bot

Di local terminal (bukan PythonAnywhere):
```bash
curl -X POST https://api.telegram.org/botTOKEN/setWebhook \
     -H "Content-Type: application/json" \
     -d '{"url": "https://sadas.pythonanywhere.com/webhook"}'
```

Ganti TOKEN dengan bot token kamu.

Response harus:
```json
{"ok":true,"result":true}
```

Terus buka Telegram, cari bot kamu, send `/start`. Bot harus reply!

---

# ⚠️ Jika Ada Masalah

1. **Error 502**: Lihat error log, biasanya ada clue
2. **ImportError**: Berarti pip install belum complete, run lagi
3. **Bot tidak respond**: Check DATABASE_URL dan TELEGRAM_BOT_TOKEN di environment
4. **Dashboard blank**: Test /health dulu

---

🎉 **DONE! Your bot is LIVE!**
