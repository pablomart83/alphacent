"""Verify if orders in our database actually exist in eToro."""

import sys
sys.path.insert(0, '.')

from src.core.config import Configuration
from src.api.etoro_client import EToroAPIClient
from src.models import TradingMode
from src.models.database import get_database
from src.models.orm import OrderORM
from src.models.enums import OrderStatus

print("=" * 70)
print("Verifying Orders in eToro")
print("=" * 70)

# Get orders from database
db = get_database()
session = db.get_session()
filled_orders = session.query(OrderORM).filter(
    OrderORM.status == OrderStatus.FILLED
).order_by(OrderORM.filled_at.desc()).limit(5).all()

print(f"\nChecking last {len(filled_orders)} FILLED orders from database...")

# Initialize eToro client
config = Configuration()
creds = config.load_credentials(TradingMode.DEMO)
client = EToroAPIClient(
    public_key=creds['public_key'],
    user_key=creds['user_key'],
    mode=TradingMode.DEMO
)

# Get current portfolio from eToro
print("\n1. Getting eToro portfolio...")
portfolio_response = client._make_request(
    method="GET",
    endpoint="/api/v1/trading/info/demo/portfolio"
)

client_portfolio = portfolio_response.get("clientPortfolio", {})
etoro_positions = client_portfolio.get("positions", [])
etoro_orders = client_portfolio.get("orders", [])

print(f"✅ eToro has {len(etoro_positions)} positions and {len(etoro_orders)} pending orders")

# Check each order
print("\n2. Checking if our orders created positions in eToro...")
for order in filled_orders:
    print(f"\n📋 Order {order.id[:8]}...")
    print(f"   Symbol: {order.symbol}")
    print(f"   Side: {order.side.value}")
    print(f"   Quantity: ${order.quantity}")
    print(f"   eToro Order ID: {order.etoro_order_id}")
    print(f"   Filled at: {order.filled_at}")
    
    # Try to get order status from eToro
    if order.etoro_order_id:
        try:
            order_status = client.get_order_status(order.etoro_order_id)
            print(f"   ✅ Found in eToro: Status = {order_status.get('statusID')}")
        except Exception as e:
            print(f"   ⚠️  Could not get order status: {e}")
            print(f"   (This is normal - executed orders may not be queryable)")

# Show current positions
if etoro_positions:
    print(f"\n3. Current eToro Positions:")
    for pos in etoro_positions:
        print(f"\n   Position {pos.get('positionID')}:")
        print(f"      Instrument: {pos.get('instrumentID')}")
        print(f"      Amount: ${pos.get('amount', 0):,.2f}")
        print(f"      Is Buy: {pos.get('isBuy')}")
        print(f"      Open Rate: {pos.get('openRate')}")
        print(f"      Current Rate: {pos.get('currentRate')}")
        print(f"      Net Profit: ${pos.get('netProfit', 0):,.2f}")

session.close()
print("\n" + "=" * 70)
