#!/usr/bin/env python3
"""
Migration script to create Alpha Edge analytics tables.

This script creates the new database tables for logging:
- Fundamental filter results
- ML filter predictions
- Conviction scores

Run this script once to initialize the tables before using Alpha Edge analytics.
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.database import get_database, init_database

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate():
    """Run migration to create Alpha Edge tables."""
    logger.info("Starting Alpha Edge tables migration...")
    
    try:
        # Initialize database (creates all tables including new ones)
        init_database()
        
        logger.info("✅ Migration completed successfully!")
        logger.info("New tables created:")
        logger.info("  - fundamental_filter_logs")
        logger.info("  - ml_filter_logs")
        logger.info("  - conviction_score_logs")
        logger.info("")
        logger.info("You can now use Alpha Edge analytics with real data.")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    migrate()
