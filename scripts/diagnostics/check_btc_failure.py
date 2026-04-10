#!/usr/bin/env python3
"""Check why BTC order failed."""

import sys
sys.path.insert(0, 'src')

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.models.enums import TradingMode

print("=" * 70)
print("Checking BTC Order Failure")
print("=" * 70)

# Load credentials
config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)

client = EToroAPIClient(
    public_key=credentials["public_key"],
    user_key=credentials["user_key"],
    mode=TradingMode.DEMO
)

# Check the specific BTC order
btc_order_id = "328122441"

print(f"\nLooking for eToro order: {btc_order_id}")
print("-" * 70)

try:
    portfolio_endpoint = "/api/v1/trading/info/demo/portfolio"
    portfolio_data = client._make_request(
        method="GET",
        endpoint=portfolio_endpoint
    )
    
    client_portfolio = portfolio_data.get("clientPortfolio", {})
    
    # Check in pending orders
    orders_for_open = client_portfolio.get("ordersForOpen", [])
    found = False
    
    for order in orders_for_open:
        if str(order.get("orderID")) == btc_order_id:
            found = True
            print(f"✅ Found in pending orders:")
            print(f"   Order ID: {order.get('orderID')}")
            print(f"   Instrument: {order.get('instrumentID')}")
            print(f"   Amount: ${order.get('amount'):.2f}")
            print(f"   Status: {order.get('statusID')}")
            print(f"   Error Code: {order.get('errorCode', 0)}")
            break
    
    if not found:
        print(f"❌ Order {btc_order_id} NOT found in eToro pending orders")
        print(f"   This means it was rejected/failed immediately")
        print(f"\n   Possible reasons:")
        print(f"   1. Insufficient balance")
        print(f"   2. Instrument not available")
        print(f"   3. Amount too high for demo account")
        print(f"   4. Market closed")
        
        # Check account balance
        credit = client_portfolio.get("credit", 0)
        available_to_trade = client_portfolio.get("availableToTrade", 0)
        
        print(f"\n   Account Info:")
        print(f"   Credit: ${credit:.2f}")
        print(f"   Available to Trade: ${available_to_trade:.2f}")
        print(f"   Order Amount: $41,207.50")
        
        if available_to_trade < 41207.50:
            print(f"\n   ❌ INSUFFICIENT BALANCE!")
            print(f"   Need: $41,207.50")
            print(f"   Have: ${available_to_trade:.2f}")
            print(f"   Short: ${41207.50 - available_to_trade:.2f}")
        else:
            print(f"\n   ✅ Balance is sufficient")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
