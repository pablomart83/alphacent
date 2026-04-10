#!/usr/bin/env python3
"""Check current open positions and exposure."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.database import get_database
from src.models.orm import PositionORM

db = get_database()
session = db.get_session()

try:
    positions = session.query(PositionORM).filter(PositionORM.closed_at.is_(None)).all()
    print(f'Open positions: {len(positions)}')
    print()
    
    total_value = 0
    for p in positions:
        value = p.quantity * p.current_price if p.current_price else p.quantity * p.entry_price
        total_value += value
        print(f'{p.symbol:8} {p.side:5} qty={p.quantity:8.2f} entry=${p.entry_price:8.2f} current=${p.current_price:8.2f} value=${value:12,.2f} pnl=${p.unrealized_pnl:10,.2f} strategy={p.strategy_id}')
    
    print()
    print(f'Total exposure: ${total_value:,.2f}')
finally:
    session.close()
