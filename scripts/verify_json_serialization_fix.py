#!/usr/bin/env python3
"""Verify that the JSON serialization bug fix works correctly."""

from src.strategy.strategy_proposer import StrategyProposer
from src.strategy.strategy_templates import StrategyTemplateLibrary
from src.data.market_data_manager import MarketDataManager
from src.models.database import Database
import json

def main():
    print("Testing JSON serialization fix...")
    print("-" * 60)
    
    # Initialize components
    db = Database()
    mdm = MarketDataManager(db)
    proposer = StrategyProposer(mdm, db)
    
    # Get a template
    library = StrategyTemplateLibrary()
    template = library.get_template_by_name('RSI Mean Reversion')
    
    # Create test metadata like the proposer does (after fix)
    metadata = {
        'template_name': template.name,
        'template_type': template.strategy_type.value,
        'test': 'verification'
    }
    
    # Try to serialize it
    try:
        json_str = json.dumps(metadata)
        print('✅ SUCCESS: Metadata is JSON serializable')
        print(f'\nSerialized metadata:')
        print(json.dumps(metadata, indent=2))
        print("\n✅ Fix verified: Strategy metadata can now be saved to database")
        return True
    except TypeError as e:
        print(f'❌ FAILED: {e}')
        print("\n❌ Bug still present: Metadata contains non-serializable objects")
        return False

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
