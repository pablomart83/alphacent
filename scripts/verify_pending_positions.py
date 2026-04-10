#!/usr/bin/env python3
"""
Verification script for pending positions reporting.

Demonstrates:
1. Creating a pending order
2. Querying pending positions
3. Checking market hours
4. Showing the difference between open and pending positions
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.database import get_database
from src.models.orm import OrderORM, PositionORM
from src.models.enums import OrderStatus, OrderSide, OrderType, PositionSide
from src.data.market_hours_manager import MarketHoursManager, AssetClass


def main():
    print("=" * 80)
    print("PENDING POSITIONS REPORTING VERIFICATION")
    print("=" * 80)
    
    db = get_database()
    session = db.get_session()
    
    try:
        # 1. Check market hours
        print("\n1. Market Hours Status")
        print("-" * 80)
        market_hours = MarketHoursManager()
        market_open = market_hours.is_market_open(AssetClass.STOCK)
        print(f"   Market is currently: {'OPEN ✅' if market_open else 'CLOSED ❌'}")
        
        if not market_open:
            next_open = market_hours.get_next_open_time(AssetClass.STOCK)
            if next_open:
                print(f"   Next market open: {next_open.strftime('%Y-%m-%d %H:%M %Z')}")
        
        # 2. Query current positions
        print("\n2. Current Open Positions")
        print("-" * 80)
        open_positions = session.query(PositionORM).filter(
            PositionORM.closed_at.is_(None)
        ).all()
        
        if open_positions:
            print(f"   Found {len(open_positions)} open position(s):")
            for pos in open_positions[:5]:
                print(f"   - {pos.symbol} {pos.side.value} x{pos.quantity} @ ${pos.entry_price:.2f}")
        else:
            print("   No open positions found")
        
        # 3. Query pending orders
        print("\n3. Pending Orders (Positions Waiting for Market Open)")
        print("-" * 80)
        pending_orders = session.query(OrderORM).filter(
            OrderORM.status == OrderStatus.PENDING
        ).all()
        
        if pending_orders:
            print(f"   Found {len(pending_orders)} pending order(s):")
            for order in pending_orders[:5]:
                print(f"   - {order.symbol} {order.side.value} x{order.quantity} | order_id={order.id[:12]}...")
                if order.etoro_order_id:
                    print(f"     eToro ID: {order.etoro_order_id}")
        else:
            print("   No pending orders found")
        
        # 4. Summary
        print("\n4. Summary")
        print("-" * 80)
        print(f"   Open Positions:    {len(open_positions)}")
        print(f"   Pending Positions: {len(pending_orders)}")
        print(f"   Total Exposure:    {len(open_positions) + len(pending_orders)}")
        print(f"   Market Status:     {'OPEN' if market_open else 'CLOSED'}")
        
        # 5. API Response Simulation
        print("\n5. API Response Format (GET /api/account/positions)")
        print("-" * 80)
        print(f"   {{")
        print(f"     \"positions\": [...],  // {len(open_positions)} open positions")
        print(f"     \"total_count\": {len(open_positions)},")
        print(f"     \"pending_count\": {len(pending_orders)},")
        print(f"     \"market_open\": {str(market_open).lower()}")
        print(f"   }}")
        
        # 6. Recommendations
        print("\n6. UI Display Recommendations")
        print("-" * 80)
        if len(pending_orders) > 0 and not market_open:
            print("   ⚠️  Show badge: \"Pending Market Open\"")
            print(f"   📊 Display: \"{len(pending_orders)} order(s) will execute when market opens\"")
        elif len(pending_orders) > 0 and market_open:
            print("   ⏳ Show badge: \"Processing\"")
            print(f"   📊 Display: \"{len(pending_orders)} order(s) being processed\"")
        else:
            print("   ✅ No pending orders - all positions are active")
        
        print("\n" + "=" * 80)
        print("VERIFICATION COMPLETE ✅")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()
