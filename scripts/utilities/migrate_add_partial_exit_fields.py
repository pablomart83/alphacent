#!/usr/bin/env python3
"""
Migration script to add partial exit fields to risk_config and positions tables.

Adds to risk_config:
- partial_exit_enabled: Enable partial exits at profit levels
- partial_exit_levels: JSON list of profit levels and exit percentages

Adds to positions:
- partial_exits: JSON list tracking partial exit history
"""

import json
import sqlite3
import sys


def migrate_database(db_path="alphacent.db"):
    """Add partial exit columns to risk_config and positions tables."""
    print(f"Migrating database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # ===== Migrate risk_config table =====
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='risk_config'")
        if cursor.fetchone():
            print("\n📋 Migrating risk_config table...")
            
            # Check current columns
            cursor.execute("PRAGMA table_info(risk_config)")
            columns = [row[1] for row in cursor.fetchall()]
            
            # Add partial_exit_enabled column if it doesn't exist
            if 'partial_exit_enabled' not in columns:
                print("Adding 'partial_exit_enabled' column...")
                cursor.execute("ALTER TABLE risk_config ADD COLUMN partial_exit_enabled INTEGER DEFAULT 0")
                print("✓ Added 'partial_exit_enabled' column (default: 0/False)")
            else:
                print("✓ 'partial_exit_enabled' column already exists")
            
            # Add partial_exit_levels column if it doesn't exist
            if 'partial_exit_levels' not in columns:
                print("Adding 'partial_exit_levels' column...")
                # Default: [{"profit_pct": 0.05, "exit_pct": 0.5}]
                default_levels = json.dumps([{"profit_pct": 0.05, "exit_pct": 0.5}])
                cursor.execute(f"ALTER TABLE risk_config ADD COLUMN partial_exit_levels TEXT DEFAULT '{default_levels}'")
                print("✓ Added 'partial_exit_levels' column (default: 5% profit -> 50% exit)")
            else:
                print("✓ 'partial_exit_levels' column already exists")
        else:
            print("⚠️  risk_config table does not exist, skipping risk_config migration")
        
        # ===== Migrate positions table =====
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='positions'")
        if cursor.fetchone():
            print("\n📋 Migrating positions table...")
            
            # Check current columns
            cursor.execute("PRAGMA table_info(positions)")
            columns = [row[1] for row in cursor.fetchall()]
            
            # Add partial_exits column if it doesn't exist
            if 'partial_exits' not in columns:
                print("Adding 'partial_exits' column...")
                cursor.execute("ALTER TABLE positions ADD COLUMN partial_exits TEXT DEFAULT '[]'")
                print("✓ Added 'partial_exits' column (default: empty list)")
            else:
                print("✓ 'partial_exits' column already exists")
        else:
            print("⚠️  positions table does not exist, skipping positions migration")
        
        conn.commit()
        print("\n✅ Migration completed successfully!")
        print("\nPartial exit fields added:")
        print("  risk_config table:")
        print("    - partial_exit_enabled: Enable/disable partial exits (default: False)")
        print("    - partial_exit_levels: Profit levels and exit percentages (default: 5% -> 50%)")
        print("  positions table:")
        print("    - partial_exits: Track partial exit history (default: [])")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_database()
