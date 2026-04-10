#!/usr/bin/env python3
"""
Migration: Add pending_closure and closure_reason fields to positions table.

This migration adds support for marking positions for closure approval when
strategies are retired.
"""

from sqlalchemy import text
from src.models.database import get_database
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """Add pending_closure and closure_reason columns to positions table."""
    
    # Get database instance
    db = get_database("alphacent.db")
    
    logger.info("Starting migration: add_pending_closure_fields")
    
    try:
        # Add columns using raw SQL (SQLite doesn't support ALTER TABLE ADD COLUMN with defaults easily)
        with db.engine.connect() as conn:
            # Check if columns already exist
            result = conn.execute(text("PRAGMA table_info(positions)"))
            columns = [row[1] for row in result]
            
            if 'pending_closure' not in columns:
                logger.info("Adding pending_closure column...")
                conn.execute(text("ALTER TABLE positions ADD COLUMN pending_closure BOOLEAN NOT NULL DEFAULT 0"))
                conn.commit()
                logger.info("✓ Added pending_closure column")
            else:
                logger.info("pending_closure column already exists")
            
            if 'closure_reason' not in columns:
                logger.info("Adding closure_reason column...")
                conn.execute(text("ALTER TABLE positions ADD COLUMN closure_reason TEXT"))
                conn.commit()
                logger.info("✓ Added closure_reason column")
            else:
                logger.info("closure_reason column already exists")
        
        logger.info("Migration completed successfully")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    migrate()
