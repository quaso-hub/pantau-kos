# 🔌 Architecture: GitHub, GCP Cloud Run & Infrastructure

> Penjelasan lengkap bagaimana codebase ini terkoneksi dengan GitHub, GCP Cloud Run, dan layanan cloud lainnya.

---

## 📋 Ringkasan Koneksi

| Service | Status | Digunakan | Deskripsi |
|---------|--------|-----------|-----------|
| **GitHub** | ✅ Active | Yes | Source code repository, version control, webhooks |
| **GCP Cloud Run** | ✅ Active | Yes | Main hosting — serverless container deployment |
| **Google Cloud Firestore** | ✅ Active | Yes | NoSQL database — listings, preferences, blacklist, sessions |
| **Google Cloud Storage** | ✅ Active | Yes | Image storage (optional, untuk scraper images) |
| **Cloud Build** | ✅ Active | Yes | Automated CI/CD — trigger from GitHub, build → push → deploy |
| **Cloud Logging** | ✅ Active | Yes | Structured logging, error tracking |
| **Supabase** | ❌ Not Used | No | PostgreSQL database provider — **tidak digunakan** |
| **GitHub Actions** | ❌ Not Used | No | CI/CD alternative — **tidak digunakan** (pakai Cloud Build instead) |

---

## 1️⃣ GitHub Repository

### Configuration

```
Repository: github.com/quaso-hub/pantau-kos
Remote URL: https://github.com/quaso-hub/pantau-kos.git
Branch: main (default branch)
Visibility: Public
```

### Verification

```powershell
git remote -v
# Output:
# origin  https://github.com/quaso-hub/pantau-kos.git (fetch)
# origin  https://github.com/quaso-hub/pantau-kos.git (push)
```

### What's in the repo
- Source code: `main.py`, `bot/`, `engine/`, `memory/`, `web/`, `v2/`
- Docker config: `Dockerfile`, `requirements.txt`
- Deploy scripts: `deploy.cmd` (Windows), `deploy.sh` (Unix)
- Documentation: `README.md`, `CHANGELOG.md`, `POSTMORTEM.md`, `DASHBOARD_DESIGN.md`
- Git history: ~50 commits from v1.0 → v5.5+

### GitHub Workflows
- **No GitHub Actions** currently — using GCP Cloud Build instead
- Could add Actions for: pre-commit linting, PR validation, test runs

---

## 2️⃣ GCP Cloud Run (Main Hosting)

### Service Details

```
Service Name: god-eye
Project ID: kos-monitor
Region: asia-southeast1
Pricing Tier: Standard (pay-as-you-go)
Memory: 512 MB
Timeout: 120 seconds
Concurrency: 1 (default)
```

### Deployment Method

**Using `deploy.cmd` (Windows) or `deploy.sh` (Unix/Mac)**

```batch
@echo off
REM deploy.cmd — automated deployment script

REM Step 1: Load .env (TELEGRAM_TOKEN, GEMINI_API_KEY, MAPS_API_KEY, DEEPSEEK_API_KEY, ALLOWED_CHAT_ID)
REM Step 2: Validate all required env vars
REM Step 3: Run gcloud run deploy

gcloud run deploy "god-eye" \
  --project "kos-monitor" \
  --source . \
  --region "asia-southeast1" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "TELEGRAM_TOKEN=...,GEMINI_API_KEY=...,..." \
  --memory 512Mi \
  --timeout 120 \
  --service-account god-eye-sa@kos-monitor.iam.gserviceaccount.com
```

### Container Image Flow

```
┌─────────────────────┐
│   GitHub Repo       │
│   (source code)     │
└──────────┬──────────┘
           │
           ├─ (manual) git push
           │
        [Cloud Build Trigger]
           │
┌──────────▼──────────┐
│  Cloud Build        │
│  (build container)  │
└──────────┬──────────┘
           │
           ├─ Build from Dockerfile
           ├─ Install requirements.txt
           ├─ Push image to Artifact Registry
           │
┌──────────▼──────────┐
│ Artifact Registry   │
│ (image storage)     │
└──────────┬──────────┘
           │
           ├─ Trigger deploy
           │
┌──────────▼──────────┐
│  Cloud Run Service  │
│ (god-eye running)   │
└─────────────────────┘
```

### Custom Domain

```
Custom Domain: god-eye.ikrn.engineer
Setup: Cloud Run → Integrations → Custom Domains
Maps to: https://SERVICE_URL/
SSL: Auto-issued by Google Cloud
```

### Environment Variables (Injected at Deploy Time)

