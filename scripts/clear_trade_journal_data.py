"""Clear all trade journal data from the database."""

import logging
from sqlalchemy import text
from src.models.database import get_database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clear_trade_journal_data():
    """Clear all entries from the trade_journal table."""
    try:
        db = get_database()
        session = db.get_session()
        
        try:
            # Count existing entries
            result = session.execute(text("SELECT COUNT(*) FROM trade_journal"))
            count = result.scalar()
            
            if count == 0:
                logger.info("Trade journal is already empty")
                return
            
            logger.info(f"Found {count} trade journal entries")
            
            # Delete all entries
            session.execute(text("DELETE FROM trade_journal"))
            session.commit()
            
            logger.info(f"✓ Successfully cleared {count} trade journal entries")
            logger.info("Trade journal is now empty and ready for production use")
            
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Failed to clear trade journal data: {e}")
        raise


if __name__ == "__main__":
    clear_trade_journal_data()
