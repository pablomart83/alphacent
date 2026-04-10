"""Unit tests for startup position reconciliation (Task 11.8.5)."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch, PropertyMock
import uuid

from src.core.order_monitor import OrderMonitor
from src.api.etoro_client import EToroAPIClient, EToroAPIError
from src.models.database import Database
from src.models.enums import OrderStatus, OrderSide, OrderType, PositionSide, TradingMode
from src.models.orm import OrderORM, PositionORM


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


def _make_etoro_position(etoro_position_id, symbol, side=PositionSide.LONG,
                          quantity=100.0, entry_price=150.0, current_price=155.0):
    """Create a mock eToro position object."""
    pos = Mock()
    pos.etoro_position_id = etoro_position_id
    pos.symbol = symbol
    pos.side = side
    pos.quantity = quantity
    pos.entry_price = entry_price
    pos.current_price = current_price
    pos.unrealized_pnl = (current_price - entry_price) * quantity
    pos.realized_pnl = 0.0
    pos.opened_at = datetime.now() - timedelta(hours=2)
    pos.stop_loss = entry_price * 0.95
    pos.take_profit = entry_price * 1.10
    pos.closed_at = None
    pos.strategy_id = "etoro_position"
    pos.id = str(uuid.uuid4())
    return pos


def _make_db_position(etoro_position_id, symbol, strategy_id="test_strategy",
                       side=PositionSide.LONG, closed_at=None):
    """Create a mock DB position ORM object."""
    pos = PositionORM(
        id=str(uuid.uuid4()),
        strategy_id=strategy_id,
        symbol=symbol,
        side=side,
        quantity=100.0,
        entry_price=150.0,
        current_price=155.0,
        unrealized_pnl=500.0,
        realized_pnl=0.0,
        opened_at=datetime.now() - timedelta(hours=2),
        etoro_position_id=etoro_position_id,
        stop_loss=142.5,
        take_profit=165.0,
        closed_at=closed_at,
    )
    return pos


class TestReconcileOnStartup:
    """Test reconcile_on_startup() method."""

    def test_no_discrepancies_when_in_sync(self, order_monitor, mock_etoro_client, mock_database):
        """When DB and eToro are in sync, no discrepancies should be found."""
        etoro_pos = _make_etoro_position("etoro_123", "AAPL")
        mock_etoro_client.get_positions.return_value = [etoro_pos]

        db_pos = _make_db_position("etoro_123", "AAPL")

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session

        # First query: open positions, second query: submitted orders
        call_count = [0]
        def query_side_effect(model):
            mock_q = Mock()
            def filter_side(*args, **kwargs):
                call_count[0] += 1
                result_mock = Mock()
                if call_count[0] == 1:
                    result_mock.all.return_value = [db_pos]
                else:
                    result_mock.all.return_value = []
                return result_mock
            mock_q.filter = filter_side
            mock_q.filter_by = Mock(return_value=Mock(first=Mock(return_value=None)))
            return mock_q
        mock_session.query.side_effect = query_side_effect

        result = order_monitor.reconcile_on_startup()

        assert result["positions_created"] == 0
        assert result["positions_closed"] == 0
        assert result["positions_updated"] == 1
        assert result["orders_failed"] == 0
        assert len(result["discrepancies"]) == 0
        mock_session.commit.assert_called_once()

    def test_position_on_etoro_not_in_db_creates_record(self, order_monitor, mock_etoro_client, mock_database):
        """Positions on eToro but not in DB should be created."""
        etoro_pos = _make_etoro_position("etoro_new", "MSFT")
        mock_etoro_client.get_positions.return_value = [etoro_pos]

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session

        call_count = [0]
        def query_side_effect(model):
            mock_q = Mock()
            def filter_side(*args, **kwargs):
                call_count[0] += 1
                result_mock = Mock()
                if call_count[0] == 1:
                    result_mock.all.return_value = []  # No DB positions
                else:
                    result_mock.all.return_value = []  # No submitted orders
                return result_mock
            mock_q.filter = filter_side
            # For order matching query
            mock_q.filter_by = Mock(return_value=Mock(first=Mock(return_value=None)))
            mock_q.order_by = Mock(return_value=Mock(limit=Mock(return_value=Mock(all=Mock(return_value=[])))))
            return mock_q
        mock_session.query.side_effect = query_side_effect

        result = order_monitor.reconcile_on_startup()

        assert result["positions_created"] == 1
        assert result["positions_closed"] == 0
        assert len(result["discrepancies"]) == 1
        assert "CREATED" in result["discrepancies"][0]
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_position_in_db_not_on_etoro_marks_closed(self, order_monitor, mock_etoro_client, mock_database):
        """Positions in DB but not on eToro should be marked as closed."""
        mock_etoro_client.get_positions.return_value = []  # No eToro positions

        db_pos = _make_db_position("etoro_gone", "TSLA")

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session

        call_count = [0]
        def query_side_effect(model):
            mock_q = Mock()
            def filter_side(*args, **kwargs):
                call_count[0] += 1
                result_mock = Mock()
                if call_count[0] == 1:
                    result_mock.all.return_value = [db_pos]  # DB has position
                else:
                    result_mock.all.return_value = []  # No submitted orders
                return result_mock
            mock_q.filter = filter_side
            return mock_q
        mock_session.query.side_effect = query_side_effect

        result = order_monitor.reconcile_on_startup()

        assert result["positions_created"] == 0
        assert result["positions_closed"] == 1
        assert len(result["discrepancies"]) == 1
        assert "CLOSED" in result["discrepancies"][0]
        assert db_pos.closed_at is not None
        assert db_pos.unrealized_pnl == 0.0
        mock_session.commit.assert_called_once()

    def test_submitted_order_not_on_etoro_marks_failed(self, order_monitor, mock_etoro_client, mock_database):
        """SUBMITTED orders that can't be verified on eToro should be marked FAILED."""
        mock_etoro_client.get_positions.return_value = []
        mock_etoro_client.get_order_status.side_effect = EToroAPIError("Not found")

        stale_order = OrderORM(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_order_456",
            submitted_at=datetime.now() - timedelta(hours=1),
        )

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session

        call_count = [0]
        def query_side_effect(model):
            mock_q = Mock()
            def filter_side(*args, **kwargs):
                call_count[0] += 1
                result_mock = Mock()
                if call_count[0] == 1:
                    result_mock.all.return_value = []  # No open positions
                else:
                    result_mock.all.return_value = [stale_order]  # Submitted order
                return result_mock
            mock_q.filter = filter_side
            return mock_q
        mock_session.query.side_effect = query_side_effect

        result = order_monitor.reconcile_on_startup()

        assert result["orders_failed"] == 1
        assert stale_order.status == OrderStatus.FAILED
        assert len(result["discrepancies"]) == 1
        assert "FAILED" in result["discrepancies"][0]

    def test_submitted_order_with_error_on_etoro_marks_failed(self, order_monitor, mock_etoro_client, mock_database):
        """SUBMITTED orders with error codes on eToro should be marked FAILED."""
        mock_etoro_client.get_positions.return_value = []
        mock_etoro_client.get_order_status.return_value = {
            "statusID": 4,
            "errorCode": 720,
            "errorMessage": "Minimum order size violation",
        }

        failed_order = OrderORM(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_order_789",
            submitted_at=datetime.now() - timedelta(minutes=30),
        )

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session

        call_count = [0]
        def query_side_effect(model):
            mock_q = Mock()
            def filter_side(*args, **kwargs):
                call_count[0] += 1
                result_mock = Mock()
                if call_count[0] == 1:
                    result_mock.all.return_value = []
                else:
                    result_mock.all.return_value = [failed_order]
                return result_mock
            mock_q.filter = filter_side
            return mock_q
        mock_session.query.side_effect = query_side_effect

        result = order_monitor.reconcile_on_startup()

        assert result["orders_failed"] == 1
        assert failed_order.status == OrderStatus.FAILED

    def test_submitted_order_no_etoro_id_old_marks_failed(self, order_monitor, mock_etoro_client, mock_database):
        """SUBMITTED orders without eToro ID older than 5 min should be marked FAILED."""
        mock_etoro_client.get_positions.return_value = []

        old_order = OrderORM(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="GOOGL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=50.0,
            status=OrderStatus.PENDING,
            etoro_order_id=None,
            submitted_at=datetime.now() - timedelta(minutes=10),
        )

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session

        call_count = [0]
        def query_side_effect(model):
            mock_q = Mock()
            def filter_side(*args, **kwargs):
                call_count[0] += 1
                result_mock = Mock()
                if call_count[0] == 1:
                    result_mock.all.return_value = []
                else:
                    result_mock.all.return_value = [old_order]
                return result_mock
            mock_q.filter = filter_side
            return mock_q
        mock_session.query.side_effect = query_side_effect

        result = order_monitor.reconcile_on_startup()

        assert result["orders_failed"] == 1
        assert old_order.status == OrderStatus.FAILED

    def test_etoro_api_failure_returns_error(self, order_monitor, mock_etoro_client, mock_database):
        """If eToro API fails entirely, return error without crashing."""
        mock_etoro_client.get_positions.side_effect = Exception("Connection refused")

        result = order_monitor.reconcile_on_startup()

        assert "error" in result
        assert "Failed to fetch positions" in result["error"]

    def test_caches_invalidated_before_reconciliation(self, order_monitor, mock_etoro_client, mock_database):
        """Caches should be invalidated before reconciliation starts."""
        # Pre-populate caches
        order_monitor._order_status_cache = {"old_order": ("data", 0)}
        order_monitor._positions_cache = ([], 0)
        order_monitor._last_full_sync = 999999

        mock_etoro_client.get_positions.return_value = []

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session
        call_count = [0]
        def query_side_effect(model):
            mock_q = Mock()
            def filter_side(*args, **kwargs):
                call_count[0] += 1
                result_mock = Mock()
                result_mock.all.return_value = []
                return result_mock
            mock_q.filter = filter_side
            return mock_q
        mock_session.query.side_effect = query_side_effect

        order_monitor.reconcile_on_startup()

        # get_positions should be called directly (not cached)
        mock_etoro_client.get_positions.assert_called_once()

    def test_sync_timestamp_updated_after_reconciliation(self, order_monitor, mock_etoro_client, mock_database):
        """After reconciliation, sync timestamp should be updated to prevent immediate re-sync."""
        mock_etoro_client.get_positions.return_value = []

        mock_session = Mock()
        mock_database.get_session.return_value = mock_session
        call_count = [0]
        def query_side_effect(model):
            mock_q = Mock()
            def filter_side(*args, **kwargs):
                call_count[0] += 1
                result_mock = Mock()
                result_mock.all.return_value = []
                return result_mock
            mock_q.filter = filter_side
            return mock_q
        mock_session.query.side_effect = query_side_effect

        import time
        before = time.time()
        order_monitor.reconcile_on_startup()
        after = time.time()

        assert order_monitor._last_full_sync >= before
        assert order_monitor._last_full_sync <= after


