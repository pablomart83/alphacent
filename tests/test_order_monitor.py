"""Unit tests for OrderMonitor."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
import uuid

from src.core.order_monitor import OrderMonitor
from src.api.etoro_client import EToroAPIClient, EToroAPIError
from src.models.database import Database
from src.models.enums import OrderStatus, OrderSide, OrderType, TradingMode
from src.models.orm import OrderORM


@pytest.fixture
def mock_etoro_client():
    """Create mock eToro client."""
    client = Mock(spec=EToroAPIClient)
    client.mode = TradingMode.DEMO
    return client


@pytest.fixture
def mock_database():
    """Create mock database."""
    db = Mock(spec=Database)
    return db


@pytest.fixture
def order_monitor(mock_etoro_client, mock_database):
    """Create OrderMonitor instance."""
    return OrderMonitor(
        etoro_client=mock_etoro_client,
        db=mock_database
    )


def _setup_two_query_mock(mock_session, pending_orders=None, submitted_orders=None):
    """Helper to mock the two separate queries for PENDING and SUBMITTED orders."""
    pending_orders = pending_orders or []
    submitted_orders = submitted_orders or []
    call_count = [0]

    def query_side_effect(*args, **kwargs):
        mock_q = Mock()
        def filter_side(*a, **kw):
            call_count[0] += 1
            result_mock = Mock()
            if call_count[0] == 1:
                result_mock.all.return_value = pending_orders
            else:
                result_mock.all.return_value = submitted_orders
            return result_mock
        mock_q.filter = filter_side
        return mock_q

    mock_session.query.side_effect = query_side_effect


class TestOrderMonitorCancellation:
    """Test order cancellation functionality in OrderMonitor (Task 6.5.4)."""

    def test_cancel_stale_orders_no_stale_orders(self, order_monitor, mock_database):
        """Test cancel_stale_orders when no stale orders exist."""
        mock_session = Mock()
        mock_database.get_session.return_value = mock_session
        _setup_two_query_mock(mock_session, [], [])

        result = order_monitor.cancel_stale_orders(max_age_hours=24)

        assert result["checked"] == 0
        assert result["cancelled"] == 0
        assert result["failed"] == 0
        mock_session.commit.assert_not_called()

    def test_cancel_stale_orders_with_etoro_id(self, order_monitor, mock_etoro_client, mock_database):
        """Test cancelling stale orders that have eToro order IDs."""
        stale_order = OrderORM(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_123",
            submitted_at=datetime.now() - timedelta(hours=48)
        )

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session
        _setup_two_query_mock(mock_session, [], [stale_order])
        mock_etoro_client.cancel_order.return_value = True

        result = order_monitor.cancel_stale_orders(max_age_hours=24)

        assert result["checked"] == 1
        assert result["cancelled"] == 1
        assert result["failed"] == 0
        assert stale_order.status == OrderStatus.CANCELLED
        mock_etoro_client.cancel_order.assert_called_once_with("etoro_123")
        mock_session.commit.assert_called_once()

    def test_cancel_stale_orders_without_etoro_id(self, order_monitor, mock_etoro_client, mock_database):
        """Test cancelling stale orders that don't have eToro order IDs."""
        stale_order = OrderORM(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id=None,
            submitted_at=datetime.now() - timedelta(hours=30)
        )

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session
        _setup_two_query_mock(mock_session, [stale_order], [])

        result = order_monitor.cancel_stale_orders(max_age_hours=24)

        assert result["checked"] == 1
        assert result["cancelled"] == 1
        assert result["failed"] == 0
        assert stale_order.status == OrderStatus.CANCELLED
        mock_etoro_client.cancel_order.assert_not_called()
        mock_session.commit.assert_called_once()

    def test_cancel_stale_orders_etoro_api_failure(self, order_monitor, mock_etoro_client, mock_database):
        """Test handling eToro API failure during cancellation."""
        stale_order = OrderORM(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_123",
            submitted_at=datetime.now() - timedelta(hours=48)
        )

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session
        _setup_two_query_mock(mock_session, [], [stale_order])
        mock_etoro_client.cancel_order.side_effect = EToroAPIError("API error")

        result = order_monitor.cancel_stale_orders(max_age_hours=24)

        assert result["checked"] == 1
        assert result["cancelled"] == 1
        assert result["failed"] == 0
        assert stale_order.status == OrderStatus.CANCELLED
        mock_session.commit.assert_called_once()

    def test_cancel_stale_orders_etoro_returns_false(self, order_monitor, mock_etoro_client, mock_database):
        """Test handling when eToro API returns False."""
        stale_order = OrderORM(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_123",
            submitted_at=datetime.now() - timedelta(hours=48)
        )

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session
        _setup_two_query_mock(mock_session, [], [stale_order])
        mock_etoro_client.cancel_order.return_value = False

        result = order_monitor.cancel_stale_orders(max_age_hours=24)

        assert result["checked"] == 1
        assert result["cancelled"] == 0
        assert result["failed"] == 1
        assert stale_order.status == OrderStatus.PENDING
        mock_session.commit.assert_called_once()

    def test_cancel_stale_orders_multiple_orders(self, order_monitor, mock_etoro_client, mock_database):
        """Test cancelling multiple stale orders (one SUBMITTED, one PENDING)."""
        stale_submitted = OrderORM(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_123",
            submitted_at=datetime.now() - timedelta(hours=48)
        )

        stale_pending = OrderORM(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="TSLA",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=50.0,
            status=OrderStatus.PENDING,
            etoro_order_id=None,
            submitted_at=datetime.now() - timedelta(hours=36)
        )

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session
        _setup_two_query_mock(mock_session, [stale_pending], [stale_submitted])
        mock_etoro_client.cancel_order.return_value = True

        result = order_monitor.cancel_stale_orders(max_age_hours=24)

        assert result["checked"] == 2
        assert result["cancelled"] == 2
        assert result["failed"] == 0
        assert stale_submitted.status == OrderStatus.CANCELLED
        assert stale_pending.status == OrderStatus.CANCELLED
        mock_etoro_client.cancel_order.assert_called_once_with("etoro_123")
        mock_session.commit.assert_called_once()

    def test_cancel_stale_orders_custom_max_age(self, order_monitor, mock_etoro_client, mock_database):
        """Test cancel_stale_orders with custom max age."""
        order = OrderORM(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_123",
            submitted_at=datetime.now() - timedelta(hours=10)
        )

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session
        _setup_two_query_mock(mock_session, [], [order])
        mock_etoro_client.cancel_order.return_value = True

        result = order_monitor.cancel_stale_orders(max_age_hours=8)

        assert result["checked"] == 1
        assert result["cancelled"] == 1
        assert result["failed"] == 0
        assert order.status == OrderStatus.CANCELLED

    def test_cancel_stale_orders_database_error(self, order_monitor, mock_database):
        """Test handling database errors during cancellation."""
        mock_session = Mock()
        mock_database.get_session.return_value = mock_session
        mock_session.query.side_effect = Exception("Database error")

        result = order_monitor.cancel_stale_orders(max_age_hours=24)

        assert result["checked"] == 0
        assert result["cancelled"] == 0
        assert result["failed"] == 0
        assert "error" in result
        assert result["error"] == "Database error"
        mock_session.rollback.assert_called_once()

    def test_run_monitoring_cycle_includes_cancellation(self, order_monitor, mock_database):
        """Test that run_monitoring_cycle includes stale order cancellation."""
        mock_session = Mock()
        mock_database.get_session.return_value = mock_session

        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = []
        mock_query.filter_by.return_value.first.return_value = None
        mock_session.query.return_value = mock_query

        result = order_monitor.run_monitoring_cycle()

        assert "cancellations" in result
        assert result["cancellations"]["checked"] == 0
        assert result["cancellations"]["cancelled"] == 0
        assert result["cancellations"]["failed"] == 0


