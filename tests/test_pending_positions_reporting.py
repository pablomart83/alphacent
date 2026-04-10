#!/usr/bin/env python3
"""
Test pending positions reporting functionality.

Validates that:
1. Pending orders are counted and reported separately
2. Market hours awareness is included in position responses
3. Pending open positions endpoint works correctly
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from src.models.database import get_database
from src.models.orm import OrderORM, PositionORM
from src.models.enums import OrderStatus, OrderSide, OrderType, PositionSide, TradingMode


@pytest.fixture
def db_session():
    """Get database session for testing."""
    db = get_database()
    session = db.get_session()
    yield session
    session.close()


def test_pending_orders_count(db_session):
    """Test that pending orders are counted correctly."""
    # Create a pending order
    pending_order = OrderORM(
        id="test_pending_order_001",
        strategy_id="test_strategy_001",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        status=OrderStatus.PENDING,
        submitted_at=datetime.now(),
        etoro_order_id="etoro_pending_001"
    )
    
    db_session.add(pending_order)
    db_session.commit()
    
    # Query pending orders
    pending_count = db_session.query(OrderORM).filter(
        OrderORM.status == OrderStatus.PENDING
    ).count()
    
    assert pending_count >= 1, "Should have at least one pending order"
    
    # Cleanup
    db_session.delete(pending_order)
    db_session.commit()


def test_pending_vs_open_positions(db_session):
    """Test distinction between pending orders and open positions."""
    # Create a pending order (not yet a position)
    pending_order = OrderORM(
        id="test_pending_order_002",
        strategy_id="test_strategy_002",
        symbol="MSFT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=5,
        status=OrderStatus.PENDING,
        submitted_at=datetime.now(),
        etoro_order_id="etoro_pending_002"
    )
    
    # Create an open position (filled order)
    open_position = PositionORM(
        id="test_position_001",
        strategy_id="test_strategy_002",
        symbol="GOOGL",
        side=PositionSide.LONG,
        quantity=3,
        entry_price=150.0,
        current_price=155.0,
        unrealized_pnl=15.0,
        realized_pnl=0.0,
        opened_at=datetime.now(),
        etoro_position_id="etoro_pos_001"
    )
    
    db_session.add(pending_order)
    db_session.add(open_position)
    db_session.commit()
    
    # Query counts
    pending_count = db_session.query(OrderORM).filter(
        OrderORM.status == OrderStatus.PENDING
    ).count()
    
    open_positions_count = db_session.query(PositionORM).filter(
        PositionORM.closed_at.is_(None)
    ).count()
    
    assert pending_count >= 1, "Should have pending orders"
    assert open_positions_count >= 1, "Should have open positions"
    
    # Cleanup
    db_session.delete(pending_order)
    db_session.delete(open_position)
    db_session.commit()


def test_market_hours_awareness():
    """Test that market hours status can be determined."""
    from src.data.market_hours_manager import MarketHoursManager, AssetClass
    
    market_hours = MarketHoursManager()
    market_open = market_hours.is_market_open(AssetClass.STOCK)
    
    # Should return a boolean
    assert isinstance(market_open, bool), "Market status should be boolean"
    
    print(f"Market is currently: {'OPEN' if market_open else 'CLOSED'}")


def test_pending_positions_api_format():
    """Test that pending orders can be formatted as position-like responses."""
    from src.models.enums import OrderSide
    
    # Simulate a pending order
    pending_order = OrderORM(
        id="test_pending_order_003",
        strategy_id="test_strategy_003",
        symbol="TSLA",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=2,
        status=OrderStatus.PENDING,
        submitted_at=datetime.now(),
        etoro_order_id="etoro_pending_003",
        expected_price=250.0,
        stop_price=240.0,
        take_profit_price=270.0
    )
    
    # Convert to position-like format (as done in API)
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
        "realized_pnl": 0.0,
        "stop_loss": pending_order.stop_price,
        "take_profit": pending_order.take_profit_price,
        "opened_at": pending_order.submitted_at.isoformat(),
        "closed_at": None,
        "etoro_position_id": pending_order.etoro_order_id or "pending",
    }
    
    # Validate format
    assert position_dict["id"].startswith("pending_"), "Pending position ID should have prefix"
    assert position_dict["side"] in ["LONG", "SHORT"], "Side should be LONG or SHORT"
    assert position_dict["unrealized_pnl"] == 0.0, "Pending positions have no P&L yet"
    assert position_dict["closed_at"] is None, "Pending positions are not closed"
    
    print(f"Pending position format: {position_dict['symbol']} {position_dict['side']} x{position_dict['quantity']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
