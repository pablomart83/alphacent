#!/usr/bin/env python3
"""Clean up all test positions."""

from src.models.database import get_database
from src.models.orm import PositionORM, OrderORM
from datetime import datetime

db = get_database()
session = db.get_session()

try:
    # Close all open positions
    positions = session.query(PositionORM).filter(PositionORM.closed_at.is_(None)).all()
    print(f"Closing {len(positions)} open positions...")
    
    for p in positions:
        p.closed_at = datetime.now()
    
    session.commit()
    print(f"✅ Closed {len(positions)} positions")
    
    # Delete old orders
    orders = session.query(OrderORM).all()
    print(f"Deleting {len(orders)} orders...")
    
    for o in orders:
        session.delete(o)
    
    session.commit()
    print(f"✅ Deleted {len(orders)} orders")
    
except Exception as e:
    print(f"❌ Error: {e}")
    session.rollback()
finally:
    session.close()
