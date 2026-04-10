"""Test positions API endpoint."""

import sys
sys.path.insert(0, '.')

import requests
import json

# Create a session
session = requests.Session()

print("=" * 70)
print("Testing Positions API")
print("=" * 70)

# Login
print("\n1. Logging in...")
login_response = session.post(
    "http://127.0.0.1:8000/auth/login",
    json={"username": "admin", "password": "admin123"}
)

if login_response.status_code != 200:
    print(f"❌ Login failed")
    exit(1)

print("✅ Login successful")

# Get positions
print("\n2. Getting positions...")
positions_response = session.get("http://127.0.0.1:8000/account/positions?mode=DEMO")

if positions_response.status_code == 200:
    data = positions_response.json()
    print(f"\n📊 Total Positions: {data.get('total_count', 0)}")
    
    positions = data.get('positions', [])
    for pos in positions:
        print(f"\n   Position {pos.get('id')}:")
        print(f"      Symbol: {pos.get('symbol')}")
        print(f"      Side: {pos.get('side')}")
        print(f"      Quantity: ${pos.get('quantity', 0):,.2f}")
        print(f"      Entry Price: ${pos.get('entry_price', 0):,.2f}")
        print(f"      Current Price: ${pos.get('current_price', 0):,.2f}")
        print(f"      Unrealized P&L: ${pos.get('unrealized_pnl', 0):,.2f}")
        print(f"      eToro Position ID: {pos.get('etoro_position_id')}")
        print(f"      Opened: {pos.get('opened_at')}")
    
    print(f"\n📄 Full JSON:")
    print(json.dumps(data, indent=2))
else:
    print(f"❌ Failed: {positions_response.status_code}")
    print(positions_response.text)

print("\n" + "=" * 70)
