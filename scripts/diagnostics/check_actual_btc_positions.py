#!/usr/bin/env python3
"""Check actual BTC positions on eToro"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.models import TradingMode

def check_positions():
    print("=" * 70)
    print("Checking Actual BTC Positions on eToro")
    print("=" * 70)
    
    # Load credentials
    config = get_config()
    creds = config.load_credentials(TradingMode.DEMO)
    
    client = EToroAPIClient(creds["public_key"], creds["user_key"], TradingMode.DEMO)
    
    # Get all positions
    positions = client.get_positions()
    
    print(f"\nTotal positions: {len(positions)}")
    
    # Filter BTC positions
    btc_positions = [p for p in positions if p.symbol == "BTC"]
    
    if btc_positions:
        print(f"\nBTC Positions: {len(btc_positions)}")
        for pos in btc_positions:
            print(f"\n  Position ID: {pos.etoro_position_id}")
            print(f"  Symbol: {pos.symbol}")
            print(f"  Side: {pos.side.value}")
            print(f"  Quantity: {pos.quantity}")
            print(f"  Entry Price: ${pos.entry_price:,.2f}")
            print(f"  Current Price: ${pos.current_price:,.2f}")
            print(f"  Unrealized P&L: ${pos.unrealized_pnl:,.2f}")
            print(f"  Opened At: {pos.opened_at}")
    else:
        print("\n❌ No BTC positions found!")
    
    # Show all positions for comparison
    print(f"\n{'='*70}")
    print("All Positions:")
    print(f"{'='*70}")
    for pos in positions:
        print(f"  {pos.symbol}: {pos.side.value}, Qty: {pos.quantity}, P&L: ${pos.unrealized_pnl:,.2f}")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    check_positions()
