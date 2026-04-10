#!/usr/bin/env python3
"""Direct test of unit conversion logic."""

import sys
import re

# Test the regex pattern
test_inputs = [
    "buy 1 unit of BTC",
    "buy 10 shares of AAPL",
    "buy $50 of BTC",
    "purchase 2.5 units of ETH",
]

unit_pattern = r'(\d+(?:\.\d+)?)\s*(unit|share|coin)s?'

print("=" * 70)
print("Testing Unit Pattern Matching")
print("=" * 70)

for text in test_inputs:
    print(f"\nInput: '{text}'")
    match = re.search(unit_pattern, text, re.IGNORECASE)
    if match:
        num_units = float(match.group(1))
        unit_type = match.group(2)
        print(f"  ✅ MATCHED: {num_units} {unit_type}(s)")
        print(f"  → Will convert to dollars using market price")
    else:
        print(f"  ℹ️  No unit pattern found")
        
        # Check for dollar pattern
        dollar_patterns = [
            r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*dollars?',
        ]
        
        for pattern in dollar_patterns:
            dollar_match = re.search(pattern, text, re.IGNORECASE)
            if dollar_match:
                amount = float(dollar_match.group(1).replace(',', ''))
                print(f"  ✅ DOLLAR AMOUNT: ${amount:.2f}")
                print(f"  → Will use directly (no conversion needed)")
                break

print("\n" + "=" * 70)
