#!/usr/bin/env python3
"""Test $800 BTC order."""

import requests

BASE_URL = "http://localhost:8000"

# Create session
session = requests.Session()

# Login
print("Logging in...")
login_response = session.post(
    f"{BASE_URL}/auth/login",
    json={"username": "admin", "password": "admin123"}
)
login_response.raise_for_status()
print("✅ Logged in")

# Test the specific command
command = "buy $800 of BTC"
print(f"\nTesting: {command}")

response = session.post(
    f"{BASE_URL}/strategies/vibe-code/translate",
    json={"natural_language": command}
)

if response.status_code == 200:
    result = response.json()
    print(f"\n✅ Translation successful:")
    print(f"   Action: {result.get('action')}")
    print(f"   Symbol: {result.get('symbol')}")
    print(f"   Quantity: ${result.get('quantity')}")
    print(f"   Reason: {result.get('reason')}")
    
    if result.get('quantity') == 800:
        print("\n   ✅✅✅ CORRECT! $800 extracted properly!")
    else:
        print(f"\n   ❌ WRONG! Expected 800, got {result.get('quantity')}")
else:
    print(f"❌ Failed: {response.status_code}")
    print(f"   {response.text}")
