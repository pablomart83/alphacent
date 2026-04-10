"""Check eToro trade history to see executed orders."""

import sys
sys.path.insert(0, '.')

from src.core.config import Configuration
from src.api.etoro_client import EToroAPIClient
from src.models import TradingMode
import requests
import uuid

print("=" * 70)
print("Checking eToro Trade History")
print("=" * 70)

# Initialize eToro client
config = Configuration()
creds = config.load_credentials(TradingMode.DEMO)

headers = {
    "x-request-id": str(uuid.uuid4()),
    "x-api-key": creds['public_key'],
    "x-user-key": creds['user_key'],
    "Content-Type": "application/json"
}

# Try to get trade history
print("\n1. Attempting to get trade history...")
url = "https://public-api.etoro.com/api/v1/trading/info/demo/trade/history"

try:
    response = requests.get(url, headers=headers, timeout=30)
    print(f"Response status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ Trade history retrieved")
        print(f"Raw response: {data}")
        
        # Try to parse trades
        trades = data.get("trades", []) or data.get("Trades", []) or data.get("clientPortfolio", {}).get("trades", [])
        print(f"\nFound {len(trades)} trades")
        
        if trades:
            print("\n📊 Recent Trades:")
            for trade in trades[:10]:
                print(f"\n   Trade:")
                for key, value in trade.items():
                    print(f"      {key}: {value}")
    else:
        print(f"❌ Failed: {response.status_code}")
        print(f"Response: {response.text}")
        
except Exception as e:
    print(f"❌ Error: {e}")

# Also check PnL endpoint for realized profits
print("\n\n2. Checking PnL data...")
url = "https://public-api.etoro.com/api/v1/trading/info/demo/pnl"

try:
    response = requests.get(url, headers=headers, timeout=30)
    print(f"Response status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ PnL data retrieved:")
        print(f"{data}")
    else:
        print(f"❌ Failed: {response.status_code}")
        
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "=" * 70)
