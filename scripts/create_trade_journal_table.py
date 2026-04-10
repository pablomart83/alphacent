"""Create trade_journal table in the database."""

import logging
from sqlalchemy import inspect
from src.models.database import get_database
from src.analytics.trade_journal import TradeJournalEntryORM

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_trade_journal_table():
    """Create the trade_journal table if it doesn't exist."""
    try:
        # Get database instance
        db = get_database()
        
        # Check if table exists
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()
        
        if 'trade_journal' in existing_tables:
            logger.info("trade_journal table already exists")
            return
        
        # Create the table
        logger.info("Creating trade_journal table...")
        TradeJournalEntryORM.__table__.create(db.engine)
        logger.info("✓ trade_journal table created successfully")
        
    except Exception as e:
        logger.error(f"Failed to create trade_journal table: {e}")
        raise


if __name__ == "__main__":
    create_trade_journal_table()
