#!/usr/bin/env python3
"""
Seed database with realistic demo data.

Since eToro API endpoints need proper configuration, this script
creates realistic demo data to populate the database so the frontend
can display data while the API integration is being finalized.
"""

import logging
from datetime import datetime, timedelta
import random

from src.models.database import get_database
from src.models.enums import TradingMode, PositionSide, OrderSide, OrderStatus, OrderType
from src.models.orm import AccountInfoORM, PositionORM, OrderORM

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def seed_account_data():
    """Seed realistic account data."""
    logger.info("=" * 60)
    logger.info("SEEDING DATABASE WITH REALISTIC DEMO DATA")
    logger.info("=" * 60)
    
    db = get_database("alphacent.db")
    session = db.get_session()
    
    try:
        # Create demo account
        logger.info("\nCreating demo account...")
        account = AccountInfoORM(
            account_id="demo_account_001",
            mode=TradingMode.DEMO,
            balance=100000.00,
            buying_power=95000.00,
            margin_used=5000.00,
            margin_available=95000.00,
            daily_pnl=1250.50,
            total_pnl=8750.25,
            positions_count=5,
            updated_at=datetime.now()
        )
        
        # Check if exists
        existing = session.query(AccountInfoORM).filter_by(account_id="demo_account_001").first()
        if existing:
            session.delete(existing)
            session.commit()
        
        session.add(account)
        session.commit()
        logger.info(f"✓ Account created: ${account.balance:,.2f} balance")
        
        # Create positions
        logger.info("\nCreating positions...")
        positions_data = [
            {
                "symbol": "AAPL",
                "side": PositionSide.LONG,
                "quantity": 50.0,
                "entry_price": 175.50,
                "current_price": 178.25,
            },
            {
                "symbol": "MSFT",
                "side": PositionSide.LONG,
                "quantity": 30.0,
                "entry_price": 380.00,
                "current_price": 385.50,
            },
            {
                "symbol": "GOOGL",
                "side": PositionSide.LONG,
                "quantity": 20.0,
                "entry_price": 140.75,
                "current_price": 142.10,
            },
            {
                "symbol": "BTC",
                "side": PositionSide.LONG,
                "quantity": 0.5,
                "entry_price": 45000.00,
                "current_price": 46500.00,
            },
            {
                "symbol": "TSLA",
                "side": PositionSide.LONG,
                "quantity": 25.0,
                "entry_price": 195.00,
                "current_price": 192.50,
            },
        ]
        
        # Clear existing positions
        session.query(PositionORM).delete()
        session.commit()
        
        for i, pos_data in enumerate(positions_data):
            unrealized_pnl = (pos_data["current_price"] - pos_data["entry_price"]) * pos_data["quantity"]
            unrealized_pnl_percent = ((pos_data["current_price"] - pos_data["entry_price"]) / pos_data["entry_price"]) * 100
            
            position = PositionORM(
                id=f"pos_{i+1:03d}",
                strategy_id="manual",
                symbol=pos_data["symbol"],
                side=pos_data["side"],
                quantity=pos_data["quantity"],
                entry_price=pos_data["entry_price"],
                current_price=pos_data["current_price"],
                unrealized_pnl=unrealized_pnl,
                realized_pnl=0.0,
                opened_at=datetime.now() - timedelta(days=random.randint(1, 30)),
                etoro_position_id=f"etoro_pos_{i+1}",
                stop_loss=pos_data["entry_price"] * 0.95,  # 5% stop loss
                take_profit=pos_data["entry_price"] * 1.10,  # 10% take profit
                closed_at=None
            )
            session.add(position)
            logger.info(f"  ✓ {pos_data['symbol']}: {pos_data['quantity']} @ ${pos_data['entry_price']:.2f} → ${pos_data['current_price']:.2f} (P&L: ${unrealized_pnl:+.2f})")
        
        session.commit()
        logger.info(f"✓ Created {len(positions_data)} positions")
        
        # Create orders
        logger.info("\nCreating orders...")
        orders_data = [
            {
                "symbol": "NVDA",
                "side": OrderSide.BUY,
                "type": OrderType.LIMIT,
                "quantity": 15.0,
                "price": 480.00,
                "status": OrderStatus.PENDING,
                "created_at": datetime.now() - timedelta(hours=2),
            },
            {
                "symbol": "AAPL",
                "side": OrderSide.BUY,
                "type": OrderType.MARKET,
                "quantity": 50.0,
                "price": 175.50,
                "status": OrderStatus.FILLED,
                "created_at": datetime.now() - timedelta(days=5),
                "filled_at": datetime.now() - timedelta(days=5),
            },
            {
                "symbol": "MSFT",
                "side": OrderSide.BUY,
                "type": OrderType.MARKET,
                "quantity": 30.0,
                "price": 380.00,
                "status": OrderStatus.FILLED,
                "created_at": datetime.now() - timedelta(days=10),
                "filled_at": datetime.now() - timedelta(days=10),
            },
            {
                "symbol": "AMD",
                "side": OrderSide.BUY,
                "type": OrderType.LIMIT,
                "quantity": 40.0,
                "price": 145.00,
                "status": OrderStatus.CANCELLED,
                "created_at": datetime.now() - timedelta(days=3),
            },
        ]
        
        # Clear existing orders
        session.query(OrderORM).delete()
        session.commit()
        
        for i, order_data in enumerate(orders_data):
            order = OrderORM(
                id=f"order_{i+1:03d}",
                strategy_id="manual",
                symbol=order_data["symbol"],
                side=order_data["side"],
                order_type=order_data["type"],
                quantity=order_data["quantity"],
                filled_quantity=order_data["quantity"] if order_data["status"] == OrderStatus.FILLED else 0.0,
                price=order_data.get("price"),
                status=order_data["status"],
                submitted_at=order_data["created_at"],
                filled_at=order_data.get("filled_at"),
                etoro_order_id=f"etoro_order_{i+1}"
            )
            session.add(order)
            logger.info(f"  ✓ {order_data['symbol']} {order_data['side'].value} {order_data['quantity']} @ ${order_data.get('price', 'MARKET')} - {order_data['status'].value}")
        
        session.commit()
        logger.info(f"✓ Created {len(orders_data)} orders")
        
        logger.info("\n" + "=" * 60)
        logger.info("DATABASE SEEDING COMPLETE")
        logger.info("=" * 60)
        logger.info("\nYou can now:")
        logger.info("1. Refresh the frontend")
        logger.info("2. Account Overview will show $100,000 demo balance")
        logger.info("3. Positions will show 5 open positions")
        logger.info("4. Orders will show 4 orders (1 pending, 2 filled, 1 cancelled)")
        logger.info("\nNote: This is demo data for UI testing.")
        logger.info("Configure real eToro credentials to see live data.")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to seed database: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
        return False
        
    finally:
        session.close()


def main():
    """Main entry point."""
    import sys
    
    success = seed_account_data()
    
    if success:
        logger.info("\n✓ SUCCESS: Database seeded with realistic demo data")
        sys.exit(0)
    else:
        logger.error("\n✗ FAILED: Could not seed database")
        sys.exit(1)


if __name__ == '__main__':
    main()
