#!/usr/bin/env python3
"""
Test script to verify Alpha Vantage and FRED API keys are working.
Run this after adding your API keys to config/autonomous_trading.yaml
"""

import yaml
from alpha_vantage.timeseries import TimeSeries
from fredapi import Fred


def load_config():
    """Load configuration from YAML file."""
    with open('config/autonomous_trading.yaml', 'r') as f:
        return yaml.safe_load(f)


def test_alpha_vantage(api_key):
    """Test Alpha Vantage API key."""
    print("\n🔍 Testing Alpha Vantage API...")
    
    if api_key == "YOUR_ALPHA_VANTAGE_KEY_HERE":
        print("❌ Please replace YOUR_ALPHA_VANTAGE_KEY_HERE with your actual API key")
        return False
    
    try:
        # Use daily data (free tier) instead of intraday (premium)
        ts = TimeSeries(key=api_key, output_format='pandas')
        data, meta_data = ts.get_daily(symbol='AAPL', outputsize='compact')
        print(f"✅ Alpha Vantage API working! Retrieved {len(data)} daily data points for AAPL")
        print(f"   Latest close: ${data['4. close'].iloc[0]:.2f}")
        return True
    except Exception as e:
        print(f"❌ Alpha Vantage API failed: {e}")
        return False


def test_fred(api_key):
    """Test FRED API key."""
    print("\n🔍 Testing FRED API...")
    
    if api_key == "YOUR_FRED_KEY_HERE":
        print("❌ Please replace YOUR_FRED_KEY_HERE with your actual API key")
        return False
    
    try:
        fred = Fred(api_key=api_key)
        vix_data = fred.get_series('VIXCLS', limit=10)
        print(f"✅ FRED API working! Retrieved {len(vix_data)} VIX data points")
        print(f"   Latest VIX: {vix_data.iloc[-1]:.2f}")
        return True
    except Exception as e:
        print(f"❌ FRED API failed: {e}")
        return False


def main():
    """Main test function."""
    print("=" * 60)
    print("API Key Verification Test")
    print("=" * 60)
    
    # Load config
    try:
        config = load_config()
    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        return
    
    # Test Alpha Vantage
    av_config = config.get('data_sources', {}).get('alpha_vantage', {})
    av_enabled = av_config.get('enabled', False)
    av_key = av_config.get('api_key', '')
    
    if av_enabled:
        av_success = test_alpha_vantage(av_key)
    else:
        print("\n⚠️  Alpha Vantage is disabled in config")
        av_success = None
    
    # Test FRED
    fred_config = config.get('data_sources', {}).get('fred', {})
    fred_enabled = fred_config.get('enabled', False)
    fred_key = fred_config.get('api_key', '')
    
    if fred_enabled:
        fred_success = test_fred(fred_key)
    else:
        print("\n⚠️  FRED is disabled in config")
        fred_success = None
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    if av_success and fred_success:
        print("✅ All API keys are working correctly!")
        print("\n📋 Next steps:")
        print("   1. Implement Task 9.9.1 (Market Data Integration)")
        print("   2. Run integration tests")
        print("   3. Start using enhanced market data in strategies")
    elif av_success is None and fred_success is None:
        print("⚠️  Both APIs are disabled. Enable them in config to use.")
    else:
        print("⚠️  Some API keys need attention. Check the errors above.")
        print("\n📋 To get API keys:")
        print("   Alpha Vantage: https://www.alphavantage.co/support/#api-key")
        print("   FRED: https://fred.stlouisfed.org/docs/api/api_key.html")


if __name__ == '__main__':
    main()
