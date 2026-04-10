#!/usr/bin/env python3
"""
Comprehensive check for GE order duplication bug.

This script checks:
1. Open positions in database
2. Closed positions in database  
3. Pending/submitted orders in database
4. Filled orders in database
5. Open positions in eToro (live data)
"""
import sys
sys.path.insert(0, '.')

from src.models.database import Database
from src.models.orm import OrderORM, PositionORM
from src.models.enums import OrderStatus, PositionSide
from src.core.config import get_config
from src.api.etoro_client import EToroAPIClient
from src.models.enums import TradingMode
from sqlalchemy import and_

def main():
    print("=" * 80)
    print("GE Order Duplication Bug Investigation")
    print("=" * 80)
    
    db = Database()
    
    # 1. Check database positions
    print("\n1. DATABASE POSITIONS FOR GE:")
    print("-" * 80)
    with db.get_session() as session:
        all_ge_positions = session.query(PositionORM).filter(
            PositionORM.symbol == 'GE'
        ).all()
        
        open_positions = [p for p in all_ge_positions if p.closed_at is None]
        closed_positions = [p for p in all_ge_positions if p.closed_at is not None]
        
        print(f"Total GE positions: {len(all_ge_positions)}")
        print(f"  - Open: {len(open_positions)}")
        print(f"  - Closed: {len(closed_positions)}")
        
        if open_positions:
            print("\nOPEN GE Positions:")
            for pos in open_positions:
                print(f"  - Position ID: {pos.id}")
                print(f"    Strategy: {pos.strategy_id}")
                print(f"    Side: {pos.side}")
                print(f"    Quantity: {pos.quantity}")
                print(f"    Entry Price: ${pos.entry_price}")
                print(f"    Opened: {pos.opened_at}")
                print()
        
        if closed_positions:
            print(f"\nCLOSED GE Positions (showing first 3 of {len(closed_positions)}):")
            for pos in closed_positions[:3]:
                print(f"  - Position ID: {pos.id}")
                print(f"    Strategy: {pos.strategy_id}")
                print(f"    Closed: {pos.closed_at}")
                print()
    
    # 2. Check database orders
    print("\n2. DATABASE ORDERS FOR GE:")
    print("-" * 80)
    with db.get_session() as session:
        all_ge_orders = session.query(OrderORM).filter(
            OrderORM.symbol == 'GE'
        ).all()
        
        print(f"Total GE orders: {len(all_ge_orders)}")
        
        # Group by status
        from collections import defaultdict
        by_status = defaultdict(list)
        for order in all_ge_orders:
            by_status[order.status].append(order)
        
        for status in [OrderStatus.PENDING, OrderStatus.FILLED, 
                       OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCELLED, OrderStatus.FAILED]:
            orders = by_status.get(status, [])
            if orders:
                print(f"\n{status}: {len(orders)} orders")
                for order in orders:
                    print(f"  - Order ID: {order.id}")
                    print(f"    Strategy: {order.strategy_id}")
                    print(f"    Side: {order.side}")
                    print(f"    Quantity: {order.quantity}")
                    if order.submitted_at:
                        print(f"    Submitted: {order.submitted_at}")
                    if order.filled_at:
                        print(f"    Filled: {order.filled_at}")
                    
                    # Get strategy name
                    from src.models.orm import StrategyORM
                    strategy = session.query(StrategyORM).filter(
                        StrategyORM.id == order.strategy_id
                    ).first()
                    if strategy:
                        print(f"    Strategy Name: {strategy.name}")
                        print(f"    Strategy Status: {strategy.status}")
                    print()
    
    # 3. Check eToro live positions
    print("\n3. ETORO LIVE POSITIONS FOR GE:")
    print("-" * 80)
    try:
        config = get_config()
        creds = config.load_credentials(TradingMode.DEMO)
        etoro_client = EToroAPIClient(
            public_key=creds['public_key'],
            user_key=creds['user_key'],
            mode=TradingMode.DEMO
        )
        
        # Get all positions from eToro
        positions = etoro_client.get_positions()
        ge_positions = [p for p in positions if p.symbol == 'GE']
        
        print(f"Total GE positions in eToro: {len(ge_positions)}")
        
        if ge_positions:
            for pos in ge_positions:
                print(f"  - eToro Position ID: {pos.etoro_position_id}")
                print(f"    Symbol: {pos.symbol}")
                print(f"    Side: {pos.side}")
                print(f"    Quantity: {pos.quantity}")
                print(f"    Entry Price: ${pos.entry_price}")
                print(f"    Current Price: ${pos.current_price}")
                print(f"    P&L: ${pos.unrealized_pnl}")
                print()
        else:
            print("  No GE positions in eToro")
    
    except Exception as e:
        print(f"  ⚠️  Error fetching eToro positions: {e}")
    
    # 4. Summary and analysis
    print("\n4. DUPLICATION ANALYSIS:")
    print("-" * 80)
    
    with db.get_session() as session:
        open_positions = session.query(PositionORM).filter(
            and_(
                PositionORM.symbol == 'GE',
                PositionORM.closed_at.is_(None)
            )
        ).all()
        
        pending_orders = session.query(OrderORM).filter(
            and_(
                OrderORM.symbol == 'GE',
                OrderORM.status == OrderStatus.PENDING
            )
        ).all()
        
        filled_orders = session.query(OrderORM).filter(
            and_(
                OrderORM.symbol == 'GE',
                OrderORM.status == OrderStatus.FILLED
            )
        ).all()
        
        print(f"Open GE positions: {len(open_positions)}")
        print(f"Pending/Submitted GE orders: {len(pending_orders)}")
        print(f"Filled GE orders: {len(filled_orders)}")
        
        if len(pending_orders) > 1:
            print(f"\n⚠️  DUPLICATION DETECTED: {len(pending_orders)} pending orders for GE!")
            print("   This indicates the duplication prevention failed.")
            
            # Check if they're from different strategies
            strategy_ids = set(o.strategy_id for o in pending_orders)
            if len(strategy_ids) > 1:
                print(f"   Orders are from {len(strategy_ids)} different strategies:")
                for order in pending_orders:
                    strategy = session.query(StrategyORM).filter(
                        StrategyORM.id == order.strategy_id
                    ).first()
                    if strategy:
                        print(f"     - {strategy.name} ({strategy.status})")
            else:
                print(f"   All orders are from the same strategy (unusual!)")
        
        if len(open_positions) > 0 and len(pending_orders) > 0:
            print(f"\n⚠️  RISK: {len(open_positions)} open position(s) + {len(pending_orders)} pending order(s)")
            print("   If pending orders fill, we'll have multiple GE positions!")
    
    print("\n" + "=" * 80)
    print("Investigation complete")
    print("=" * 80)

if __name__ == "__main__":
    main()
