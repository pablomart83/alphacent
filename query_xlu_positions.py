#!/usr/bin/env python3
"""Query XLU positions and orders to investigate duplicates"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.models.database import get_database
from src.models.orm import OrderORM, PositionORM, StrategyORM
from datetime import datetime

db = get_database()
session = db.get_session()

try:
    print("=" * 80)
    print("XLU POSITION AND ORDER ANALYSIS")
    print("=" * 80)
    
    # Query all XLU positions (open and closed)
    print("\n1. ALL XLU POSITIONS (Open and Closed)")
    print("-" * 80)
    all_xlu_positions = session.query(PositionORM).filter(
        PositionORM.symbol == 'XLU'
    ).order_by(PositionORM.opened_at.desc()).all()
    
    print(f"Total XLU positions: {len(all_xlu_positions)}")
    
    open_count = 0
    closed_count = 0
    
    for p in all_xlu_positions:
        status = 'OPEN' if p.closed_at is None else 'CLOSED'
        if p.closed_at is None:
            open_count += 1
        else:
            closed_count += 1
        
        print(f"\n  Position ID: {p.id[:12]}...")
        print(f"    Status: {status}")
        print(f"    Strategy ID: {p.strategy_id}")
        print(f"    Side: {p.side.value}")
        print(f"    Quantity: {p.quantity}")
        print(f"    Entry Price: ${p.entry_price:.2f}")
        print(f"    Current Price: ${p.current_price:.2f}")
        print(f"    Unrealized PnL: ${p.unrealized_pnl:.2f}")
        print(f"    Realized PnL: ${p.realized_pnl:.2f}")
        print(f"    Opened At: {p.opened_at}")
        print(f"    Closed At: {p.closed_at}")
        print(f"    eToro Position ID: {p.etoro_position_id}")
    
    print(f"\n  Summary: {open_count} OPEN, {closed_count} CLOSED")
    
    # Query all XLU orders
    print("\n\n2. ALL XLU ORDERS")
    print("-" * 80)
    all_xlu_orders = session.query(OrderORM).filter(
        OrderORM.symbol == 'XLU'
    ).order_by(OrderORM.submitted_at.desc()).all()
    
    print(f"Total XLU orders: {len(all_xlu_orders)}")
    
    for o in all_xlu_orders:
        print(f"\n  Order ID: {o.id[:12]}...")
        print(f"    Status: {o.status.value}")
        print(f"    Strategy ID: {o.strategy_id}")
        print(f"    Side: {o.side.value}")
        print(f"    Quantity: {o.quantity}")
        print(f"    Order Type: {o.order_type.value}")
        print(f"    Price: ${o.price:.2f}" if o.price else "    Price: N/A")
        print(f"    Submitted At: {o.submitted_at}")
        print(f"    Filled At: {o.filled_at}")
        print(f"    eToro Order ID: {o.etoro_order_id}")
    
    # Query strategies that created XLU positions
    print("\n\n3. STRATEGIES THAT CREATED XLU POSITIONS")
    print("-" * 80)
    strategy_ids = set(p.strategy_id for p in all_xlu_positions)
    
    for strategy_id in strategy_ids:
        strategy = session.query(StrategyORM).filter(
            StrategyORM.id == strategy_id
        ).first()
        
        if strategy:
            print(f"\n  Strategy: {strategy.name}")
            print(f"    ID: {strategy.id}")
            print(f"    Status: {strategy.status.value}")
            print(f"    Symbols: {strategy.symbols}")
            print(f"    Created At: {strategy.created_at}")
            print(f"    Activated At: {strategy.activated_at}")
            
            # Count positions by this strategy
            strategy_positions = [p for p in all_xlu_positions if p.strategy_id == strategy_id]
            print(f"    XLU Positions Created: {len(strategy_positions)}")
        else:
            print(f"\n  Strategy ID: {strategy_id} (NOT FOUND IN DB)")
    
    # Check for duplicate open positions (same symbol, same side)
    print("\n\n4. DUPLICATE POSITION CHECK")
    print("-" * 80)
    
    open_positions = [p for p in all_xlu_positions if p.closed_at is None]
    
    if len(open_positions) > 1:
        print(f"⚠️  WARNING: {len(open_positions)} OPEN XLU POSITIONS DETECTED!")
        print("\nOpen positions by side:")
        
        long_positions = [p for p in open_positions if p.side.value == 'LONG']
        short_positions = [p for p in open_positions if p.side.value == 'SHORT']
        
        if long_positions:
            print(f"\n  LONG positions: {len(long_positions)}")
            for p in long_positions:
                print(f"    - {p.id[:12]}... (strategy: {p.strategy_id}, qty: {p.quantity})")
        
        if short_positions:
            print(f"\n  SHORT positions: {len(short_positions)}")
            for p in short_positions:
                print(f"    - {p.id[:12]}... (strategy: {p.strategy_id}, qty: {p.quantity})")
    else:
        print(f"✓ No duplicate open positions detected ({len(open_positions)} open position)")
    
    # Check for pending orders that might create duplicates
    print("\n\n5. PENDING/SUBMITTED ORDERS THAT COULD CREATE DUPLICATES")
    print("-" * 80)
    
    pending_xlu_orders = [o for o in all_xlu_orders if o.status.value in ['PENDING', 'SUBMITTED']]
    
    if pending_xlu_orders:
        print(f"⚠️  WARNING: {len(pending_xlu_orders)} PENDING XLU ORDERS DETECTED!")
        for o in pending_xlu_orders:
            print(f"\n  Order: {o.id[:12]}...")
            print(f"    Status: {o.status.value}")
            print(f"    Strategy: {o.strategy_id}")
            print(f"    Side: {o.side.value}")
            print(f"    Quantity: {o.quantity}")
            print(f"    Submitted: {o.submitted_at}")
    else:
        print("✓ No pending XLU orders")
    
    print("\n" + "=" * 80)

finally:
    session.close()
