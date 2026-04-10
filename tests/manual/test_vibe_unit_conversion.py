#!/usr/bin/env python3
"""Test vibe coding unit conversion fix."""

import sys
sys.path.insert(0, 'src')

from src.llm.llm_service import LLMService

# Initialize LLM service
llm_service = LLMService()

# Test cases
test_cases = [
    "buy 1 unit of BTC",
    "buy 10 shares of AAPL",
    "buy $50 of BTC",
    "buy $1000 of GOOGL",
    "purchase 2.5 units of ETH",
]

print("=" * 70)
print("Testing Vibe Coding Unit Conversion")
print("=" * 70)

for test_input in test_cases:
    print(f"\nInput: '{test_input}'")
    try:
        command = llm_service.translate_vibe_code(test_input)
        print(f"  Action: {command.action}")
        print(f"  Symbol: {command.symbol}")
        print(f"  Quantity: ${command.quantity:.2f}")
        print(f"  Reason: {command.reason}")
        
        # Validate
        if command.quantity >= 10.0:
            print(f"  ✅ VALID: Meets $10 minimum")
        else:
            print(f"  ❌ INVALID: Below $10 minimum")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")

print("\n" + "=" * 70)
