#!/usr/bin/env python3
"""Check recent orders to diagnose position sizing issues."""

from src.models.database import get_database
from src.models.orm import OrderORM, StrategyORM
from datetime import datetime, timedelta

db = get_database()
session = db.get_session()

# Get recent orders
recent_orders = session.query(OrderORM).filter(
    OrderORM.submitted_at >= datetime.now() - timedelta(hours=3)
).order_by(OrderORM.submitted_at.desc()).limit(20).all()

print('Recent Orders (last 3 hours):')
print('=' * 100)
for order in recent_orders:
    # Get strategy name
    strategy = session.query(StrategyORM).filter_by(id=order.strategy_id).first()
    strategy_name = strategy.name if strategy else "Unknown"
    
    print(f'Order ID: {order.id[:12]}... | Symbol: {order.symbol:6s} | Quantity: ${order.quantity:>12,.2f} | Status: {order.status.value}')
    print(f'  Strategy: {strategy_name[:60]}')
    print(f'  Submitted: {order.submitted_at}')
    print()

# Get unique symbols from recent orders
symbols = set(order.symbol for order in recent_orders)
print(f'\nUnique symbols in recent orders: {symbols}')
print(f'Total recent orders: {len(recent_orders)}')

# Check strategies
demo_strategies = session.query(StrategyORM).filter(
    StrategyORM.status == 'DEMO'
).all()

print(f'\nActive DEMO strategies: {len(demo_strategies)}')
for strat in demo_strategies[:10]:  # Show first 10
    print(f'  - {strat.name[:60]} | Symbols: {strat.symbols}')

session.close()
