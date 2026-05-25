# PYTHONANYWHERE CONFIGURATION UNTUK SADAS

## Akun Info
- Username: sadas
- Domain: sadas.pythonanywhere.com
- Python: 3.11

## Yang Harus di-Set di Web Tab

### 1. Source Code Path
```
/home/sadas/kost-bot
```

### 2. Working Directory
```
/home/sadas/kost-bot
```

### 3. Virtualenv Path
```
/home/sadas/.virtualenvs/kos_bot
```

### 4. WSGI File
File: `/var/www/sadas_pythonanywhere_com_wsgi.py`
Content: Lihat WSGI_CONTENT.py di repository

### 5. Environment Variables

Go to Account (top right) > Environment variables
Add ini:

```
DATABASE_URL = postgresql://neondb_owner:npg_PASSWORD@ep-withered-feather-aotbugls.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require

TELEGRAM_BOT_TOKEN = YOUR_BOT_TOKEN

GEMINI_API_KEY = YOUR_GEMINI_API_KEY
```

Replace PASSWORD, YOUR_BOT_TOKEN, YOUR_GEMINI_API_KEY dengan nilai asli!

### 6. After Setup
1. Click Reload (green button)
2. Wait 15 seconds
3. Test: https://sadas.pythonanywhere.com/health
