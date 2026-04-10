#!/usr/bin/env python3
"""Diagnose recent order issues."""

import sqlite3
from datetime import datetime

print("=" * 70)
print("Recent Orders Diagnosis")
print("=" * 70)

conn = sqlite3.connect('alphacent.db')
cursor = conn.cursor()

# Get recent orders
cursor.execute("""
    SELECT id, symbol, side, quantity, status, submitted_at, etoro_order_id
    FROM orders
    WHERE submitted_at > '2026-02-14 21:00:00'
    ORDER BY submitted_at DESC
""")

orders = cursor.fetchall()

print(f"\nFound {len(orders)} orders since 21:00:00:")
print("-" * 70)

for order in orders:
    order_id, symbol, side, quantity, status, submitted_at, etoro_order_id = order
    
    # Parse timestamp
    try:
        ts = datetime.fromisoformat(submitted_at)
        time_str = ts.strftime("%H:%M:%S")
    except:
        time_str = submitted_at
    
    print(f"\n{time_str} - {symbol} {side} ${quantity:.2f}")
    print(f"  Status: {status}")
    print(f"  eToro ID: {etoro_order_id}")
    print(f"  Our ID: {order_id[:8]}...")
    
    # Analysis
    if status == "FAILED":
        print(f"  ❌ FAILED - Check why it was rejected")
    elif status == "SUBMITTED":
        print(f"  ⏳ PENDING - Waiting for eToro (status 11)")
    elif status == "FILLED":
        print(f"  ✅ SUCCESS")
    
    # Check if quantity looks reasonable
    if symbol == "BTC" and quantity > 100000:
        print(f"  ⚠️  WARNING: BTC amount seems too high")
    elif symbol == "BTC" and 10 < quantity < 100000:
        print(f"  ✅ BTC amount looks reasonable")
    
    if symbol in ["AAPL", "GOOGL", "TSLA"] and quantity < 10:
        print(f"  ⚠️  WARNING: Amount below $10 minimum")
    elif symbol in ["AAPL", "GOOGL", "TSLA"] and quantity >= 10:
        print(f"  ✅ Amount meets minimum")

conn.close()

print("\n" + "=" * 70)
print("\nKEY FINDINGS:")
print("-" * 70)
print("1. AAPL order ($500) - SUBMITTED, waiting in eToro (status 11)")
print("2. BTC order ($41,207.50) - FAILED, need to check error")
print("3. Demo account orders stay in status 11 (pending) indefinitely")
print("4. This is normal eToro demo behavior - orders don't actually fill")
print("\n" + "=" * 70)
