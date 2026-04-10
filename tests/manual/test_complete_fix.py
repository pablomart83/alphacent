#!/usr/bin/env python3
"""Test the complete vibe coding fix with correct prices."""

import sys
sys.path.insert(0, 'src')

from src.llm.llm_service import LLMService

print("=" * 70)
print("COMPLETE FIX VERIFICATION")
print("=" * 70)

llm_service = LLMService()

test_cases = [
    ("buy 1 unit of BTC", "unit", 69000, 71000),  # Should be ~$70K
    ("buy $100 of BTC", "dollar", 100, 100),      # Should be exactly $100
    ("buy 10 shares of AAPL", "share", 2500, 2600), # Should be ~$2,550
]

print("\nTesting with REAL prices:")
print("-" * 70)

all_passed = True

for test_input, input_type, min_expected, max_expected in test_cases:
    print(f"\nInput: '{test_input}'")
    print(f"Type: {input_type}")
    print(f"Expected range: ${min_expected:,.2f} - ${max_expected:,.2f}")
    
    try:
        command = llm_service.translate_vibe_code(test_input)
        
        print(f"Result:")
        print(f"  Action: {command.action}")
        print(f"  Symbol: {command.symbol}")
        print(f"  Quantity: ${command.quantity:,.2f}")
        
        # Validate
        if min_expected <= command.quantity <= max_expected:
            print(f"  ✅ PASS: Quantity in expected range")
        else:
            print(f"  ❌ FAIL: Quantity outside expected range")
            all_passed = False
            
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        all_passed = False

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

if all_passed:
    print("✅ ALL TESTS PASSED!")
    print("\nBoth fixes are working:")
    print("  1. ✅ Quantity conversion (units → dollars)")
    print("  2. ✅ Price data (Yahoo Finance fallback)")
    print("\nReady to use in production!")
else:
    print("❌ SOME TESTS FAILED")
    print("Check the output above for details")

print("=" * 70)
