#!/usr/bin/env python3
"""
Migration script to add trailing stop-loss fields to risk_config table.

Adds:
- trailing_stop_enabled: Enable trailing stop-loss for profitable positions
- trailing_stop_activation_pct: Profit threshold before trailing activates (default 5%)
- trailing_stop_distance_pct: Trailing distance from current price (default 3%)
"""

import sqlite3
import sys


def migrate_database(db_path="alphacent.db"):
    """Add trailing stop-loss columns to risk_config table."""
    print(f"Migrating database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if risk_config table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='risk_config'")
        if not cursor.fetchone():
            print("⚠️  risk_config table does not exist, skipping migration")
            return
        
        # Check current columns
        cursor.execute("PRAGMA table_info(risk_config)")
        columns = [row[1] for row in cursor.fetchall()]
        
        print(f"Current columns: {columns}")
        
        # Add trailing_stop_enabled column if it doesn't exist
        if 'trailing_stop_enabled' not in columns:
            print("Adding 'trailing_stop_enabled' column...")
            cursor.execute("ALTER TABLE risk_config ADD COLUMN trailing_stop_enabled INTEGER DEFAULT 0")
            print("✓ Added 'trailing_stop_enabled' column (default: 0/False)")
        else:
            print("✓ 'trailing_stop_enabled' column already exists")
        
        # Add trailing_stop_activation_pct column if it doesn't exist
        if 'trailing_stop_activation_pct' not in columns:
            print("Adding 'trailing_stop_activation_pct' column...")
            cursor.execute("ALTER TABLE risk_config ADD COLUMN trailing_stop_activation_pct REAL DEFAULT 0.05")
            print("✓ Added 'trailing_stop_activation_pct' column (default: 0.05 = 5%)")
        else:
            print("✓ 'trailing_stop_activation_pct' column already exists")
        
        # Add trailing_stop_distance_pct column if it doesn't exist
        if 'trailing_stop_distance_pct' not in columns:
            print("Adding 'trailing_stop_distance_pct' column...")
            cursor.execute("ALTER TABLE risk_config ADD COLUMN trailing_stop_distance_pct REAL DEFAULT 0.03")
            print("✓ Added 'trailing_stop_distance_pct' column (default: 0.03 = 3%)")
        else:
            print("✓ 'trailing_stop_distance_pct' column already exists")
        
        conn.commit()
        print("\n✅ Migration completed successfully!")
        print("\nTrailing stop-loss fields added to risk_config table:")
        print("  - trailing_stop_enabled: Enable/disable trailing stops (default: False)")
        print("  - trailing_stop_activation_pct: Profit threshold to activate (default: 5%)")
        print("  - trailing_stop_distance_pct: Distance from current price (default: 3%)")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_database()
