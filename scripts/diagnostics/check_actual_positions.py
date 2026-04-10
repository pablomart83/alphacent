#!/usr/bin/env python3
"""Check actual positions in eToro vs our database."""

import sys
sys.path.insert(0, 'src')

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.models.enums import TradingMode
import sqlite3

print("=" * 70)
print("Checking Actual Positions: eToro vs Database")
print("=" * 70)

# Load credentials
config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)

if not credentials or not credentials.get("public_key") or not credentials.get("user_key"):
    print("❌ No eToro credentials configured")
    sys.exit(1)

# Initialize client
client = EToroAPIClient(
    public_key=credentials["public_key"],
    user_key=credentials["user_key"],
    mode=TradingMode.DEMO
)

print("\n1. CHECKING ETORO ACTUAL POSITIONS")
print("-" * 70)

try:
    portfolio_endpoint = "/api/v1/trading/info/demo/portfolio"
    portfolio_data = client._make_request(
        method="GET",
        endpoint=portfolio_endpoint
    )
    
    client_portfolio = portfolio_data.get("clientPortfolio", {})
    positions = client_portfolio.get("positions", [])
    
    if len(positions) == 0:
        print("✅ NO OPEN POSITIONS in eToro")
    else:
        print(f"Found {len(positions)} open positions in eToro:")
        for pos in positions:
            instrument_id = pos.get("instrumentID")
            amount = pos.get("amount")
            net_profit = pos.get("netProfit", 0)
            position_id = pos.get("positionID")
            print(f"\n  Position ID: {position_id}")
            print(f"  Instrument: {instrument_id}")
            print(f"  Amount: ${amount:.2f}")
            print(f"  P&L: ${net_profit:.2f}")
    
except Exception as e:
    print(f"❌ Error checking eToro: {e}")
    import traceback
    traceback.print_exc()

print("\n\n2. CHECKING DATABASE POSITIONS")
print("-" * 70)

conn = sqlite3.connect('alphacent.db')
cursor = conn.cursor()

# Check for open positions in database
cursor.execute("""
    SELECT symbol, side, quantity, entry_price, opened_at, closed_at
    FROM positions
    WHERE closed_at IS NULL OR closed_at = ''
    ORDER BY opened_at DESC
""")

db_positions = cursor.fetchall()

if len(db_positions) == 0:
    print("✅ NO OPEN POSITIONS in database")
else:
    print(f"Found {len(db_positions)} open positions in database:")
    for pos in db_positions:
        symbol, side, quantity, entry_price, opened_at, closed_at = pos
        print(f"\n  Symbol: {symbol}")
        print(f"  Side: {side}")
        print(f"  Quantity: {quantity}")
        print(f"  Entry Price: ${entry_price:.2f}")
        print(f"  Opened: {opened_at}")
        print(f"  Closed: {closed_at if closed_at else 'STILL OPEN'}")

conn.close()

print("\n\n3. ANALYSIS")
print("-" * 70)

if len(positions) == 0 and len(db_positions) == 0:
    print("✅ GOOD: No positions in eToro or database")
elif len(positions) == 0 and len(db_positions) > 0:
    print("⚠️  MISMATCH: Database shows open positions but eToro doesn't")
    print("   → Database is out of sync")
    print("   → These positions should be marked as closed")
elif len(positions) > 0 and len(db_positions) == 0:
    print("⚠️  MISMATCH: eToro has positions but database doesn't")
    print("   → Need to sync from eToro")
else:
    print("ℹ️  Both have positions - checking if they match...")

print("\n" + "=" * 70)
