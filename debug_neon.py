#!/usr/bin/env python3
"""Debug Neon connection issues"""

import asyncio
import asyncpg
import ssl

DATABASE_URL = (
    "postgresql://neondb_owner:npg_ZrOPR1udvmY7"
    "@ep-withered-feather-aotbugls.c-2.ap-southeast-1.aws.neon.tech/neondb"
    "?sslmode=require"
)

async def debug_connection():
    print("🔍 Debugging Neon connection...\n")
    
    print(f"📍 Connection string:")
    print(f"   postgresql://neondb_owner:***@ep-withered-feather-aotbugls.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require\n")
    
    # Parse components
    parts = DATABASE_URL.replace("postgresql://", "").split("@")
    creds, host_part = parts[0], parts[1]
    user, password = creds.split(":")
    
    host_parts = host_part.split("/")
    host = host_parts[0]
    database = host_parts[1].split("?")[0]
    
    print(f"✔️  Connection components:")
    print(f"   User: {user}")
    print(f"   Password: {'*' * len(password)}")
    print(f"   Host: {host}")
    print(f"   Port: 5432 (default)")
    print(f"   Database: {database}")
    print(f"   SSL: required\n")
    
    # Try connection with detailed error
    print("🔗 Attempting connection...\n")
    
    try:
        # Try simple connection first
        conn = await asyncpg.connect(DATABASE_URL)
        result = await conn.fetchval("SELECT 1")
        print(f"✅ Connection successful! Result: {result}")
        await conn.close()
        return True
        
    except asyncpg.InvalidCatalogNameError as e:
        print(f"❌ Catalog (database) error: {e}")
        print(f"   → Database name might be wrong or doesn't exist\n")
        
    except asyncpg.InvalidCredentialsError as e:
        print(f"❌ Credentials error: {e}")
        print(f"   → Username or password might be wrong\n")
        
    except asyncpg.CannotConnectNowError as e:
        print(f"❌ Cannot connect error: {e}")
        print(f"   → Server might be down or IP blocked\n")
        
    except OSError as e:
        print(f"❌ Network error: {e}")
        print(f"   → DNS resolution failed or host unreachable\n")
        
    except Exception as e:
        print(f"❌ Connection error ({type(e).__name__}): {e}\n")
    
    print("💡 Troubleshooting steps:")
    print("   1. Verify connection string from Neon dashboard")
    print("   2. Check if Neon project is active (not suspended)")
    print("   3. Verify IP whitelist in Neon (might need to add your IP)")
    print("   4. Test: psql <connection_string>")
    print("   5. Check Neon console for any warnings/errors\n")
    
    return False

if __name__ == "__main__":
    asyncio.run(debug_connection())
