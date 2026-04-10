#!/usr/bin/env python3
"""Clean up strategies with non-tradeable symbols."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.models.database import get_database
from src.models.orm import StrategyORM
from src.core.tradeable_instruments import is_tradeable
from src.models.enums import TradingMode, StrategyStatus
import json

db = get_database()
session = db.get_session()

try:
    # Get all non-retired strategies
    strategies = session.query(StrategyORM).filter(
        StrategyORM.status != StrategyStatus.RETIRED
    ).all()
    
    print(f"Checking {len(strategies)} strategies for non-tradeable symbols...")
    
    invalid_count = 0
    for strategy in strategies:
        symbols = strategy.symbols if isinstance(strategy.symbols, list) else json.loads(strategy.symbols or "[]")
        
        # Check if any symbol is not tradeable
        invalid_symbols = [s for s in symbols if not is_tradeable(s, TradingMode.DEMO)]
        
        if invalid_symbols:
            print(f"  Retiring: {strategy.name} (invalid symbols: {invalid_symbols})")
            strategy.status = StrategyStatus.RETIRED
            invalid_count += 1
    
    session.commit()
    print(f"\n✅ Retired {invalid_count} strategies with non-tradeable symbols")
    
except Exception as e:
    print(f"❌ Error: {e}")
    session.rollback()
finally:
    session.close()
