#!/usr/bin/env python3
"""Cancel all pending orders to free up funds."""

import sys
sys.path.insert(0, 'src')

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.models.enums import TradingMode
import time

print("=" * 70)
print("Cancel All Pending Orders")
print("=" * 70)

# Load credentials
config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)

if not credentials or not credentials.get("public_key") or not credentials.get("user_key"):
    print("❌ No eToro credentials configured")
    sys.exit(1)

client = EToroAPIClient(
    public_key=credentials["public_key"],
    user_key=credentials["user_key"],
    mode=TradingMode.DEMO
)

print("\n1. Fetching pending orders...")
print("-" * 70)

try:
    portfolio_endpoint = "/api/v1/trading/info/demo/portfolio"
    portfolio_data = client._make_request(
        method="GET",
        endpoint=portfolio_endpoint
    )
    
    client_portfolio = portfolio_data.get("clientPortfolio", {})
    orders_for_open = client_portfolio.get("ordersForOpen", [])
    
    print(f"Found {len(orders_for_open)} pending orders")
    
    if len(orders_for_open) == 0:
        print("✅ No pending orders to cancel")
        sys.exit(0)
    
    # Show what we're about to cancel
    total_locked = sum(order.get("amount", 0) for order in orders_for_open)
    print(f"Total funds locked: ${total_locked:.2f}")
    
    print("\nOrders to cancel:")
    for order in orders_for_open:
        order_id = order.get("orderID")
        instrument_id = order.get("instrumentID")
        amount = order.get("amount")
        print(f"  - Order {order_id}: Instrument {instrument_id}, ${amount:.2f}")
    
    # Ask for confirmation
    print("\n" + "=" * 70)
    response = input("Cancel all these orders? (yes/no): ")
    
    if response.lower() != 'yes':
        print("❌ Cancelled by user")
        sys.exit(0)
    
    print("\n2. Cancelling orders...")
    print("-" * 70)
    
    cancelled = 0
    failed = 0
    
    for order in orders_for_open:
        order_id = order.get("orderID")
        amount = order.get("amount")
        
        try:
            print(f"Cancelling order {order_id} (${amount:.2f})...", end=" ")
            client.cancel_order(order_id)
            print("✅ Cancelled")
            cancelled += 1
            time.sleep(0.5)  # Rate limiting
        except Exception as e:
            print(f"❌ Failed: {e}")
            failed += 1
    
    print("\n3. Summary")
    print("-" * 70)
    print(f"✅ Cancelled: {cancelled}")
    print(f"❌ Failed: {failed}")
    print(f"💰 Funds freed: ~${total_locked:.2f}")
    
    # Check new balance
    print("\n4. Checking new balance...")
    print("-" * 70)
    
    portfolio_data = client._make_request(
        method="GET",
        endpoint=portfolio_endpoint
    )
    
    client_portfolio = portfolio_data.get("clientPortfolio", {})
    credit = client_portfolio.get("credit", 0)
    available_to_trade = client_portfolio.get("availableToTrade", 0)
    
    print(f"Credit: ${credit:.2f}")
    print(f"Available to Trade: ${available_to_trade:.2f}")
    
    if available_to_trade > 1000:
        print(f"\n✅ SUCCESS! You now have ${available_to_trade:.2f} available")
        print("You can place new orders now!")
    else:
        print(f"\n⚠️  Still low balance: ${available_to_trade:.2f}")
        print("Orders may have been cancelled but funds not released yet")
        print("Wait a few minutes and check again")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
