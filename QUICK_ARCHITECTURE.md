# 🔗 Quick Architecture Reference

## Connection Status

```
✅ GitHub          → Active (source repo)
✅ GCP Cloud Run   → Active (main hosting)
✅ Firestore       → Active (database)
✅ Cloud Build     → Active (CI/CD, sometimes flaky)
❌ Supabase        → Not Used (PostgreSQL alternative)
```

---

## Quick Facts

| Component | Value |
|-----------|-------|
| **GitHub Repo** | `github.com/quaso-hub/pantau-kos` (public) |
| **Cloud Run Service** | `god-eye` in region `asia-southeast1` |
| **Project ID** | `kos-monitor` |
| **Custom Domain** | `god-eye.ikrn.engineer` |
| **Database** | Google Cloud Firestore (NoSQL) |
| **Container Runtime** | gunicorn + 1 worker + 8 threads |
| **Memory** | 512 MB |
| **Timeout** | 120 seconds |
| **Service Account** | `god-eye-sa@kos-monitor.iam.gserviceaccount.com` |

---

## Data Flow

```
Telegram Bot User / n8n Scraper
           ↓
    [POST /webhook or /monitor]
           ↓
Cloud Run Service (Flask)
           ↓
Google Cloud Firestore
           ↓
    [Collections: listings, preferences, blacklist, etc]
```

---

## Deploy Command

```powershell
# Windows
deploy.cmd

# Unix/Mac
bash deploy.sh
```

Or manual trigger:
```bash
gcloud builds triggers run rmgpgab-god-eye-asia-southeast1-quaso-hub-pantau-kos--mabje --branch=main
```

---

## Why Firestore (not Supabase)?

✅ **Firestore is better for this project because:**
- Semi-structured data (variable optional fields)
- Native GCP integration
- Auto-scaling to millions
- Real-time capabilities
- No schema migrations
- Async-friendly (non-blocking operations)

❌ **Supabase would require:**
- Rewrite all database code
- Schema design + migrations
- Different async library (asyncpg)
- Extra external dependency

---

## Environment Variables (at Deploy)

These are loaded from `.env` and injected into Cloud Run:

```
TELEGRAM_TOKEN           (required) — Telegram bot token
GEMINI_API_KEY          (required) — Google Gemini API key
MAPS_API_KEY            (required) — Google Maps API key
DEEPSEEK_API_KEY        (required) — DeepSeek API key
ALLOWED_CHAT_ID         (required) — Telegram chat ID allowed to use bot
GOOGLE_CLOUD_PROJECT    (auto) — Set to PROJECT_ID (kos-monitor)
N8N_WEBHOOK_SECRET      (optional) — Secret for /monitor endpoint
GEMINI_MODEL            (optional) — Override model name
```

---

## Key Files

| File | Purpose |
|------|---------|
| `deploy.cmd` / `deploy.sh` | Deploy script — builds + pushes + deploys to Cloud Run |
| `Dockerfile` | Container definition (Python 3.11-slim) |
| `requirements.txt` | Python dependencies (Flask, Telegram, Firestore, google-genai, etc) |
| `main.py` | Flask entry point — register blueprints, set webhook |
| `v2/adapters/repositories/firestore_repo.py` | Firestore CRUD operations |
| `v2/infrastructure/config.py` | Config from environment variables |
| `v2/infrastructure/container.py` | Dependency injection — builds service objects |

---

## Cloud Build Issue

**Problem:** Auto-trigger sometimes doesn't fire when pushing to GitHub

**Solution:** Manually trigger build
```bash
gcloud builds triggers run rmgpgab-god-eye-asia-southeast1-quaso-hub-pantau-kos--mabje --branch=main
```

**Check status:**
```bash
gcloud builds list --project=kos-monitor --limit=5
gcloud builds log BUILD_ID --project=kos-monitor --stream
```

---

## Monitoring

Check service status:
```bash
# List services
gcloud run services list --project=kos-monitor

# Get service details
gcloud run services describe god-eye --project=kos-monitor --region=asia-southeast1

# View logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=god-eye" \
  --limit=20 --format="value(timestamp,textPayload)" --project=kos-monitor
```

---

For full details, see [`INFRASTRUCTURE.md`](./INFRASTRUCTURE.md)
