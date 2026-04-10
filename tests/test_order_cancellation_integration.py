"""Integration test for order cancellation functionality (Task 6.5.4)."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import uuid

from src.execution.order_executor import OrderExecutor
from src.core.order_monitor import OrderMonitor
from src.api.etoro_client import EToroAPIClient
from src.data.market_hours_manager import MarketHoursManager
from src.models.database import Database
from src.models.enums import OrderStatus, OrderSide, OrderType, TradingMode
from src.models.orm import OrderORM


class TestOrderCancellationIntegration:
    """Integration tests for order cancellation workflow."""

    def test_full_cancellation_workflow(self):
        """Test complete workflow: create order, let it become stale, cancel it."""
        # Setup mocks
        mock_etoro_client = Mock(spec=EToroAPIClient)
        mock_etoro_client.mode = TradingMode.DEMO
        mock_etoro_client.cancel_order.return_value = True
        
        mock_market_hours = Mock(spec=MarketHoursManager)
        mock_market_hours.is_market_open.return_value = True
        
        mock_database = Mock(spec=Database)
        mock_session = Mock()
        mock_database.get_session.return_value = mock_session
        
        # Create OrderExecutor and OrderMonitor
        order_executor = OrderExecutor(
            etoro_client=mock_etoro_client,
            market_hours=mock_market_hours
        )
        
        order_monitor = OrderMonitor(
            etoro_client=mock_etoro_client,
            db=mock_database
        )
        
        # Step 1: Create a pending order via OrderExecutor
        from src.models import Order
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id=None
        )
        order_executor._orders[order.id] = order
        
        # Step 2: Manually cancel via OrderExecutor
        success = order_executor.cancel_order(order.id, "Manual cancellation test")
        
        assert success is True
        assert order.status == OrderStatus.CANCELLED
        
        # Step 3: Create a stale order in database
        stale_order = OrderORM(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="TSLA",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=50.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_stale_123",
            submitted_at=datetime.now() - timedelta(hours=48)  # 48 hours old
        )
        
        # Mock two separate queries (PENDING then SUBMITTED)
        call_count = [0]
        def query_side_effect(*args, **kwargs):
            mock_q = Mock()
            def filter_side(*a, **kw):
                call_count[0] += 1
                result_mock = Mock()
                if call_count[0] == 1:
                    result_mock.all.return_value = []  # No stale PENDING
                else:
                    result_mock.all.return_value = [stale_order]  # Stale SUBMITTED
                return result_mock
            mock_q.filter = filter_side
            return mock_q
        mock_session.query.side_effect = query_side_effect
        
        # Step 4: Run OrderMonitor to cancel stale orders
        result = order_monitor.cancel_stale_orders(max_age_hours=24)
        
        assert result["checked"] == 1
        assert result["cancelled"] == 1
        assert result["failed"] == 0
        assert stale_order.status == OrderStatus.CANCELLED
        mock_etoro_client.cancel_order.assert_called_with("etoro_stale_123")

    def test_monitoring_cycle_cancels_stale_orders(self):
        """Test that monitoring cycle automatically cancels stale orders."""
        # Setup mocks
        mock_etoro_client = Mock(spec=EToroAPIClient)
        mock_etoro_client.mode = TradingMode.DEMO
        mock_etoro_client.cancel_order.return_value = True
        
        mock_database = Mock(spec=Database)
        mock_session = Mock()
        mock_database.get_session.return_value = mock_session
        
        order_monitor = OrderMonitor(
            etoro_client=mock_etoro_client,
            db=mock_database
        )
        
        # Create stale order
        stale_order = OrderORM(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_123",
            submitted_at=datetime.now() - timedelta(hours=30)
        )
        
        # Mock queries — run_monitoring_cycle calls multiple queries.
        # For cancel_stale_orders: two queries (PENDING, SUBMITTED)
        # For other operations: various queries
        call_count = [0]
        def mock_query_side_effect(*args):
            mock_q = Mock()
            mock_q.filter_by.return_value.first.return_value = None
            def filter_side(*a, **kw):
                call_count[0] += 1
                result_mock = Mock()
                # The cancel_stale_orders queries happen last in run_monitoring_cycle
                # We can't predict exact call order, so return stale_order for SUBMITTED queries
                result_mock.all.return_value = [stale_order]
                return result_mock
            mock_q.filter.side_effect = filter_side
            return mock_q
        
        mock_session.query.side_effect = mock_query_side_effect
        
        # Run monitoring cycle
        result = order_monitor.run_monitoring_cycle()
        
        # Verify cancellation happened
        assert "cancellations" in result
        assert result["cancellations"]["cancelled"] >= 1
        assert stale_order.status == OrderStatus.CANCELLED

    def test_cancel_order_removes_from_queue(self):
        """Test that cancelling a queued order removes it from the queue."""
        # Setup
        mock_etoro_client = Mock(spec=EToroAPIClient)
        mock_etoro_client.mode = TradingMode.DEMO
        
        mock_market_hours = Mock(spec=MarketHoursManager)
        mock_market_hours.is_market_open.return_value = False  # Market closed
        
        order_executor = OrderExecutor(
            etoro_client=mock_etoro_client,
            market_hours=mock_market_hours
        )
        
        # Create queued order
        from src.models import Order
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id=None
        )
        order_executor._orders[order.id] = order
        order_executor._queued_orders.append(order)
        
        # Verify order is in queue
        assert len(order_executor._queued_orders) == 1
        assert order_executor.get_queued_orders_count() == 1
        
        # Cancel order
        success = order_executor.cancel_order(order.id, "Remove from queue")
        
        # Verify order removed from queue
        assert success is True
        assert order.status == OrderStatus.CANCELLED
        assert len(order_executor._queued_orders) == 0
        assert order_executor.get_queued_orders_count() == 0
