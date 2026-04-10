#!/usr/bin/env python3
"""Check positions in database"""

from src.models.database import get_database
from src.risk.risk_manager import EXTERNAL_POSITION_STRATEGY_IDS
from src.models.orm import PositionORM

db = get_database()
session = db.get_session()

positions = session.query(PositionORM).filter(PositionORM.closed_at == None).all()
print(f'Total open positions in DB: {len(positions)}')
print()

etoro_positions = [p for p in positions if p.strategy_id in EXTERNAL_POSITION_STRATEGY_IDS]
print(f'eToro positions: {len(etoro_positions)}')
for p in etoro_positions[:10]:
    value = p.quantity  # For eToro positions, quantity should be dollar amount
    print(f'  {p.symbol} | qty={p.quantity:.2f} | entry=${p.entry_price:.2f} | current=${p.current_price:.2f} | value=${value:.2f}')

print()
autonomous_positions = [p for p in positions if p.strategy_id not in EXTERNAL_POSITION_STRATEGY_IDS]
print(f'Autonomous positions: {len(autonomous_positions)}')
for p in autonomous_positions[:10]:
    value = p.quantity * p.current_price  # For autonomous, quantity is units
    print(f'  {p.symbol} | qty={p.quantity:.2f} | entry=${p.entry_price:.2f} | current=${p.current_price:.2f} | value=${value:.2f}')

session.close()
