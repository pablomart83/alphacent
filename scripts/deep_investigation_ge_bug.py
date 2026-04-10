#!/usr/bin/env python3
"""
Deep investigation of GE duplication bug.

This script checks:
1. Database state (positions, orders, symbols)
2. eToro state (positions, orders, instrument IDs)
3. Symbol mapping consistency
4. Duplication prevention logic
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.database import Database
from src.models.orm import OrderORM, PositionORM, StrategyORM
from src.models.enums import OrderStatus, TradingMode, PositionSide
from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from datetime import datetime

def main():
    print("=" * 100)
    print("DEEP INVESTIGATION: GE DUPLICATION BUG")
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
        # ========== PART 1: DATABASE STATE ==========
        print("PART 1: DATABASE STATE")
        print("-" * 100)
        
        # Check all GE-related positions (any symbol variation)
        print("\n1.1 All GE-related positions in database:")
        ge_positions = session.query(PositionORM).filter(
            PositionORM.symbol.in_(['GE', 'ID_1017', '1017'])
        ).all()
        
        print(f"  Total GE positions: {len(ge_positions)}")
        for pos in ge_positions:
            status = "OPEN" if pos.closed_at is None else "CLOSED"
            print(f"    - {status}: ID={pos.id}, symbol={pos.symbol}, qty={pos.quantity:.2f}, "
                  f"strategy={pos.strategy_id}, etoro_id={pos.etoro_position_id}, "
                  f"closed_at={pos.closed_at}")
        
        # Check open positions specifically
        open_ge_positions = [p for p in ge_positions if p.closed_at is None]
        print(f"\n  Open GE positions: {len(open_ge_positions)}")
        
        # Check all GE-related orders
        print("\n1.2 All GE-related orders in database:")
        ge_orders = session.query(OrderORM).filter(
            OrderORM.symbol.in_(['GE', 'ID_1017', '1017'])
        ).all()
        
        print(f"  Total GE orders: {len(ge_orders)}")
        for order in ge_orders:
            print(f"    - {order.status.value}: ID={order.id}, symbol={order.symbol}, "
                  f"qty={order.quantity:.2f}, strategy={order.strategy_id}, "
                  f"submitted={order.submitted_at}")
        
        # Check pending/submitted orders specifically
        pending_ge_orders = [o for o in ge_orders if o.status == OrderStatus.PENDING]
        print(f"\n  Pending/Submitted GE orders: {len(pending_ge_orders)}")
        
        # Check strategies trading GE
        print("\n1.3 Strategies with GE positions/orders:")
        ge_strategy_ids = set([p.strategy_id for p in ge_positions] + [o.strategy_id for o in ge_orders])
        for strategy_id in ge_strategy_ids:
            strategy = session.query(StrategyORM).filter_by(id=strategy_id).first()
            if strategy:
                print(f"    - {strategy_id}: {strategy.name}, status={strategy.status.value}")
            else:
                print(f"    - {strategy_id}: (not found in database)")
        
        # ========== PART 2: ETORO STATE ==========
        print("\n" + "=" * 100)
        print("PART 2: ETORO STATE")
        print("-" * 100)
        
        # Get all positions from eToro
        print("\n2.1 All positions from eToro:")
        etoro_positions = client.get_positions()
        print(f"  Total positions: {len(etoro_positions)}")
        
        # Filter GE positions
        ge_etoro_positions = [p for p in etoro_positions if p.symbol == 'GE' or 'GE' in str(p.symbol)]
        print(f"\n  GE positions in eToro: {len(ge_etoro_positions)}")
        for pos in ge_etoro_positions:
            print(f"    - symbol={pos.symbol}, qty={pos.quantity:.2f}, "
                  f"etoro_id={pos.etoro_position_id}, strategy={pos.strategy_id}")
        
        # Get all orders from eToro
        print("\n2.2 All orders from eToro:")
        try:
            etoro_orders = client.get_orders()
            print(f"  Total orders: {len(etoro_orders)}")
            
            # Filter GE orders
            ge_etoro_orders = [o for o in etoro_orders if o.symbol == 'GE' or 'GE' in str(o.symbol)]
            print(f"\n  GE orders in eToro: {len(ge_etoro_orders)}")
            for order in ge_etoro_orders:
                print(f"    - status={order.status.value}, symbol={order.symbol}, "
                      f"qty={order.quantity:.2f}, etoro_id={order.id}")
        except Exception as e:
            print(f"  Error getting orders from eToro: {e}")
        
        # ========== PART 3: SYMBOL MAPPING ==========
        print("\n" + "=" * 100)
        print("PART 3: SYMBOL MAPPING CONSISTENCY")
        print("-" * 100)
        
        from src.api.etoro_client import INSTRUMENT_ID_TO_SYMBOL, SYMBOL_TO_INSTRUMENT_ID
        
        print("\n3.1 GE instrument mapping:")
        print(f"  GE -> Instrument ID: {SYMBOL_TO_INSTRUMENT_ID.get('GE', 'NOT FOUND')}")
        print(f"  Instrument ID 1017 -> Symbol: {INSTRUMENT_ID_TO_SYMBOL.get(1017, 'NOT FOUND')}")
        
        print("\n3.2 Symbol variations in database:")
        all_symbols = session.query(PositionORM.symbol).distinct().all()
        ge_variations = [s[0] for s in all_symbols if 'GE' in str(s[0]).upper() or '1017' in str(s[0])]
        print(f"  GE-related symbols: {ge_variations}")
        
        # ========== PART 4: DUPLICATION PREVENTION LOGIC ==========
        print("\n" + "=" * 100)
        print("PART 4: DUPLICATION PREVENTION LOGIC")
        print("-" * 100)
        
        print("\n4.1 What _coordinate_signals() would see for GE:")
        
        # Simulate what _coordinate_signals checks
        symbol = 'GE'
        direction = 'LONG'
        
        # Check existing positions
        existing_positions = session.query(PositionORM).filter(
            PositionORM.symbol == symbol,
            PositionORM.closed_at.is_(None)
        ).all()
        print(f"  Existing OPEN positions for symbol='{symbol}': {len(existing_positions)}")
        for pos in existing_positions:
            print(f"    - {pos.id}: strategy={pos.strategy_id}, qty={pos.quantity:.2f}")
        
        # Check pending orders
        from src.models.enums import OrderSide
        pending_orders = session.query(OrderORM).filter(
            OrderORM.symbol == symbol,
            OrderORM.side == OrderSide.BUY,
            OrderORM.status == OrderStatus.PENDING
        ).all()
        print(f"  Pending/Submitted BUY orders for symbol='{symbol}': {len(pending_orders)}")
        for order in pending_orders:
            print(f"    - {order.id}: strategy={order.strategy_id}, qty={order.quantity:.2f}")
        
        # Calculate total strategies
        total_strategies = len(existing_positions) + len(pending_orders)
        print(f"\n  Total strategies trading {symbol} {direction}: {total_strategies}")
        print(f"  Max allowed: 3")
        print(f"  Would block new orders: {total_strategies >= 3}")
        
        # ========== PART 5: THE PROBLEM ==========
        print("\n" + "=" * 100)
        print("PART 5: ROOT CAUSE ANALYSIS")
        print("-" * 100)
        
        print("\n5.1 Comparing database vs eToro:")
        print(f"  Database open GE positions: {len(open_ge_positions)}")
        print(f"  eToro GE positions: {len(ge_etoro_positions)}")
        print(f"  Match: {len(open_ge_positions) == len(ge_etoro_positions)}")
        
        if len(open_ge_positions) != len(ge_etoro_positions):
            print("\n  ⚠️  MISMATCH DETECTED!")
            print(f"  Database is missing {len(ge_etoro_positions) - len(open_ge_positions)} positions")
            
            # Check if positions are using different symbols
            db_symbols = set([p.symbol for p in open_ge_positions])
            etoro_symbols = set([p.symbol for p in ge_etoro_positions])
            print(f"\n  Database symbols: {db_symbols}")
            print(f"  eToro symbols: {etoro_symbols}")
            
            if db_symbols != etoro_symbols:
                print("\n  ❌ SYMBOL MISMATCH: Database and eToro using different symbols!")
        
        print("\n5.2 Duplication prevention check:")
        if len(existing_positions) == 0 and len(ge_etoro_positions) > 0:
            print("  ❌ CRITICAL BUG: Database shows 0 open GE positions")
            print(f"     But eToro has {len(ge_etoro_positions)} open GE positions")
            print("     Duplication prevention will FAIL!")
        elif len(existing_positions) > 0:
            print(f"  ✅ Database correctly shows {len(existing_positions)} open GE positions")
        
        # ========== SUMMARY ==========
        print("\n" + "=" * 100)
        print("SUMMARY")
        print("=" * 100)
        print(f"\nDatabase State:")
        print(f"  - Open GE positions: {len(open_ge_positions)}")
        print(f"  - Pending GE orders: {len(pending_ge_orders)}")
        print(f"  - Total strategies: {len(ge_strategy_ids)}")
        
        print(f"\neToro State:")
        print(f"  - Open GE positions: {len(ge_etoro_positions)}")
        
        print(f"\nDuplication Prevention:")
        print(f"  - Would see {len(existing_positions)} open positions")
        print(f"  - Would see {len(pending_orders)} pending orders")
        print(f"  - Total: {total_strategies} strategies")
        print(f"  - Would block: {total_strategies >= 3}")
        
        if len(open_ge_positions) != len(ge_etoro_positions):
            print(f"\n❌ CRITICAL: Database out of sync with eToro!")
        else:
            print(f"\n✅ Database in sync with eToro")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    main()
