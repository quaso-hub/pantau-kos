#!/usr/bin/env python3
"""
GCP Resource Inventory Script

Check for available backups, exports, or data in:
- Cloud Storage (gs:// buckets)
- Cloud Datastore (alternative to Firestore)
- Firestore exports
- Recent backups
"""

import json
import subprocess
from pathlib import Path

PROJECT_ID = "kos-monitor"

def run_gcloud(cmd: list) -> str:
    """Run a gcloud command and return output."""
    try:
        result = subprocess.run(
            ["gcloud"] + cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout + result.stderr
    except Exception as e:
        return f"Error: {e}"


def check_resources():
    """Check all GCP resources for potential data recovery."""
    print("\n" + "="*70)
    print("  GCP RESOURCE INVENTORY - Checking for Backups/Exports")
    print("="*70 + "\n")
    
    resources = {
        "Cloud Storage Buckets": [
            "gsutil", "ls", "-p", PROJECT_ID
        ],
        "Firestore Backups": [
            "gcloud", "firestore", "backups", "list",
            "--project", PROJECT_ID
        ],
        "Firestore Databases": [
            "gcloud", "firestore", "databases", "list",
            "--project", PROJECT_ID
        ],
        "Datastore Entities": [
            "gcloud", "datastore", "entities", "list",
            "--project", PROJECT_ID,
            "--kind", "kos_listings"
        ],
        "Recent Operations": [
            "gcloud", "operations", "list",
            "--project", PROJECT_ID,
            "--limit", "10",
            "--sort-by", "~CREATE_TIME"
        ],
    }
    
    print(f"🔍 Checking resources in project: {PROJECT_ID}\n")
    
    for resource_name, cmd in resources.items():
        print(f"📊 {resource_name}:")
        print("-" * 70)
        
        output = run_gcloud(cmd)
        
        if "Error" in output or "does not exist" in output or "NOT_FOUND" in output:
            print(f"   ❌ Not found or not available")
        elif "ERROR" in output.upper():
            print(f"   ⚠️  Error: {output[:200]}")
        elif not output.strip():
            print(f"   ⓘ  No results")
        else:
            print(output[:500])
        
        print()
    
    print("="*70 + "\n")
    print("💡 Summary:")
    print("   If Cloud Storage buckets exist → May have Firestore exports")
    print("   If Backups exist → Can restore to new Firestore instance")
    print("   If empty → Data recovery likely not possible")
    print("\n")


if __name__ == "__main__":
    check_resources()
