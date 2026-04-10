#!/usr/bin/env python3
"""Test script to diagnose strategies endpoint timeout."""

import time
import sqlite3
from src.models.orm import StrategyORM
from src.models.enums import StrategyStatus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Create database session
engine = create_engine("sqlite:///alphacent.db")
Session = sessionmaker(bind=engine)

def test_query():
    """Test the strategies query directly."""
    print("Testing strategies query...")
    start = time.time()
    
    session = Session()
    try:
        # Same query as the endpoint
        query = session.query(StrategyORM).filter(StrategyORM.status != StrategyStatus.RETIRED.value)
        strategies = query.all()
        
        elapsed = time.time() - start
        print(f"✓ Query completed in {elapsed:.2f}s")
        print(f"✓ Found {len(strategies)} strategies")
        
        # Test conversion to dict
        print("\nTesting to_dict() conversion...")
        start = time.time()
        for i, strategy in enumerate(strategies):
            strategy_dict = strategy.to_dict()
            if i == 0:
                print(f"  Sample strategy keys: {list(strategy_dict.keys())}")
        
        elapsed = time.time() - start
        print(f"✓ Conversion completed in {elapsed:.2f}s")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    test_query()
