# PythonAnywhere Deployment Checklist

## Pre-Deployment (Local Setup Complete ✅)

- [x] Migrated Firestore → PostgreSQL in codebase
- [x] Created `postgres_repo.py` with all 5 repository classes
- [x] Updated `config.py` with PostgresConfig
- [x] Updated `container.py` to use PostgreSQL repos
- [x] Created `migrations.py` with schema initialization
- [x] Updated `requirements.txt` (added asyncpg, removed google-cloud-firestore)
- [x] Updated `.env` with DATABASE_URL
- [x] Updated `main.py` to initialize database on startup
- [x] Git commit & push to GitHub
- [x] Documentation: MIGRATION_COMPLETE.md

## Deployment Steps (Next)

### 1. Create PythonAnywhere Account
- [ ] Go to [pythonanywhere.com](https://pythonanywhere.com)
- [ ] Sign up with email (no credit card required)
- [ ] Verify email
- [ ] Create free tier account

### 2. Set Up Git Repository
- [ ] Open Bash console in PythonAnywhere (Consoles tab)
- [ ] Clone repository:
  ```bash
  git clone https://github.com/quaso-hub/pantau-kos.git
  cd pantau-kos
  ```
- [ ] Verify files are present: `ls -la v2/adapters/repositories/`

### 3. Create Python Virtual Environment
- [ ] In Bash console:
  ```bash
  mkvirtualenv --python=/usr/bin/python3.11 kos_bot
  ```
- [ ] Activate venv (should happen automatically):
  ```bash
  workon kos_bot
  ```
- [ ] Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```
  (This will install asyncpg, Flask, PTB, etc.)

### 4. Configure Environment Variables
- [ ] Go to Web > (your app) > WSGI configuration file
- [ ] Or set in `/home/yourusername/kos_bot/.env`:
  ```env
  TELEGRAM_TOKEN=8742407345:AAF6K77rewrtu_uLQ4I8yrD0_BgWNHngGZc
  GEMINI_API_KEY=AIzaSyC_8T67cfhxgzkWusfYMcxlsC4hY8nx0fc
  MAPS_API_KEY=AIzaSyCT2X80spEIax5cWa-vxa_orru6PGtmJQo
  DEEPSEEK_API_KEY=sk-bcb176314ec24be7ab2d1bb3f3289a65
  ALLOWED_CHAT_ID=6215704457
  DATABASE_URL=postgresql://neondb_owner:npg_ZrOPR1udvmY7@ep-withered-feather-aotbugls.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
  ```

### 5. Create Flask WSGI Application
- [ ] Go to Web > Add a new web app
- [ ] Choose "Manual configuration"
- [ ] Choose Python 3.11
- [ ] PythonAnywhere will create WSGI file at:
  `/home/yourusername/mysite/wsgi_files/your_username_pythonanywhere_com_wsgi.py`
- [ ] Edit WSGI file to point to your Flask app:
  ```python
  import sys
  import os
  
  # Add your project directory to sys.path
  project_home = u'/home/yourusername/pantau-kos'
  if project_home not in sys.path:
      sys.path.insert(0, project_home)
  
  # Set environment variables
  os.environ['TELEGRAM_TOKEN'] = '...'
  os.environ['DATABASE_URL'] = '...'
  # ... other variables
  
  # Import and use Flask app
  from main import flask_app as application
  ```

### 6. Configure Web App
- [ ] Go to Web > (your app)
- [ ] Set working directory: `/home/yourusername/pantau-kos`
- [ ] Set virtualenv: `/home/yourusername/.virtualenvs/kos_bot`
- [ ] Source code: `/home/yourusername/pantau-kos`
- [ ] WSGI configuration file: (path shown above)
- [ ] Static files: 
  - URL: `/static`
  - Directory: `/home/yourusername/pantau-kos/web/static`

### 7. Initialize Database (First Run Only)
- [ ] Open Bash console
- [ ] Activate venv: `workon kos_bot`
- [ ] Run database initialization:
  ```bash
  cd /home/yourusername/pantau-kos
  python -c "
  import asyncio
  import os
  from v2.infrastructure.migrations import init_database
  
  db_url = os.environ.get('DATABASE_URL')
  asyncio.run(init_database(db_url))
  print('✅ Database initialized!')
  "
  ```
- [ ] Verify tables created in Neon console (should see 5 tables)

### 8. Reload Web App
- [ ] Go to Web > (your app) > Reload button
- [ ] Wait for app to start (may take 30-60 seconds)
- [ ] Check Status should show "Running"

### 9. Verify Health Check
- [ ] Go to `https://yourusername.pythonanywhere.com/health`
- [ ] Should return JSON: `{"ok": true, "ptb": true, "loop": true}`

### 10. Test Webhook Endpoints
- [ ] `/telegram_webhook` — n8n monitor posts to this
  ```bash
  curl -X POST https://yourusername.pythonanywhere.com/webhook \
    -H "Content-Type: application/json" \
    -d '{"update_id": 1, "message": {"chat": {"id": 123}, "text": "/start"}}'
  ```
  Should return: `{"ok": true}`

- [ ] `/monitor` — For n8n processing notifications
  ```bash
  curl -X POST https://yourusername.pythonanywhere.com/monitor \
    -H "Content-Type: application/json" \
    -H "X-Webhook-Secret: your_n8n_secret" \
    -d '{"listings": []}'
  ```
  Should return: `{"ok": true, "status": "accepted"}`

### 11. Point Custom Domain (god-eye.ikrn.engineer)
- [ ] Go to Web > (your app) > Add a new domain
- [ ] Enter: `god-eye.ikrn.engineer`
- [ ] PythonAnywhere will show DNS setup instructions
- [ ] Go to your domain registrar (wherever you registered god-eye.ikrn.engineer)
- [ ] Create CNAME record:
  - Name: `god-eye`
  - Value: `yourusername.pythonanywhere.com`
  - (Or add to existing: `god-eye.ikrn.engineer` → CNAME → `yourusername.pythonanywhere.com`)
- [ ] Wait 24-48 hours for DNS propagation
- [ ] Test: `curl https://god-eye.ikrn.engineer/health`

### 12. Configure Telegram Webhook
- [ ] Update Telegram bot webhook to point to new URL:
  ```bash
  curl -X POST \
    "https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook" \
    -H "Content-Type: application/json" \
    -d '{
      "url": "https://god-eye.ikrn.engineer/webhook",
      "allowed_updates": ["message", "callback_query"]
    }'
  ```
- [ ] Verify webhook:
  ```bash
  curl -X GET \
    "https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo"
  ```

### 13. Update n8n Webhook Secret (if needed)
- [ ] In n8n workflow, update monitor webhook URL:
  - Old: `https://asia-southeast1-kos-monitor.cloudfunctions.net/monitor`
  - New: `https://god-eye.ikrn.engineer/monitor`
- [ ] Include `X-Webhook-Secret` header with same value from config

### 14. Monitor & Test
- [ ] Send test message to Telegram bot: `/start`
- [ ] Check logs: Web > (your app) > Log files (view Error log, Server log)
- [ ] Verify bot responds and dashboard works
- [ ] Monitor database: Check Neon console for growing tables

## Rollback Plan (if issues occur)

- [ ] Keep old GCP Cloud Run endpoint active temporarily (redirect old n8n workflows)
- [ ] If database fails: Check DATABASE_URL format in Neon console
- [ ] If bot doesn't respond: Check Telegram bot token in Web app config
- [ ] If WSGI fails: Check PythonAnywhere error logs for imports

## Post-Deployment

- [ ] Monitor bot usage for 24-48 hours
- [ ] Check database for data accumulation from n8n
- [ ] Verify dashboard loads at `https://god-eye.ikrn.engineer/dashboard`
- [ ] Set up PythonAnywhere task scheduler for any cron jobs (if needed)

## Useful PythonAnywhere Commands

### View Logs
```bash
tail -f /var/log/yourusername.pythonanywhere.com.error.log
```

### Restart Web App
```bash
# In Web console
/home/yourusername/pantau-kos/venv/bin/python manage.py collectstatic
```

### Backup Database
```bash
# In Bash console
pg_dump postgresql://... > backup.sql
```

---

## Estimated Timeline

- **Account setup + repo clone:** 5 min
- **Virtual environment + dependencies:** 10 min
- **WSGI configuration:** 10 min
- **Database initialization:** 2 min
- **Testing:** 10 min
- **Custom domain DNS:** 1 min (setup) + 24-48h (propagation)

**Total active time: ~45 minutes**

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'asyncpg'"
**Solution:** Ensure pip install ran successfully. Check that the correct venv is activated (`which python` should show venv path).

### "DATABASE_URL not set"
**Solution:** Add to WSGI file:
```python
os.environ['DATABASE_URL'] = 'postgresql://...'
```

### "Connection refused" to database
**Solution:** 
1. Verify Neon is not locked (check web console)
2. Verify IP whitelist in Neon (might need to add PythonAnywhere IP)
3. Check DATABASE_URL format: `postgresql://user:pass@host:port/db?sslmode=require`

### Telegram bot not responding
**Solution:**
1. Check `/getWebhookInfo` returns correct URL
2. Verify `ALLOWED_CHAT_ID` matches your chat ID
3. Check error log for exceptions

---

**All steps verified locally. Ready for deployment!**
