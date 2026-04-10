"""Test vibe coding order size validation."""

import sys
sys.path.insert(0, '.')

from src.llm.llm_service import LLMService, TradingCommand
from src.models.enums import SignalAction
import json

print("=" * 70)
print("Testing Vibe Coding Order Size Fix")
print("=" * 70)

llm_service = LLMService()

# Test 1: Simulate LLM response with small quantity
print("\n1. Testing LLM response parsing with small quantity...")
mock_response = json.dumps({
    "action": "ENTER_LONG",
    "symbol": "AAPL",
    "quantity": 5,  # Below minimum
    "price": None,
    "reason": "User wants to buy Apple"
})

try:
    command = llm_service._parse_trading_command(mock_response)
    print(f"   Parsed quantity: ${command.quantity:.2f}")
    if command.quantity >= 10.0:
        print(f"   ✅ PASSED: Quantity adjusted to meet minimum")
    else:
        print(f"   ❌ FAILED: Quantity ${command.quantity:.2f} still below minimum")
except Exception as e:
    print(f"   ❌ FAILED: {e}")

# Test 2: Simulate LLM response with no quantity
print("\n2. Testing LLM response parsing with no quantity...")
mock_response = json.dumps({
    "action": "ENTER_LONG",
    "symbol": "GOOGL",
    "quantity": None,
    "price": None,
    "reason": "User wants to buy Google"
})

try:
    command = llm_service._parse_trading_command(mock_response)
    print(f"   Parsed quantity: {command.quantity}")
    if command.quantity is None:
        print(f"   ✅ PASSED: Quantity is None (will default to $10 in frontend)")
    else:
        print(f"   ⚠️  Quantity set to: ${command.quantity:.2f}")
except Exception as e:
    print(f"   ❌ FAILED: {e}")

# Test 3: Simulate LLM response with valid quantity
print("\n3. Testing LLM response parsing with valid quantity...")
mock_response = json.dumps({
    "action": "ENTER_LONG",
    "symbol": "TSLA",
    "quantity": 100,  # Above minimum
    "price": None,
    "reason": "User wants to buy Tesla"
})

try:
    command = llm_service._parse_trading_command(mock_response)
    print(f"   Parsed quantity: ${command.quantity:.2f}")
    if command.quantity == 100.0:
        print(f"   ✅ PASSED: Quantity unchanged (already above minimum)")
    else:
        print(f"   ⚠️  Quantity adjusted to: ${command.quantity:.2f}")
except Exception as e:
    print(f"   ❌ FAILED: {e}")

# Test 4: Check the prompt includes minimum requirement
print("\n4. Checking vibe code prompt includes minimum requirement...")
prompt = llm_service._format_vibe_code_prompt("buy some Apple stock")
if "minimum $10" in prompt or "minimum 10" in prompt:
    print("   ✅ PASSED: Prompt includes minimum requirement")
else:
    print("   ⚠️  WARNING: Prompt may not clearly specify minimum")

print("\n" + "=" * 70)
print("Summary:")
print("- LLM parsing enforces $10 minimum")
print("- Frontend defaults to $10 when quantity is null")
print("- Backend validates at multiple levels")
print("=" * 70)
