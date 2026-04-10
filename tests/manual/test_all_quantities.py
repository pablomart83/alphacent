#!/usr/bin/env python3
"""Test various quantity formats."""

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
print("✅ Logged in\n")

# Test cases
test_cases = [
    ("buy $800 of BTC", 800, "BTC"),
    ("buy $100 of Bitcoin", 100, "BTC"),
    ("purchase $500 worth of TSLA", 500, "TSLA"),
    ("buy $8000 of BTC", 8000, "BTC"),
    ("buy $50 of AAPL", 50, "AAPL"),
    ("buy $1,000 of GOOGL", 1000, "GOOGL"),
    ("buy 250 dollars of ETH", 250, "ETH"),
]

passed = 0
failed = 0

for command, expected_qty, expected_symbol in test_cases:
    print(f"Testing: {command}")
    
    response = session.post(
        f"{BASE_URL}/strategies/vibe-code/translate",
        json={"natural_language": command}
    )
    
    if response.status_code == 200:
        result = response.json()
        actual_qty = result.get('quantity')
        actual_symbol = result.get('symbol')
        
        qty_match = actual_qty == expected_qty
        symbol_match = actual_symbol == expected_symbol
        
        if qty_match and symbol_match:
            print(f"   ✅ PASS: ${actual_qty} {actual_symbol}")
            passed += 1
        else:
            print(f"   ❌ FAIL:")
            if not qty_match:
                print(f"      Quantity: expected {expected_qty}, got {actual_qty}")
            if not symbol_match:
                print(f"      Symbol: expected {expected_symbol}, got {actual_symbol}")
            failed += 1
    else:
        print(f"   ❌ FAIL: HTTP {response.status_code}")
        failed += 1
    
    print()

print(f"\n{'='*60}")
print(f"Results: {passed} passed, {failed} failed")
print('='*60)
