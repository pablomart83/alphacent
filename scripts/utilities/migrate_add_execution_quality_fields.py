"""
Database migration: Add execution quality tracking fields to orders table.

Adds:
- expected_price: Expected price at order creation
- slippage: Calculated slippage (filled_price - expected_price)
- fill_time_seconds: Time from submission to fill in seconds
"""

import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_add_execution_quality_fields(db_path: str = "alphacent.db"):
    """
    Add execution quality tracking fields to orders table.
    
    Args:
        db_path: Path to SQLite database file
    """
    logger.info(f"Starting migration: Add execution quality fields to orders table")
    logger.info(f"Database: {db_path}")
    
    # Check if database exists
    if not Path(db_path).exists():
        logger.error(f"Database not found: {db_path}")
        return False
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(orders)")
        columns = [row[1] for row in cursor.fetchall()]
        
        migrations_needed = []
        if "expected_price" not in columns:
            migrations_needed.append("expected_price")
        if "slippage" not in columns:
            migrations_needed.append("slippage")
        if "fill_time_seconds" not in columns:
            migrations_needed.append("fill_time_seconds")
        
        if not migrations_needed:
            logger.info("All execution quality fields already exist - no migration needed")
            conn.close()
            return True
        
        logger.info(f"Adding columns: {', '.join(migrations_needed)}")
        
        # Add expected_price column
        if "expected_price" in migrations_needed:
            cursor.execute("""
                ALTER TABLE orders
                ADD COLUMN expected_price REAL
            """)
            logger.info("Added expected_price column")
        
        # Add slippage column
        if "slippage" in migrations_needed:
            cursor.execute("""
                ALTER TABLE orders
                ADD COLUMN slippage REAL
            """)
            logger.info("Added slippage column")
        
        # Add fill_time_seconds column
        if "fill_time_seconds" in migrations_needed:
            cursor.execute("""
                ALTER TABLE orders
                ADD COLUMN fill_time_seconds REAL
            """)
            logger.info("Added fill_time_seconds column")
        
        # Commit changes
        conn.commit()
        
        # Verify columns were added
        cursor.execute("PRAGMA table_info(orders)")
        columns_after = [row[1] for row in cursor.fetchall()]
        
        success = all(col in columns_after for col in ["expected_price", "slippage", "fill_time_seconds"])
        
        if success:
            logger.info("✅ Migration completed successfully")
            logger.info(f"Orders table now has {len(columns_after)} columns")
        else:
            logger.error("❌ Migration failed - columns not added")
        
        conn.close()
        return success
        
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    import sys
    
    db_path = sys.argv[1] if len(sys.argv) > 1 else "alphacent.db"
    success = migrate_add_execution_quality_fields(db_path)
    
    if success:
        print("\n✅ Migration completed successfully")
        sys.exit(0)
    else:
        print("\n❌ Migration failed")
        sys.exit(1)
