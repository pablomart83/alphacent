#!/usr/bin/env python3
"""Check order details."""

from src.models.database import get_database
from src.models.orm import OrderORM, PositionORM

db = get_database()
session = db.get_session()

# Get the recent order
orders = session.query(OrderORM).order_by(OrderORM.submitted_at.desc()).limit(5).all()

print(f"Recent orders: {len(orders)}\n")

for o in orders:
    print(f"Order: {o.id[:12]}...")
    print(f"  Strategy: {o.strategy_id}")
    print(f"  Symbol: {o.symbol}")
    print(f"  Side: {o.side.value}")
    print(f"  Quantity: {o.quantity}")
    print(f"  Status: {o.status.value}")
    print(f"  Filled Price: {o.filled_price}")
    print(f"  Filled Quantity: {o.filled_quantity}")
    print(f"  eToro Order ID: {o.etoro_order_id}")
    print()

# Check if position was created
positions = session.query(PositionORM).all()
print(f"\nTotal positions in DB: {len(positions)}")

for p in positions[:5]:
    print(f"Position: {p.id[:12]}...")
    print(f"  Strategy: {p.strategy_id}")
    print(f"  Symbol: {p.symbol}")
    print(f"  Quantity: {p.quantity}")
    print(f"  Entry Price: {p.entry_price}")
    print(f"  Closed: {p.closed_at}")
    print()

session.close()
