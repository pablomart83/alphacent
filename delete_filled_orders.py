#!/usr/bin/env python3
"""Delete all filled orders from database."""

from src.models.database import Database
from src.models.orm import OrderORM
from src.models.enums import OrderStatus

db = Database("alphacent.db")
session = db.get_session()

# Get all filled orders
filled = session.query(OrderORM).filter(
    OrderORM.status == OrderStatus.FILLED
).all()

print(f"Found {len(filled)} filled orders")

for order in filled:
    session.delete(order)
    print(f"Deleted order {order.id}")

session.commit()
session.close()

print(f"\nDeleted {len(filled)} filled orders")
