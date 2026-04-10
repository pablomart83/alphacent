"""
Migration: Add fundamental_data_cache table for persistent FMP API caching.

This table stores fundamental data fetched from FMP/Alpha Vantage APIs
to avoid repeated API calls and preserve data across system restarts.
"""

import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """Add fundamental_data_cache table."""
    db_path = Path("alphacent.db")
    
    if not db_path.exists():
        logger.error(f"Database not found at {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='fundamental_data_cache'
        """)
        
        if cursor.fetchone():
            logger.info("Table 'fundamental_data_cache' already exists")
            return True
        
        # Create fundamental_data_cache table
        cursor.execute("""
            CREATE TABLE fundamental_data_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL UNIQUE,
                
                -- Income statement
                eps REAL,
                revenue REAL,
                revenue_growth REAL,
                
                -- Balance sheet
                total_debt REAL,
                total_equity REAL,
                debt_to_equity REAL,
                
                -- Key metrics
                roe REAL,
                pe_ratio REAL,
                market_cap REAL,
                
                -- Insider trading
                insider_net_buying REAL,
                
                -- Share dilution
                shares_outstanding REAL,
                shares_change_percent REAL,
                
                -- Metadata
                source TEXT NOT NULL,
                fetched_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for faster lookups
        cursor.execute("""
            CREATE INDEX idx_fundamental_data_symbol 
            ON fundamental_data_cache(symbol)
        """)
        
        cursor.execute("""
            CREATE INDEX idx_fundamental_data_fetched_at 
            ON fundamental_data_cache(fetched_at)
        """)
        
        conn.commit()
        logger.info("✓ Created table 'fundamental_data_cache' with indexes")
        
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()


if __name__ == '__main__':
    success = migrate()
    if success:
        logger.info("Migration completed successfully")
    else:
        logger.error("Migration failed")
        exit(1)
