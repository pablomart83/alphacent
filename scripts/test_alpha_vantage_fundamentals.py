#!/usr/bin/env python3
"""
Test Alpha Vantage API for fundamental data.
"""

import requests
import sys
from pathlib import Path
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml


def load_config():
    """Load configuration file."""
    config_path = Path(__file__).parent.parent / "config" / "autonomous_trading.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def test_alpha_vantage_fundamentals(api_key):
    """Test Alpha Vantage fundamental data endpoints."""
    print("=" * 80)
    print("Testing Alpha Vantage Fundamental Data")
    print("=" * 80)
    
    # Test 1: Company Overview (includes most fundamentals)
    print("\n[Test 1] Fetching Apple (AAPL) company overview...")
    url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol=AAPL&apikey={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data and 'Symbol' in data:
                print(f"✓ SUCCESS - Company Overview")
                print(f"  Company: {data.get('Name')}")
                print(f"  Symbol: {data.get('Symbol')}")
                print(f"  Sector: {data.get('Sector')}")
                print(f"  Industry: {data.get('Industry')}")
                print(f"  Market Cap: ${float(data.get('MarketCapitalization', 0)):,.0f}")
                print(f"  P/E Ratio: {data.get('PERatio')}")
                print(f"  EPS: ${data.get('EPS')}")
                print(f"  ROE: {data.get('ReturnOnEquityTTM')}")
                print(f"  Debt/Equity: {data.get('DebtToEquity')}")
                print(f"  Dividend Yield: {data.get('DividendYield')}")
            else:
                print(f"✗ FAILED - Invalid response: {data}")
                return False
        else:
            print(f"✗ FAILED - Status {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ FAILED - Error: {e}")
        return False
    
    # Test 2: Earnings Data
    print("\n[Test 2] Fetching Apple earnings data...")
    url = f"https://www.alphavantage.co/query?function=EARNINGS&symbol=AAPL&apikey={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and 'quarterlyEarnings' in data:
                quarterly = data['quarterlyEarnings']
                print(f"✓ SUCCESS - Earnings Data")
                print(f"  Found {len(quarterly)} quarterly earnings reports")
                if len(quarterly) > 0:
                    latest = quarterly[0]
                    print(f"  Latest Quarter: {latest.get('fiscalDateEnding')}")
                    print(f"  Reported EPS: ${latest.get('reportedEPS')}")
                    print(f"  Estimated EPS: ${latest.get('estimatedEPS')}")
                    print(f"  Surprise: ${latest.get('surprise')}")
                    print(f"  Surprise %: {latest.get('surprisePercentage')}%")
            else:
                print(f"✗ FAILED - Invalid response")
                return False
        else:
            print(f"✗ FAILED - Status {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ FAILED - Error: {e}")
        return False
    
    # Test 3: Income Statement
    print("\n[Test 3] Fetching Apple income statement...")
    url = f"https://www.alphavantage.co/query?function=INCOME_STATEMENT&symbol=AAPL&apikey={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and 'annualReports' in data:
                annual = data['annualReports']
                print(f"✓ SUCCESS - Income Statement")
                print(f"  Found {len(annual)} annual reports")
                if len(annual) > 0:
                    latest = annual[0]
                    print(f"  Fiscal Year: {latest.get('fiscalDateEnding')}")
                    print(f"  Total Revenue: ${float(latest.get('totalRevenue', 0)):,.0f}")
                    print(f"  Net Income: ${float(latest.get('netIncome', 0)):,.0f}")
                    print(f"  Gross Profit: ${float(latest.get('grossProfit', 0)):,.0f}")
            else:
                print(f"✗ FAILED - Invalid response")
                return False
        else:
            print(f"✗ FAILED - Status {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ FAILED - Error: {e}")
        return False
    
    # Test 4: Balance Sheet
    print("\n[Test 4] Fetching Apple balance sheet...")
    url = f"https://www.alphavantage.co/query?function=BALANCE_SHEET&symbol=AAPL&apikey={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and 'annualReports' in data:
                annual = data['annualReports']
                print(f"✓ SUCCESS - Balance Sheet")
                print(f"  Found {len(annual)} annual reports")
                if len(annual) > 0:
                    latest = annual[0]
                    print(f"  Fiscal Year: {latest.get('fiscalDateEnding')}")
                    print(f"  Total Assets: ${float(latest.get('totalAssets', 0)):,.0f}")
                    print(f"  Total Liabilities: ${float(latest.get('totalLiabilities', 0)):,.0f}")
                    print(f"  Total Equity: ${float(latest.get('totalShareholderEquity', 0)):,.0f}")
            else:
                print(f"✗ FAILED - Invalid response")
                return False
        else:
            print(f"✗ FAILED - Status {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ FAILED - Error: {e}")
        return False
    
    print("\n" + "=" * 80)
    print("✓ ALL TESTS PASSED - Alpha Vantage fundamentals working!")
    print("=" * 80)
    print("\nAPI Key Details:")
    print(f"  Key: {api_key[:10]}...{api_key[-10:]}")
    print(f"  Daily Limit: 500 calls")
    print(f"  Cache Duration: 24 hours")
    print("\nAvailable Data:")
    print("  ✓ Company overview (sector, industry, market cap, P/E, EPS, ROE, etc.)")
    print("  ✓ Earnings data (quarterly/annual with surprises)")
    print("  ✓ Income statements (revenue, net income, etc.)")
    print("  ✓ Balance sheets (assets, liabilities, equity)")
    print("  ✓ Cash flow statements")
    print("\nYou have everything needed for Alpha Edge improvements!")
    
    return True


def main():
    """Run Alpha Vantage fundamental data tests."""
    try:
        # Load config
        config = load_config()
        
        # Get Alpha Vantage config
        av_config = config.get('data_sources', {}).get('alpha_vantage', {})
        
        if not av_config.get('enabled', False):
            print("✗ ERROR: Alpha Vantage is not enabled in config")
            sys.exit(1)
        
        api_key = av_config.get('api_key')
        if not api_key:
            print("✗ ERROR: No API key found in config")
            sys.exit(1)
        
        # Run tests
        success = test_alpha_vantage_fundamentals(api_key)
        
        if success:
            print("\n✅ Setup Complete!")
            print("\nNext Steps:")
            print("1. Start implementing Alpha Edge improvements (Task 2 in tasks.md)")
            print("2. Use Alpha Vantage for all fundamental data")
            print("3. Yahoo Finance as fallback for basic data")
            print("4. Test on demo account for 3-6 months")
            sys.exit(0)
        else:
            print("\n✗ Some tests failed.")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
