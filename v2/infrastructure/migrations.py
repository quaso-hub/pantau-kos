"""
PostgreSQL Schema Initialization & Migrations

This module provides idempotent SQL migrations to set up the PostgreSQL database
for the KOS Monitor bot. All migrations use CREATE TABLE IF NOT EXISTS patterns
to be safely re-runnable.

Collections -> Tables Mapping:
  - kos_listings -> kos_listings (listing analysis results)
  - user_preferences -> user_preferences (user search preferences)
  - blacklist -> blacklist (blocked phone numbers)
  - area_cache -> area_cache (area statistics cache, 24h TTL)
  - sessions -> sessions (chat session state)
"""

import asyncpg
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# SQL migrations to create all required tables
MIGRATION_001_CREATE_TABLES = """
-- kos_listings: Scraped listing analysis results
CREATE TABLE IF NOT EXISTS kos_listings (
  id VARCHAR(255) PRIMARY KEY,
  source VARCHAR(50) NOT NULL,
  source_link TEXT NOT NULL UNIQUE,
  text_snippet TEXT,
  location VARCHAR(255),
  price INTEGER,
  phones JSONB DEFAULT '[]',
  score FLOAT,
  fraud_risk VARCHAR(20),
  distance_km FLOAT,
  geocode JSONB,
  air_quality JSONB,
  recommendation TEXT,
  timestamp TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  INDEX_created_at TIMESTAMP DEFAULT NOW()
);

-- user_preferences: User search configuration
CREATE TABLE IF NOT EXISTS user_preferences (
  chat_id BIGINT PRIMARY KEY,
  max_distance_km FLOAT DEFAULT 15.0,
  budget_min INTEGER DEFAULT 300000,
  budget_max INTEGER DEFAULT 800000,
  area_preferences JSONB DEFAULT '[]',
  skip_counts JSONB DEFAULT '{}',
  avoided_areas JSONB DEFAULT '[]',
  updated_at TIMESTAMP DEFAULT NOW()
);

-- blacklist: Blocked phone numbers
CREATE TABLE IF NOT EXISTS blacklist (
  phone VARCHAR(20) PRIMARY KEY,
  reason TEXT,
  added_at TIMESTAMP DEFAULT NOW()
);

-- area_cache: Area statistics with 24h TTL
CREATE TABLE IF NOT EXISTS area_cache (
  area_name VARCHAR(255) PRIMARY KEY,
  skip_count INTEGER DEFAULT 0,
  survey_count INTEGER DEFAULT 0,
  avg_score FLOAT DEFAULT 0.0,
  cached_at TIMESTAMP DEFAULT NOW()
);

-- sessions: User chat session state
CREATE TABLE IF NOT EXISTS sessions (
  chat_id BIGINT PRIMARY KEY,
  state VARCHAR(50) DEFAULT 'idle',
  current_listing_id VARCHAR(255),
  created_at TIMESTAMP DEFAULT NOW(),
  last_activity TIMESTAMP DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_kos_listings_created_at 
  ON kos_listings (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_kos_listings_source_link 
  ON kos_listings (source_link);
CREATE INDEX IF NOT EXISTS idx_kos_listings_fraud_risk 
  ON kos_listings (fraud_risk);
CREATE INDEX IF NOT EXISTS idx_area_cache_cached_at 
  ON area_cache (cached_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_last_activity 
  ON sessions (last_activity DESC);
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    """
    Execute all pending migrations against the database.
    
    Args:
        pool: asyncpg connection pool
        
    Raises:
        asyncpg.PostgresError: If migration fails
    """
    try:
        async with pool.acquire() as conn:
            # Execute all migrations
            await conn.execute(MIGRATION_001_CREATE_TABLES)
            logger.info("✅ PostgreSQL migrations completed successfully")
    except asyncpg.PostgresError as e:
        logger.error(f"❌ Migration failed: {e}")
        raise


async def init_database(db_url: str) -> asyncpg.Pool:
    """
    Initialize the database with all required tables and indexes.
    
    Args:
        db_url: PostgreSQL connection string (e.g., postgresql://user:pass@host/db)
        
    Returns:
        asyncpg connection pool
        
    Raises:
        asyncpg.PostgresError: If connection or migration fails
    """
    try:
        # Create connection pool
        pool = await asyncpg.create_pool(
            db_url,
            min_size=1,
            max_size=5,
            command_timeout=60
        )
        logger.info("✅ Database connection pool created")
        
        # Run migrations
        await run_migrations(pool)
        
        return pool
    except asyncpg.PostgresError as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error during database init: {e}")
        raise


# Version tracking for future migrations
CURRENT_SCHEMA_VERSION = "001"
MIGRATIONS = [
    ("001", "Create initial schema (tables & indexes)", MIGRATION_001_CREATE_TABLES),
]
