#!/usr/bin/env python3
"""
Clean up test positions from the database.

This script closes:
1. All positions with strategy_id="test"
2. All positions with strategy_id="etoro_position" (synced test data)
3. Keeps only positions from legitimate autonomous strategies
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.database import get_database
from src.models.orm import PositionORM, StrategyORM
from src.models.enums import StrategyStatus

def main():
    print("=" * 80)
    print("  DATABASE CLEANUP: Closing Test Positions")
    print("=" * 80)
    
    db = get_database()
    session = db.get_session()
    
    try:
        # Get all open positions
        open_positions = session.query(PositionORM).filter(
            PositionORM.closed_at.is_(None)
        ).all()
        
        print(f"\nTotal open positions: {len(open_positions)}")
        
        # Get valid autonomous strategy IDs (DEMO and LIVE)
        valid_strategies = session.query(StrategyORM).filter(
            StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE])
        ).all()
        valid_strategy_ids = {s.id for s in valid_strategies}
        
        print(f"Valid autonomous strategies: {len(valid_strategy_ids)}")
        
        # Identify positions to close
        positions_to_close = []
        positions_to_keep = []
        
        for pos in open_positions:
            # Close if:
            # 1. strategy_id is "test"
            # 2. strategy_id is "etoro_position" (synced test data)
            # 3. strategy_id is not in valid autonomous strategies
            if (pos.strategy_id == "test" or 
                pos.strategy_id == "etoro_position" or
                pos.strategy_id not in valid_strategy_ids):
                positions_to_close.append(pos)
            else:
                positions_to_keep.append(pos)
        
        print(f"\nPositions to close: {len(positions_to_close)}")
        print(f"Positions to keep: {len(positions_to_keep)}")
        
        # Show breakdown
        test_count = sum(1 for p in positions_to_close if p.strategy_id == "test")
        etoro_count = sum(1 for p in positions_to_close if p.strategy_id == "etoro_position")
        other_count = len(positions_to_close) - test_count - etoro_count
        
        print(f"\nBreakdown:")
        print(f"  - Test positions (strategy_id='test'): {test_count}")
        print(f"  - eToro synced positions: {etoro_count}")
        print(f"  - Other invalid positions: {other_count}")
        
        # Calculate exposure
        total_exposure_to_close = 0
        total_exposure_to_keep = 0
        
        for pos in positions_to_close:
            value = pos.quantity * (pos.current_price or pos.entry_price)
            total_exposure_to_close += value
        
        for pos in positions_to_keep:
            value = pos.quantity * (pos.current_price or pos.entry_price)
            total_exposure_to_keep += value
        
        print(f"\nExposure:")
        print(f"  - To close: ${total_exposure_to_close:,.2f}")
        print(f"  - To keep: ${total_exposure_to_keep:,.2f}")
        
        # Close positions
        if positions_to_close:
            print(f"\nClosing {len(positions_to_close)} positions...")
            now = datetime.now()
            
            for pos in positions_to_close:
                pos.closed_at = now
                # Set realized P&L to unrealized P&L
                pos.realized_pnl = pos.unrealized_pnl or 0.0
                pos.unrealized_pnl = 0.0
            
            session.commit()
            print(f"  ✅ Closed {len(positions_to_close)} positions")
        else:
            print("\n  No positions to close")
        
        # Show remaining positions
        print(f"\n{'='*80}")
        print(f"  REMAINING OPEN POSITIONS: {len(positions_to_keep)}")
        print(f"{'='*80}")
        
        if positions_to_keep:
            for pos in positions_to_keep:
                value = pos.quantity * (pos.current_price or pos.entry_price)
                print(f"{pos.symbol:8} {pos.side.value:5} qty={pos.quantity:8.2f} "
                      f"value=${value:12,.2f} pnl=${pos.unrealized_pnl:10,.2f} "
                      f"strategy={pos.strategy_id[:36]}")
            print(f"\nTotal remaining exposure: ${total_exposure_to_keep:,.2f}")
        else:
            print("  No positions remaining (clean slate)")
        
        print(f"\n{'='*80}")
        print("  CLEANUP COMPLETE")
        print(f"{'='*80}")
        
    except Exception as exc:
        session.rollback()
        print(f"\n❌ Error during cleanup: {exc}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    main()
