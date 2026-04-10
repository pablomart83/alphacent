#!/usr/bin/env python3
"""
Fix historical position symbols.

Updates positions with ID_* symbols to their normalized form.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.database import Database
from src.models.orm import PositionORM
from src.utils.symbol_normalizer import normalize_symbol

def main():
    print("=" * 80)
    print("FIX HISTORICAL POSITION SYMBOLS")
    print("=" * 80)
    print()
    
    db = Database()
    session = db.get_session()
    
    try:
        # Find all positions with ID_* symbols
        bad_positions = session.query(PositionORM).filter(
            PositionORM.symbol.like('ID_%')
        ).all()
        
        print(f"Found {len(bad_positions)} positions with ID_* symbols")
        print()
        
        if not bad_positions:
            print("✅ No positions need fixing!")
            return
        
        # Group by symbol
        by_symbol = {}
        for pos in bad_positions:
            if pos.symbol not in by_symbol:
                by_symbol[pos.symbol] = []
            by_symbol[pos.symbol].append(pos)
        
        print("Positions to fix:")
        for symbol, positions in by_symbol.items():
            normalized = normalize_symbol(symbol)
            print(f"  {symbol} → {normalized}: {len(positions)} positions")
        
        print()
        response = input("Fix these positions? (yes/no): ")
        if response.lower() != 'yes':
            print("Cancelled")
            return
        
        print()
        print("Fixing positions...")
        fixed_count = 0
        
        for pos in bad_positions:
            old_symbol = pos.symbol
            new_symbol = normalize_symbol(old_symbol)
            
            if old_symbol != new_symbol:
                pos.symbol = new_symbol
                fixed_count += 1
                print(f"  ✅ Position {pos.id}: {old_symbol} → {new_symbol}")
        
        session.commit()
        
        print()
        print("=" * 80)
        print(f"✅ Fixed {fixed_count} positions")
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
