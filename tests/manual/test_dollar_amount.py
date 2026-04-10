#!/usr/bin/env python3
"""Test dollar amount handling."""

import sys
sys.path.insert(0, 'src')

from src.llm.llm_service import LLMService

print("=" * 70)
print("Testing Dollar Amount Handling")
print("=" * 70)

llm_service = LLMService()

test_cases = [
    ("buy $50 of BTC", 50.0),
    ("buy $100 of AAPL", 100.0),
    ("buy $1000 of GOOGL", 1000.0),
]

for test_input, expected in test_cases:
    print(f"\nTest: '{test_input}'")
    print(f"Expected: ${expected:.2f}")
    
    try:
        command = llm_service.translate_vibe_code(test_input)
        print(f"Got: ${command.quantity:.2f}")
        
        if command.quantity == expected:
            print(f"✅ CORRECT!")
        else:
            print(f"❌ WRONG! Expected ${expected:.2f}, got ${command.quantity:.2f}")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")

print("\n" + "=" * 70)
