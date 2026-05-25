# PythonAnywhere Deployment Guide - Step by Step

## Prerequisites
- ✅ Neon PostgreSQL database ready (tables created)
- ✅ Code committed to GitHub (`pantau-kos` repo)
- ✅ Python code tested locally
- ❌ PythonAnywhere account (CREATE THIS)

---

## Step 1: Create PythonAnywhere Account

### 1a. Sign Up
1. Open: https://pythonanywhere.com
2. Click: "Start hosting Python online for free!"
3. Fill in:
   - Username: `choose your username` (will be part of URL)
   - Email: `your email`
   - Password: `strong password`
4. Agree to terms
5. Click: "Create a Beginner account"

### 1b. Verify Email
1. Check your email inbox
2. Click verification link from PythonAnywhere
3. You're now logged in!

**Result:** You'll see the Dashboard with tabs: Dashboard, Consoles, Files, Web, Tasks, Databases

---

## Step 2: Clone Repository from GitHub

### 2a. Open Bash Console
1. Click: **Consoles** tab (top menu)
2. Click: **Start a new console** → **Bash**
3. Wait for shell prompt: `~ $`

### 2b. Clone Repository
Run these commands in the Bash console:

```bash
# Clone the repository
git clone https://github.com/quaso-hub/pantau-kos.git

# Enter directory
cd pantau-kos

# Verify files
ls -la

# Should see: main.py, requirements.txt, v2/, etc.
```

**Expected output:**
```
Cloning into 'pantau-kos'...
remote: Enumerating objects: ...
Receiving objects: 100% (XXX/XXX), done.
```

---

## Step 3: Create Python Virtual Environment

### 3a. Create Virtual Environment
In the same Bash console:

```bash
# Create venv for Python 3.11
mkvirtualenv --python=/usr/bin/python3.11 kos_bot

# It should activate automatically (you'll see (kos_bot) $ prompt)
```

### 3b. Verify venv Active
```bash
# Check Python version
python --version
# Should show: Python 3.11.x

# Check pip
pip --version
# Should show: pip X.X.X from ... (kos_bot)
```

---

## Step 4: Install Dependencies

In the Bash console (with venv activated):

```bash
# Navigate to project
cd ~/pantau-kos

# Install from requirements.txt
pip install -r requirements.txt

# This will install:
# - Flask
# - python-telegram-bot
# - asyncpg (PostgreSQL)
# - google-genai
# - httpx
# - Pillow

# Wait for completion (may take 2-3 minutes)
```

**Expected end message:**
```
Successfully installed flask-3.0.3 gunicorn-22.0.0 ... asyncpg-0.29.0 ...
```

---

## Step 5: Set Environment Variables

### 5a. Create .env File
```bash
# Edit using nano
nano ~/.bashrc

# Add these lines at the end:
export TELEGRAM_TOKEN="8742407345:AAF6K77rewrtu_uLQ4I8yrD0_BgWNHngGZc"
export GEMINI_API_KEY="AIzaSyC_8T67cfhxgzkWusfYMcxlsC4hY8nx0fc"
export MAPS_API_KEY="AIzaSyCT2X80spEIax5cWa-vxa_orru6PGtmJQo"
export DEEPSEEK_API_KEY="sk-bcb176314ec24be7ab2d1bb3f3289a65"
export ALLOWED_CHAT_ID="6215704457"
export DATABASE_URL="postgresql://neondb_owner:npg_ZrOPR1udvmY7@ep-withered-feather-aotbugls.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"

# Save: Ctrl+O, Enter, Ctrl+X

# Reload bashrc
source ~/.bashrc
```

### 5b. Verify Environment Variables
```bash
echo $DATABASE_URL
# Should print: postgresql://neondb_owner:***@ep-...

echo $TELEGRAM_TOKEN
# Should print: 8742407345:AAF6K77...
```

---

## Step 6: Create Flask WSGI Application

### 6a. Go to Web Tab
1. Click: **Web** tab (top menu)
2. Click: **+ Add a new web app**

### 6b. Configure Web App
1. Choose: **Manual configuration** (not framework)
2. Choose: **Python 3.11**
3. PythonAnywhere will create a web app

**You'll see:**
- Web app URL: `https://yourusername.pythonanywhere.com`
- WSGI configuration file path
- Code location field

### 6c. Edit WSGI Configuration File
1. After creating web app, click: **Go to web app settings** link
2. Or click: **Web** tab → select your app → **WSGI configuration file**
3. Click to edit the file

**Replace entire content with this:**

```python
import sys
import os

# Add project to path
project_home = u'/home/yourusername/pantau-kos'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Set working directory
os.chdir(project_home)

# Load environment variables (set in .bashrc)
# They're automatically available in PythonAnywhere

# Import Flask app
from main import flask_app as application
```

**Replace `yourusername` with your actual PythonAnywhere username!**

---

## Step 7: Configure Web App Settings

### 7a. Virtualenv
1. Go to **Web** tab → your app
2. Find **"Virtualenv:"** field
3. Click and type: `/home/yourusername/.virtualenvs/kos_bot`
4. Press Enter (green checkmark should appear)

### 7b. Static Files (if needed)
1. Click: **"Add a new static files mapping"**
2. URL path: `/static`
3. Directory: `/home/yourusername/pantau-kos/web/static`
4. Click: **Add**

### 7c. Working Directory
1. Set to: `/home/yourusername/pantau-kos`

