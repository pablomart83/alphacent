#!/usr/bin/env python3
"""
Demo script showing pending positions functionality.

Creates a test pending order and demonstrates the reporting.
"""

import sys
from pathlib import Path
from datetime import datetime
import uuid

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.database import get_database
from src.models.orm import OrderORM
from src.models.enums import OrderStatus, OrderSide, OrderType
from src.data.market_hours_manager import MarketHoursManager, AssetClass


def main():
    print("=" * 80)
    print("PENDING POSITIONS DEMO")
    print("=" * 80)
    
    db = get_database()
    session = db.get_session()
    
    # Create a test pending order
    test_order_id = f"demo_pending_{uuid.uuid4().hex[:8]}"
    
    try:
        print("\n1. Creating test pending order...")
        print("-" * 80)
        
        pending_order = OrderORM(
            id=test_order_id,
            strategy_id="demo_strategy_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            status=OrderStatus.PENDING,
            submitted_at=datetime.now(),
            etoro_order_id=f"etoro_demo_{uuid.uuid4().hex[:8]}",
            expected_price=150.0,
            stop_price=145.0,
            take_profit_price=165.0
        )
        
        session.add(pending_order)
        session.commit()
        
        print(f"   ✅ Created pending order: {test_order_id}")
        print(f"   Symbol: {pending_order.symbol}")
        print(f"   Side: {pending_order.side.value}")
        print(f"   Quantity: {pending_order.quantity}")
        print(f"   Expected Price: ${pending_order.expected_price:.2f}")
        
        # Check market status
        print("\n2. Checking market status...")
        print("-" * 80)
        market_hours = MarketHoursManager()
        market_open = market_hours.is_market_open(AssetClass.STOCK)
        print(f"   Market is: {'OPEN ✅' if market_open else 'CLOSED ❌'}")
        
        # Query pending orders
        print("\n3. Querying pending orders...")
        print("-" * 80)
        pending_count = session.query(OrderORM).filter(
            OrderORM.status == OrderStatus.PENDING
        ).count()
        print(f"   Found {pending_count} pending order(s)")
        
        # Simulate API response
        print("\n4. Simulated API Response")
        print("-" * 80)
        print(f"   GET /api/account/positions?mode=DEMO")
        print(f"   {{")
        print(f"     \"positions\": [...],")
        print(f"     \"total_count\": <open_positions_count>,")
        print(f"     \"pending_count\": {pending_count},")
        print(f"     \"market_open\": {str(market_open).lower()}")
        print(f"   }}")
        
        # Simulate pending position format
        print("\n5. Pending Position Format (for UI)")
        print("-" * 80)
        position_dict = {
            "id": f"pending_{pending_order.id}",
            "strategy_id": pending_order.strategy_id,
            "symbol": pending_order.symbol,
            "side": "LONG" if pending_order.side == OrderSide.BUY else "SHORT",
            "quantity": pending_order.quantity,
            "entry_price": pending_order.expected_price or 0.0,
            "current_price": pending_order.expected_price or 0.0,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_percent": 0.0,
            "stop_loss": pending_order.stop_price,
            "take_profit": pending_order.take_profit_price,
            "status": "PENDING_OPEN",  # UI can show special badge
        }
        
        print(f"   {{")
        print(f"     \"id\": \"{position_dict['id']}\",")
        print(f"     \"symbol\": \"{position_dict['symbol']}\",")
        print(f"     \"side\": \"{position_dict['side']}\",")
        print(f"     \"quantity\": {position_dict['quantity']},")
        print(f"     \"entry_price\": {position_dict['entry_price']},")
        print(f"     \"unrealized_pnl\": {position_dict['unrealized_pnl']},")
        print(f"     \"status\": \"{position_dict['status']}\"")
        print(f"   }}")
        
        # UI recommendations
        print("\n6. UI Display Recommendations")
        print("-" * 80)
        if not market_open:
            print("   🔵 Badge: \"Pending Market Open\"")
            print(f"   📊 Message: \"Order will execute when market opens\"")
            next_open = market_hours.get_next_open_time(AssetClass.STOCK)
            if next_open:
                print(f"   ⏰ Next open: {next_open.strftime('%Y-%m-%d %H:%M %Z')}")
        else:
            print("   🟡 Badge: \"Processing\"")
            print(f"   📊 Message: \"Order is being processed\"")
        
        print("\n7. Cleanup")
        print("-" * 80)
        session.delete(pending_order)
        session.commit()
        print(f"   ✅ Deleted test order: {test_order_id}")
        
        print("\n" + "=" * 80)
        print("DEMO COMPLETE ✅")
        print("=" * 80)
        print("\nKey Takeaways:")
        print("  • Pending orders are tracked separately from open positions")
        print("  • API returns both pending_count and market_open status")
        print("  • UI can show appropriate badges based on market status")
        print("  • Pending positions have 0 P&L until filled")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        # Cleanup on error
        try:
            order = session.query(OrderORM).filter_by(id=test_order_id).first()
            if order:
                session.delete(order)
                session.commit()
        except:
            pass
    finally:
        session.close()


if __name__ == "__main__":
    main()
