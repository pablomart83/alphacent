#!/usr/bin/env python3
"""
Diagnostic script to check why components aren't showing data.
"""

import sqlite3
import json

def check_database():
    """Check database contents."""
    print("=" * 60)
    print("DATABASE DIAGNOSTIC")
    print("=" * 60)
    
    conn = sqlite3.connect('alphacent.db')
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print(f"\nTables in database: {[t[0] for t in tables]}")
    
    # Check each table
    for table in tables:
        table_name = table[0]
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"\n{table_name}: {count} rows")
        
        if count > 0 and count < 10:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
            rows = cursor.fetchall()
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [col[1] for col in cursor.fetchall()]
            print(f"  Columns: {columns}")
            print(f"  Sample data:")
            for row in rows:
                print(f"    {row}")
    
    conn.close()


def check_config():
    """Check configuration files."""
    print("\n" + "=" * 60)
    print("CONFIGURATION DIAGNOSTIC")
    print("=" * 60)
    
    import os
    
    config_files = [
        'config/config.json',
        'config/demo_credentials.json',
        'config/live_credentials.json',
        'config/risk_params.json'
    ]
    
    for config_file in config_files:
        if os.path.exists(config_file):
            print(f"\n✓ {config_file} exists")
            try:
                with open(config_file, 'r') as f:
                    data = json.load(f)
                    # Mask sensitive data
                    if 'public_key' in data:
                        data['public_key'] = '***' if data['public_key'] else None
                    if 'user_key' in data:
                        data['user_key'] = '***' if data['user_key'] else None
                    print(f"  Content: {json.dumps(data, indent=2)}")
            except Exception as e:
                print(f"  Error reading: {e}")
        else:
            print(f"\n✗ {config_file} does not exist")


def check_backend_status():
    """Check if backend is running and responding."""
    print("\n" + "=" * 60)
    print("BACKEND STATUS DIAGNOSTIC")
    print("=" * 60)
    
    import requests
    
    try:
        # Check health endpoint
        response = requests.get('http://localhost:8000/health', timeout=2)
        print(f"\n✓ Backend is running")
        print(f"  Status: {response.status_code}")
        print(f"  Response: {response.json()}")
        
        # Try to get account info (will fail without auth)
        response = requests.get('http://localhost:8000/account?mode=DEMO', timeout=2)
        print(f"\n/account endpoint:")
        print(f"  Status: {response.status_code}")
        if response.status_code == 401:
            print(f"  ✓ Authentication required (expected)")
        else:
            print(f"  Response: {response.text[:200]}")
            
    except requests.exceptions.ConnectionError:
        print(f"\n✗ Backend is not running on http://localhost:8000")
    except Exception as e:
        print(f"\n✗ Error checking backend: {e}")


def main():
    """Run all diagnostics."""
    check_database()
    check_config()
    check_backend_status()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("""
To see data in the frontend:
1. Ensure backend is running (python -m uvicorn src.api.app:app)
2. Login to frontend (default: admin/admin123)
3. Configure eToro credentials in Settings
4. The components will show data once credentials are configured
   
If no eToro credentials:
- Account Overview will show error
- Positions will show empty list
- Orders will show empty list
- Strategies will show empty list (need to create strategies)
- Market Data will work (uses Yahoo Finance fallback)
    """)


if __name__ == '__main__':
    main()
