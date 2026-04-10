#!/usr/bin/env python3
"""Test real vibe coding API."""

import requests
import json

BASE_URL = "http://localhost:8000"

# Login first
session = requests.Session()
login_response = session.post(
    f"{BASE_URL}/auth/login",
    json={"username": "admin", "password": "admin"}
)
print(f"Login: {login_response.status_code}")

# Test cases
test_cases = [
    "buy 1 unit of BTC",
    "buy $50 of BTC",
    "buy 10 shares of AAPL",
]

print("\n" + "=" * 70)
print("Testing Vibe Coding API")
print("=" * 70)

for command in test_cases:
    print(f"\nCommand: '{command}'")
    
    # Translate
    response = session.post(
        f"{BASE_URL}/strategies/vibe-code/translate",
        json={"natural_language": command}
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"  Action: {result.get('action')}")
        print(f"  Symbol: {result.get('symbol')}")
        print(f"  Quantity: ${result.get('quantity')}")
        print(f"  Reason: {result.get('reason')}")
        
        if result.get('quantity') and result.get('quantity') >= 10:
            print(f"  ✅ VALID: Meets $10 minimum")
        elif result.get('quantity') is None:
            print(f"  ⚠️  WARNING: Quantity is None")
        else:
            print(f"  ❌ INVALID: Below $10 minimum")
    else:
        print(f"  ❌ ERROR: {response.status_code} - {response.text}")

print("\n" + "=" * 70)
