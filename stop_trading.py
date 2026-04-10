#!/usr/bin/env python3
"""
Emergency stop script - retire all active strategies and stop autonomous trading.
"""
import sqlite3
from datetime import datetime

def stop_all_trading():
    conn = sqlite3.connect('alphacent.db')
    cursor = conn.cursor()
    
    # Count active strategies
    cursor.execute("SELECT COUNT(*) FROM strategies WHERE status != 'RETIRED'")
    active_count = cursor.fetchone()[0]
    print(f"Found {active_count} active strategies")
    
    # Retire all non-retired strategies
    now = datetime.now().isoformat()
    cursor.execute("""
        UPDATE strategies 
        SET status = 'RETIRED', retired_at = ?
        WHERE status != 'RETIRED'
    """, (now,))
    retired_count = cursor.rowcount
    print(f"✓ Retired {retired_count} strategies")
    
    # Set system state to STOPPED
    cursor.execute("""
        UPDATE system_state 
        SET state = 'STOPPED', 
            reason = 'Emergency stop - all strategies retired',
            timestamp = ?,
            is_current = 1
        WHERE is_current = 1
    """, (now,))
    print(f"✓ System state set to STOPPED")
    
    # Add state transition record
    cursor.execute("""
        INSERT INTO state_transition_history 
        (from_state, to_state, reason, timestamp, initiated_by, active_strategies_count, open_positions_count)
        VALUES ('ACTIVE', 'STOPPED', 'Emergency stop - all strategies retired', ?, 'admin', 0, 0)
    """, (now,))
    print(f"✓ State transition recorded")
    
    conn.commit()
    conn.close()
    
    print("\n✓ All trading stopped successfully!")
    print("You can now restart the backend safely.")

if __name__ == "__main__":
    stop_all_trading()
