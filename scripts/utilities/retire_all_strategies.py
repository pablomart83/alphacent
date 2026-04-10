"""
Script to retire all strategies in the database.

This is useful for cleaning up test strategies created during development.
"""

import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.models.database import Database
from src.models.enums import StrategyStatus
from src.models.orm import StrategyORM

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def retire_all_strategies():
    """Retire all strategies in the database."""
    logger.info("=" * 80)
    logger.info("RETIRING ALL STRATEGIES")
    logger.info("=" * 80)
    
    try:
        # Initialize database
        db = Database()
        session = db.get_session()
        
        # Get all strategies
        all_strategies = session.query(StrategyORM).all()
        logger.info(f"\nFound {len(all_strategies)} strategies in database")
        
        if len(all_strategies) == 0:
            logger.info("No strategies to retire.")
            return
        
        # Count by status
        status_counts = {}
        for strategy in all_strategies:
            status = strategy.status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        logger.info("\nCurrent status breakdown:")
        for status, count in status_counts.items():
            logger.info(f"  {status}: {count}")
        
        # Ask for confirmation
        print("\n" + "=" * 80)
        print(f"WARNING: This will retire ALL {len(all_strategies)} strategies!")
        print("=" * 80)
        response = input("\nAre you sure you want to continue? (yes/no): ")
        
        if response.lower() != 'yes':
            logger.info("Operation cancelled by user.")
            return
        
        # Retire all strategies
        retired_count = 0
        for strategy in all_strategies:
            if strategy.status != StrategyStatus.RETIRED.value:
                strategy.status = StrategyStatus.RETIRED.value
                retired_count += 1
                logger.info(f"  Retired: {strategy.name} (ID: {strategy.id})")
        
        # Commit changes
        session.commit()
        session.close()
        
        logger.info("\n" + "=" * 80)
        logger.info(f"SUCCESS: Retired {retired_count} strategies")
        logger.info("=" * 80)
        
        # Show final status
        session = db.get_session()
        all_strategies = session.query(StrategyORM).all()
        
        status_counts = {}
        for strategy in all_strategies:
            status = strategy.status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        logger.info("\nFinal status breakdown:")
        for status, count in status_counts.items():
            logger.info(f"  {status}: {count}")
        
        session.close()
        
    except Exception as e:
        logger.error(f"\n❌ ERROR: {str(e)}", exc_info=True)
        return False
    
    return True


if __name__ == "__main__":
    success = retire_all_strategies()
    sys.exit(0 if success else 1)
