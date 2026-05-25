# 🔧 Troubleshooting Guide untuk sadas.pythonanywhere.com

Berdasarkan screenshot konfigurasi Anda, inilah solusi untuk masalah-masalah yang mungkin terjadi.

---

## 📋 Info Akun Anda

```
Username: sadas
Domain: sadas.pythonanywhere.com
Password protection: Disabled
Python: 3.11
Source code: /home/sadas/mysite
WSGI file: /var/www/sadas_pythonanywhere_com_wsgi.py
```

**⚠️ PENTING:** Karena Anda punya account baru, pastikan:
1. Repository sudah di `/home/sadas/kost-bot` (bukan `/home/sadas/mysite`)
2. WSGI file di-update dengan kode yang benar
3. Virtualenv path di-set dengan benar

---

## ❌ Error 502 Bad Gateway

**Penyebab paling umum:**

### 1. WSGI File Error
**Cek:**
1. Klik Web tab
2. Scroll ke WSGI configuration file
3. Klik link file
4. Pastikan isinya seperti ini:

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

**Jika salah, edit dan klik Save**

### 2. Virtualenv Path Salah
**Cek:**
1. Web tab
2. Scroll ke Virtualenv section
3. Pastikan terisi: `/home/sadas/.virtualenvs/kos_bot`

**Jika kosong atau salah:**
1. Isi dengan path yang benar
2. Tekan Enter
3. Reload web app

### 3. Missing Dependencies
**Fix:**
```bash
# Di Bash console
workon kos_bot
pip install -r ~/kost-bot/requirements.txt
```

### 4. Check Error Log
**Paling penting!**
1. Web tab
2. Klik link **Error log** (warna orange)
3. Lihat pesan error terbaru
4. Baca pesan error untuk clue

---

## ❌ ImportError: No module named X

**Contoh:** `No module named 'flask'` atau `No module named 'asyncpg'`

**Fix:**
```bash
# Di PythonAnywhere Bash console
workon kos_bot
pip install --upgrade pip
pip install -r ~/kost-bot/requirements.txt
```

**Jika masih error:**
1. List packages yang terinstall:
   ```bash
   pip list
   ```
2. Cek requirements.txt ada package tersebut:
   ```bash
   cat ~/kost-bot/requirements.txt
   ```
3. Jika ada yang missing, install manual:
   ```bash
   pip install flask python-telegram-bot asyncpg
   ```

---

## ❌ /health endpoint tidak respond

### Penyebab 1: App tidak jalan
**Cek:**
1. Error log ada pesan error?
2. Virtualenv path benar?
3. WSGI file benar?

**Fix:**
1. Klik Reload
2. Tunggu 15 detik
3. Refresh browser

### Penyebab 2: Path repository salah
**Pastikan:**
```bash
# Di PythonAnywhere Bash console
ls ~/kost-bot/
```

Output seharusnya:
```
main.py
requirements.txt
v2/
pythonanywhere_wsgi.py
SETUP_CHECKLIST.md
...
```

Jika tidak ada, clone lagi:
```bash
cd ~
rm -rf kost-bot
git clone https://github.com/quaso-hub/pantau-kos.git kost-bot
```

### Penyebab 3: Environment variables tidak di-set
**Pastikan DATABASE_URL ada:**
```bash
# Di Bash console
echo $DATABASE_URL
```

Jika kosong, set di Account > Environment variables

---

## ❌ Telegram Bot tidak merespons

### Penyebab 1: Webhook belum di-set
**Cek:**
```bash
# Di komputer lokal
curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo
```

Ganti `<TOKEN>` dengan bot token Anda.

Output yang benar:
```json
{"ok":true,"result":{"url":"https://sadas.pythonanywhere.com/webhook","...}}
```

**Jika salah:**
```bash
curl -X POST https://api.telegram.org/bot<TOKEN>/setWebhook \
     -H "Content-Type: application/json" \
     -d '{"url": "https://sadas.pythonanywhere.com/webhook"}'
```

### Penyebab 2: DATABASE_URL salah
**Cek:**
1. Account > Environment variables
2. Pastikan DATABASE_URL benar
3. Format harus: `postgresql://user:password@host/database?sslmode=require`

**Test connection:**
```bash
# Di Bash console
python3 << 'EOF'
import asyncpg
import os
import asyncio

async def test():
    url = os.environ.get('DATABASE_URL')
    if not url:
        print("DATABASE_URL not set!")
        return
    try:
        conn = await asyncpg.connect(url)
        print("✓ Database connection OK!")
        await conn.close()
    except Exception as e:
        print(f"✗ Database connection failed: {e}")

asyncio.run(test())
EOF
```

### Penyebab 3: Telegram Bot Token salah
**Cek:**
1. Account > Environment variables
2. TELEGRAM_BOT_TOKEN ada?
3. Token benar? (Mulai dengan angka, panjang ~45 karakter)

**Test token:**
```bash
# Di Bash console
curl https://api.telegram.org/bot<TOKEN>/getMe
```

Ganti `<TOKEN>` dengan token Anda. Jika valid:
```json
{"ok":true,"result":{"id":123456789,"is_bot":true,"...}}
```

---

## ❌ Dashboard tidak muncul

**Penyebab:** Biasanya ada error di app.

**Fix:**
1. Check error log di Web tab
2. Pastikan /health endpoint respond (test di browser)
3. Reload web app
4. Clear browser cache (Ctrl+Shift+Delete)

---

## 📝 Viewing Logs

**Error Log:**
1. Web tab
2. Link berwarna orange "Error log"

**Server Log:**
1. Web tab
2. Link berwarna biru "Server log"

**Di Bash console:**
```bash
# Tail error log (last 20 lines)
tail -20 /var/log/sadas.pythonanywhere.com.error.log

# Tail server log
tail -20 /var/log/sadas.pythonanywhere.com.server.log
```

---

## 🔄 Reloading Web App

Jika ada perubahan (code, environment, dll):

1. Web tab
2. Klik tombol hijau **Reload** di atas
3. Tunggu 10-15 detik
4. Test lagi

---

## 🆘 Jika Masih Stuck

1. **Check error log** (paling penting!)
2. Verify semua variable di Account > Environment variables
3. Verify WSGI file benar
4. Verify virtualenv path benar
5. Reload web app
6. Clear browser cache
7. Test /health endpoint

Jika semua di atas sudah benar tapi masih error, baca error log dengan seksama - error message akan memberi clue!

---

## ✅ Success Signs

```
✓ /health endpoint return {"status": "ok"}
✓ Dashboard halaman muncul
✓ Bot merespons di Telegram
✓ Error log tidak ada pesan baru
```

Jika semua di atas, Anda sudah berhasil! 🎉
