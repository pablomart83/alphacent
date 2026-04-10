"""
Migration: Fix SHORT strategy direction metadata

Problem: Strategies with "Short" in their name were not properly marked with
direction='short' in their metadata, causing them to generate LONG signals
instead of SHORT signals.

This migration:
1. Finds all strategies with "Short" in the name
2. Updates their metadata to include direction='short'
3. Logs the changes

Run: python migrations/fix_short_strategy_direction.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.database import get_database
from src.models.orm import StrategyORM
from datetime import datetime


def fix_short_strategy_direction():
    """Fix direction metadata for SHORT strategies."""
    db = get_database()
    session = db.get_session()
    
    try:
        # Find all strategies with "Short" in the name
        strategies = session.query(StrategyORM).filter(
            StrategyORM.name.like('%Short%')
        ).all()
        
        print(f"Found {len(strategies)} strategies with 'Short' in name")
        print("=" * 80)
        
        updated_count = 0
        already_correct = 0
        
        for strategy in strategies:
            # Initialize metadata if None or empty
            if strategy.strategy_metadata is None or strategy.strategy_metadata == {}:
                strategy.strategy_metadata = {'direction': 'short'}
                print(f"✅ {strategy.name[:60]:60s} | Fixed: None/empty → short")
                updated_count += 1
            else:
                # Check current direction
                current_direction = strategy.strategy_metadata.get('direction')
                
                if current_direction == 'short':
                    print(f"✓ {strategy.name[:60]:60s} | Already correct")
                    already_correct += 1
                else:
                    # Update to short
                    strategy.strategy_metadata['direction'] = 'short'
                    print(f"✅ {strategy.name[:60]:60s} | Fixed: {current_direction} → short")
                    updated_count += 1
        
        # Commit changes
        session.commit()
        
        print("=" * 80)
        print(f"\nMigration complete:")
        print(f"  Total strategies checked: {len(strategies)}")
        print(f"  Already correct: {already_correct}")
        print(f"  Updated: {updated_count}")
        
        if updated_count > 0:
            print(f"\n⚠️  IMPORTANT: Restart any running trading processes to pick up the changes.")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error during migration: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    print("SHORT Strategy Direction Fix Migration")
    print("=" * 80)
    print(f"Started at: {datetime.now().isoformat()}")
    print()
    
    fix_short_strategy_direction()
    
    print()
    print(f"Completed at: {datetime.now().isoformat()}")
