"""Test LLM quantity parsing for various inputs."""

import sys
sys.path.insert(0, '.')

from src.llm.llm_service import LLMService

print("=" * 70)
print("Testing LLM Quantity Parsing")
print("=" * 70)

llm_service = LLMService()

test_cases = [
    "buy $1000 of shares of AAPL",
    "buy $100 worth of Tesla",
    "buy 10 shares of Apple",
    "buy some Google stock",
    "purchase $500 of Bitcoin",
]

for test_input in test_cases:
    print(f"\nInput: '{test_input}'")
    try:
        command = llm_service.translate_vibe_code(test_input)
        print(f"  Symbol: {command.symbol}")
        print(f"  Quantity: ${command.quantity if command.quantity else 'None (will default to $10)'}")
        print(f"  Reason: {command.reason}")
    except Exception as e:
        print(f"  ERROR: {e}")

print("\n" + "=" * 70)