| Variable | Source | Example |
|----------|--------|---------|
| `TELEGRAM_TOKEN` | `.env` file | `8742407345:AAF6K77...` |
| `GEMINI_API_KEY` | `.env` file | `AIzaSyC_8T67cfhx...` |
| `MAPS_API_KEY` | `.env` file | `AIzaSyCT2X80spEI...` |
| `DEEPSEEK_API_KEY` | `.env` file | `sk-bcb1763...` |
| `ALLOWED_CHAT_ID` | `.env` file | `6215704457` |
| `GOOGLE_CLOUD_PROJECT` | auto (PROJECT_ID) | `kos-monitor` |
| `N8N_WEBHOOK_SECRET` | `.env` (optional) | `secret-xyz` |
| `GEMINI_MODEL` | `.env` (optional) | `gemini-3.1-pro-preview` |

---

## 3️⃣ Google Cloud Firestore (Database)

### Configuration

```python
# v2/infrastructure/config.py
class FirestoreConfig:
    project_id: str = "kos-monitor"
    database_id: str = "kos-monitor-firestore"
    
    # AsyncClient — non-blocking, all operations async
    # Uses service account (god-eye-sa) for authentication
```

### Collections (NoSQL Structure)

| Collection | Purpose | Fields |
|-----------|---------|--------|
| **kos_listings** | Core data — kos listings scraped + analyzed | `id`, `source`, `location`, `price`, `score`, `status`, `geocode`, `air_quality`, `phones`, `fraud_risk`, `timestamp`, `gemini_raw`, `deepseek_raw` |
| **user_preferences** | User survey feedback + learning | `chat_id`, `max_distance_km`, `budget_min`, `budget_max`, `area_preferences`, `skip_counts`, `avoided_areas`, `last_updated` |
| **blacklist** | Blocked phone numbers | `phone`, `reason`, `added_at`, `added_by` |
| **area_cache** | Area stats (24h cache) | `area_name`, `skip_count`, `survey_count`, `avg_score`, `cached_at` |
| **sessions** | User session tracking (optional) | `chat_id`, `state`, `current_listing_id`, `created_at`, `last_activity` |

### Data Flow

```
┌───────────────────┐
│  n8n Workflows    │
│  (6 scrapers)     │
└────────┬──────────┘
         │
         ├─ Mamikos, OLX, Rumah123, Sewakost, 99.co, Kost.com
         │
    [POST /monitor]
         │
┌────────▼──────────────────┐
│  Flask Web Service         │
│  (god-eye Cloud Run)       │
│  ├─ /webhook (Telegram)    │
│  ├─ /monitor (n8n)         │
│  ├─ /dashboard (UI)        │
│  └─ /api/* (JSON endpoints)│
└────────┬──────────────────┘
         │
    [AsyncClient]
         │
┌────────▼──────────────────┐
│  Google Cloud Firestore    │
│  ├─ kos_listings           │
│  ├─ user_preferences       │
│  ├─ blacklist              │
│  ├─ area_cache             │
│  └─ sessions               │
└────────────────────────────┘
```

### Firestore Access

```python
# v2/adapters/repositories/firestore_repo.py
from google.cloud import firestore
from google.cloud.firestore_v1.async_client import AsyncClient

# In container.py
async def get_firestore_client(project_id):
    return AsyncClient(project=project_id)

# Example: Create listing
await db.collection('kos_listings').document(listing_id).set(data)

# Example: Query listings
query = db.collection('kos_listings').where('status', '==', 'survey')
docs = await query.stream()

# Example: Update preference
await db.collection('user_preferences').document(chat_id).update(data)
```

### Why Firestore (not Supabase)?

| Aspect | Firestore | Supabase (PostgreSQL) |
|--------|-----------|----------------------|
| **Type** | NoSQL (document) | Relational (SQL) |
| **GCP Integration** | Native | Third-party |
| **Scaling** | Auto-scale to millions | Manual scaling |
| **Auth** | Service Account (built-in) | JWT tokens |
| **Cost** | Pay-per-read/write | Pay-per-CPU |
| **Real-time** | Built-in listeners | Via WebSockets (Realtime) |
| **Project Fit** | Semi-structured data (JSON) | Highly structured relational |

**Kesimpulan:** Firestore dipilih karena:
1. Semi-structured data (listings punya field optional variable)
2. Real-time capability (future Telegram updates)
3. Simple async operations (non-blocking)
4. No schema migrations needed

---

## 4️⃣ Cloud Build (CI/CD Pipeline)

### Trigger Configuration

```
Trigger Name: rmgpgab-god-eye-asia-southeast1-quaso-hub-pantau-kos--mabje
Repository: github.com/quaso-hub/pantau-kos
Branch: main
Build Config: Dockerfile (inline)
```

### Build Process

