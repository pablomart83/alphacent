#!/usr/bin/env python3
"""
Migration script to add strategy_proposals and strategy_retirements tables.
"""

import sqlite3
import sys

def migrate_database(db_path="alphacent.db"):
    """Add strategy_proposals and strategy_retirements tables."""
    print(f"Migrating database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if strategy_proposals table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='strategy_proposals'
        """)
        proposals_exists = cursor.fetchone() is not None
        
        if not proposals_exists:
            print("Creating 'strategy_proposals' table...")
            cursor.execute("""
                CREATE TABLE strategy_proposals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_id TEXT NOT NULL,
                    proposed_at TIMESTAMP NOT NULL,
                    market_regime TEXT NOT NULL,
                    backtest_sharpe REAL,
                    activated INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
                )
            """)
            print("✓ Created 'strategy_proposals' table")
        else:
            print("✓ 'strategy_proposals' table already exists")
        
        # Check if strategy_retirements table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='strategy_retirements'
        """)
        retirements_exists = cursor.fetchone() is not None
        
        if not retirements_exists:
            print("Creating 'strategy_retirements' table...")
            cursor.execute("""
                CREATE TABLE strategy_retirements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_id TEXT NOT NULL,
                    retired_at TIMESTAMP NOT NULL,
                    reason TEXT NOT NULL,
                    final_sharpe REAL,
                    final_return REAL,
                    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
                )
            """)
            print("✓ Created 'strategy_retirements' table")
        else:
            print("✓ 'strategy_retirements' table already exists")
        
        conn.commit()
        print("\n✅ Migration completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()
