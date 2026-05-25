# Architecture After PostgreSQL Migration

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        KOS Monitor v6.0                             │
│                   Firestore → PostgreSQL Migration                  │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Deployment Layer (PythonAnywhere Free Tier)                         │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Flask + python-telegram-bot (WSGI Application)             │   │
│  │ ├─ /health — Health check endpoint                          │   │
│  │ ├─ /webhook — Telegram webhook (POST updates)              │   │
│  │ ├─ /monitor — n8n monitor webhook                          │   │
│  │ └─ /dashboard — Web dashboard (Tailwind + Jinja2)          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│         ↓ (sync)                                   ↓ (async)        │
│  ┌────────────────────┐               ┌──────────────────────┐     │
│  │ Flask Request/     │               │ PTB Event Loop       │     │
│  │ Response (sync)    │               │ (background thread)  │     │
│  └────────────────────┘               └──────────────────────┘     │
│                                              ↓                      │
└──────────────────────┬───────────────────────┬───────────────────────┘
                       ↓                       ↓
         ┌─────────────────────┐   ┌──────────────────────┐
         │  Services Layer     │   │ Gateway Layer        │
         ├─────────────────────┤   ├──────────────────────┤
         │ AnalysisService     │   │ GeminiGateway        │
         │ (score listings)    │   │ DeepSeekGateway      │
         │                     │   │ GoogleMapsGateway    │
         └─────────────────────┘   └──────────────────────┘
                  ↓                          ↓
         ┌──────────────────────────────────────────────┐
         │  Repository Layer (Data Abstraction)         │
         ├──────────────────────────────────────────────┤
         │ ✅ PostgresListingRepo                        │
         │ ✅ PostgresPreferencesRepo                    │
         │ ✅ PostgresBlacklistRepo                      │
         │ ✅ PostgresAreaCacheRepo                      │
         │ ✅ PostgresSessionRepo                        │
         └──────────────────────────────────────────────┘
                        ↓
         ┌──────────────────────────────────────────────┐
         │  asyncpg Connection Pool (1-5 connections)   │
         │  + Async SQL Query Execution                 │
         └──────────────────────────────────────────────┘
                        ↓
         ┌──────────────────────────────────────────────┐
         │  PostgreSQL Database (Neon Free Tier)        │
         │  • 3 projects                                │
         │  • 1 GB storage                              │
         │  • 5 concurrent connections (enough!)        │
         │  • Region: Asia Southeast (ap-southeast-1)   │
         └──────────────────────────────────────────────┘
```

## Data Layer Architecture

### Connection Pool Management

```python
# v2/adapters/repositories/postgres_repo.py

Global Pool:
  _pool: Optional[asyncpg.Pool] = None

Initialization (on app startup):
  init_pool(db_url: str) → Creates pool with:
    - min_size: 1 connection
    - max_size: 5 connections (free tier limit)
    - command_timeout: 60 seconds

Acquisition (in each method):
  async with pool.acquire() as conn:
      await conn.execute(query, params)

Cleanup (on app shutdown):
  close_pool() → Closes all connections
