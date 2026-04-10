#!/usr/bin/env python3
"""Quick test to verify the fix is working."""

import sys
sys.path.insert(0, 'src')

from src.llm.llm_service import LLMService

print("=" * 70)
print("Testing Vibe Coding Fix - Server Restarted")
print("=" * 70)

llm_service = LLMService()

# Test case that was failing before
test_input = "buy 1 unit of BTC"

print(f"\nTest: '{test_input}'")
print("-" * 70)

try:
    command = llm_service.translate_vibe_code(test_input)
    
    print(f"Action: {command.action}")
    print(f"Symbol: {command.symbol}")
    print(f"Quantity: ${command.quantity:.2f}")
    
    # Validate
    if command.quantity >= 10.0 and command.quantity < 50000:
        print(f"\n✅ SUCCESS! Quantity is reasonable: ${command.quantity:.2f}")
        print(f"   (Expected ~$41,000 for 1 BTC)")
    elif command.quantity >= 50000:
        print(f"\n❌ STILL BROKEN! Quantity too high: ${command.quantity:.2f}")
        print(f"   This suggests the old conversion is still happening")
    else:
        print(f"\n⚠️  WARNING: Quantity below minimum: ${command.quantity:.2f}")
        
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    print("\nThis might be an LLM parsing issue, not the conversion bug")

print("\n" + "=" * 70)
print("\nNext: Test in the Vibe Coding UI!")
print("Try: 'buy $50 of BTC' and 'buy 1 unit of BTC'")
print("=" * 70)
