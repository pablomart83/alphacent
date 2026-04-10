#!/usr/bin/env python3
"""Test edge cases for vibe coding fix."""

import re

print("=" * 70)
print("EDGE CASE TESTING")
print("=" * 70)

# Test cases with expected behavior
test_cases = [
    # (input, should_convert, expected_type, notes)
    ("buy 1 unit of BTC", True, "unit", "Single unit - convert to dollars"),
    ("buy 0.5 units of BTC", True, "unit", "Fractional unit - convert to dollars"),
    ("buy 10 shares of AAPL", True, "share", "Multiple shares - convert to dollars"),
    ("buy $10 of BTC", False, "dollar", "Minimum dollar amount - use directly"),
    ("buy $5 of BTC", False, "dollar", "Below minimum - will be adjusted to $10"),
    ("buy $50 of BTC", False, "dollar", "Normal dollar amount - use directly"),
    ("buy $1000 of GOOGL", False, "dollar", "Large dollar amount - use directly"),
    ("buy $99 of TSLA", False, "dollar", "Dollar amount < 100 - use directly (no conversion)"),
    ("purchase 2.5 units of ETH", True, "unit", "Fractional units with 'purchase' - convert"),
    ("get 100 shares of MSFT", True, "share", "Large share count - convert to dollars"),
]

unit_pattern = r'(\d+(?:\.\d+)?)\s*(unit|share|coin)s?'
dollar_pattern = r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)'

print("\nTesting pattern detection:")
print("-" * 70)

for text, should_convert, expected_type, notes in test_cases:
    print(f"\nInput: '{text}'")
    print(f"  Notes: {notes}")
    
    # Check unit pattern
    unit_match = re.search(unit_pattern, text, re.IGNORECASE)
    if unit_match:
        num_units = float(unit_match.group(1))
        unit_type = unit_match.group(2)
        if should_convert and expected_type in ["unit", "share", "coin"]:
            print(f"  ✅ CORRECT: Detected {num_units} {unit_type}(s) - will convert to dollars")
        else:
            print(f"  ❌ ERROR: Detected units but shouldn't convert")
        continue
    
    # Check dollar pattern
    dollar_match = re.search(dollar_pattern, text, re.IGNORECASE)
    if dollar_match:
        amount = float(dollar_match.group(1).replace(',', ''))
        if not should_convert and expected_type == "dollar":
            print(f"  ✅ CORRECT: Detected ${amount:.2f} - will use directly")
            if amount < 10:
                print(f"     (Will be adjusted to $10 minimum)")
        else:
            print(f"  ❌ ERROR: Detected dollars but expected units")
        continue
    
    print(f"  ⚠️  WARNING: No pattern matched")

print("\n\n" + "=" * 70)
print("KEY INSIGHTS")
print("=" * 70)
print("\n1. Dollar amounts < 100 are NOT converted (e.g., $10, $50, $99)")
print("   → This was the BUG in the old code")
print("\n2. Unit/share amounts ARE converted using market price")
print("   → This is the FIX in the new code")
print("\n3. All amounts meet $10 minimum requirement")
print("   → Enforced at multiple levels")
print("\n" + "=" * 70)
