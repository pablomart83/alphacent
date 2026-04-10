"""Check the GOOGL order status."""

import sys
sys.path.insert(0, '.')

from src.core.config import Configuration
from src.api.etoro_client import EToroAPIClient
from src.models import TradingMode
from src.models.database import get_database
from src.models.orm import OrderORM
import requests
import uuid

print("=" * 70)
print("Checking GOOGL Order")
print("=" * 70)

# Get the GOOGL order from database
db = get_database()
session = db.get_session()
googl_order = session.query(OrderORM).filter(
    OrderORM.id == "af01b6f5-d352-41dc-a68d-0b0cd3242ca9"
).first()

if googl_order:
    print(f"\n📋 GOOGL Order in Database:")
    print(f"   ID: {googl_order.id}")
    print(f"   Symbol: {googl_order.symbol}")
    print(f"   Side: {googl_order.side.value}")
    print(f"   Quantity: ${googl_order.quantity}")
    print(f"   Status: {googl_order.status.value}")
    print(f"   eToro Order ID: {googl_order.etoro_order_id}")
    print(f"   Submitted: {googl_order.submitted_at}")
    print(f"   Filled: {googl_order.filled_at}")
else:
    print("\n❌ GOOGL order not found in database")
    session.close()
    exit(1)

# Initialize eToro client
config = Configuration()
creds = config.load_credentials(TradingMode.DEMO)

headers = {
    "x-request-id": str(uuid.uuid4()),
    "x-api-key": creds['public_key'],
    "x-user-key": creds['user_key'],
    "Content-Type": "application/json"
}

# Check order status in eToro
print(f"\n1. Checking order status in eToro...")
etoro_order_id = googl_order.etoro_order_id

if etoro_order_id:
    url = f"https://public-api.etoro.com/api/v1/trading/info/demo/orders/{etoro_order_id}"
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        print(f"   Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Order found in eToro:")
            print(f"   Status ID: {data.get('statusID')}")
            print(f"   Full response: {data}")
        else:
            print(f"   ⚠️  Response: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

# Check portfolio for pending orders
print(f"\n2. Checking eToro portfolio for pending orders...")
url = "https://public-api.etoro.com/api/v1/trading/info/demo/portfolio"

try:
    response = requests.get(url, headers=headers, timeout=30)
    
    if response.status_code == 200:
        data = response.json()
        client_portfolio = data.get("clientPortfolio", {})
        
        # Check ordersForOpen
        orders_for_open = client_portfolio.get("ordersForOpen", [])
        print(f"   Found {len(orders_for_open)} orders in ordersForOpen")
        
        # Look for our GOOGL order
        googl_found = False
        for order in orders_for_open:
            if str(order.get('orderID')) == str(etoro_order_id):
                googl_found = True
                print(f"\n   ✅ GOOGL Order Found!")
                print(f"      Order ID: {order.get('orderID')}")
                print(f"      Instrument ID: {order.get('instrumentID')}")
                print(f"      Amount: ${order.get('amount')}")
                print(f"      Status ID: {order.get('statusID')}")
                print(f"      Is Buy: {order.get('isBuy')}")
                print(f"      Open DateTime: {order.get('openDateTime')}")
                print(f"      Last Update: {order.get('lastUpdate')}")
        
        if not googl_found:
            print(f"\n   ⚠️  GOOGL order {etoro_order_id} not found in ordersForOpen")
            print(f"   This could mean:")
            print(f"      - Order already executed and became a position")
            print(f"      - Order was cancelled")
            print(f"      - Order is in a different array")
        
        # Check positions
        positions = client_portfolio.get("positions", [])
        print(f"\n   Checking {len(positions)} positions for GOOGL...")
        for pos in positions:
            instrument_id = pos.get('instrumentID')
            # GOOGL is instrument 1002
            if instrument_id == 1002:
                print(f"\n   ✅ Found GOOGL Position!")
                print(f"      Position ID: {pos.get('positionID')}")
                print(f"      Amount: ${pos.get('amount')}")
                print(f"      Open Rate: {pos.get('openRate')}")
                print(f"      Current Rate: {pos.get('currentRate')}")
                
except Exception as e:
    print(f"   ❌ Error: {e}")

session.close()
print("\n" + "=" * 70)
