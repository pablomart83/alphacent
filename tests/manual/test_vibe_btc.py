#!/usr/bin/env python3
"""Test vibe coding with BTC order."""

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
print(f"✅ Logged in")

# Test vibe coding with BTC
test_commands = [
    "buy $8000 of BTC",
    "buy $100 of Bitcoin",
    "purchase $500 worth of TSLA"
]

for command in test_commands:
    print(f"\n{'='*60}")
    print(f"Testing: {command}")
    print('='*60)
    
    response = session.post(
        f"{BASE_URL}/strategies/vibe-code/translate",
        json={"natural_language": command}
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Translation successful:")
        print(f"   Action: {result.get('action')}")
        print(f"   Symbol: {result.get('symbol')}")
        print(f"   Quantity: ${result.get('quantity')}")
        print(f"   Reason: {result.get('reason')}")
        
        if result.get('symbol') == 'BTC' and command.startswith("buy $8000 of BTC"):
            if result.get('quantity') == 8000:
                print("   ✅ Correct! BTC with $8000")
            else:
                print(f"   ❌ Wrong quantity! Expected 8000, got {result.get('quantity')}")
        
        if result.get('order_id'):
            print(f"   Order ID: {result.get('order_id')}")
    else:
        print(f"❌ Failed: {response.status_code}")
        print(f"   {response.text}")
