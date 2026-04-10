"""Test fetching full portfolio data from eToro."""

import sys
sys.path.insert(0, '.')

from src.core.config import Configuration
from src.models import TradingMode
import requests
import uuid
import json

config = Configuration()
creds = config.load_credentials(TradingMode.DEMO)

headers = {
    "x-request-id": str(uuid.uuid4()),
    "x-api-key": creds['public_key'],
    "x-user-key": creds['user_key'],
    "Content-Type": "application/json"
}

print("=" * 70)
print("eToro Portfolio Data")
print("=" * 70)

url = "https://public-api.etoro.com/api/v1/trading/info/demo/portfolio"

try:
    response = requests.get(url, headers=headers, timeout=30)
    if response.status_code == 200:
        data = response.json()
        portfolio = data.get("clientPortfolio", {})
        
        print(f"\n💰 Account Info:")
        print(f"   Balance: ${portfolio.get('credit', 0):,.2f}")
        print(f"   Equity: ${portfolio.get('equity', 0):,.2f}")
        print(f"   Available to Trade: ${portfolio.get('availableToTrade', 0):,.2f}")
        print(f"   Total Profit/Loss: ${portfolio.get('totalProfitLoss', 0):,.2f}")
        
        positions = portfolio.get("positions", [])
        print(f"\n📊 Positions ({len(positions)}):")
        for pos in positions:
            print(f"\n   Position {pos.get('positionID')}:")
            print(f"      Instrument: {pos.get('instrumentID')}")
            print(f"      Direction: {'BUY' if pos.get('isBuy') else 'SELL'}")
            print(f"      Amount: ${pos.get('amount', 0):,.2f}")
            print(f"      Units: {pos.get('units', 0):.4f}")
            print(f"      Open Rate: ${pos.get('openRate', 0):,.2f}")
            print(f"      Current Rate: ${pos.get('currentRate', 0):,.2f}")
            print(f"      Net Profit: ${pos.get('netProfit', 0):,.2f}")
            print(f"      Profit %: {pos.get('profitPercentage', 0):.2f}%")
            print(f"      Stop Loss: {pos.get('stopLossRate') if not pos.get('isNoStopLoss') else 'None'}")
            print(f"      Take Profit: {pos.get('takeProfitRate') if not pos.get('isNoTakeProfit') else 'None'}")
            print(f"      Opened: {pos.get('openDateTime')}")
        
        orders = portfolio.get("orders", [])
        print(f"\n📋 Pending Orders ({len(orders)}):")
        for order in orders:
            print(f"\n   Order {order.get('orderID')}:")
            print(f"      Instrument: {order.get('instrumentID')}")
            print(f"      Direction: {'BUY' if order.get('isBuy') else 'SELL'}")
            print(f"      Amount: ${order.get('amount', 0):,.2f}")
            print(f"      Status: {order.get('statusID')}")
            print(f"      Type: {order.get('orderType')}")
            
        print(f"\n📄 Full JSON:")
        print(json.dumps(data, indent=2))
        
    else:
        print(f"❌ Failed: {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
