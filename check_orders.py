#!/usr/bin/env python3
"""Check orders in database and cancel them via eToro."""

from src.models.database import Database
from src.models.orm import OrderORM
from src.models.enums import OrderStatus, TradingMode
from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config

db = Database("alphacent.db")
session = db.get_session()

# Get all pending orders (previously "submitted" orders are now PENDING)
submitted = session.query(OrderORM).filter(
    OrderORM.status == OrderStatus.PENDING
).all()

print(f"Found {len(submitted)} submitted orders in database")

if submitted:
    # Setup eToro client
    config = get_config()
    creds = config.load_credentials(TradingMode.DEMO)
    client = EToroAPIClient(
        public_key=creds["public_key"],
        user_key=creds["user_key"],
        mode=TradingMode.DEMO
    )
    
    for order in submitted:
        print(f"\nOrder {order.id}:")
        print(f"  Symbol: {order.symbol}")
        print(f"  Side: {order.side.value}")
        print(f"  Quantity: {order.quantity}")
        print(f"  eToro ID: {order.etoro_order_id}")
        
        if order.etoro_order_id:
            try:
                # Try to cancel
                print(f"  Attempting to cancel...")
                result = client.cancel_order(order.etoro_order_id)
                print(f"  ✓ Cancelled")
                
                # Update in DB
                order.status = OrderStatus.CANCELLED
            except Exception as e:
                print(f"  ✗ Cancel failed: {e}")
    
    session.commit()
    print(f"\nUpdated database")

session.close()
