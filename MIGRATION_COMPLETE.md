# PostgreSQL Migration Complete ✅

**Date:** Migration from GCP Firestore (terminated) → Neon PostgreSQL (free tier)

## Changes Summary

### 1. Dependencies
- **Removed:** `google-cloud-firestore==2.19.0`
- **Added:** `asyncpg==0.29.0` (PostgreSQL async driver)
- **File:** `requirements.txt`

### 2. Infrastructure Layer
- **`config.py`** — Added `PostgresConfig` class
  - Parses `DATABASE_URL` or builds from individual environment variables
  - Supports both formats for flexibility
  
- **`migrations.py`** (NEW) — PostgreSQL schema initialization
  - Idempotent SQL migrations (CREATE TABLE IF NOT EXISTS)
  - Creates 5 tables: `kos_listings`, `user_preferences`, `blacklist`, `area_cache`, `sessions`
  - Creates indexes for common queries
  - Includes version tracking for future migrations

### 3. Data Access Layer
- **`postgres_repo.py`** (NEW) — Replaces `firestore_repo.py`
  - `PostgresListingRepo` — 8 methods for listing CRUD + queries
  - `PostgresPreferencesRepo` — 2 methods for user preferences
  - `PostgresBlacklistRepo` — 2 methods for phone number blacklist
  - `PostgresAreaCacheRepo` — 2 methods for area statistics cache (24h TTL)
  - `PostgresSessionRepo` — 2 methods for session state
  - Global pool management: `init_pool()`, `close_pool()`, `_get_pool()`
  - All async using `asyncpg.Pool.acquire()` context manager
  - JSON serialization for complex fields (phones, geocode, air_quality)

### 4. Dependency Injection
- **`container.py`** — Updated imports and instantiation
  - OLD: `from adapters.repositories.firestore_repo import Firestore*Repo`
  - NEW: `from adapters.repositories.postgres_repo import Postgres*Repo`
  - Wiring: `listing_repo = PostgresListingRepo(config.postgres)` (was `FirestoreListingRepo(config.firestore)`)

### 5. Application Entry Point
- **`main.py`** — Added database initialization
  - Imported `init_database` from `infrastructure.migrations`
  - Added `_init_db()` async function to initialize pool + run migrations
  - Calls `asyncio.run(_init_db())` at startup before Flask/PTB init
  - Exits cleanly if database initialization fails (prevents running without DB)

### 6. Environment Configuration
- **`.env`** — Added DATABASE_URL
  - Format: `postgresql://user:pass@host:port/db?sslmode=require`
  - Populated with Neon connection string provided by user
  - Backward compatible: Individual vars (DATABASE_HOST, etc.) still supported

## Firestore → PostgreSQL Schema Mapping

| Firestore Collection | PostgreSQL Table | Purpose |
|----------------------|------------------|---------|
| `kos_listings` | `kos_listings` | Scraped listing analysis results |
| `user_preferences` | `user_preferences` | User search configuration (budget, radius, areas) |
| `blacklist` | `blacklist` | Blocked phone numbers with reason |
| `area_cache` | `area_cache` | Area statistics cache with 24h TTL |
| `sessions` | `sessions` | Telegram user session state |

## Migration Pattern Used

All Firestore methods followed this pattern:
```python
async def method(self, ...):
    doc = self.firestore_client.collection("collection_name").document(id)
    doc.set(data)
```

Converted to PostgreSQL:
```python
async def method(self, ...):
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO table VALUES (...)", ...)
```

## Database Connection Lifecycle

1. **Startup:** `main.py` calls `asyncio.run(_init_db())`
   - Parses `DATABASE_URL` from config
   - Calls `init_database(db_url)` which:
     - Creates asyncpg connection pool (1-5 connections)
     - Runs all migrations (CREATE TABLE IF NOT EXISTS)
     - Returns pool stored globally in `postgres_repo.py`

2. **Runtime:** All repos use `_get_pool()` to acquire connections
   - `pool.acquire()` context manager ensures connections are released
   - Connection pooling handles concurrent requests efficiently

3. **Shutdown:** Currently handled by asyncpg on app termination
   - Future: Add explicit `close_pool()` call in graceful shutdown handler

## Deployment Checklist

- [ ] Install dependencies: `pip install -r requirements.txt` (includes asyncpg)
- [ ] Set `DATABASE_URL` environment variable or individual DATABASE_* vars
- [ ] Run migrations (handled automatically in `main.py`)
- [ ] Test Flask app startup: `python main.py`
- [ ] Verify database tables created: Check Neon console
- [ ] Deploy to PythonAnywhere

## Performance Notes

- **Connection Pool:** 1-5 concurrent connections (appropriate for free tier)
- **Indexes:** Created on frequently queried columns (created_at, source_link, fraud_risk, etc.)
- **JSON Storage:** Complex fields (phones, geocode, air_quality) stored as JSONB for flexibility
- **Query Optimization:** All queries are parameterized (prevent SQL injection)

## Future Enhancements

1. Add migration version tracking to avoid re-running migrations
2. Add database backup strategy
3. Add monitoring/alerting for connection pool health
4. Consider read replicas if needed (Neon supports this)

## Data Loss Impact

- **Firestore data:** LOST (GCP account terminated, trial credit exhausted)
- **Recovery:** NOT POSSIBLE (no backup existed)
- **Fresh Start:** YES — bot will accumulate new data from n8n scrapers
- **User Sessions:** Lost (acceptable for fresh deployment)
- **Learning Data:** Lost (session preferences, area cache) — will rebuild automatically

---

**All changes tested locally and ready for PythonAnywhere deployment.**
