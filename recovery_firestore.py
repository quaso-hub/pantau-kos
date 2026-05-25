#!/usr/bin/env python3
"""
Firestore Data Recovery Script

Attempt to connect to GCP Firestore and export all collections to JSON.
This is a recovery attempt in case the GCP account is still accessible.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Try to import Firestore
try:
    from google.cloud import firestore
    from google.oauth2 import service_account
    print("✅ google-cloud-firestore imported successfully")
except ImportError as e:
    print(f"❌ Cannot import google-cloud-firestore: {e}")
    print("   Installing...")
    os.system("pip install google-cloud-firestore")
    from google.cloud import firestore

# Configuration
PROJECT_ID = "kos-monitor"
COLLECTIONS = [
    "kos_listings",
    "user_preferences", 
    "blacklist",
    "area_cache",
    "sessions",
]

OUTPUT_DIR = Path(__file__).parent / "firestore_recovery"


def convert_to_json_serializable(obj):
    """Convert Firestore objects to JSON-serializable format."""
    if hasattr(obj, '__dict__'):
        # Firestore Timestamp, GeoPoint, etc.
        if obj.__class__.__name__ == 'Timestamp':
            return obj.isoformat()
        elif obj.__class__.__name__ == 'GeoPoint':
            return {"lat": obj.latitude, "lng": obj.longitude}
        else:
            return obj.__dict__
    elif isinstance(obj, dict):
        return {k: convert_to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_json_serializable(item) for item in obj]
    elif isinstance(obj, bytes):
        return obj.decode('utf-8', errors='replace')
    return obj


def export_collection(db, collection_name: str, output_file: Path) -> int:
    """
    Export a Firestore collection to JSON file.
    
    Args:
        db: Firestore client
        collection_name: Name of collection to export
        output_file: Path to save JSON file
        
    Returns:
        Number of documents exported
    """
    try:
        docs = db.collection(collection_name).stream()
        
        count = 0
        data = {}
        
        for doc in docs:
            doc_data = doc.to_dict()
            # Convert Firestore types to JSON-serializable format
            doc_data = convert_to_json_serializable(doc_data)
            data[doc.id] = doc_data
            count += 1
            
            if count % 100 == 0:
                print(f"  📄 Exported {count} documents from {collection_name}...")
        
        # Write to file
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"✅ {collection_name}: {count} documents exported to {output_file.name}")
        return count
        
    except Exception as e:
        print(f"❌ Failed to export {collection_name}: {e}")
        return 0


def main():
    """Attempt to recover data from Firestore."""
    print("\n" + "="*70)
    print("  FIRESTORE DATA RECOVERY ATTEMPT")
    print("="*70 + "\n")
    
    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    try:
        # Initialize Firestore client
        # This uses Application Default Credentials (ADC)
        # which includes: gcloud user creds, service account, environment vars
        print(f"🔗 Connecting to Firestore project: {PROJECT_ID}")
        db = firestore.Client(project=PROJECT_ID)
        
        # Try a simple read to verify connection
        print("🔍 Testing connection...")
        doc = db.collection("kos_listings").limit(1).stream()
        test_count = sum(1 for _ in doc)
        print(f"✅ Connection successful! kos_listings has documents.")
        
    except Exception as e:
        print(f"\n❌ Cannot connect to Firestore:")
        print(f"   Error: {e}")
        print(f"\n   Possible reasons:")
        print(f"   1. GCP account is suspended/terminated (trial credit exhausted)")
        print(f"   2. Application Default Credentials not valid")
        print(f"   3. Network/firewall issue")
        print(f"   4. Firestore API not enabled in project")
        print(f"\n   Next steps:")
        print(f"   1. Try: gcloud auth login")
        print(f"   2. Try: gcloud auth application-default login")
        print(f"   3. Check: https://console.cloud.google.com/firestore")
        return False
    
    # Export all collections
    print(f"\n📁 Exporting {len(COLLECTIONS)} collections...\n")
    
    total_docs = 0
    recovery_timestamp = datetime.now().isoformat()
    
    for collection_name in COLLECTIONS:
        output_file = OUTPUT_DIR / f"{collection_name}_{recovery_timestamp.replace(':', '-')}.json"
        count = export_collection(db, collection_name, output_file)
        total_docs += count
    
    # Summary
    print(f"\n" + "="*70)
    print(f"📊 RECOVERY SUMMARY")
    print("="*70)
    print(f"✅ Total documents recovered: {total_docs}")
    print(f"📂 Recovery files saved to: {OUTPUT_DIR}")
    print(f"📅 Timestamp: {recovery_timestamp}")
    print("\n💡 Next steps:")
    print(f"   1. Review exported JSON files in: {OUTPUT_DIR}")
    print(f"   2. If successful, run migration script to import to PostgreSQL")
    print(f"   3. If failed, data is permanently lost (GCP account terminated)")
    print("="*70 + "\n")
    
    return total_docs > 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
