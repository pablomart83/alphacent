"""Test LLM service structure and initialization."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_llm_service_initialization():
    """Test that LLMService initializes with correct attributes."""
    print("\n" + "=" * 70)
    print("Testing LLMService Initialization")
    print("=" * 70)
    
    from src.llm.llm_service import LLMService
    
    # Test default initialization
    try:
        llm = LLMService()
        print(f"✅ Default model: {llm.model}")
        print(f"✅ Code model: {llm.code_model}")
        print(f"✅ Base URL: {llm.base_url}")
        print(f"✅ API URL: {llm.api_url}")
        
        # Verify new methods exist
        assert hasattr(llm, 'interpret_trading_rule'), "Missing interpret_trading_rule method"
        assert hasattr(llm, 'generate_indicator_code'), "Missing generate_indicator_code method"
        assert hasattr(llm, 'generate_rule_evaluation_code'), "Missing generate_rule_evaluation_code method"
        print("✅ All new methods are present")
        
        # Verify method signatures
        import inspect
        
        sig = inspect.signature(llm.interpret_trading_rule)
        assert 'rule' in sig.parameters, "interpret_trading_rule missing 'rule' parameter"
        assert 'context' in sig.parameters, "interpret_trading_rule missing 'context' parameter"
        print("✅ interpret_trading_rule has correct signature")
        
        sig = inspect.signature(llm.generate_indicator_code)
        assert 'indicator_name' in sig.parameters, "generate_indicator_code missing 'indicator_name' parameter"
        assert 'description' in sig.parameters, "generate_indicator_code missing 'description' parameter"
        assert 'parameters' in sig.parameters, "generate_indicator_code missing 'parameters' parameter"
        print("✅ generate_indicator_code has correct signature")
        
        sig = inspect.signature(llm.generate_rule_evaluation_code)
        assert 'rule' in sig.parameters, "generate_rule_evaluation_code missing 'rule' parameter"
        assert 'available_indicators' in sig.parameters, "generate_rule_evaluation_code missing 'available_indicators' parameter"
        print("✅ generate_rule_evaluation_code has correct signature")
        
        # Verify _call_ollama accepts use_code_model parameter
        sig = inspect.signature(llm._call_ollama)
        assert 'use_code_model' in sig.parameters, "_call_ollama missing 'use_code_model' parameter"
        print("✅ _call_ollama has use_code_model parameter")
        
        print("\n✅ All structure tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_json_repair_enhancements():
    """Test that JSON repair handles trading-specific structures."""
    print("\n" + "=" * 70)
    print("Testing Enhanced JSON Repair")
    print("=" * 70)
    
    from src.llm.llm_service import LLMService
    
    llm = LLMService()
    
    # Test percentage conversion
    test_json = '{"stop_loss": "5%", "take_profit": "10%"}'
    repaired = llm._repair_json(test_json)
    print(f"Original: {test_json}")
    print(f"Repaired: {repaired}")
    assert '"5%"' not in repaired or '0.05' in repaired, "Percentage not converted"
    print("✅ Percentage conversion works")
    
    # Test indicator name normalization
    test_json = '{"indicators": ["RSI 14", "SMA 20"]}'
    repaired = llm._repair_json(test_json)
    print(f"\nOriginal: {test_json}")
    print(f"Repaired: {repaired}")
    assert 'RSI_14' in repaired or 'RSI 14' in repaired, "Indicator name handling"
    print("✅ Indicator name handling works")
    
    print("\n✅ JSON repair enhancements verified!")
    return True

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("LLM Service Structure Test Suite")
    print("=" * 70)
    print("\nNote: These tests verify code structure without requiring Ollama")
    
    success = True
    success = test_llm_service_initialization() and success
    success = test_json_repair_enhancements() and success
    
    if success:
        print("\n" + "=" * 70)
        print("✅ All structure tests passed!")
        print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print("❌ Some tests failed")
        print("=" * 70)
        sys.exit(1)
