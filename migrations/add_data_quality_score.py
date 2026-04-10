"""
Migration: Add data_quality_score to fundamental_filter_logs table

This migration adds a data_quality_score column to track the percentage
of critical fundamental data fields that are available for each symbol.
"""

from sqlalchemy import Column, Float, text
from src.models.database import Database
import logging

logger = logging.getLogger(__name__)


def upgrade():
    """Add data_quality_score column to fundamental_filter_logs table."""
    db = Database()
    engine = db.engine
    
    try:
        with engine.connect() as conn:
            # Check if column already exists
            result = conn.execute(text("PRAGMA table_info(fundamental_filter_logs)"))
            columns = [row[1] for row in result]
            
            if 'data_quality_score' not in columns:
                # Add data_quality_score column (0-100 scale)
                conn.execute(text("""
                    ALTER TABLE fundamental_filter_logs 
                    ADD COLUMN data_quality_score FLOAT DEFAULT 0.0
                """))
                conn.commit()
                logger.info("Added data_quality_score column to fundamental_filter_logs table")
            else:
                logger.info("data_quality_score column already exists")
            
    except Exception as e:
        logger.error(f"Error adding data_quality_score column: {e}")
        raise


def downgrade():
    """Remove data_quality_score column from fundamental_filter_logs table."""
    db = Database()
    engine = db.engine
    
    try:
        with engine.connect() as conn:
            # SQLite doesn't support DROP COLUMN directly
            # We would need to recreate the table, but for now just log
            logger.warning("SQLite doesn't support DROP COLUMN - manual migration required")
            
    except Exception as e:
        logger.error(f"Error removing data_quality_score column: {e}")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Running migration: add_data_quality_score")
    upgrade()
    print("Migration complete!")
