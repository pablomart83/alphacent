#!/usr/bin/env python3
"""Cancel all submitted orders in eToro."""

import sys
from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.models.enums import TradingMode

def main():
    config = get_config()
    
    # Load demo credentials
    creds = config.load_credentials(TradingMode.DEMO)
    
    # Create eToro client
    client = EToroAPIClient(
        public_key=creds["public_key"],
        user_key=creds["user_key"],
        mode=TradingMode.DEMO
    )
    
    print("Fetching all orders...")
    orders = client.get_orders()
    
    # Filter for submitted/pending orders
    pending_orders = [o for o in orders if o.get("statusID") in [1, 11]]
    
    if not pending_orders:
        print("No pending orders to cancel")
        return
    
    print(f"Found {len(pending_orders)} pending orders")
    
    for order in pending_orders:
        order_id = order.get("order_id") or order.get("orderID")
        symbol = order.get("symbol")
        print(f"Cancelling order {order_id} ({symbol})...")
        
        try:
            client.cancel_order(order_id)
            print(f"  ✓ Cancelled {order_id}")
        except Exception as e:
            print(f"  ✗ Failed to cancel {order_id}: {e}")
    
    print("\nDone!")

if __name__ == "__main__":
    main()
