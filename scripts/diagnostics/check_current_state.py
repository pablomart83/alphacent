#!/usr/bin/env python3
"""Quick check of current trading state."""

from src.models.database import get_database
from src.models.enums import StrategyStatus
from src.models.orm import StrategyORM, OrderORM, PositionORM
from datetime import datetime, timedelta

db = get_database()
session = db.get_session()

# Get DEMO strategies
demo_strategies = session.query(StrategyORM).filter(StrategyORM.status == StrategyStatus.DEMO).all()
print(f'DEMO Strategies: {len(demo_strategies)}')
for s in demo_strategies[:5]:
    print(f'  - {s.name} | symbols={s.symbols}')

# Get recent orders
cutoff = datetime.now() - timedelta(hours=24)
recent_orders = session.query(OrderORM).filter(OrderORM.submitted_at >= cutoff).all()
print(f'\nRecent Orders (24h): {len(recent_orders)}')
for o in recent_orders[:5]:
    print(f'  - {o.symbol} {o.side.value} qty={o.quantity} status={o.status.value}')

# Get open positions
open_positions = session.query(PositionORM).filter(PositionORM.closed_at.is_(None)).all()
print(f'\nOpen Positions: {len(open_positions)}')
for p in open_positions[:5]:
    print(f'  - {p.symbol} {p.side.value} qty={p.quantity} entry=${p.entry_price:.2f}')

session.close()