---

## Step 8: Reload and Test

### 8a. Reload Web App
1. On **Web** tab, click **Green "Reload"** button
2. Wait 30-60 seconds for app to start
3. Status should show: "Running"

### 8b. Test Health Endpoint
Open in browser:
```
https://yourusername.pythonanywhere.com/health
```

**Expected response:**
```json
{
  "ok": true,
  "ptb": true,
  "loop": true
}
```

If you see an error:
1. Click: **"View error logs"**
2. Check what went wrong
3. Common issues: wrong Python path, missing packages, wrong WSGI file

### 8c. Test Root Redirect
Open in browser:
```
https://yourusername.pythonanywhere.com/
```

Should redirect to `/dashboard/`

---

## Step 9: Set Up Custom Domain (Optional - After DNS Works)

### 9a. Add Domain in Web Settings
1. On **Web** tab → your app
2. Find: **"Web app URLs"**
3. Click: **"Add a new domain"**
4. Enter: `god-eye.ikrn.engineer`
5. Click: **Add**

### 9b. Update DNS Records
1. Go to your domain registrar (wherever you bought god-eye.ikrn.engineer)
2. Find: **DNS settings** or **Zone file**
3. Create/update CNAME record:
   - **Name:** `god-eye`
   - **Value:** `yourusername.pythonanywhere.com`
   - **TTL:** 3600 (or default)
4. Save

### 9c. Wait for DNS Propagation
DNS changes take 24-48 hours to propagate globally.

Test with:
```bash
nslookup god-eye.ikrn.engineer
# Should eventually show: yourusername.pythonanywhere.com
```

---

## Step 10: Configure Telegram Webhook

### 10a. Set Webhook URL
Replace `{TOKEN}` with your actual Telegram token:

```bash
curl -X POST "https://api.telegram.org/bot{TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://yourusername.pythonanywhere.com/webhook",
    "allowed_updates": ["message", "callback_query"]
  }'
```

**Example:**
```bash
curl -X POST "https://api.telegram.org/bot8742407345:AAF6K77rewrtu_uLQ4I8yrD0_BgWNHngGZc/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://yourusername.pythonanywhere.com/webhook",
    "allowed_updates": ["message", "callback_query"]
  }'
```

### 10b. Verify Webhook
```bash
curl "https://api.telegram.org/bot{TOKEN}/getWebhookInfo"
```

**Expected response:**
```json
{
  "ok": true,
  "result": {
    "url": "https://yourusername.pythonanywhere.com/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0
  }
}
```

---

## Step 11: Update n8n Webhook URL

### 11a. Modify n8n Workflow
1. Open your n8n workflow (where you scrape listings)
2. Find the **HTTP Request node** that posts to `/monitor`
3. Update URL:
   - **Old:** `https://asia-southeast1-kos-monitor.cloudfunctions.net/monitor`
   - **New:** `https://yourusername.pythonanywhere.com/monitor`
4. **Keep headers:** `X-Webhook-Secret` with the same value
5. Save and deploy workflow

### 11b. Test n8n Integration
1. Manually trigger n8n workflow
2. Check PythonAnywhere logs:
   - **Web** tab → **Log files** → **Error log**
3. Should see your data being processed

---

## Step 12: Monitor and Debug

### 12a. View Logs
**Error logs:**
```
https://yourusername.pythonanywhere.com/
→ Click: "Error log" or "Server log"
```

**Live logs** (in Bash):
```bash
cd ~/pantau-kos
tail -f /var/log/yourusername.pythonanywhere.com.error.log
```

### 12b. Restart Web App (if needed)
```
Web tab → Click green "Reload" button
```

### 12c. Check Database Connection
```bash
# In Bash console with venv activated
cd ~/pantau-kos

python3 << EOF
import asyncpg
import asyncio
import os

async def test():
    db_url = os.environ['DATABASE_URL']
    try:
        conn = await asyncpg.connect(db_url)
        result = await conn.fetchval("SELECT COUNT(*) FROM kos_listings")
        print(f"✅ DB connection OK! Listings in DB: {result}")
        await conn.close()
    except Exception as e:
        print(f"❌ DB error: {e}")

asyncio.run(test())
EOF
```

---

## Troubleshooting

### Problem: "ModuleNotFoundError: No module named 'flask'"
**Solution:**
```bash
workon kos_bot
pip install flask
pip install -r requirements.txt
```

### Problem: "DATABASE_URL not set"
**Solution:**
1. Check `.bashrc` has export statements
2. Run: `source ~/.bashrc`
3. Verify: `echo $DATABASE_URL`
4. Reload web app

### Problem: "Connection refused" to database
**Solution:**
1. Verify DATABASE_URL format
2. Test from Bash: `psql $DATABASE_URL`
3. Check Neon console for any alerts

### Problem: "TypeError: unsupported operand type(s)"
**Solution:** Usually Python version mismatch
- Ensure venv is Python 3.11: `python --version`
- Update WSGI file to use `/usr/bin/python3.11`

---

## Success Criteria

When everything works:
- ✅ `/health` returns `{"ok": true, ...}`
- ✅ Bot responds to `/start` in Telegram
- ✅ Dashboard loads at `https://yourusername.pythonanywhere.com/dashboard`
- ✅ n8n webhook integration working (listings appearing in database)
- ✅ No errors in error log (only normal logs)

---

**You're done! The bot is now live on PythonAnywhere!**
