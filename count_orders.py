#!/usr/bin/env python3
"""Count orders in database by status."""

from src.models.database import Database
from src.models.orm import OrderORM
from src.models.enums import OrderStatus

db = Database("alphacent.db")
session = db.get_session()

# Count by status
for status in OrderStatus:
    count = session.query(OrderORM).filter(OrderORM.status == status).count()
    print(f"{status.value}: {count}")

total = session.query(OrderORM).count()
print(f"\nTotal: {total}")

session.close()
