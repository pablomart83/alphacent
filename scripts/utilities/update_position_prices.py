#!/usr/bin/env python3
"""
Update position current prices to simulate P&L for testing.
This adds a small random variation to show P&L percentages.
"""

import sqlite3
import random

def update_prices():
    """Update current prices with small variations."""
    conn = sqlite3.connect('alphacent.db')
    cursor = conn.cursor()
    
    # Get all open positions
    cursor.execute("SELECT id, symbol, entry_price, side FROM positions WHERE closed_at IS NULL")
    positions = cursor.fetchall()
    
    print(f"Updating prices for {len(positions)} positions...")
    
    for position_id, symbol, entry_price, side in positions:
        # Add a random variation between -5% and +5%
        variation = random.uniform(-0.05, 0.05)
        current_price = entry_price * (1 + variation)
        
        # Calculate P&L based on side
        if side == 'LONG':
            unrealized_pnl = (current_price - entry_price) * 100  # Assuming 100 units for simplicity
        else:
            unrealized_pnl = (entry_price - current_price) * 100
        
        # Update the position
        cursor.execute(
            "UPDATE positions SET current_price = ?, unrealized_pnl = ? WHERE id = ?",
            (current_price, unrealized_pnl, position_id)
        )
        
        pnl_percent = ((current_price - entry_price) / entry_price) * 100
        print(f"  {symbol}: ${entry_price:.2f} → ${current_price:.2f} ({pnl_percent:+.2f}%)")
    
    conn.commit()
    conn.close()
    
    print(f"\nUpdated {len(positions)} positions with simulated price changes")
    print("Done!")

if __name__ == "__main__":
    update_prices()
