#!/usr/bin/env python3
"""Verify position data format in database."""

from src.models.database import get_database
from src.models.orm import PositionORM, StrategyORM
from src.risk.risk_manager import EXTERNAL_POSITION_STRATEGY_IDS

db = get_database()
session = db.get_session()

# Get all open positions
positions = session.query(PositionORM).filter(PositionORM.closed_at.is_(None)).all()

print(f"Total open positions: {len(positions)}\n")

# Separate by type
etoro_positions = [p for p in positions if p.strategy_id in EXTERNAL_POSITION_STRATEGY_IDS]
autonomous_positions = [p for p in positions if p.strategy_id not in EXTERNAL_POSITION_STRATEGY_IDS]

print(f"eToro-synced positions: {len(etoro_positions)}")
for p in etoro_positions[:3]:
    print(f"  {p.symbol}: qty={p.quantity:.2f} @ ${p.entry_price:.2f}")
    print(f"    → Value = ${p.quantity:.2f} (quantity IS dollar amount)")

print(f"\nAutonomous positions: {len(autonomous_positions)}")
for p in autonomous_positions[:3]:
    calculated_value = p.quantity * p.entry_price
    print(f"  {p.symbol}: qty={p.quantity:.2f} @ ${p.entry_price:.2f}")
    print(f"    → Value = ${calculated_value:,.2f} (qty * price)")
    if calculated_value > 1_000_000:
        print(f"    ⚠️  SUSPICIOUS: Value > $1M suggests qty is dollar amount, not shares!")

# Check strategy IDs
print(f"\nStrategy IDs in use:")
strategy_ids = set(p.strategy_id for p in positions)
for sid in list(strategy_ids)[:10]:
    count = sum(1 for p in positions if p.strategy_id == sid)
    is_external = sid in EXTERNAL_POSITION_STRATEGY_IDS
    print(f"  {sid}: {count} positions {'(EXTERNAL)' if is_external else '(AUTONOMOUS)'}")

session.close()