**Automatic (when it works):**
```
push to main → Cloud Build auto-detects Dockerfile → builds → pushes to Artifact Registry → deploys to Cloud Run
```

**Manual (when auto-trigger fails):**
```bash
gcloud builds triggers run rmgpgab-god-eye-asia-southeast1-quaso-hub-pantau-kos--mabje --branch=main
```

### Build Output

```
Step 1: FROM python:3.11-slim
Step 2: COPY requirements.txt .
Step 3: RUN pip install --no-cache-dir -r requirements.txt
Step 4: COPY main.py . (+ domain/, services/, adapters/, infrastructure/, web/)
Step 5: CMD ["gunicorn", "--bind", "0.0.0.0:8080", ...]

Result: Docker image tagged with commit SHA, pushed to asia-southeast1-docker.pkg.dev/kos-monitor/cloud-run-source-deploy/...
```

### Known Issue

**Auto-trigger sometimes silent-fails** — GitHub push doesn't trigger Cloud Build.

**Workaround:**
```powershell
# Check build status
gcloud builds list --project=kos-monitor --limit=5

# Manual trigger if needed
gcloud builds triggers run rmgpgab-god-eye-asia-southeast1-quaso-hub-pantau-kos--mabje --branch=main

# Watch build logs
gcloud builds log BUILD_ID --project=kos-monitor --stream
```

---

## 5️⃣ Other GCP Services (Active)

### Cloud Logging
```
Logs collected from Cloud Run service
Endpoint: https://console.cloud.google.com/logs
Query: resource.type=cloud_run_revision AND resource.labels.service_name=god-eye
Used in: README View Logs button (links to Cloud Run logs)
```

### Service Account (god-eye-sa)
```
Email: god-eye-sa@kos-monitor.iam.gserviceaccount.com
Roles:
  - Cloud Run Admin (deploy)
  - Firestore User (read/write database)
  - Artifact Registry Write (push images)
  - Cloud Logging Write (structured logs)
  - Cloud Build Editor (trigger builds)
Permissions: Scoped to project kos-monitor
```

### Artifact Registry
```
Repository: asia-southeast1-docker.pkg.dev/kos-monitor/cloud-run-source-deploy
Contains: Docker images built by Cloud Build
Used by: Cloud Run pulls latest image on deploy
Retention: Configurable (default: keep last 10)
```

---

## ❌ Supabase (NOT Used)

### Why Not Supabase?

Supabase = PostgreSQL + Auth + Realtime + Storage

**Current stack uses:**
- **Database:** Firestore (NoSQL) — not PostgreSQL
- **Auth:** Service Account (GCP IAM) — not Supabase Auth
- **Realtime:** Could use Firestore listeners — not Supabase Realtime
- **Storage:** (planned) Google Cloud Storage — not Supabase Storage

**Migration to Supabase would require:**
1. Schema design (SQL) for listings, preferences, blacklist, sessions
2. Change all async Firestore calls to async PostgreSQL (asyncpg)
3. Rewrite repositories: `FirestoreListingRepo` → `SupabaseListingRepo`
4. Set up Supabase project + API keys
5. Update deploy scripts with Supabase connection string

**Would Supabase be better?**
- ✅ Pro: Full SQL capabilities, easier relational queries, familiar for SQL devs
- ✅ Pro: Cheaper for very high traffic (pay-per-CPU vs per-operation)
- ❌ Con: Overkill for semi-structured data
- ❌ Con: Extra external dependency
- ❌ Con: Schema migrations needed (more overhead)

**Current choice is correct** — Firestore is right for this project's data model.

---

