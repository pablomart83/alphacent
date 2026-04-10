"""Check orders in database."""

import sys
sys.path.insert(0, '.')

from src.models.database import get_database
from src.models.orm import OrderORM
from src.models.enums import OrderStatus

db = get_database()
session = db.get_session()

print("=" * 70)
print("Database Orders Check")
print("=" * 70)

# Get all orders
orders = session.query(OrderORM).order_by(OrderORM.submitted_at.desc()).all()

print(f"\nTotal orders in database: {len(orders)}")

# Group by status
pending = [o for o in orders if o.status == OrderStatus.PENDING]
filled = [o for o in orders if o.status == OrderStatus.FILLED]

print(f"\nStatus breakdown:")
print(f"  PENDING: {len(pending)}")
print(f"  FILLED: {len(filled)}")

if pending:
    print(f"\n⏳ PENDING Orders:")
    for order in pending:
        print(f"\n  Order {order.id}:")
        print(f"    Symbol: {order.symbol}")
        print(f"    Side: {order.side.value}")
        print(f"    Quantity: {order.quantity}")
        print(f"    Created: {order.submitted_at}")
        print(f"    eToro ID: {order.etoro_order_id}")

if filled:
    print(f"\n✅ FILLED Orders (last 3):")
    for order in filled[:3]:
        print(f"\n  Order {order.id}:")
        print(f"    Symbol: {order.symbol}")
        print(f"    Filled at: {order.filled_at}")
        print(f"    eToro ID: {order.etoro_order_id}")

session.close()
print("\n" + "=" * 70)