```

### Database Schema

```sql
┌─────────────────────────────────────────────────────┐
│ PostgreSQL Database: "neondb"                       │
├─────────────────────────────────────────────────────┤
│                                                     │
│ TABLE: kos_listings                                │
│ ├─ id (VARCHAR, PRIMARY KEY)                       │
│ ├─ source (VARCHAR)         — e.g., "mamikos"      │
│ ├─ source_link (TEXT, UNIQUE)                      │
│ ├─ text_snippet (TEXT)      — listing description  │
│ ├─ location (VARCHAR)       — city/area            │
│ ├─ price (INTEGER)          — Rp                   │
│ ├─ phones (JSONB)           — ["0811...", ...]     │
│ ├─ score (FLOAT)            — 0-100                │
│ ├─ fraud_risk (VARCHAR)     — HIGH/MEDIUM/LOW      │
│ ├─ distance_km (FLOAT)      — from user location   │
│ ├─ geocode (JSONB)          — {lat, lng, ...}      │
│ ├─ air_quality (JSONB)      — {AQI, status, ...}   │
│ ├─ recommendation (TEXT)    — analysis notes       │
│ ├─ timestamp (TIMESTAMP)    — when posted          │
│ ├─ created_at (TIMESTAMP)   — inserted at          │
│ └─ INDEX on: created_at, source_link, fraud_risk   │
│                                                     │
│ TABLE: user_preferences                            │
│ ├─ chat_id (BIGINT, PRIMARY KEY)                   │
│ ├─ max_distance_km (FLOAT)  — default 15.0         │
│ ├─ budget_min (INTEGER)     — default 300,000      │
│ ├─ budget_max (INTEGER)     — default 800,000      │
│ ├─ area_preferences (JSONB) — ["Senayan", ...]     │
│ ├─ skip_counts (JSONB)      — {area: count, ...}   │
│ ├─ avoided_areas (JSONB)    — ["Blok M", ...]      │
│ └─ updated_at (TIMESTAMP)                          │
│                                                     │
│ TABLE: blacklist                                   │
│ ├─ phone (VARCHAR, PRIMARY KEY)                    │
│ ├─ reason (TEXT)            — why blocked          │
│ └─ added_at (TIMESTAMP)                            │
│                                                     │
│ TABLE: area_cache                                  │
│ ├─ area_name (VARCHAR, PRIMARY KEY)                │
│ ├─ skip_count (INTEGER)     — times skipped        │
│ ├─ survey_count (INTEGER)   — times searched       │
│ ├─ avg_score (FLOAT)        — average listing      │
│ ├─ cached_at (TIMESTAMP)    — TTL: 24h             │
│ └─ INDEX on: cached_at DESC                        │
│                                                     │
│ TABLE: sessions                                    │
│ ├─ chat_id (BIGINT, PRIMARY KEY)                   │
│ ├─ state (VARCHAR)          — conversation state   │
│ ├─ current_listing_id (VARCHAR)                    │
│ ├─ created_at (TIMESTAMP)                          │
│ ├─ last_activity (TIMESTAMP)                       │
│ └─ INDEX on: last_activity DESC                    │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Firestore → PostgreSQL Mapping

| Firestore | PostgreSQL | Rationale |
|-----------|-----------|-----------|
| Collection | Table | Firestore collections become SQL tables |
| Document ID | Primary Key (id) | Unique document identifier |
| Document fields | Table columns | Field becomes column |
| Nested objects (phones, geocode, air_quality) | JSONB | JSON Binary for flexibility + querying |
| Auto timestamp (createdAt) | created_at with DEFAULT NOW() | Server-side timestamp |
| Reference (e.g., to user) | Foreign key (implicit via chat_id) | Maintain referential integrity |
| TTL (area_cache: 24h) | Application logic in get_cache() | Check cached_at and age |

## Repository Pattern Details

### Example: PostgresListingRepo

```python
class PostgresListingRepo:
    def __init__(self, config: PostgresConfig):
        self.config = config
    
    async def save(self, result: AnalysisResult) -> None:
        """Save or update a listing."""
        pool = _get_pool()
        async with pool.acquire() as conn:
            # Serialize complex fields
            phones_json = json.dumps(result.phones)
            geocode_json = json.dumps(result.geocode.dict()) if result.geocode else None
            air_quality_json = json.dumps(result.air_quality.dict()) if result.air_quality else None
            
            # Upsert (INSERT or UPDATE)
            await conn.execute("""
                INSERT INTO kos_listings (id, source, source_link, ...)
                VALUES ($1, $2, $3, ...)
                ON CONFLICT (id) DO UPDATE SET ...
            """, result.id, result.source, result.source_link, ...)
    
    async def exists_by_link(self, source_link: str) -> bool:
        """Check if already scraped (prevent duplicates)."""
        pool = _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM kos_listings WHERE source_link = $1",
                source_link
            )
            return row is not None
    
    async def count_high_risk(self) -> int:
        """Count fraud risk listings for stats."""
        pool = _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) as count FROM kos_listings WHERE fraud_risk = 'HIGH'"
            )
            return row['count']
```

## Configuration Management

### Environment Variables

