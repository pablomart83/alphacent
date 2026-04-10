#!/usr/bin/env python3
"""Debug eToro's BTC price endpoint."""

import sys
sys.path.insert(0, 'src')

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.models.enums import TradingMode
import requests

print("=" * 70)
print("Debugging eToro BTC Price Endpoint")
print("=" * 70)

config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)

client = EToroAPIClient(
    public_key=credentials["public_key"],
    user_key=credentials["user_key"],
    mode=TradingMode.DEMO
)

# Get BTC instrument ID
instrument_id = client._get_instrument_id("BTC")
print(f"\nBTC Instrument ID: {instrument_id}")

# Try the public endpoint
print("\n1. Public Rate Endpoint (Current Method)")
print("-" * 70)

try:
    url = f"{client.PUBLIC_URL}/sapi/trade-real/rates/{instrument_id}"
    print(f"URL: {url}")
    
    response = requests.get(url, timeout=10)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\nResponse:")
        import json
        print(json.dumps(data, indent=2))
        
        rate = data.get("Rate", {})
        if rate:
            ask = float(rate.get("Ask", 0))
            bid = float(rate.get("Bid", 0))
            mid = (ask + bid) / 2
            
            print(f"\nParsed:")
            print(f"  Ask: ${ask:,.2f}")
            print(f"  Bid: ${bid:,.2f}")
            print(f"  Mid: ${mid:,.2f}")
            print(f"  Date: {rate.get('Date')}")
    else:
        print(f"Failed: {response.text}")
        
except Exception as e:
    print(f"Error: {e}")

# Try authenticated portfolio endpoint
print("\n2. Authenticated Portfolio Endpoint")
print("-" * 70)

try:
    portfolio_endpoint = "/api/v1/trading/info/demo/portfolio"
    portfolio_data = client._make_request(
        method="GET",
        endpoint=portfolio_endpoint
    )
    
    # Look for instrument rates in portfolio
    if "rates" in portfolio_data:
        print("Found rates in portfolio:")
        rates = portfolio_data.get("rates", {})
        if str(instrument_id) in rates:
            btc_rate = rates[str(instrument_id)]
            print(f"  BTC Rate: {btc_rate}")
    
    # Check aggregated positions for price info
    if "aggregatedPositions" in portfolio_data:
        print("\nChecking aggregated positions...")
        agg_pos = portfolio_data.get("aggregatedPositions", [])
        for pos in agg_pos:
            if pos.get("instrumentID") == instrument_id:
                print(f"Found BTC position data:")
                print(f"  Current Rate: {pos.get('currentRate')}")
                print(f"  Open Rate: {pos.get('openRate')}")
                
except Exception as e:
    print(f"Error: {e}")

# Try market discovery endpoint
print("\n3. Market Discovery Endpoint")
print("-" * 70)

try:
    # Try to get instrument details
    discovery_url = f"{client.PUBLIC_URL}/sapi/app-data/web/discovery/instruments/{instrument_id}"
    print(f"URL: {discovery_url}")
    
    response = requests.get(discovery_url, timeout=10)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\nInstrument Data:")
        if "lastPrice" in data:
            print(f"  Last Price: ${data.get('lastPrice'):,.2f}")
        if "askPrice" in data:
            print(f"  Ask Price: ${data.get('askPrice'):,.2f}")
        if "bidPrice" in data:
            print(f"  Bid Price: ${data.get('bidPrice'):,.2f}")
            
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 70)
print("\nRECOMMENDATION:")
print("The public rate endpoint is returning stale data ($41K vs real $70K)")
print("We need to find the correct eToro endpoint for current BTC price")
print("=" * 70)
