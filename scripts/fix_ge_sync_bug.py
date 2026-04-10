#!/usr/bin/env python3
"""
Fix GE position sync bug.

This script:
1. Cancels pending GE orders
2. Forces a position sync from eToro
3. Verifies database is in sync with eToro
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.database import Database
from src.models.orm import OrderORM, PositionORM
from src.models.enums import OrderStatus, TradingMode
from src.api.etoro_client import EToroAPIClient
from src.core.order_monitor import OrderMonitor
from src.core.config import get_config
from datetime import datetime

def main():
    print("=" * 80)
    print("GE POSITION SYNC BUG FIX")
    print("=" * 80)
    print()
    
    # Initialize database
    db = Database()
    session = db.get_session()
    
    # Initialize eToro client
    config = get_config()
    credentials = config.load_credentials(TradingMode.DEMO)
    client = EToroAPIClient(
        public_key=credentials["public_key"],
        user_key=credentials["user_key"],
        mode=TradingMode.DEMO
    )
    
    try:
        # Step 1: Check and cancel pending GE orders
        print("Step 1: Checking for pending GE orders...")
        pending_orders = session.query(OrderORM).filter(
            OrderORM.symbol == 'GE',
            OrderORM.status == OrderStatus.PENDING
        ).all()
        
        if pending_orders:
            print(f"  Found {len(pending_orders)} pending GE orders:")
            for order in pending_orders:
                print(f"    - Order {order.id}: {order.quantity} shares, status={order.status.value}")
            
            # Cancel them
            print("\n  Cancelling pending orders...")
            for order in pending_orders:
                try:
                    # Update status to CANCELLED
                    order.status = OrderStatus.CANCELLED
                    order.updated_at = datetime.now()
                    print(f"    ✅ Cancelled order {order.id}")
                except Exception as e:
                    print(f"    ❌ Error cancelling order {order.id}: {e}")
            
            session.commit()
            print(f"\n  ✅ Cancelled {len(pending_orders)} pending GE orders")
        else:
            print("  ✅ No pending GE orders found")
        
        # Step 2: Check current database state
        print("\nStep 2: Checking current database state...")
        db_positions = session.query(PositionORM).filter(
            PositionORM.symbol.in_(['GE', 'ID_1017', '1017']),
            PositionORM.closed_at.is_(None)
        ).all()
        
        print(f"  Database shows {len(db_positions)} open GE positions:")
        for pos in db_positions:
            print(f"    - Position {pos.id}: symbol={pos.symbol}, qty={pos.quantity}, etoro_id={pos.etoro_position_id}")
        
        # Step 3: Force sync from eToro
        print("\nStep 3: Forcing position sync from eToro...")
        monitor = OrderMonitor(client, db)
        sync_result = monitor.sync_positions(force=True)
        
        print(f"  Sync result: {sync_result}")
        
        # Step 4: Verify sync worked
        print("\nStep 4: Verifying sync...")
        session.expire_all()  # Refresh from database
        
        db_positions_after = session.query(PositionORM).filter(
            PositionORM.symbol == 'GE',
            PositionORM.closed_at.is_(None)
        ).all()
        
        print(f"  Database now shows {len(db_positions_after)} open GE positions:")
        for pos in db_positions_after:
            print(f"    - Position {pos.id}: symbol={pos.symbol}, qty={pos.quantity:.2f}, etoro_id={pos.etoro_position_id}")
        
        # Step 5: Get eToro positions for comparison
        print("\nStep 5: Comparing with eToro...")
        etoro_positions = client.get_positions()
        ge_positions_etoro = [p for p in etoro_positions if p.symbol == 'GE']
        
        print(f"  eToro shows {len(ge_positions_etoro)} open GE positions:")
        for pos in ge_positions_etoro:
            print(f"    - Position {pos.etoro_position_id}: symbol={pos.symbol}, qty={pos.quantity:.2f}")
        
        # Final verification
        print("\n" + "=" * 80)
        if len(db_positions_after) == len(ge_positions_etoro):
            print("✅ SUCCESS: Database is now in sync with eToro!")
            print(f"   Both show {len(db_positions_after)} open GE positions")
        else:
            print("⚠️  WARNING: Database and eToro still out of sync!")
            print(f"   Database: {len(db_positions_after)} positions")
            print(f"   eToro: {len(ge_positions_etoro)} positions")
            print("\n   This may require manual investigation.")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    main()
