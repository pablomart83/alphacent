#!/usr/bin/env python3
"""
Test script to verify pending closures implementation.
"""

from src.models.database import get_database
from src.models.orm import PositionORM, StrategyORM
from src.models.enums import PositionSide, StrategyStatus
from datetime import datetime
from sqlalchemy import text

def test_pending_closures():
    """Test the pending closures functionality."""
    
    print("=" * 70)
    print("Testing Pending Closures Implementation")
    print("=" * 70)
    
    # Get database
    db = get_database("alphacent.db")
    session = db.get_session()
    
    try:
        # 1. Verify columns exist
        print("\n1. Verifying database schema...")
        result = session.execute(text("PRAGMA table_info(positions)"))
        columns = [row[1] for row in result]
        
        assert 'pending_closure' in columns, "pending_closure column missing!"
        assert 'closure_reason' in columns, "closure_reason column missing!"
        print("   ✓ Database schema is correct")
        
        # 2. Test creating a position with pending_closure
        print("\n2. Testing position creation with pending_closure...")
        test_position = PositionORM(
            id="test_pos_001",
            strategy_id="test_strategy",
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=10.0,
            entry_price=150.0,
            current_price=155.0,
            unrealized_pnl=50.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro_123",
            pending_closure=True,
            closure_reason="Test: Strategy retired"
        )
        
        session.add(test_position)
        session.commit()
        print("   ✓ Position created with pending_closure=True")
        
        # 3. Query pending closures
        print("\n3. Querying pending closures...")
        pending = session.query(PositionORM).filter(
            PositionORM.pending_closure == True,
            PositionORM.closed_at.is_(None)
        ).all()
        
        print(f"   ✓ Found {len(pending)} pending closure(s)")
        for pos in pending:
            print(f"     - {pos.symbol}: {pos.closure_reason}")
        
        # 4. Test to_dict() includes new fields
        print("\n4. Testing to_dict() method...")
        pos_dict = test_position.to_dict()
        assert 'pending_closure' in pos_dict, "pending_closure not in to_dict()!"
        assert 'closure_reason' in pos_dict, "closure_reason not in to_dict()!"
        assert pos_dict['pending_closure'] == True
        assert pos_dict['closure_reason'] == "Test: Strategy retired"
        print("   ✓ to_dict() includes new fields correctly")
        
        # 5. Clean up test data
        print("\n5. Cleaning up test data...")
        session.delete(test_position)
        session.commit()
        print("   ✓ Test data cleaned up")
        
        print("\n" + "=" * 70)
        print("✅ All tests passed!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    test_pending_closures()
