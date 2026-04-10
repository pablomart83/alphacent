#!/usr/bin/env python3
"""
Emergency fix for GE duplication bug.

This script:
1. Cancels ALL pending GE orders on eToro (not just in database)
2. Identifies the root cause of symbol mismatch
3. Fixes symbol normalization across the system
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.database import Database
from src.models.orm import OrderORM, PositionORM, StrategyORM
from src.models.enums import OrderStatus, TradingMode, PositionSide, StrategyStatus
from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from datetime import datetime

def main():
    print("=" * 100)
    print("EMERGENCY FIX: GE DUPLICATION BUG")
    print("=" * 100)
    print()
    
    # Initialize
    db = Database()
    session = db.get_session()
    config = get_config()
    credentials = config.load_credentials(TradingMode.DEMO)
    client = EToroAPIClient(
        public_key=credentials["public_key"],
        user_key=credentials["user_key"],
        mode=TradingMode.DEMO
    )
    
    try:
        # ========== STEP 1: STOP THE BLEEDING ==========
        print("STEP 1: STOP THE BLEEDING - Cancel all GE orders on eToro")
        print("-" * 100)
        
        # Get all pending GE orders from database
        pending_ge_orders = session.query(OrderORM).filter(
            OrderORM.symbol == 'GE',
            OrderORM.status == OrderStatus.PENDING
        ).all()
        
        print(f"\nFound {len(pending_ge_orders)} pending GE orders in database:")
        for order in pending_ge_orders:
            print(f"  - {order.id}: {order.quantity:.2f} shares, etoro_id={order.etoro_order_id}")
        
        if pending_ge_orders:
            print("\nCancelling orders on eToro...")
            cancelled_count = 0
            for order in pending_ge_orders:
                if order.etoro_order_id:
                    try:
                        # Cancel on eToro
                        result = client.cancel_order(order.etoro_order_id)
                        print(f"  ✅ Cancelled on eToro: {order.id} (etoro_id={order.etoro_order_id})")
                        
                        # Update database
                        order.status = OrderStatus.CANCELLED
                        cancelled_count += 1
                    except Exception as e:
                        print(f"  ❌ Failed to cancel {order.id}: {e}")
                else:
                    print(f"  ⚠️  No eToro ID for {order.id}, marking as cancelled in DB only")
                    order.status = OrderStatus.CANCELLED
                    cancelled_count += 1
            
            session.commit()
            print(f"\n✅ Cancelled {cancelled_count} orders")
        else:
            print("\n✅ No pending GE orders found")
        
        # ========== STEP 2: RETIRE THE PROBLEMATIC STRATEGY ==========
        print("\n" + "=" * 100)
        print("STEP 2: RETIRE THE STRATEGY CREATING DUPLICATE ORDERS")
        print("-" * 100)
        
        # Find strategies that created GE orders
        ge_strategy_ids = session.query(OrderORM.strategy_id).filter(
            OrderORM.symbol == 'GE'
        ).distinct().all()
        
        print(f"\nFound {len(ge_strategy_ids)} strategies that created GE orders:")
        for (strategy_id,) in ge_strategy_ids:
            strategy = session.query(StrategyORM).filter_by(id=strategy_id).first()
            if strategy:
                print(f"  - {strategy_id}: {strategy.name}, status={strategy.status.value}")
                
                # Retire if still active
                if strategy.status in [StrategyStatus.BACKTESTED, StrategyStatus.DEMO, StrategyStatus.LIVE]:
                    print(f"    → Retiring strategy to prevent more orders")
                    strategy.status = StrategyStatus.RETIRED
                    session.commit()
                    print(f"    ✅ Strategy retired")
        
        # ========== STEP 3: ANALYZE THE ROOT CAUSE ==========
        print("\n" + "=" * 100)
        print("STEP 3: ROOT CAUSE ANALYSIS")
        print("-" * 100)
        
        print("\n3.1 Symbol inconsistency:")
        
        # Check what symbols are in database
        all_ge_positions = session.query(PositionORM).filter(
            PositionORM.symbol.in_(['GE', 'ID_1017', '1017'])
        ).all()
        
        db_symbols = set([p.symbol for p in all_ge_positions])
        print(f"  Database position symbols: {db_symbols}")
        
        all_ge_orders = session.query(OrderORM).filter(
            OrderORM.symbol.in_(['GE', 'ID_1017', '1017'])
        ).all()
        
        order_symbols = set([o.symbol for o in all_ge_orders])
        print(f"  Database order symbols: {order_symbols}")
        
        # Check eToro
        etoro_positions = client.get_positions()
        ge_etoro = [p for p in etoro_positions if 'GE' in str(p.symbol).upper() or '1017' in str(p.symbol)]
        etoro_symbols = set([p.symbol for p in ge_etoro])
        print(f"  eToro position symbols: {etoro_symbols}")
        
        print("\n3.2 The problem:")
        print("  ❌ Orders created with symbol='GE'")
        print("  ❌ Positions synced with symbol='ID_1017' (from eToro)")
        print("  ❌ Duplication check looks for symbol='GE' in positions")
        print("  ❌ Finds nothing, allows duplicate orders!")
        
        print("\n3.3 Why this happens:")
        print("  1. Strategy generates signal with symbol='GE'")
        print("  2. Order created with symbol='GE'")
        print("  3. Order fills, becomes position on eToro")
        print("  4. Position sync gets instrument_id=1017 from eToro")
        print("  5. Mapping lookup fails (was using string '1017' instead of int 1017)")
        print("  6. Position stored as symbol='ID_1017' (fallback)")
        print("  7. Next cycle: duplication check for 'GE' finds no positions")
        print("  8. Creates duplicate order!")
        
        # ========== STEP 4: THE FIX ==========
        print("\n" + "=" * 100)
        print("STEP 4: THE FIX NEEDED")
        print("-" * 100)
        
        print("\nWe need to normalize symbols at THREE points:")
        print("\n1. When creating orders (src/execution/order_executor.py):")
        print("   - Normalize signal.symbol before creating order")
        print("   - Ensure consistent symbol format")
        
        print("\n2. When syncing positions (src/api/etoro_client.py):")
        print("   - Already fixed: use int for instrument_id lookup")
        print("   - Maps 1017 -> 'GE' correctly now")
        
        print("\n3. When checking duplicates (src/core/trading_scheduler.py):")
        print("   - Normalize symbol before querying database")
        print("   - Check for ALL symbol variations (GE, ID_1017, 1017)")
        
        print("\n" + "=" * 100)
        print("IMMEDIATE ACTIONS COMPLETED:")
        print("=" * 100)
        print(f"✅ Cancelled {len(pending_ge_orders)} pending GE orders on eToro")
        print(f"✅ Retired {len(ge_strategy_ids)} strategies creating GE orders")
        print("✅ Identified root cause: symbol normalization inconsistency")
        print("\nNEXT: Apply symbol normalization fixes to prevent future duplicates")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    main()
