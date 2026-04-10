#!/usr/bin/env python3
"""Delete all failed orders from database."""

from src.models.database import Database
from src.models.orm import OrderORM
from src.models.enums import OrderStatus

db = Database("alphacent.db")
session = db.get_session()

# Get all failed orders
failed = session.query(OrderORM).filter(
    OrderORM.status == OrderStatus.FAILED
).all()

print(f"Found {len(failed)} failed orders")

for order in failed:
    session.delete(order)

session.commit()
session.close()

print(f"Deleted {len(failed)} failed orders")
