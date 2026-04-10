#!/usr/bin/env python3
"""
Debug script to test Support/Resistance calculation.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from strategy.indicator_library import IndicatorLibrary

def create_test_data():
    """Create test data with known values."""
    dates = pd.date_range(start='2024-01-01', periods=50, freq='D')
    
    # Create data with clear support and resistance levels
    # Price oscillates between 90 and 110
    np.random.seed(42)
    base_price = 100
    prices = base_price + np.sin(np.linspace(0, 4*np.pi, 50)) * 10 + np.random.randn(50) * 2
    
    data = pd.DataFrame({
        'open': prices + np.random.randn(50) * 0.5,
        'high': prices + abs(np.random.randn(50) * 2),
        'low': prices - abs(np.random.randn(50) * 2),
        'close': prices,
        'volume': np.random.randint(1000000, 5000000, 50)
    }, index=dates)
    
    return data

def test_support_resistance():
    """Test Support/Resistance calculation."""
    print("="*70)
    print("Testing Support/Resistance Calculation")
    print("="*70)
    
    # Create test data
    data = create_test_data()
    print(f"\nTest data shape: {data.shape}")
    print(f"Price range: ${data['close'].min():.2f} - ${data['close'].max():.2f}")
    print(f"\nFirst 5 rows:")
    print(data.head())
    print(f"\nLast 5 rows:")
    print(data.tail())
    
    # Test with IndicatorLibrary
    lib = IndicatorLibrary()
    
    print("\n" + "-"*70)
    print("Testing with period=20")
    print("-"*70)
    
    result, key = lib.calculate('SUPPORT_RESISTANCE', data, symbol='TEST', period=20)
    
    print(f"\nResult type: {type(result)}")
    print(f"Standardized key: {key}")
    
    if isinstance(result, dict):
        print(f"\nResult keys: {list(result.keys())}")
        for k, v in result.items():
            print(f"\n{k}:")
            print(f"  Type: {type(v)}")
            print(f"  Shape: {v.shape if hasattr(v, 'shape') else 'N/A'}")
            print(f"  Non-null count: {v.notna().sum()}")
            print(f"  Min: {v.min():.2f}")
            print(f"  Max: {v.max():.2f}")
            print(f"  Mean: {v.mean():.2f}")
            print(f"  First 5 values:")
            print(f"    {v.head().tolist()}")
            print(f"  Last 5 values:")
            print(f"    {v.tail().tolist()}")
            
            # Check for zeros
            zero_count = (v == 0).sum()
            print(f"  Zero count: {zero_count}")
            
            # Check for NaN
            nan_count = v.isna().sum()
            print(f"  NaN count: {nan_count}")
    else:
        print(f"\nResult is not a dict, it's: {type(result)}")
        print(f"Result: {result}")
    
    # Test the raw calculation method
    print("\n" + "-"*70)
    print("Testing raw _calculate_support_resistance method")
    print("-"*70)
    
    raw_result = lib._calculate_support_resistance(data, period=20)
    print(f"\nRaw result type: {type(raw_result)}")
    print(f"Raw result keys: {list(raw_result.keys())}")
    
    for k, v in raw_result.items():
        print(f"\n{k}:")
        print(f"  Min: {v.min():.2f}")
        print(f"  Max: {v.max():.2f}")
        print(f"  Mean: {v.mean():.2f}")
        print(f"  Last 10 values:")
        print(f"    {v.tail(10).tolist()}")
    
    # Compare with current price
    print("\n" + "-"*70)
    print("Validation: Support < Price < Resistance")
    print("-"*70)
    
    support = raw_result['support']
    resistance = raw_result['resistance']
    price = data['close']
    
    # Check last 10 days (after rolling window is established)
    for i in range(-10, 0):
        s = support.iloc[i]
        r = resistance.iloc[i]
        p = price.iloc[i]
        valid = s < p < r if not (pd.isna(s) or pd.isna(r)) else False
        status = "✅" if valid else "❌"
        print(f"  Day {i}: Support={s:.2f}, Price={p:.2f}, Resistance={r:.2f} {status}")
    
    print("\n" + "="*70)
    print("Test Complete")
    print("="*70)

if __name__ == "__main__":
    test_support_resistance()
