#!/usr/bin/env python3
"""
Test Financial Modeling Prep API connection and functionality.
"""

import requests
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml


def load_config():
    """Load configuration file."""
    config_path = Path(__file__).parent.parent / "config" / "autonomous_trading.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def test_fmp_connection(api_key):
    """Test basic FMP API connection."""
    print("=" * 80)
    print("Testing Financial Modeling Prep API Connection")
    print("=" * 80)
    
    # Test 1: Search Symbol
    print("\n[Test 1] Searching for Apple (AAPL)...")
    url = f"https://financialmodelingprep.com/stable/search-symbol?query=AAPL&apikey={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                result = data[0]
                print(f"✓ SUCCESS - Symbol Search")
                print(f"  Symbol: {result.get('symbol')}")
                print(f"  Name: {result.get('name')}")
                print(f"  Exchange: {result.get('stockExchange', result.get('exchange'))}")
            else:
                print("✗ FAILED - Empty response")
                return False
        else:
            print(f"✗ FAILED - Status {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ FAILED - Error: {e}")
        return False
    
    # Test 2: Real-time Quote
    print("\n[Test 2] Fetching Apple real-time quote...")
    url = f"https://financialmodelingprep.com/stable/quote?symbol=AAPL&apikey={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                quote = data[0]
                print(f"✓ SUCCESS - Real-time Quote")
                print(f"  Symbol: {quote.get('symbol')}")
                print(f"  Name: {quote.get('name')}")
                print(f"  Price: ${quote.get('price', 0):.2f}")
                print(f"  Change: ${quote.get('change', 0):.2f} ({quote.get('changesPercentage', 0):.2f}%)")
                print(f"  Volume: {quote.get('volume', 0):,}")
            else:
                print("✗ FAILED - Empty response")
                return False
        else:
            print(f"✗ FAILED - Status {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ FAILED - Error: {e}")
        return False
    
    # Test 3: Company Profile
    print("\n[Test 3] Fetching Apple company profile...")
    url = f"https://financialmodelingprep.com/stable/profile?symbol=AAPL&apikey={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                profile = data[0]
                print(f"✓ SUCCESS - Company Profile")
                print(f"  Company: {profile.get('companyName')}")
                print(f"  Sector: {profile.get('sector')}")
                print(f"  Industry: {profile.get('industry')}")
                print(f"  Market Cap: ${profile.get('mktCap', 0):,.0f}")
                print(f"  CEO: {profile.get('ceo')}")
            else:
                print("✗ FAILED - Empty response")
                return False
        else:
            print(f"✗ FAILED - Status {response.status_code}")
            print(f"Response: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"✗ FAILED - Error: {e}")
        return False
    
    # Test 4: Income Statement
    print("\n[Test 4] Fetching Apple income statement...")
    url = f"https://financialmodelingprep.com/stable/income-statement?symbol=AAPL&apikey={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                income = data[0]
                print(f"✓ SUCCESS - Income Statement")
                print(f"  Date: {income.get('date')}")
                print(f"  Revenue: ${income.get('revenue', 0):,.0f}")
                print(f"  Net Income: ${income.get('netIncome', 0):,.0f}")
                print(f"  EPS: ${income.get('eps', 0):.2f}")
            else:
                print("✗ FAILED - Empty response")
                return False
        else:
            print(f"✗ FAILED - Status {response.status_code}")
            print(f"Response: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"✗ FAILED - Error: {e}")
        return False
    
    # Test 5: Historical Price Data
    print("\n[Test 5] Fetching Apple historical price data...")
    url = f"https://financialmodelingprep.com/stable/historical-price-eod/full?symbol=AAPL&apikey={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and isinstance(data, list) and len(data) > 0:
                historical = data[:5]  # Get last 5 days
                print(f"✓ SUCCESS - Historical Price Data")
                print(f"  Found {len(data)} historical data points")
                print(f"  Latest 5 days:")
                for day in historical:
                    print(f"    {day.get('date')}: ${day.get('close', 0):.2f} (Vol: {day.get('volume', 0):,})")
            else:
                print("✗ FAILED - Invalid response format")
                return False
        else:
            print(f"✗ FAILED - Status {response.status_code}")
            print(f"Response: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"✗ FAILED - Error: {e}")
        return False
    
    print("\n" + "=" * 80)
    print("✓ CORE TESTS PASSED - FMP API is working!")
    print("=" * 80)
    print("\nAPI Key Details:")
    print(f"  Key: {api_key[:10]}...{api_key[-10:]}")
    print(f"  Daily Limit: 250 calls")
    print(f"  Cache Duration: 24 hours")
    print("\nAvailable Endpoints (Free Tier - Stable API):")
    print("  ✓ Symbol search (/stable/search-symbol)")
    print("  ✓ Real-time quotes (/stable/quote)")
    print("  ✓ Company profiles (/stable/profile)")
    print("  ✓ Income statements (/stable/income-statement)")
    print("  ✓ Balance sheets (/stable/balance-sheet-statement)")
    print("  ✓ Cash flow (/stable/cash-flow-statement)")
    print("  ✓ Historical prices (/stable/historical-price-eod/full)")
    print("\nYou're ready to implement the Alpha Edge improvements!")
    
    return True


def main():
    """Run FMP API tests."""
    try:
        # Load config
        config = load_config()
        
        # Get FMP config
        fmp_config = config.get('data_sources', {}).get('financial_modeling_prep', {})
        
        if not fmp_config.get('enabled', False):
            print("✗ ERROR: Financial Modeling Prep is not enabled in config")
            print("Please set 'enabled: true' in config/autonomous_trading.yaml")
            sys.exit(1)
        
        api_key = fmp_config.get('api_key')
        if not api_key:
            print("✗ ERROR: No API key found in config")
            print("Please add your FMP API key to config/autonomous_trading.yaml")
            sys.exit(1)
        
        # Run tests
        success = test_fmp_connection(api_key)
        
        if success:
            sys.exit(0)
        else:
            print("\n✗ Some tests failed. Please check your API key and try again.")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
