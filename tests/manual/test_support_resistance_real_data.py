#!/usr/bin/env python3
"""
Test Support/Resistance calculation with real AAPL data using eToro client.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
from datetime import datetime, timedelta
from strategy.indicator_library import IndicatorLibrary
from data.market_data_manager import MarketDataManager
from api.etoro_client import EToroAPIClient
from models import TradingMode
from core.config import get_config

def test_with_real_data():
    """Test Support/Resistance with real AAPL data."""
    print("="*70)
    print("Testing Support/Resistance with Real AAPL Data")
    print("="*70)
    
    try:
        # Initialize eToro client
        config_manager = get_config()
        
        try:
            credentials = config_manager.load_credentials(TradingMode.DEMO)
            etoro_client = EToroAPIClient(
                public_key=credentials['public_key'],
                user_key=credentials['user_key'],
                mode=TradingMode.DEMO
            )
            print("✓ eToro client initialized")
        except Exception as e:
            print(f"⚠ Could not initialize eToro client: {e}")
            print("Using mock eToro client for testing")
            from unittest.mock import Mock
            etoro_client = Mock()
        
        # Initialize market data manager
        market_data = MarketDataManager(etoro_client=etoro_client)
        
        # Get real market data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        
        print(f"\nFetching AAPL data from {start_date.date()} to {end_date.date()}")
        
        data_list = market_data.get_historical_data(
            symbol='AAPL',
            start=start_date,
            end=end_date
        )
        
        # Convert to DataFrame
        data = pd.DataFrame([
            {
                "timestamp": d.timestamp,
                "open": d.open,
                "high": d.high,
                "low": d.low,
                "close": d.close,
                "volume": d.volume
            }
            for d in data_list
        ])
        data.set_index("timestamp", inplace=True)
        
        print(f"Data shape: {data.shape}")
        print(f"Date range: {data.index[0]} to {data.index[-1]}")
        print(f"Price range: ${data['close'].min():.2f} - ${data['close'].max():.2f}")
        
        # Calculate Support/Resistance
        lib = IndicatorLibrary()
        
        print("\n" + "-"*70)
        print("Calculating Support/Resistance (period=20)")
        print("-"*70)
        
        result, key = lib.calculate('SUPPORT_RESISTANCE', data, symbol='AAPL', period=20)
        
        print(f"\nResult type: {type(result)}")
        print(f"Standardized key: {key}")
        print(f"Result keys: {list(result.keys())}")
        
        support = result['support']
        resistance = result['resistance']
        
        print(f"\nSupport statistics:")
        print(f"  Non-null count: {support.notna().sum()}")
        print(f"  Min: ${support.min():.2f}")
        print(f"  Max: ${support.max():.2f}")
        print(f"  Mean: ${support.mean():.2f}")
        print(f"  Zero count: {(support == 0).sum()}")
        
        print(f"\nResistance statistics:")
        print(f"  Non-null count: {resistance.notna().sum()}")
        print(f"  Min: ${resistance.min():.2f}")
        print(f"  Max: ${resistance.max():.2f}")
        print(f"  Mean: ${resistance.mean():.2f}")
        print(f"  Zero count: {(resistance == 0).sum()}")
        
        # Validate last 10 days
        print("\n" + "-"*70)
        print("Validation: Support < Price < Resistance (Last 10 days)")
        print("-"*70)
        
        price = data['close']
        valid_count = 0
        total_count = 0
        
        for i in range(-10, 0):
            s = support.iloc[i]
            r = resistance.iloc[i]
            p = price.iloc[i]
            
            if not (pd.isna(s) or pd.isna(r)):
                valid = s < p < r
                status = "✅" if valid else "❌"
                print(f"  {data.index[i].date()}: Support=${s:.2f}, Price=${p:.2f}, Resistance=${r:.2f} {status}")
                
                if valid:
                    valid_count += 1
                total_count += 1
        
        print(f"\nValidation rate: {valid_count}/{total_count} ({100*valid_count/total_count:.1f}%)")
        
        # Check for zeros
        if (support == 0).any() or (resistance == 0).any():
            print("\n❌ ERROR: Found zero values in Support/Resistance!")
            print(f"  Support zeros: {(support == 0).sum()}")
            print(f"  Resistance zeros: {(resistance == 0).sum()}")
            return False
        else:
            print("\n✅ SUCCESS: No zero values found!")
            
        # Additional validation: Support should be less than Resistance
        print("\n" + "-"*70)
        print("Additional Validation: Support < Resistance")
        print("-"*70)
        
        # Only check non-NaN values
        valid_mask = support.notna() & resistance.notna()
        valid_sr = (support < resistance) & valid_mask
        valid_sr_count = valid_sr.sum()
        total_sr = valid_mask.sum()
        
        print(f"Valid S<R: {valid_sr_count}/{total_sr} ({100*valid_sr_count/total_sr:.1f}%)")
        
        if valid_sr_count == total_sr:
            print("✅ All Support values are less than Resistance values!")
            return True
        else:
            print(f"❌ WARNING: {total_sr - valid_sr_count} cases where Support >= Resistance")
            # Show the problematic cases
            problem_mask = (support >= resistance) & valid_mask
            if problem_mask.any():
                print("\nProblematic cases:")
                for idx in data.index[problem_mask][:5]:  # Show first 5
                    s = support.loc[idx]
                    r = resistance.loc[idx]
                    p = price.loc[idx]
                    print(f"  {idx.date()}: Support=${s:.2f}, Price=${p:.2f}, Resistance=${r:.2f}")
            return False
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_with_real_data()
    print("\n" + "="*70)
    print(f"Test Result: {'✅ PASS' if success else '❌ FAIL'}")
    print("="*70)
    sys.exit(0 if success else 1)
