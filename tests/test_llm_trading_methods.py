"""Test new trading-specific LLM methods."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.llm.llm_service import LLMService

def test_interpret_trading_rule():
    """Test rule interpretation."""
    print("\n" + "=" * 70)
    print("Testing interpret_trading_rule()")
    print("=" * 70)
    
    llm_service = LLMService()
    
    test_rules = [
        "RSI below 30",
        "Price above 50-day SMA",
        "20-day price change > 5%",
        "Volume above 20-day average"
    ]
    
    context = {
        "available_indicators": ["RSI", "SMA", "EMA", "MACD", "Volume_SMA"],
        "data_columns": ["open", "high", "low", "close", "volume"]
    }
    
    for rule in test_rules:
        print(f"\nRule: '{rule}'")
        try:
            result = llm_service.interpret_trading_rule(rule, context)
            print(f"  ✅ Code: {result['code']}")
            print(f"  ✅ Required indicators: {result['required_indicators']}")
            print(f"  ✅ Description: {result.get('description', 'N/A')}")
        except Exception as e:
            print(f"  ❌ Error: {e}")

def test_generate_indicator_code():
    """Test indicator code generation."""
    print("\n" + "=" * 70)
    print("Testing generate_indicator_code()")
    print("=" * 70)
    
    llm_service = LLMService()
    
    test_cases = [
        {
            "name": "Simple_Momentum",
            "description": "Calculate price momentum as the difference between current price and price N periods ago",
            "parameters": {"period": 14}
        },
        {
            "name": "Price_ROC",
            "description": "Calculate rate of change as percentage change over N periods",
            "parameters": {"period": 10}
        }
    ]
    
    for case in test_cases:
        print(f"\nIndicator: {case['name']}")
        print(f"Description: {case['description']}")
        try:
            code = llm_service.generate_indicator_code(
                case['name'],
                case['description'],
                case['parameters']
            )
            print(f"  ✅ Generated code:")
            print("  " + "\n  ".join(code.split('\n')[:10]))  # Show first 10 lines
            if len(code.split('\n')) > 10:
                print(f"  ... ({len(code.split('\n')) - 10} more lines)")
        except Exception as e:
            print(f"  ❌ Error: {e}")

def test_generate_rule_evaluation_code():
    """Test rule evaluation code generation."""
    print("\n" + "=" * 70)
    print("Testing generate_rule_evaluation_code()")
    print("=" * 70)
    
    llm_service = LLMService()
    
    test_rules = [
        ("RSI below 30 and price above SMA", ["RSI_14", "SMA_20"]),
        ("Volume spike above 2x average", ["Volume_SMA_20"]),
        ("Price breaks above upper Bollinger Band", ["BB_upper"])
    ]
    
    for rule, indicators in test_rules:
        print(f"\nRule: '{rule}'")
        print(f"Available indicators: {indicators}")
        try:
            code = llm_service.generate_rule_evaluation_code(rule, indicators)
            print(f"  ✅ Code: {code}")
        except Exception as e:
            print(f"  ❌ Error: {e}")

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("LLM Trading Methods Test Suite")
    print("=" * 70)
    print("\nNote: These tests require Ollama to be running with qwen2.5-coder:32b model")
    print("If tests fail, ensure Ollama is running: ollama serve")
    print("And the model is available: ollama pull qwen2.5-coder:32b")
    
    try:
        test_interpret_trading_rule()
        test_generate_indicator_code()
        test_generate_rule_evaluation_code()
        
        print("\n" + "=" * 70)
        print("✅ All tests completed!")
        print("=" * 70)
    except Exception as e:
        print(f"\n❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
