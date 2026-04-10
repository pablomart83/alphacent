#!/usr/bin/env python3
"""Check what's blocking BTC orders."""

import sys
sys.path.insert(0, 'src')

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.models.enums import TradingMode

print("=" * 70)
print("Checking What's Blocking BTC Orders")
print("=" * 70)

config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)

client = EToroAPIClient(
    public_key=credentials["public_key"],
    user_key=credentials["user_key"],
    mode=TradingMode.DEMO
)

try:
    portfolio_endpoint = "/api/v1/trading/info/demo/portfolio"
    portfolio_data = client._make_request(
        method="GET",
        endpoint=portfolio_endpoint
    )
    
    client_portfolio = portfolio_data.get("clientPortfolio", {})
    
    # Check positions
    positions = client_portfolio.get("positions", [])
    print(f"\n1. Open Positions: {len(positions)}")
    print("-" * 70)
    
    btc_positions = []
    for pos in positions:
        instrument_id = pos.get("instrumentID")
        # BTC is typically instrument 1003 or similar
        print(f"Position: Instrument {instrument_id}, Amount ${pos.get('amount'):.2f}")
        if instrument_id in [1003, 1004, 1005]:  # Common BTC instrument IDs
            btc_positions.append(pos)
    
    if btc_positions:
        print(f"\n❌ Found {len(btc_positions)} BTC position(s)!")
        for pos in btc_positions:
            print(f"   Instrument: {pos.get('instrumentID')}")
            print(f"   Amount: ${pos.get('amount'):.2f}")
            print(f"   Position ID: {pos.get('positionID')}")
    else:
        print("✅ No BTC positions found")
    
    # Check pending orders
    orders_for_open = client_portfolio.get("ordersForOpen", [])
    print(f"\n2. Pending Orders: {len(orders_for_open)}")
    print("-" * 70)
    
    btc_orders = []
    for order in orders_for_open:
        instrument_id = order.get("instrumentID")
        if instrument_id in [1003, 1004, 1005]:  # BTC
            btc_orders.append(order)
            print(f"❌ BTC Order: {order.get('orderID')}")
            print(f"   Instrument: {instrument_id}")
            print(f"   Amount: ${order.get('amount'):.2f}")
            print(f"   Status: {order.get('statusID')}")
    
    if not btc_orders:
        print("✅ No pending BTC orders")
    
    # Get instrument info
    print(f"\n3. Checking BTC Instrument Details")
    print("-" * 70)
    
    try:
        # Try to get BTC market data
        btc_data = client.get_market_data("BTC")
        print(f"BTC Symbol: {btc_data.symbol}")
        print(f"BTC Price: ${btc_data.close:.2f}")
        print(f"BTC Instrument ID: {btc_data.instrument_id}")
        
        # Check if this instrument ID appears in positions or orders
        btc_instrument_id = btc_data.instrument_id
        
        blocking_positions = [p for p in positions if p.get("instrumentID") == btc_instrument_id]
        blocking_orders = [o for o in orders_for_open if o.get("instrumentID") == btc_instrument_id]
        
        print(f"\n4. Analysis for Instrument {btc_instrument_id}")
        print("-" * 70)
        
        if blocking_positions:
            print(f"❌ BLOCKING: {len(blocking_positions)} open position(s)")
            for pos in blocking_positions:
                print(f"   Position ID: {pos.get('positionID')}")
                print(f"   Amount: ${pos.get('amount'):.2f}")
        
        if blocking_orders:
            print(f"⚠️  PENDING: {len(blocking_orders)} pending order(s)")
            for order in blocking_orders:
                print(f"   Order ID: {order.get('orderID')}")
                print(f"   Amount: ${order.get('amount'):.2f}")
                print(f"   Status: {order.get('statusID')}")
        
        if not blocking_positions and not blocking_orders:
            print("✅ Nothing blocking BTC orders")
            print("\nPossible reasons for error 746:")
            print("1. eToro demo account restriction")
            print("2. Instrument temporarily unavailable")
            print("3. Account not verified for crypto")
            print("4. Demo account limitation")
        
    except Exception as e:
        print(f"Could not get BTC data: {e}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