## 🏗️ Complete Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                     External World                                │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌─────────────────┐        ┌─────────────────┐                  │
│  │  Telegram Bot   │        │  n8n Workflows  │                  │
│  │  (users send    │        │  (6 scrapers)   │                  │
│  │   messages)     │        │                 │                  │
│  └────────┬────────┘        └────────┬────────┘                  │
│           │                         │                            │
│      [POST /webhook]           [POST /monitor]                   │
│           │                         │                            │
│           └─────────────────┬───────┘                            │
│                             │                                    │
└─────────────────────────────┼────────────────────────────────────┘
                              │
                    [Internet / HTTP]
                              │
              ┌───────────────▼────────────────┐
              │  GitHub Repository             │
              │  github.com/quaso-hub/pantau-kos
              │  ├─ main.py                    │
              │  ├─ Dockerfile                 │
              │  ├─ deploy.cmd / deploy.sh     │
              │  └─ (source code)              │
              └───────────────┬────────────────┘
                              │
                    [git push, Webhook]
                              │
              ┌───────────────▼────────────────┐
              │  GCP Cloud Build               │
              │  (CI/CD Pipeline)              │
              │  ├─ Build Docker image         │
              │  ├─ Push to Artifact Registry  │
              │  └─ Trigger deploy             │
              └───────────────┬────────────────┘
                              │
              ┌───────────────▼────────────────┐
              │  GCP Artifact Registry         │
              │  (Image storage)               │
              └───────────────┬────────────────┘
                              │
              ┌───────────────▼────────────────┐
              │  GCP Cloud Run                 │
              │  (god-eye service)             │
              │  ├─ main.py (Flask)            │
              │  ├─ 512 MB RAM                 │
              │  ├─ asia-southeast1 region     │
              │  └─ Custom domain: god-eye... │
              └───────────────┬────────────────┘
                              │
                    [Async Firestore calls]
                              │
              ┌───────────────▼────────────────┐
              │  GCP Cloud Firestore           │
              │  (NoSQL Database)              │
              │  ├─ kos_listings               │
              │  ├─ user_preferences           │
              │  ├─ blacklist                  │
              │  ├─ area_cache                 │
              │  └─ sessions                   │
              └───────────────┬────────────────┘
                              │
                              ├─ [Logs sent]
                              │
              ┌───────────────▼────────────────┐
              │  GCP Cloud Logging             │
              │  (Structured logs)             │
              └────────────────────────────────┘
```

---

## 🔄 Deployment Workflow

### Step-by-Step Manual Deploy

```powershell
# 1. Make code changes
git add .
git commit -m "feat: new feature"

# 2. Push to GitHub
git push origin main

# 3. Wait for Cloud Build auto-trigger (or manual trigger)
gcloud builds triggers run rmgpgab-god-eye-asia-southeast1-quaso-hub-pantau-kos--mabje --branch=main

# 4. Check build status
gcloud builds list --project=kos-monitor --limit=3

# 5. Watch logs
gcloud builds log BUILD_ID --project=kos-monitor --stream

# 6. Verify Cloud Run service deployed
gcloud run services list --project=kos-monitor

# 7. Test the service
curl https://god-eye.ikrn.engineer/
```

### Alternative: Direct Deploy (without Cloud Build)

```powershell
# From Windows
deploy.cmd

# From Unix/Mac
bash deploy.sh
```

This directly builds Docker image → pushes to Artifact Registry → deploys to Cloud Run (no Cloud Build trigger needed).

---

## 📊 Traffic & Monitoring

### Cloud Run Metrics
- **Requests:** All POST /webhook (Telegram) + GET /dashboard (UI)
- **Latency:** Typical 1-2s (analysis requests up to 120s timeout)
- **Errors:** Logged to Cloud Logging
- **Concurrency:** 1 worker + 8 threads per worker (gunicorn config)

### Firestore Metrics
- **Reads:** Per query to fetch listings
- **Writes:** Per new listing received, user feedback updated
- **Storage:** ~10-50KB per listing document

### Cost Estimate (Monthly)
- Cloud Run: ~$5-15 (based on invocations + CPU time)
- Firestore: ~$5-20 (based on read/write operations)
- Artifact Registry: <$1 (free tier includes 500GB)
- **Total:** ~$10-35/month

---

## 🔐 Security

### Authentication
- **Telegram:** Webhook token validation (Flask checks X-Telegram-Bot-Api-Secret-Token)
- **n8n:** Optional X-Secret header check (N8N_WEBHOOK_SECRET)
- **Firestore:** Service account (IAM role restricted to project)
- **GCP:** All services within same project, no cross-project access

### Secrets Management
- **Stored in:** `.env` file (local) or Cloud Run environment variables (production)
- **Never committed** to git (`.env` in `.gitignore`)
- **Rotation:** Manual — update env vars in deploy script, re-deploy

### API Keys
- `TELEGRAM_TOKEN` — needs protection (if leaked, attackers can control bot)
- `GEMINI_API_KEY` — needs protection (if leaked, attackers can call Gemini API)
- `MAPS_API_KEY` — less critical (API restriction to MAPS APIs only)
- `DEEPSEEK_API_KEY` — needs protection (if leaked, attackers can call DeepSeek)

---

## 🚀 Future Improvements

- [ ] Use GitHub Actions for PR validation + linting (before Cloud Build)
- [ ] Add Cloud Monitoring dashboard for real-time metrics
- [ ] Implement Cloud Tasks for delayed/scheduled jobs (for long analysis)
- [ ] Use Secret Manager for sensitive env vars (not plain env vars)
- [ ] Add Cloud Armor for DDoS protection
- [ ] Set up alerts (PagerDuty / Slack) for service failures
- [ ] Implement canary deployments (Cloud Run traffic splitting)
- [ ] Add database backups + disaster recovery plan

---

*Last updated: 2026-05-26*
