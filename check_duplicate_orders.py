#!/usr/bin/env python3
"""Check for duplicate orders and positions for GE and PLTR"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.models.database import get_database
from src.models.orm import OrderORM, PositionORM

db = get_database()
session = db.get_session()

try:
    # Check GE and PLTR orders
    print('=== GE Orders ===')
    ge_orders = session.query(OrderORM).filter(OrderORM.symbol == 'GE').order_by(OrderORM.submitted_at.desc()).limit(10).all()
    for o in ge_orders:
        print(f'{o.id[:12]}... | {o.status.value} | {o.side.value} | qty={o.quantity} | submitted={o.submitted_at} | etoro_id={o.etoro_order_id}')

    print('\n=== PLTR Orders ===')
    pltr_orders = session.query(OrderORM).filter(OrderORM.symbol == 'PLTR').order_by(OrderORM.submitted_at.desc()).limit(10).all()
    for o in pltr_orders:
        print(f'{o.id[:12]}... | {o.status.value} | {o.side.value} | qty={o.quantity} | submitted={o.submitted_at} | etoro_id={o.etoro_order_id}')

    print('\n=== GE Positions ===')
    ge_positions = session.query(PositionORM).filter(PositionORM.symbol == 'GE').all()
    for p in ge_positions:
        status = 'OPEN' if p.closed_at is None else 'CLOSED'
        print(f'{p.id[:12]}... | {status} | {p.side.value} | qty={p.quantity} | entry=${p.entry_price} | etoro_id={p.etoro_position_id}')

    print('\n=== PLTR Positions ===')
    pltr_positions = session.query(PositionORM).filter(PositionORM.symbol == 'PLTR').all()
    for p in pltr_positions:
        status = 'OPEN' if p.closed_at is None else 'CLOSED'
        print(f'{p.id[:12]}... | {status} | {p.side.value} | qty={p.quantity} | entry=${p.entry_price} | etoro_id={p.etoro_position_id}')

finally:
    session.close()
