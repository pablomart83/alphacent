#!/usr/bin/env python3
"""
Emergency database cleanup script.
Removes old retired strategies to fix performance issues.
"""
import sqlite3
from datetime import datetime, timedelta

def cleanup_database():
    conn = sqlite3.connect('alphacent.db')
    cursor = conn.cursor()
    
    # Count current strategies
    cursor.execute("SELECT COUNT(*) FROM strategies")
    total_before = cursor.fetchone()[0]
    print(f"Total strategies before cleanup: {total_before}")
    
    # Count by status
    cursor.execute("SELECT status, COUNT(*) FROM strategies GROUP BY status")
    for status, count in cursor.fetchall():
        print(f"  {status}: {count}")
    
    # Delete RETIRED strategies older than 7 days
    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
    cursor.execute("""
        DELETE FROM strategies 
        WHERE status = 'RETIRED' 
        AND retired_at < ?
    """, (seven_days_ago,))
    deleted_retired = cursor.rowcount
    print(f"\nDeleted {deleted_retired} old RETIRED strategies")
    
    # Keep only the 100 most recent RETIRED strategies
    cursor.execute("""
        DELETE FROM strategies 
        WHERE id IN (
            SELECT id FROM strategies 
            WHERE status = 'RETIRED'
            ORDER BY retired_at DESC
            LIMIT -1 OFFSET 100
        )
    """)
    deleted_excess = cursor.rowcount
    print(f"Deleted {deleted_excess} excess RETIRED strategies (keeping 100 most recent)")
    
    # Count after cleanup
    cursor.execute("SELECT COUNT(*) FROM strategies")
    total_after = cursor.fetchone()[0]
    print(f"\nTotal strategies after cleanup: {total_after}")
    print(f"Freed up: {total_before - total_after} strategies")
    
    conn.commit()
    conn.close()
    
    # Vacuum to reclaim space (must be done outside transaction)
    print("\nVacuuming database to reclaim space...")
    conn = sqlite3.connect('alphacent.db')
    conn.execute("VACUUM")
    conn.close()
    
    print("✓ Database cleanup complete!")

if __name__ == "__main__":
    cleanup_database()
