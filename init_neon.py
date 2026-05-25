#!/usr/bin/env python3
"""
Neon PostgreSQL Database Initialization Script

This script:
1. Tests connection to Neon PostgreSQL
2. Creates all required tables (kos_listings, user_preferences, blacklist, area_cache, sessions)
3. Creates indexes for performance
4. Verifies schema is ready for application use
"""

import asyncio
import asyncpg
import sys
from datetime import datetime
from pathlib import Path

# Connection string (from .env or passed as argument)
# Format: postgresql://user:password@host:port/database?sslmode=require
DATABASE_URL = (
    "postgresql://neondb_owner:npg_ZrOPR1udvmY7"
    "@ep-withered-feather-aotbugls.c-2.ap-southeast-1.aws.neon.tech/neondb"
    "?sslmode=require"
)

# SQL Schema Definition
SCHEMA_SQL = """
-- ============================================================================
-- KOS Monitor PostgreSQL Schema (migrated from Firestore)
-- ============================================================================

-- Table: kos_listings
-- Purpose: Scraped listing analysis results
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
    created_at TIMESTAMP DEFAULT NOW()
);

-- Index for common queries
CREATE INDEX IF NOT EXISTS idx_kos_listings_created_at 
    ON kos_listings (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_kos_listings_source_link 
    ON kos_listings (source_link);
CREATE INDEX IF NOT EXISTS idx_kos_listings_fraud_risk 
    ON kos_listings (fraud_risk);

-- ============================================================================

-- Table: user_preferences
-- Purpose: User search configuration and preferences
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

-- ============================================================================

-- Table: blacklist
-- Purpose: Blocked phone numbers
CREATE TABLE IF NOT EXISTS blacklist (
    phone VARCHAR(20) PRIMARY KEY,
    reason TEXT,
    added_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================================

-- Table: area_cache
-- Purpose: Area statistics cache with 24h TTL
CREATE TABLE IF NOT EXISTS area_cache (
    area_name VARCHAR(255) PRIMARY KEY,
    skip_count INTEGER DEFAULT 0,
    survey_count INTEGER DEFAULT 0,
    avg_score FLOAT DEFAULT 0.0,
    cached_at TIMESTAMP DEFAULT NOW()
);

-- Index for TTL filtering
CREATE INDEX IF NOT EXISTS idx_area_cache_cached_at 
    ON area_cache (cached_at DESC);

-- ============================================================================

-- Table: sessions
-- Purpose: Telegram user chat session state
CREATE TABLE IF NOT EXISTS sessions (
    chat_id BIGINT PRIMARY KEY,
    state VARCHAR(50) DEFAULT 'idle',
    current_listing_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    last_activity TIMESTAMP DEFAULT NOW()
);

-- Index for session cleanup
CREATE INDEX IF NOT EXISTS idx_sessions_last_activity 
    ON sessions (last_activity DESC);

-- ============================================================================
-- Schema initialization complete!
-- ============================================================================
"""


async def test_connection(db_url: str) -> bool:
    """Test if we can connect to the database."""
    try:
        print("🔗 Testing connection to Neon PostgreSQL...")
        conn = await asyncpg.connect(db_url)
        result = await conn.fetchval("SELECT version()")
        print(f"✅ Connection successful!")
        print(f"   PostgreSQL: {result[:80]}...")
        await conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def create_schema(db_url: str) -> bool:
    """Create all database schema (tables and indexes)."""
    try:
        print("\n📊 Creating database schema...")
        
        conn = await asyncpg.connect(db_url)
        
        # Execute schema creation (no format needed, schema_sql is static)
        await conn.execute(SCHEMA_SQL)
        print(f"✅ Schema created successfully!")
        
        await conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Schema creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def verify_schema(db_url: str) -> bool:
    """Verify that all tables were created correctly."""
    try:
        print("\n✔️  Verifying schema...")
        
        conn = await asyncpg.connect(db_url)
        
        # Query table information
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        
        expected_tables = {
            "kos_listings",
            "user_preferences",
            "blacklist",
            "area_cache",
            "sessions",
        }
        
        found_tables = {row['table_name'] for row in tables}
        
        print(f"\n   Tables in database ({len(found_tables)}):")
        for table in sorted(found_tables):
            status = "✅" if table in expected_tables else "ℹ️ "
            print(f"      {status} {table}")
        
        # Check for missing tables
        missing = expected_tables - found_tables
        if missing:
            print(f"\n   ❌ Missing tables: {missing}")
            await conn.close()
            return False
        
        # Check indexes
        indexes = await conn.fetch("""
            SELECT tablename, indexname 
            FROM pg_indexes 
            WHERE schemaname = 'public'
            ORDER BY tablename, indexname;
        """)
        
        print(f"\n   Indexes ({len(indexes)}):")
        for idx in indexes:
            print(f"      ✅ {idx['tablename']}.{idx['indexname']}")
        
        print(f"\n✅ Schema verification passed!")
        
        await conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Schema verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def get_schema_stats(db_url: str) -> None:
    """Get detailed schema statistics."""
    try:
        print("\n📈 Schema Statistics:")
        
        conn = await asyncpg.connect(db_url)
        
        # Get table sizes
        sizes = await conn.fetch("""
            SELECT 
                schemaname,
                tablename,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
                (SELECT count(*) FROM information_schema.columns 
                 WHERE table_schema = schemaname AND table_name = tablename) AS columns
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename;
        """)
        
        total_size = 0
        for row in sizes:
            print(f"   📋 {row['tablename']:20} | Columns: {row['columns']:2} | Size: {row['size']}")
        
        # Get database info
        db_info = await conn.fetchrow("""
            SELECT 
                current_database() AS database,
                pg_size_pretty(pg_database_size(current_database())) AS size,
                version() AS version;
        """)
        
        print(f"\n   🗄️  Database: {db_info['database']}")
        print(f"   💾 Total size: {db_info['size']}")
        print(f"   🔧 Version: {db_info['version'][:50]}...")
        
        await conn.close()
        
    except Exception as e:
        print(f"⚠️  Could not get stats: {e}")


async def main():
    """Main initialization workflow."""
    print("\n" + "="*75)
    print("  NEON POSTGRESQL - DATABASE INITIALIZATION")
    print("="*75)
    
    print(f"\n📍 Database URL: postgresql://***:***@ep-...neon.tech/neondb?sslmode=require")
    
    # Step 1: Test connection
    if not await test_connection(DATABASE_URL):
        print("\n❌ Cannot proceed without database connection!")
        return False
    
    # Step 2: Create schema
    if not await create_schema(DATABASE_URL):
        print("\n❌ Schema creation failed!")
        return False
    
    # Step 3: Verify schema
    if not await verify_schema(DATABASE_URL):
        print("\n❌ Schema verification failed!")
        return False
    
    # Step 4: Get stats
    await get_schema_stats(DATABASE_URL)
    
    # Summary
    print("\n" + "="*75)
    print("✅ DATABASE INITIALIZATION COMPLETE!")
    print("="*75)
    print("\n📝 Next steps:")
    print("   1. Copy the DATABASE_URL to your .env file")
    print("   2. Deploy to PythonAnywhere")
    print("   3. Run: python main.py (to initialize pool)")
    print("   4. Test endpoints: /health, /webhook")
    print("   5. Configure Telegram webhook")
    print("\n💡 Database is now ready for application use!")
    print("="*75 + "\n")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
