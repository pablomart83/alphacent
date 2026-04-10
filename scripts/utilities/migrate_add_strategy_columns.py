#!/usr/bin/env python3
"""
Migration script to add reasoning and backtest_results columns to strategies table.
"""

import sqlite3
import sys

def migrate_database(db_path="alphacent.db"):
    """Add new columns to strategies table."""
    print(f"Migrating database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(strategies)")
        columns = [row[1] for row in cursor.fetchall()]
        
        print(f"Current columns: {columns}")
        
        # Add reasoning column if it doesn't exist
        if 'reasoning' not in columns:
            print("Adding 'reasoning' column...")
            cursor.execute("ALTER TABLE strategies ADD COLUMN reasoning TEXT")
            print("✓ Added 'reasoning' column")
        else:
            print("✓ 'reasoning' column already exists")
        
        # Add backtest_results column if it doesn't exist
        if 'backtest_results' not in columns:
            print("Adding 'backtest_results' column...")
            cursor.execute("ALTER TABLE strategies ADD COLUMN backtest_results TEXT")
            print("✓ Added 'backtest_results' column")
        else:
            print("✓ 'backtest_results' column already exists")
        
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
