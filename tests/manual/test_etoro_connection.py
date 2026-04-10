#!/usr/bin/env python3
"""Test eToro API connection."""

import json
import logging
from src.api.etoro_client import EToroAPIClient, EToroAPIError
from src.models.enums import TradingMode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_connection():
    """Test eToro API connection."""
    print("=" * 60)
    print("ETORO API CONNECTION TEST")
    print("=" * 60)
    
    # Load credentials
    try:
        with open('config/demo_credentials.json', 'r') as f:
            creds = json.load(f)
            
        print(f"\n✓ Credentials loaded")
        print(f"  Mode: {creds.get('mode')}")
        print(f"  Public Key: {'***' if creds.get('public_key') else 'NOT SET'}")
        print(f"  User Key: {'***' if creds.get('user_key') else 'NOT SET'}")
        
        if not creds.get('public_key') or not creds.get('user_key'):
            print("\n✗ Credentials are empty! Please configure in Settings.")
            return
            
        # Create client
        client = EToroAPIClient(
            public_key=creds['public_key'],
            user_key=creds['user_key'],
            mode=TradingMode.DEMO
        )
        
        print(f"\n✓ Client created")
        
        # Test account info
        print(f"\nTesting get_account_info()...")
        try:
            account_info = client.get_account_info()
            print(f"✓ Account info retrieved:")
            print(f"  Account ID: {account_info.account_id}")
            print(f"  Balance: ${account_info.balance:,.2f}")
            print(f"  Buying Power: ${account_info.buying_power:,.2f}")
            print(f"  Positions: {account_info.positions_count}")
        except EToroAPIError as e:
            print(f"✗ Failed to get account info: {e}")
            print(f"  This is expected if using placeholder credentials")
            
        # Test positions
        print(f"\nTesting get_positions()...")
        try:
            positions = client.get_positions()
            print(f"✓ Positions retrieved: {len(positions)} positions")
            for pos in positions[:3]:
                print(f"  - {pos.symbol}: {pos.quantity} @ ${pos.entry_price}")
        except EToroAPIError as e:
            print(f"✗ Failed to get positions: {e}")
            
        # Test market data
        print(f"\nTesting get_market_data('AAPL')...")
        try:
            market_data = client.get_market_data('AAPL')
            print(f"✓ Market data retrieved:")
            print(f"  Symbol: {market_data.symbol}")
            print(f"  Price: ${market_data.price}")
            print(f"  Source: {market_data.source}")
        except EToroAPIError as e:
            print(f"✗ Failed to get market data: {e}")
            
    except FileNotFoundError:
        print("\n✗ Credentials file not found")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("CONCLUSION")
    print("=" * 60)
    print("""
If you see errors above, it means:
1. eToro credentials are not real/valid
2. eToro API is not accessible
3. You need to configure real eToro API credentials in Settings

The platform will work with real credentials. For testing without
real credentials, you can add seed data to the database.
    """)

if __name__ == '__main__':
    test_connection()
