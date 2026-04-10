"""Diagnose current order state."""

import sys
sys.path.insert(0, '.')

import requests
import json

# Create a session
session = requests.Session()

print("=" * 70)
print("Order Diagnosis")
print("=" * 70)

# Login
print("\n1. Logging in...")
login_response = session.post(
    "http://127.0.0.1:8000/auth/login",
    json={"username": "admin", "password": "admin123"}
)

if login_response.status_code != 200:
    print(f"❌ Login failed")
    exit(1)

print("✅ Login successful")

# Get all orders
print("\n2. Getting all orders...")
orders_response = session.get("http://127.0.0.1:8000/orders?mode=DEMO")

if orders_response.status_code == 200:
    data = orders_response.json()
    print(f"\n📋 Total Orders: {data['total_count']}")
    
    pending = [o for o in data['orders'] if o['status'] == 'PENDING']
    submitted = [o for o in data['orders'] if o['status'] == 'SUBMITTED']
    filled = [o for o in data['orders'] if o['status'] == 'FILLED']
    
    print(f"\n📊 Order Status Breakdown:")
    print(f"   PENDING: {len(pending)}")
    print(f"   SUBMITTED: {len(submitted)}")
    print(f"   FILLED: {len(filled)}")
    
    if pending:
        print(f"\n⏳ PENDING Orders:")
        for order in pending:
            print(f"\n   Order {order['id']}:")
            print(f"      Symbol: {order['symbol']}")
            print(f"      Side: {order['side']}")
            print(f"      Type: {order['order_type']}")
            print(f"      Quantity: {order['quantity']}")
            print(f"      Created: {order['created_at']}")
            print(f"      eToro ID: {order.get('etoro_order_id', 'None')}")
    
    if submitted:
        print(f"\n📤 SUBMITTED Orders:")
        for order in submitted:
            print(f"\n   Order {order['id']}:")
            print(f"      Symbol: {order['symbol']}")
            print(f"      Side: {order['side']}")
            print(f"      Type: {order['order_type']}")
            print(f"      Quantity: {order['quantity']}")
            print(f"      Created: {order['created_at']}")
            print(f"      eToro ID: {order.get('etoro_order_id', 'None')}")
    
    if filled:
        print(f"\n✅ FILLED Orders:")
        for order in filled[:3]:  # Show first 3
            print(f"\n   Order {order['id']}:")
            print(f"      Symbol: {order['symbol']}")
            print(f"      Filled at: {order.get('filled_at', 'N/A')}")

else:
    print(f"❌ Failed: {orders_response.status_code}")
    print(orders_response.text)

# Check eToro portfolio
print(f"\n3. Checking eToro portfolio...")
from src.core.config import Configuration
from src.models import TradingMode
import requests as req
import uuid

config = Configuration()
creds = config.load_credentials(TradingMode.DEMO)

headers = {
    "x-request-id": str(uuid.uuid4()),
    "x-api-key": creds['public_key'],
    "x-user-key": creds['user_key'],
    "Content-Type": "application/json"
}

url = "https://public-api.etoro.com/api/v1/trading/info/demo/portfolio"
response = req.get(url, headers=headers, timeout=30)

if response.status_code == 200:
    data = response.json()
    client_portfolio = data.get("clientPortfolio", {})
    
    positions = client_portfolio.get("positions", [])
    orders = client_portfolio.get("orders", [])
    
    print(f"\n💰 Balance: ${client_portfolio.get('credit', 0):,.2f}")
    print(f"📊 Positions in eToro: {len(positions)}")
    print(f"📋 Pending Orders in eToro: {len(orders)}")
    
    if orders:
        print(f"\n📝 eToro Pending Orders:")
        for order in orders:
            print(f"\n   Order {order.get('orderID')}:")
            print(f"      Instrument: {order.get('instrumentID')}")
            print(f"      Amount: ${order.get('amount', 0):,.2f}")
            print(f"      Type: {order.get('orderType')}")

print(f"\n" + "=" * 70)
