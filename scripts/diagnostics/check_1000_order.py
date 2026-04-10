"""Check the $1000 order in detail."""

import sys
sys.path.insert(0, '.')

from src.models.database import get_database
from src.models.orm import OrderORM
from src.core.config import Configuration
from src.models import TradingMode
import requests
import uuid

print("=" * 70)
print("Checking $1000 Order")
print("=" * 70)

# Get the $1000 order from database
db = get_database()
session = db.get_session()
order = session.query(OrderORM).filter(
    OrderORM.id == "359f3a64-0dbe-49f5-8901-636d78535cde"
).first()

if order:
    print(f"\n📋 Order in Database:")
    print(f"   ID: {order.id}")
    print(f"   Symbol: {order.symbol}")
    print(f"   Side: {order.side.value}")
    print(f"   Quantity: ${order.quantity}")
    print(f"   Status: {order.status.value}")
    print(f"   eToro Order ID: {order.etoro_order_id}")
    print(f"   Submitted: {order.submitted_at}")
else:
    print("\n❌ Order not found in database")
    session.close()
    exit(1)

# Check in eToro
if order.etoro_order_id:
    print(f"\n🔍 Checking in eToro (Order ID: {order.etoro_order_id})...")
    
    config = Configuration()
    creds = config.load_credentials(TradingMode.DEMO)
    
    headers = {
        "x-request-id": str(uuid.uuid4()),
        "x-api-key": creds['public_key'],
        "x-user-key": creds['user_key'],
        "Content-Type": "application/json"
    }
    
    url = f"https://public-api.etoro.com/api/v1/trading/info/demo/orders/{order.etoro_order_id}"
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ Found in eToro!")
            print(f"   Status ID: {data.get('statusID')}")
            print(f"   Amount: ${data.get('amount')}")
            print(f"   Error Code: {data.get('errorCode', 0)}")
            if data.get('errorMessage'):
                print(f"   Error Message: {data.get('errorMessage')}")
            print(f"\n   Full response: {data}")
        else:
            print(f"\n❌ Not found in eToro (status {response.status_code})")
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"\n❌ Error checking eToro: {e}")
else:
    print(f"\n⚠️  No eToro order ID - order may not have been submitted")

session.close()
print("\n" + "=" * 70)
