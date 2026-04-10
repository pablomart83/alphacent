"""
Database migration for Task 6: Reduce Trading Frequency

Adds the rejected_signals table for tracking rejected signals.

Run this manually with:
    python3 -c "from src.models.database import get_database; from src.models.orm import Base, RejectedSignalORM; db = get_database(); Base.metadata.create_all(db.engine, tables=[RejectedSignalORM.__table__]); print('Migration complete!')"

Or import and call migrate() from your application startup.
"""

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """Run database migration for Task 6."""
    logger.info("Starting Task 6 database migration...")
    
    try:
        from src.models.database import get_database
        from src.models.orm import Base, RejectedSignalORM
        
        # Get database instance
        db = get_database()
        
        # Create rejected_signals table
        logger.info("Creating rejected_signals table...")
        Base.metadata.create_all(db.engine, tables=[RejectedSignalORM.__table__])
        
        logger.info("✓ Migration completed successfully!")
        logger.info("  - rejected_signals table created")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Migration failed: {e}")
        return False


if __name__ == "__main__":
    success = migrate()
    exit(0 if success else 1)
