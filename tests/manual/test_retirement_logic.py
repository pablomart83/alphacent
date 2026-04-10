#!/usr/bin/env python3
"""
Test script to verify the new retirement logic.
Checks that only non-activated strategies are retired, keeping DEMO and LIVE strategies.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.models.database import get_database
from src.models.enums import StrategyStatus
from src.models.orm import StrategyORM

def test_retirement_logic():
    """Test the retirement logic by checking which strategies would be retired."""
    
    db = get_database()
    session = db.get_session()
    
    try:
        print("=" * 80)
        print("Testing Retirement Logic")
        print("=" * 80)
        
        # Get all strategies
        all_strategies = session.query(StrategyORM).all()
        print(f"\nTotal strategies in database: {len(all_strategies)}")
        
        # Count by status
        status_counts = {}
        for s in all_strategies:
            status = s.status.value if hasattr(s.status, "value") else str(s.status)
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print("\nStrategies by status:")
        for status, count in sorted(status_counts.items()):
            print(f"  {status}: {count}")
        
        # Strategies that WOULD be retired (new logic)
        strategies_to_retire = (
            session.query(StrategyORM)
            .filter(StrategyORM.status.in_([
                StrategyStatus.PROPOSED,
                StrategyStatus.BACKTESTED,
                StrategyStatus.INVALID
            ]))
            .all()
        )
        
        print(f"\n{'=' * 80}")
        print(f"NEW LOGIC: Would retire {len(strategies_to_retire)} strategies")
        print(f"{'=' * 80}")
        
        if strategies_to_retire:
            print("\nStrategies that would be retired:")
            for s in strategies_to_retire:
                status = s.status.value if hasattr(s.status, "value") else str(s.status)
                print(f"  - {s.name} (status: {status})")
        
        # Strategies that would be KEPT (DEMO and LIVE)
        active_strategies = (
            session.query(StrategyORM)
            .filter(StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE]))
            .all()
        )
        
        print(f"\n{'=' * 80}")
        print(f"Would KEEP {len(active_strategies)} active strategies (DEMO + LIVE)")
        print(f"{'=' * 80}")
        
        if active_strategies:
            print("\nActive strategies that would be kept:")
            for s in active_strategies:
                status = s.status.value if hasattr(s.status, "value") else str(s.status)
                print(f"  - {s.name} (status: {status})")
        
        # Old logic comparison
        old_logic_count = (
            session.query(StrategyORM)
            .filter(StrategyORM.status != StrategyStatus.RETIRED)
            .count()
        )
        
        print(f"\n{'=' * 80}")
        print(f"COMPARISON:")
        print(f"  OLD LOGIC: Would retire {old_logic_count} strategies (ALL non-RETIRED)")
        print(f"  NEW LOGIC: Would retire {len(strategies_to_retire)} strategies (only non-activated)")
        print(f"  DIFFERENCE: Keeps {old_logic_count - len(strategies_to_retire)} more strategies")
        print(f"  (Preserves {len(active_strategies)} DEMO + LIVE strategies generating signals)")
        print(f"{'=' * 80}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        session.close()

if __name__ == "__main__":
    success = test_retirement_logic()
    sys.exit(0 if success else 1)
