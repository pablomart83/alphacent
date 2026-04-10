"""Test standardized indicator naming convention."""

import pandas as pd
import numpy as np
from src.strategy.indicator_library import IndicatorLibrary

def test_indicator_naming():
    """Test that indicators return standardized keys."""
    library = IndicatorLibrary()
    
    # Create sample data
    dates = pd.date_range('2025-01-01', periods=100, freq='D')
    data = pd.DataFrame({
        'open': np.random.randn(100).cumsum() + 100,
        'high': np.random.randn(100).cumsum() + 102,
        'low': np.random.randn(100).cumsum() + 98,
        'close': np.random.randn(100).cumsum() + 100,
        'volume': np.random.randint(1000000, 10000000, 100)
    }, index=dates)
    
    print("Testing Indicator Naming Convention\n")
    print("=" * 60)
    
    # Test SMA
    result, key = library.calculate("SMA", data, symbol="TEST", period=20)
    print(f"SMA with period=20: key='{key}'")
    assert key == "SMA_20", f"Expected 'SMA_20', got '{key}'"
    assert len(result) == 100
    print("  ✓ Correct naming format")
    
    # Test RSI
    result, key = library.calculate("RSI", data, symbol="TEST", period=14)
    print(f"\nRSI with period=14: key='{key}'")
    assert key == "RSI_14", f"Expected 'RSI_14', got '{key}'"
    assert len(result) == 100
    print("  ✓ Correct naming format")
    
    # Test EMA
    result, key = library.calculate("EMA", data, symbol="TEST", period=20)
    print(f"\nEMA with period=20: key='{key}'")
    assert key == "EMA_20", f"Expected 'EMA_20', got '{key}'"
    assert len(result) == 100
    print("  ✓ Correct naming format")
    
    # Test MACD
    result, key = library.calculate("MACD", data, symbol="TEST", fast_period=12, slow_period=26, signal_period=9)
    print(f"\nMACD with default params: key='{key}'")
    assert key == "MACD_12_26_9", f"Expected 'MACD_12_26_9', got '{key}'"
    assert len(result) == 100
    print("  ✓ Correct naming format")
    
    # Test Bollinger Bands
    result, key = library.calculate("BBANDS", data, symbol="TEST", period=20, std_dev=2)
    print(f"\nBollinger Bands with period=20, std_dev=2: key='{key}'")
    assert key == "BBANDS_20_2", f"Expected 'BBANDS_20_2', got '{key}'"
    assert len(result) == 100
    print("  ✓ Correct naming format")
    
    # Test ATR
    result, key = library.calculate("ATR", data, symbol="TEST", period=14)
    print(f"\nATR with period=14: key='{key}'")
    assert key == "ATR_14", f"Expected 'ATR_14', got '{key}'"
    assert len(result) == 100
    print("  ✓ Correct naming format")
    
    print("\n" + "=" * 60)
    print("✓ All indicator naming tests passed!")
    print("\nStandardized naming format: {INDICATOR}_{PERIOD}")
    print("Examples: SMA_20, RSI_14, EMA_50, MACD_12_26_9, BBANDS_20_2")
    
    return True

if __name__ == "__main__":
    import sys
    success = test_indicator_naming()
    sys.exit(0 if success else 1)
