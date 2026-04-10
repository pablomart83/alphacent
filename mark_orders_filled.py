#!/usr/bin/env python3
"""Mark all submitted orders as filled to stop monitoring."""

from datetime import datetime
from src.models.database import Database
from src.models.orm import OrderORM
from src.models.enums import OrderStatus

db = Database("alphacent.db")
session = db.get_session()

# Get all pending orders (previously "submitted" orders are now PENDING)
submitted = session.query(OrderORM).filter(
    OrderORM.status == OrderStatus.PENDING
).all()

print(f"Found {len(submitted)} submitted orders")

for order in submitted:
    order.status = OrderStatus.FILLED
    order.filled_at = datetime.now()
    order.filled_quantity = order.quantity
    print(f"Marked order {order.id} as FILLED")

session.commit()
session.close()

print(f"\nMarked {len(submitted)} orders as FILLED")