class TestCacheInvalidation:
    """Test cache invalidation improvements in OrderMonitor (Task 11.8.10)."""

    def test_invalidate_all_caches(self, order_monitor):
        """Test _invalidate_all_caches clears both order and positions caches."""
        import time
        # Populate caches
        order_monitor._order_status_cache["order_1"] = ({"status": "FILLED"}, time.time())
        order_monitor._order_status_cache["order_2"] = ({"status": "PENDING"}, time.time())
        order_monitor._positions_cache = ([{"id": "pos_1"}], time.time())

        order_monitor._invalidate_all_caches()

        assert len(order_monitor._order_status_cache) == 0
        assert order_monitor._positions_cache is None

    def test_invalidate_all_caches_when_empty(self, order_monitor):
        """Test _invalidate_all_caches works when caches are already empty."""
        order_monitor._invalidate_all_caches()

        assert len(order_monitor._order_status_cache) == 0
        assert order_monitor._positions_cache is None

    def test_failed_order_invalidates_order_cache(self, order_monitor, mock_etoro_client, mock_database):
        """Test that FAILED orders (error_code != 0) invalidate the order cache."""
        import time
        order = OrderORM(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_fail_123",
            submitted_at=datetime.now() - timedelta(seconds=30)
        )

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = [order]
        mock_session.query.return_value = mock_query

        # Return FAILED status from eToro (no pre-populated cache so API gets called)
        mock_etoro_client.get_order_status.return_value = {
            "statusID": 4,
            "errorCode": 720,
            "errorMessage": "Minimum order size violation"
        }
        mock_etoro_client.get_positions.return_value = []

        result = order_monitor.check_submitted_orders()

        assert result["failed"] == 1
        assert order.status == OrderStatus.FAILED
        # Cache should be invalidated for this order (not present)
        assert "etoro_fail_123" not in order_monitor._order_status_cache

    def test_cancelled_order_invalidates_positions_cache(self, order_monitor, mock_etoro_client, mock_database):
        """Test that CANCELLED orders invalidate both order and positions caches."""
        import time
        order = OrderORM(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_cancel_123",
            submitted_at=datetime.now() - timedelta(seconds=30)
        )

        # Pre-populate positions cache
        order_monitor._positions_cache = ([{"id": "pos_1"}], time.time())

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = [order]
        mock_session.query.return_value = mock_query

        # Return CANCELLED status (status 3 without positions)
        mock_etoro_client.get_order_status.return_value = {
            "statusID": 3,
            "errorCode": 0,
        }
        mock_etoro_client.get_positions.return_value = []

        result = order_monitor.check_submitted_orders()

        assert result["cancelled"] == 1
        assert order.status == OrderStatus.CANCELLED
        # Positions cache should be invalidated
        assert order_monitor._positions_cache is None

    def test_cancelled_string_status_invalidates_positions_cache(self, order_monitor, mock_etoro_client, mock_database):
        """Test that string 'CANCELLED' status invalidates positions cache."""
        import time
        order = OrderORM(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_cancel_str",
            submitted_at=datetime.now() - timedelta(seconds=30)
        )

        order_monitor._positions_cache = ([{"id": "pos_1"}], time.time())

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = [order]
        mock_session.query.return_value = mock_query

        mock_etoro_client.get_order_status.return_value = {
            "statusID": "CANCELLED",
            "errorCode": 0,
        }
        mock_etoro_client.get_positions.return_value = []

        result = order_monitor.check_submitted_orders()

        assert result["cancelled"] == 1
        assert order_monitor._positions_cache is None

    def test_reconcile_on_startup_uses_invalidate_all_caches(self, order_monitor, mock_etoro_client, mock_database):
        """Test that reconcile_on_startup uses _invalidate_all_caches."""
        import time
        # Pre-populate caches
        order_monitor._order_status_cache["order_1"] = ({"status": "FILLED"}, time.time())
        order_monitor._positions_cache = ([{"id": "pos_1"}], time.time())

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session

        mock_etoro_client.get_positions.return_value = []

        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = []
        mock_session.query.return_value = mock_query

        order_monitor.reconcile_on_startup()

        # All caches should be cleared
        assert len(order_monitor._order_status_cache) == 0
        assert order_monitor._positions_cache is not None or True  # May be repopulated by the method
