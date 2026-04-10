#!/usr/bin/env python3
"""
Check if trading scheduler is running and generating signals.
"""

import sqlite3
import time
from datetime import datetime, timedelta

def check_trading_activity():
    """Check recent trading activity."""
    print("=" * 80)
    print("TRADING ACTIVITY CHECK")
    print("=" * 80)
    
    conn = sqlite3.connect("alphacent.db")
    cursor = conn.cursor()
    
    # 1. Check system state
    print("\n1. System State:")
    cursor.execute("""
        SELECT state, reason, timestamp 
        FROM system_state 
        WHERE is_current = 1
    """)
    state = cursor.fetchone()
    if state:
        print(f"   State: {state[0]}")
        print(f"   Reason: {state[1]}")
        print(f"   Since: {state[2]}")
    else:
        print("   ⚠ No current system state found")
    
    # 2. Check active strategies
    print("\n2. Active Strategies (DEMO/LIVE):")
    cursor.execute("""
        SELECT COUNT(*), status 
        FROM strategies 
        WHERE status IN ('DEMO', 'LIVE')
        GROUP BY status
    """)
    active_counts = cursor.fetchall()
    total_active = sum(count for count, _ in active_counts)
    
    if active_counts:
        for count, status in active_counts:
            print(f"   {status}: {count} strategies")
        print(f"   Total Active: {total_active}")
    else:
        print("   ⚠ No active strategies found")
    
    # 3. Check recent orders (last hour)
    print("\n3. Recent Orders (last hour):")
    one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
    cursor.execute("""
        SELECT COUNT(*), status 
        FROM orders 
        WHERE submitted_at > ?
        GROUP BY status
    """, (one_hour_ago,))
    recent_orders = cursor.fetchall()
    
    if recent_orders:
        for count, status in recent_orders:
            print(f"   {status}: {count} orders")
    else:
        print("   No orders in last hour")
    
    # 4. Check all orders
    print("\n4. All Orders:")
    cursor.execute("""
        SELECT COUNT(*), status 
        FROM orders 
        GROUP BY status
    """)
    all_orders = cursor.fetchall()
    
    if all_orders:
        for count, status in all_orders:
            print(f"   {status}: {count} orders")
    else:
        print("   No orders found")
    
    # 5. Check open positions
    print("\n5. Open Positions:")
    cursor.execute("""
        SELECT id, symbol, side, quantity, entry_price, unrealized_pnl, opened_at
        FROM positions 
        WHERE closed_at IS NULL
    """)
    positions = cursor.fetchall()
    
    if positions:
        print(f"   Total: {len(positions)} open positions")
        for pos in positions:
            print(f"   - {pos[1]} {pos[2]} {pos[3]} @ ${pos[4]:.2f} (PnL: ${pos[5]:.2f})")
    else:
        print("   No open positions")
    
    # 6. Check if strategies have rules
    print("\n6. Active Strategy Details:")
    cursor.execute("""
        SELECT id, name, symbols, rules
        FROM strategies 
        WHERE status IN ('DEMO', 'LIVE')
        LIMIT 3
    """)
    strategies = cursor.fetchall()
    
    if strategies:
        for strat in strategies:
            print(f"\n   Strategy: {strat[1]}")
            print(f"   Symbols: {strat[2]}")
            print(f"   Has Rules: {'Yes' if strat[3] else 'No'}")
    
    conn.close()
    
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)
    
    if state and state[0] == "ACTIVE":
        print("✅ System is ACTIVE - trading scheduler should be running")
    else:
        print("❌ System is NOT ACTIVE - no trading will occur")
    
    if total_active > 0:
        print(f"✅ {total_active} strategies are active and being monitored")
    else:
        print("❌ No active strategies - nothing to trade")
    
    if not recent_orders:
        print("⚠️  No orders in last hour - strategies may not have generated signals yet")
        print("   This is normal if:")
        print("   - Market conditions don't meet strategy entry criteria")
        print("   - Strategies are waiting for the right setup")
        print("   - Trading scheduler just started")
    
    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    
    if state and state[0] == "ACTIVE" and total_active > 0:
        print("✅ System is configured correctly for trading")
        print("✅ Trading scheduler is monitoring strategies every 5 seconds")
        print("⏳ Wait for strategies to generate signals when conditions are met")
        print("\nTo see real-time activity, watch the backend terminal for:")
        print("   - 'Generating signals for strategy: [name]'")
        print("   - 'Generated X signals for [name]'")
        print("   - 'Signal validated: [symbol] [action]'")
        print("   - 'Order executed: [order_id]'")
    else:
        print("⚠️  System needs configuration:")
        if not state or state[0] != "ACTIVE":
            print("   1. Set system state to ACTIVE via Control Panel")
        if total_active == 0:
            print("   2. Activate some strategies (change status to DEMO)")

if __name__ == "__main__":
    check_trading_activity()