```env
# Telegram
TELEGRAM_TOKEN=8742407345:AAF6K77rewrtu_uLQ4I8yrD0_BgWNHngGZc
ALLOWED_CHAT_ID=6215704457

# AI APIs
GEMINI_API_KEY=AIzaSyC_8T67cfhxgzkWusfYMcxlsC4hY8nx0fc
DEEPSEEK_API_KEY=sk-bcb176314ec24be7ab2d1bb3f3289a65
MAPS_API_KEY=AIzaSyCT2X80spEIax5cWa-vxa_orru6PGtmJQo

# Database (PostgreSQL)
DATABASE_URL=postgresql://neondb_owner:npg_...@ep-....compute-1.amazonaws.com/neondb?sslmode=require
# OR individual components:
# DATABASE_HOST=...
# DATABASE_USER=neondb_owner
# DATABASE_PASSWORD=...
# DATABASE_NAME=neondb
```

### AppConfig Structure

```python
@dataclass
class AppConfig:
    telegram: TelegramConfig
    gemini: GeminiConfig
    deepseek: DeepSeekConfig
    maps: MapsConfig
    postgres: PostgresConfig  # ← New!
    
    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            telegram=TelegramConfig.from_env(),
            gemini=GeminiConfig.from_env(),
            deepseek=DeepSeekConfig.from_env(),
            maps=MapsConfig.from_env(),
            postgres=PostgresConfig.from_env(),  # ← New!
        )
```

## Application Lifecycle

### Startup Sequence (main.py)

```
1. Load configuration from environment
   └─ config = AppConfig.from_env()

2. Initialize PostgreSQL database (NEW)
   ├─ Parse DATABASE_URL from config
   ├─ Create asyncpg connection pool
   └─ Run migrations (CREATE TABLE IF NOT EXISTS)

3. Build DI Container
   ├─ Create PostgreSQL repository instances (NEW)
   ├─ Create Gemini/DeepSeek/Maps gateways
   └─ Create service instances

4. Start PTB Application (background thread)
   ├─ Create new event loop
   └─ await app.start()

5. Start Flask Web Server
   ├─ Register dashboard blueprint
   └─ Listen on 0.0.0.0:8080
```

### Shutdown Sequence

```
1. Receive SIGTERM (graceful shutdown signal)

2. Wait for running analysis tasks (8 second timeout)
   └─ Give handlers time to complete

3. Close database connection pool (implicit via asyncpg)
   └─ All connections released

4. Stop PTB event loop

5. Exit process with code 0
```

## Performance Characteristics

### Database

| Metric | Value | Notes |
|--------|-------|-------|
| Max connections | 5 | Neon free tier limit; asyncpg pool: 1-5 |
| Query timeout | 60s | Configured in pool init |
| Connection reuse | Yes | Pool maintains persistent connections |
| Indexes | 5 | On frequently queried columns |

### API Calls

| Service | Calls/day (est) | Latency |
|---------|-----------------|---------|
| Gemini (analysis) | 10-20 | 1-3s per listing |
| DeepSeek (alternative) | 5-10 | 1-3s per listing |
| Google Maps (geocoding) | 10-20 | 100-500ms per location |
| Telegram Bot API | 50+ | 100-200ms per message |

### Concurrent Limits

- **Pool connections:** 1-5 (suitable for free tier)
- **PTB concurrent updates:** Unlimited (but DB pool is bottleneck)
- **Flask workers:** 1 (single process on PythonAnywhere free)

## Migration Verification Checklist

- [x] All Firestore imports removed
- [x] All Firestore classes replaced with Postgres* equivalents
- [x] PostgreSQL schema covers all 5 collections
- [x] JSON serialization for complex fields implemented
- [x] Async/await patterns consistent with asyncpg
- [x] Connection pooling initialized on startup
- [x] Error handling and logging added
- [x] Backward compatible config parsing (DATABASE_URL or components)
- [x] git commit and push completed
- [x] No breaking changes to service layer
- [x] No breaking changes to handler layer

## Development vs Production

| Aspect | Development | Production (PythonAnywhere) |
|--------|-------------|--------------------------|
| Database | Local PostgreSQL or Neon | Neon (free tier) |
| Flask debug | True (local) | False (production) |
| Log level | DEBUG | INFO/WARNING |
| Connection pool | 1-5 | 1-5 (same) |
| Telegram webhook | ngrok/local port | https://god-eye.ikrn.engineer |

---

**Complete migration: Firestore (GCP, terminated) → PostgreSQL (Neon, free tier)**

**Status: ✅ READY FOR DEPLOYMENT**
