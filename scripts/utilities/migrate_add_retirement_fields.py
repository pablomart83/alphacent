#!/usr/bin/env python3
"""
Migration script to add retirement tracking fields to strategies table.

Adds:
- retirement_evaluation_history (JSON)
- live_trade_count (INTEGER)
- last_retirement_evaluation (DATETIME)
- final_drawdown to strategy_retirements table (FLOAT)
"""

import sqlite3
import sys
from pathlib import Path


def migrate_database(db_path: str):
    """
    Add retirement tracking fields to strategies table.
    
    Args:
        db_path: Path to SQLite database file
    """
    print(f"Migrating database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(strategies)")
        columns = {row[1] for row in cursor.fetchall()}
        
        # Add retirement_evaluation_history if not exists
        if "retirement_evaluation_history" not in columns:
            print("Adding retirement_evaluation_history column...")
            cursor.execute("""
                ALTER TABLE strategies 
                ADD COLUMN retirement_evaluation_history TEXT DEFAULT '[]'
            """)
            print("✓ Added retirement_evaluation_history")
        else:
            print("✓ retirement_evaluation_history already exists")
        
        # Add live_trade_count if not exists
        if "live_trade_count" not in columns:
            print("Adding live_trade_count column...")
            cursor.execute("""
                ALTER TABLE strategies 
                ADD COLUMN live_trade_count INTEGER DEFAULT 0
            """)
            print("✓ Added live_trade_count")
        else:
            print("✓ live_trade_count already exists")
        
        # Add last_retirement_evaluation if not exists
        if "last_retirement_evaluation" not in columns:
            print("Adding last_retirement_evaluation column...")
            cursor.execute("""
                ALTER TABLE strategies 
                ADD COLUMN last_retirement_evaluation DATETIME
            """)
            print("✓ Added last_retirement_evaluation")
        else:
            print("✓ last_retirement_evaluation already exists")
        
        # Check strategy_retirements table
        cursor.execute("PRAGMA table_info(strategy_retirements)")
        retirement_columns = {row[1] for row in cursor.fetchall()}
        
        # Add final_drawdown if not exists
        if "final_drawdown" not in retirement_columns:
            print("Adding final_drawdown column to strategy_retirements...")
            cursor.execute("""
                ALTER TABLE strategy_retirements 
                ADD COLUMN final_drawdown REAL
            """)
            print("✓ Added final_drawdown to strategy_retirements")
        else:
            print("✓ final_drawdown already exists in strategy_retirements")
        
        conn.commit()
        print("\n✅ Migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
    
    finally:
        conn.close()


def main():
    """Run migration on all database files."""
    # Find database files
    db_files = [
        "alphacent.db",
        "alphacent_test.db"
    ]
    
    for db_file in db_files:
        db_path = Path(db_file)
        if db_path.exists():
            migrate_database(str(db_path))
            print()
        else:
            print(f"⚠️  Database not found: {db_file}")
            print()


if __name__ == "__main__":
    main()
