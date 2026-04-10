#!/usr/bin/env python3
"""Check real BTC price vs what we're getting."""

import sys
sys.path.insert(0, 'src')

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.models.enums import TradingMode
import requests

print("=" * 70)
print("Checking Real BTC Price vs eToro API")
print("=" * 70)

# Get real BTC price from external source
print("\n1. Real BTC Price (from CoinGecko)")
print("-" * 70)

try:
    response = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd", timeout=5)
    if response.status_code == 200:
        data = response.json()
        real_btc_price = data.get("bitcoin", {}).get("usd", 0)
        print(f"Real BTC Price: ${real_btc_price:,.2f}")
    else:
        print(f"Could not fetch real price (status {response.status_code})")
        real_btc_price = 70000  # Approximate
        print(f"Using approximate: ${real_btc_price:,.2f}")
except Exception as e:
    print(f"Could not fetch real price: {e}")
    real_btc_price = 70000
    print(f"Using approximate: ${real_btc_price:,.2f}")

# Get price from eToro API
print("\n2. eToro API Price")
print("-" * 70)

config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)

client = EToroAPIClient(
    public_key=credentials["public_key"],
    user_key=credentials["user_key"],
    mode=TradingMode.DEMO
)

try:
    btc_data = client.get_market_data("BTC")
    etoro_price = btc_data.close
    
    print(f"eToro API Price: ${etoro_price:,.2f}")
    print(f"Symbol: {btc_data.symbol}")
    print(f"Open: ${btc_data.open:,.2f}")
    print(f"High: ${btc_data.high:,.2f}")
    print(f"Low: ${btc_data.low:,.2f}")
    
    print("\n3. Comparison")
    print("-" * 70)
    
    difference = abs(real_btc_price - etoro_price)
    percent_diff = (difference / real_btc_price) * 100
    
    print(f"Real Price:  ${real_btc_price:,.2f}")
    print(f"eToro Price: ${etoro_price:,.2f}")
    print(f"Difference:  ${difference:,.2f} ({percent_diff:.1f}%)")
    
    if percent_diff > 10:
        print(f"\n❌ MAJOR DISCREPANCY!")
        print(f"   eToro is showing a price {percent_diff:.1f}% off")
        print(f"   This could be why orders fail")
    elif percent_diff > 5:
        print(f"\n⚠️  Significant difference ({percent_diff:.1f}%)")
    else:
        print(f"\n✅ Prices are close (within {percent_diff:.1f}%)")
    
    print("\n4. Impact on Order")
    print("-" * 70)
    
    units = 1.0
    wrong_amount = units * etoro_price
    correct_amount = units * real_btc_price
    
    print(f"If ordering 1 unit of BTC:")
    print(f"  Using eToro price: ${wrong_amount:,.2f}")
    print(f"  Using real price:  ${correct_amount:,.2f}")
    print(f"  Difference: ${abs(correct_amount - wrong_amount):,.2f}")
    
    if abs(correct_amount - wrong_amount) > 1000:
        print(f"\n❌ This is a BIG problem!")
        print(f"   We're sending ${wrong_amount:,.2f}")
        print(f"   But eToro expects ~${correct_amount:,.2f}")
        print(f"   This could cause order rejection")
    
    print("\n5. Checking eToro's Raw Response")
    print("-" * 70)
    
    # Make raw API call to see what eToro returns
    try:
        instrument_id = client._get_instrument_id("BTC")
        print(f"BTC Instrument ID: {instrument_id}")
        
        # Try to get more detailed market data
        endpoint = f"/api/v1/instruments/{instrument_id}"
        raw_data = client._make_request("GET", endpoint)
        
        print(f"\nRaw instrument data:")
        if "lastPrice" in raw_data:
            print(f"  lastPrice: ${raw_data.get('lastPrice'):,.2f}")
        if "askPrice" in raw_data:
            print(f"  askPrice: ${raw_data.get('askPrice'):,.2f}")
        if "bidPrice" in raw_data:
            print(f"  bidPrice: ${raw_data.get('bidPrice'):,.2f}")
        if "price" in raw_data:
            print(f"  price: ${raw_data.get('price'):,.2f}")
            
    except Exception as e:
        print(f"Could not get raw data: {e}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
