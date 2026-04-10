#!/usr/bin/env python3
"""Check eToro order status directly."""

import sys
sys.path.insert(0, 'src')

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.models.enums import TradingMode

# Load credentials
config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)

if not credentials or not credentials.get("public_key") or not credentials.get("user_key"):
    print("❌ No eToro credentials configured")
    sys.exit(1)

# Initialize client
client = EToroAPIClient(
    public_key=credentials["public_key"],
    user_key=credentials["user_key"],
    mode=TradingMode.DEMO
)

print("=" * 70)
print("Checking eToro Orders Status")
print("=" * 70)

# Get portfolio data
try:
    portfolio_endpoint = "/api/v1/trading/info/demo/portfolio"
    portfolio_data = client._make_request(
        method="GET",
        endpoint=portfolio_endpoint
    )
    
    client_portfolio = portfolio_data.get("clientPortfolio", {})
    orders_for_open = client_portfolio.get("ordersForOpen", [])
    
    print(f"\nFound {len(orders_for_open)} pending orders in eToro:")
    print("-" * 70)
    
    for order in orders_for_open:
        order_id = order.get("orderID")
        instrument_id = order.get("instrumentID")
        amount = order.get("amount")
        status_id = order.get("statusID")
        error_code = order.get("errorCode", 0)
        
        print(f"\nOrder ID: {order_id}")
        print(f"  Instrument: {instrument_id}")
        print(f"  Amount: ${amount:.2f}")
        print(f"  Status: {status_id}")
        print(f"  Error Code: {error_code}")
        
        # Check our database for this order
        import sqlite3
        conn = sqlite3.connect('alphacent.db')
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, symbol, quantity, status FROM orders WHERE etoro_order_id = ?",
            (str(order_id),)
        )
        result = cursor.fetchone()
        conn.close()
        
        if result:
            our_id, symbol, quantity, our_status = result
            print(f"  Our DB: {symbol} ${quantity:.2f} ({our_status})")
        else:
            print(f"  Our DB: Not found")
    
    # Check positions
    positions = client_portfolio.get("positions", [])
    print(f"\n\nFound {len(positions)} open positions in eToro:")
    print("-" * 70)
    
    for pos in positions:
        instrument_id = pos.get("instrumentID")
        amount = pos.get("amount")
        net_profit = pos.get("netProfit", 0)
        print(f"\nInstrument: {instrument_id}")
        print(f"  Amount: ${amount:.2f}")
        print(f"  P&L: ${net_profit:.2f}")
        
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
