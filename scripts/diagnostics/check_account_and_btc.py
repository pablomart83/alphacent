#!/usr/bin/env python3
"""Check account balance and BTC order capability"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.models import TradingMode

def check_account():
    print("=" * 70)
    print("Account Status Check")
    print("=" * 70)
    
    # Load credentials
    config = get_config()
    creds = config.load_credentials(TradingMode.DEMO)
    
    client = EToroAPIClient(creds["public_key"], creds["user_key"], TradingMode.DEMO)
    
    # Get account info
    account = client.get_account_info()
    print(f"\nAccount Balance:")
    print(f"  Balance: ${account.balance:,.2f}")
    print(f"  Buying Power: ${account.buying_power:,.2f}")
    print(f"  Margin Used: ${account.margin_used:,.2f}")
    print(f"  Margin Available: ${account.margin_available:,.2f}")
    print(f"  Daily P&L: ${account.daily_pnl:,.2f}")
    
    # Get current positions
    positions = client.get_positions()
    print(f"\nCurrent Positions: {len(positions)}")
    
    btc_positions = [p for p in positions if p.symbol == "BTC"]
    if btc_positions:
        print(f"\nExisting BTC Positions:")
        for pos in btc_positions:
            print(f"  Position ID: {pos.etoro_position_id}")
            print(f"  Quantity: {pos.quantity}")
            print(f"  Entry Price: ${pos.entry_price:,.2f}")
            print(f"  Current Price: ${pos.current_price:,.2f}")
            print(f"  Unrealized P&L: ${pos.unrealized_pnl:,.2f}")
            print(f"  Side: {pos.side.value}")
    else:
        print(f"\nNo existing BTC positions")
    
    # Check if there's a restriction
    print(f"\n{'='*70}")
    print(f"Checking BTC instrument metadata...")
    print(f"{'='*70}")
    
    try:
        btc_id = client._get_instrument_id("BTC")
        print(f"BTC Instrument ID: {btc_id}")
        
        metadata = client.get_instrument_metadata(btc_id)
        print(f"\nBTC Metadata:")
        print(f"  Max Position Amount: {metadata.get('MaxPositionAmount', 'N/A')}")
        print(f"  Min Position Amount: {metadata.get('MinPositionAmount', 'N/A')}")
        print(f"  Max Leverage: {metadata.get('MaxLeverage', 'N/A')}")
        print(f"  Is Tradeable: {metadata.get('IsTradeable', 'N/A')}")
        print(f"  Allow Buy: {metadata.get('AllowBuy', 'N/A')}")
        print(f"  Allow Sell: {metadata.get('AllowSell', 'N/A')}")
        
    except Exception as e:
        print(f"Error getting BTC metadata: {e}")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    check_account()