class TestTradingSchedulerReconciliation:
    """Test that TradingScheduler blocks signal generation until reconciliation completes."""

    def test_reconciliation_flag_initialized_false(self):
        """TradingScheduler should initialize with reconciliation_done=False."""
        from src.core.trading_scheduler import TradingScheduler
        scheduler = TradingScheduler()
        assert scheduler._reconciliation_done is False

    @pytest.mark.asyncio
    async def test_reconciliation_runs_before_signals(self):
        """Reconciliation should run before signal generation on first cycle."""
        from src.core.trading_scheduler import TradingScheduler

        scheduler = TradingScheduler()
        scheduler._components_initialized = True
        scheduler._etoro_client = Mock()
        scheduler._market_data = Mock()
        scheduler._strategy_engine = Mock()
        scheduler._risk_manager = Mock()
        scheduler._order_executor = Mock()
        scheduler._websocket_manager = Mock()

        mock_reconcile = Mock(return_value={"positions_created": 0, "positions_closed": 0})

        with patch('src.models.database.get_database') as mock_get_db, \
             patch('src.core.order_monitor.OrderMonitor') as MockOrderMonitor:

            mock_get_db.return_value = Mock()
            mock_monitor_instance = Mock()
            mock_monitor_instance.reconcile_on_startup = mock_reconcile
            MockOrderMonitor.return_value = mock_monitor_instance

            # Run the trading cycle
            await scheduler._run_trading_cycle()

            # Reconciliation should have been called
            mock_reconcile.assert_called_once()
            assert scheduler._reconciliation_done is True
