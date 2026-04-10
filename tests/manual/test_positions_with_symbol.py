#!/usr/bin/env python3
"""Test positions endpoint to verify symbol mapping works."""

import requests
import json

BASE_URL = "http://localhost:8000"

# Create session to handle cookies
session = requests.Session()

# Login
print("Logging in...")
login_response = session.post(
    f"{BASE_URL}/auth/login",
    json={"username": "admin", "password": "admin123"}
)
login_response.raise_for_status()
login_data = login_response.json()
print(f"✅ Logged in as: {login_data['username']}")

# Get positions
print("\nFetching positions...")
positions_response = session.get(
    f"{BASE_URL}/account/positions",
    params={"mode": "DEMO"}
)
positions_response.raise_for_status()
positions_data = positions_response.json()

print(f"\n✅ Fetched {positions_data['total_count']} positions")
print("\nPositions:")
print(json.dumps(positions_data, indent=2))

# Check if BTC symbol is showing correctly
for pos in positions_data['positions']:
    print(f"\n📊 Position: {pos['symbol']}")
    print(f"   Side: {pos['side']}")
    print(f"   Quantity: ${pos['quantity']:.2f}")
    print(f"   Entry: ${pos['entry_price']:.2f}")
    print(f"   Current: ${pos['current_price']:.2f}")
    print(f"   P&L: ${pos['unrealized_pnl']:.2f}")
    print(f"   eToro ID: {pos['etoro_position_id']}")
    
    if pos['symbol'] == 'BTC':
        print("   ✅ Symbol correctly mapped from instrument ID 100000!")
    elif pos['symbol'].startswith('ID_'):
        print(f"   ❌ Symbol not mapped, showing raw ID: {pos['symbol']}")
