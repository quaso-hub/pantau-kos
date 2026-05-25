# PythonAnywhere Deployment - Step by Step untuk `sadas.pythonanywhere.com`

**Status Saat Ini:** Anda sudah punya account PythonAnywhere dan web app sudah terdaftar!

## LANGKAH 1: Clone Repository di Bash Console

```bash
# Buka Bash console dari PythonAnywhere Dashboard
cd ~
git clone https://github.com/quaso-hub/pantau-kos.git kost-bot
cd kost-bot
ls -la
```

Pastikan Anda lihat: `main.py`, `requirements.txt`, folder `v2/`

## LANGKAH 2: Buat Virtual Environment

```bash
# Membuat virtualenv dengan Python 3.11
mkvirtualenv --python=/usr/bin/python3.11 kos_bot

# Output akan terlihat seperti:
# (kos_bot) user@server:~$
```

## LANGKAH 3: Install Dependencies

```bash
# Pastikan Anda di dalam virtualenv (harus ada `(kos_bot)` di depan prompt)
workon kos_bot

# Upgrade pip dulu
pip install --upgrade pip

# Install semua packages dari requirements.txt
pip install -r ~/kost-bot/requirements.txt

# Tunggu sampai selesai (bisa 5-10 menit)
```

## LANGKAH 4: Update WSGI Configuration di PythonAnywhere Web Tab

1. Login ke https://www.pythonanywhere.com
2. Klik tab **Web** di navigation bar
3. Klik pada domain Anda: `sadas.pythonanywhere.com`
4. Scroll down ke section **WSGI configuration file**
5. Klik link WSGI file (`/var/www/sadas_pythonanywhere_com_wsgi.py`)
6. Ganti isi file dengan ini:

```python
import sys
import os

# Add project to path
project_home = os.path.expanduser('~/kost-bot')
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.chdir(project_home)

# Setup logging
from infrastructure.logger import setup_logging
setup_logging()

# Import Flask app
from main import app as application
```

7. Klik **Save** di atas
8. Kembali ke Web tab

## LANGKAH 5: Set Virtual Environment Path

Di Web tab, cari section **Virtualenv**:

```
Path to a virtualenv, if desired
/home/sadas/.virtualenvs/kos_bot
```

Isi dengan path di atas, kemudian **Enter**

## LANGKAH 6: Set Environment Variables

Ada 2 cara:

### Cara A: Via Account menu (Lebih Mudah)
1. Klik username di atas kanan
2. Pilih **Account**
3. Scroll ke **Environment variables**
4. Add setiap variable:

```
DATABASE_URL=postgresql://neondb_owner:PASSWORD@HOST/neondb?sslmode=require
TELEGRAM_BOT_TOKEN=your_bot_token_here
GEMINI_API_KEY=your_gemini_key_here
```

(Ganti `PASSWORD`, `HOST`, `your_bot_token_here`, `your_gemini_key_here` dengan nilai sebenarnya)

### Cara B: Via .env file di direktori project
```bash
# Di Bash console
cd ~/kost-bot
cat > .env << 'EOF'
DATABASE_URL=postgresql://neondb_owner:PASSWORD@HOST/neondb?sslmode=require
TELEGRAM_BOT_TOKEN=your_bot_token_here
GEMINI_API_KEY=your_gemini_key_here
EOF
```

## LANGKAH 7: Reload Web App

1. Kembali ke Web tab
2. Klik tombol hijau **Reload** di atas
3. Tunggu 10-15 detik

## LANGKAH 8: Test Website

Buka di browser:
```
https://sadas.pythonanywhere.com/health
```

Anda seharusnya lihat:
```json
{"status": "ok"}
```

Jika error, lihat error log:
1. Web tab
2. Klik **Error log** link
3. Lihat pesan error terbaru

## LANGKAH 9: Configure Telegram Webhook

Jalankan di terminal lokal Anda (bukan PythonAnywhere console):

```bash
# Ganti <TOKEN> dengan token bot Anda
curl -X POST https://api.telegram.org/bot<TOKEN>/setWebhook \
     -H "Content-Type: application/json" \
     -d '{"url": "https://sadas.pythonanywhere.com/webhook"}'
```

Respons yang diharapkan:
```json
{"ok":true,"result":true}
```

## LANGKAH 10: Test Bot di Telegram

1. Buka Telegram
2. Cari bot Anda (misalnya @MonitorBotName)
3. Kirim command: `/start`
4. Bot seharusnya reply dengan welcome message

Jika tidak ada reply:
1. Kembali ke PythonAnywhere Web tab
2. Klik **Error log**
3. Lihat error messages

## LANGKAH 11: Update n8n Webhook URL

Jika Anda menggunakan n8n untuk scraping:

1. Login ke n8n
2. Buka workflow yang mengirim data ke `/monitor` endpoint
3. Update URL menjadi: `https://sadas.pythonanywhere.com/monitor`
4. Deploy workflow

## LANGKAH 12: Monitor Dashboard

Akses dashboard di:
```
https://sadas.pythonanywhere.com/dashboard
```

Seharusnya menampilkan:
- List of kos listings
- Filter by area, price range, etc
- Stats dan analytics

---

## ⚠️ Troubleshooting

### Error 502 Bad Gateway
- Klik **Error log**, lihat pesan error
- Biasanya: missing dependencies, wrong path, atau database connection error
- Solusi: 
  - Reload web app
  - Pastikan virtualenv path benar
  - Pastikan DATABASE_URL correct

### ImportError: No module named 'X'
- Berarti package belum ter-install
- Jalankan lagi: `workon kos_bot && pip install -r ~/kost-bot/requirements.txt`
- Reload web app

### Webhook not receiving messages
- Pastikan DATABASE_URL di set dengan benar
- Check error log untuk connection errors
- Verify Telegram webhook: `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`

### Bot tidak merespons
- Tunggu 30 detik setelah setWebhook
- Reload web app
- Cek error log
- Pastikan TELEGRAM_BOT_TOKEN benar di environment variables

---

## ✅ Checklist

- [ ] Repository di-clone di PythonAnywhere
- [ ] Virtual environment sudah dibuat
- [ ] Dependencies ter-install
- [ ] WSGI file sudah di-update
- [ ] Virtualenv path sudah di-set
- [ ] Environment variables sudah di-add
- [ ] Web app sudah di-reload
- [ ] /health endpoint respond 200
- [ ] Telegram webhook sudah di-set
- [ ] Bot respond di Telegram
- [ ] Dashboard bisa di-akses

Semuanya? Congratulations! 🎉 Sistem Anda live!
