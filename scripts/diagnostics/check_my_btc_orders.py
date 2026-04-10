#!/usr/bin/env python3
"""Check status of my test BTC orders"""

import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.models import TradingMode

def check_orders():
    print("=" * 70)
    print("Checking My Test BTC Orders")
    print("=" * 70)
    
    # Load credentials
    config = get_config()
    creds = config.load_credentials(TradingMode.DEMO)
    
    client = EToroAPIClient(creds["public_key"], creds["user_key"], TradingMode.DEMO)
    
    # My test order IDs from the previous tests
    test_order_ids = [
        "328122449",  # $10,000 from test_btc_limits.py
        "328093528",  # $10,000 from vibe coding test
        "328093529",  # $10,000 from direct API test
        "328093530",  # $698M from "10000 units" test
    ]
    
    for order_id in test_order_ids:
        print(f"\nChecking order {order_id}...")
        try:
            status = client.get_order_status(order_id)
            etoro_status = status.get('Status')
            error_code = status.get('ErrorCode')
            error_msg = status.get('ErrorMessage')
            
            if error_code and error_code != 0:
                print(f"  ❌ FAILED - Status: {etoro_status}, Error {error_code}: {error_msg}")
            else:
                print(f"  ✅ OK - Status: {etoro_status}")
                
        except Exception as e:
            print(f"  ❌ Error checking: {e}")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    check_orders()
