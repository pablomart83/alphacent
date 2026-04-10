#!/usr/bin/env python3
"""
Verification script for symbol mapping feature.
Run this to verify the implementation is working correctly.
"""

import sys
from src.utils.symbol_mapper import normalize_symbol, get_display_symbol, get_all_aliases


def test_basic_functionality():
    """Test basic symbol mapping functionality."""
    print("Testing basic functionality...")
    
    tests = [
        ("BTC", "BTCUSD"),
        ("ETH", "ETHUSD"),
        ("btc", "BTCUSD"),  # Case insensitive
        (" BTC ", "BTCUSD"),  # Whitespace handling
        ("AAPL", "AAPL"),  # Stock symbols unchanged
        ("GOLD", "XAUUSD"),  # Commodities
        ("EUR", "EURUSD"),  # Forex
    ]
    
    passed = 0
    failed = 0
    
    for input_sym, expected in tests:
        result = normalize_symbol(input_sym)
        if result == expected:
            print(f"  ✅ {input_sym:10} → {result:10} (expected {expected})")
            passed += 1
        else:
            print(f"  ❌ {input_sym:10} → {result:10} (expected {expected})")
            failed += 1
    
    return passed, failed


def test_reverse_mapping():
    """Test reverse mapping (eToro → user-friendly)."""
    print("\nTesting reverse mapping...")
    
    tests = [
        ("BTCUSD", "BTC"),
        ("ETHUSD", "ETH"),
        ("XAUUSD", "GOLD"),
        ("AAPL", "AAPL"),  # No alias
    ]
    
    passed = 0
    failed = 0
    
    for input_sym, expected in tests:
        result = get_display_symbol(input_sym)
        if result == expected:
            print(f"  ✅ {input_sym:10} → {result:10} (expected {expected})")
            passed += 1
        else:
            print(f"  ❌ {input_sym:10} → {result:10} (expected {expected})")
            failed += 1
    
    return passed, failed


def test_imports():
    """Test that all imports work correctly."""
    print("\nTesting imports...")
    
    try:
        from src.data.market_data_manager import MarketDataManager
        print("  ✅ MarketDataManager import successful")
        
        from src.api.routers.market_data import router
        print("  ✅ API router import successful")
        
        return 2, 0
    except Exception as e:
        print(f"  ❌ Import failed: {e}")
        return 0, 1


def main():
    """Run all verification tests."""
    print("=" * 70)
    print("Symbol Mapping Feature Verification")
    print("=" * 70)
    print()
    
    total_passed = 0
    total_failed = 0
    
    # Test basic functionality
    passed, failed = test_basic_functionality()
    total_passed += passed
    total_failed += failed
    
    # Test reverse mapping
    passed, failed = test_reverse_mapping()
    total_passed += passed
    total_failed += failed
    
    # Test imports
    passed, failed = test_imports()
    total_passed += passed
    total_failed += failed
    
    # Summary
    print()
    print("=" * 70)
    print(f"Total: {total_passed} passed, {total_failed} failed")
    
    # Check alias count
    aliases = get_all_aliases()
    print(f"Available aliases: {len(aliases)}")
    
    if total_failed == 0:
        print()
        print("🎉 All verification tests passed!")
        print("✅ Symbol mapping feature is working correctly")
        print()
        print("Next steps:")
        print("  1. Frontend can use friendly symbols like 'BTC'")
        print("  2. Backend automatically converts to 'BTCUSD'")
        print("  3. Real eToro market data will display correctly")
        print("=" * 70)
        return 0
    else:
        print()
        print("❌ Some tests failed. Please review the output above.")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
