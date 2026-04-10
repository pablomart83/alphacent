"""Tests for stale order cleanup (Task 11.8.3).

Tests the _cleanup_stale_orders() method in MonitoringService and the
enhanced cancel_stale_orders() in OrderMonitor with separate PENDING/SUBMITTED timeouts.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock, patch, PropertyMock
import uuid

from src.core.order_monitor import OrderMonitor
from src.core.monitoring_service import MonitoringService
from src.api.etoro_client import EToroAPIClient
from src.models.database import Database
from src.models.enums import OrderStatus, OrderSide, OrderType, TradingMode
from src.models.orm import OrderORM


@pytest.fixture
def mock_etoro_client():
    client = Mock(spec=EToroAPIClient)
    client.mode = TradingMode.DEMO
    return client


@pytest.fixture
def mock_database():
    return Mock(spec=Database)


@pytest.fixture
def order_monitor(mock_etoro_client, mock_database):
    return OrderMonitor(etoro_client=mock_etoro_client, db=mock_database)


def _make_order(status, age_hours, strategy_id="test_strategy", symbol="AAPL", etoro_id=None):
    """Helper to create an OrderORM with a given age."""
    submitted = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=age_hours)
    return OrderORM(
        id=str(uuid.uuid4()),
        strategy_id=strategy_id,
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=status,
        submitted_at=submitted,
        etoro_order_id=etoro_id,
    )


class TestCancelStaleOrdersSeparateTimeouts:
    """Test cancel_stale_orders with separate PENDING/SUBMITTED timeouts."""

    def test_separate_timeouts_pending_only(self, order_monitor, mock_database):
        """PENDING orders older than pending_timeout are cancelled, SUBMITTED within submitted_timeout are kept."""
        mock_session = Mock()
        mock_database.get_session.return_value = mock_session

        stale_pending = _make_order(OrderStatus.PENDING, age_hours=30, strategy_id="strat_1")
        # SUBMITTED order is 30h old but submitted_timeout is 48h — should NOT be returned
        
        # First query (PENDING) returns the stale pending order
        # Second query (SUBMITTED) returns nothing
        pending_query = Mock()
        pending_query.all.return_value = [stale_pending]
        submitted_query = Mock()
        submitted_query.all.return_value = []

        call_count = [0]
        def side_effect(*args, **kwargs):
            mock_q = Mock()
            def filter_side(*a, **kw):
                call_count[0] += 1
                if call_count[0] == 1:
                    return pending_query
                return submitted_query
            mock_q.filter = filter_side
            return mock_q

        mock_session.query.side_effect = side_effect

        result = order_monitor.cancel_stale_orders(
            pending_timeout_hours=24,
            submitted_timeout_hours=48,
        )

        assert result["cancelled_pending"] + result["cancelled_submitted"] == result["cancelled"]
        assert result["cancelled"] >= 1
        assert stale_pending.status == OrderStatus.CANCELLED
        mock_session.commit.assert_called_once()

    def test_separate_timeouts_submitted_only(self, order_monitor, mock_database):
        """SUBMITTED orders older than submitted_timeout are cancelled."""
        mock_session = Mock()
        mock_database.get_session.return_value = mock_session

        stale_submitted = _make_order(
            OrderStatus.PENDING, age_hours=50,
            strategy_id="strat_2", symbol="MSFT", etoro_id="etoro_456"
        )

        pending_query = Mock()
        pending_query.all.return_value = []
        submitted_query = Mock()
        submitted_query.all.return_value = [stale_submitted]

        call_count = [0]
        def side_effect(*args, **kwargs):
            mock_q = Mock()
            def filter_side(*a, **kw):
                call_count[0] += 1
                if call_count[0] == 1:
                    return pending_query
                return submitted_query
            mock_q.filter = filter_side
            return mock_q

        mock_session.query.side_effect = side_effect
        order_monitor.etoro_client.cancel_order.return_value = True

        result = order_monitor.cancel_stale_orders(
            pending_timeout_hours=24,
            submitted_timeout_hours=48,
        )

        assert result["cancelled"] >= 1
        assert stale_submitted.status == OrderStatus.CANCELLED
        order_monitor.etoro_client.cancel_order.assert_called_once_with("etoro_456")

    def test_no_stale_orders(self, order_monitor, mock_database):
        """No stale orders returns zero counts."""
        mock_session = Mock()
        mock_database.get_session.return_value = mock_session

        pending_query = Mock()
        pending_query.all.return_value = []
        submitted_query = Mock()
        submitted_query.all.return_value = []

        call_count = [0]
        def side_effect(*args, **kwargs):
            mock_q = Mock()
            def filter_side(*a, **kw):
                call_count[0] += 1
                if call_count[0] == 1:
                    return pending_query
                return submitted_query
            mock_q.filter = filter_side
            return mock_q

        mock_session.query.side_effect = side_effect

        result = order_monitor.cancel_stale_orders(
            pending_timeout_hours=24,
            submitted_timeout_hours=48,
        )

        assert result["checked"] == 0
        assert result["cancelled_pending"] == 0
        assert result["cancelled_submitted"] == 0
        mock_session.commit.assert_not_called()

    def test_default_fallback_to_max_age(self, order_monitor, mock_database):
        """When specific timeouts not provided, falls back to max_age_hours."""
        mock_session = Mock()
        mock_database.get_session.return_value = mock_session

        stale_pending = _make_order(OrderStatus.PENDING, age_hours=30)

        pending_query = Mock()
        pending_query.all.return_value = [stale_pending]
        submitted_query = Mock()
        submitted_query.all.return_value = []

        call_count = [0]
        def side_effect(*args, **kwargs):
            mock_q = Mock()
            def filter_side(*a, **kw):
                call_count[0] += 1
                if call_count[0] == 1:
                    return pending_query
                return submitted_query
            mock_q.filter = filter_side
            return mock_q

        mock_session.query.side_effect = side_effect

        # Only pass max_age_hours, no specific timeouts
        result = order_monitor.cancel_stale_orders(max_age_hours=24)

        assert result["cancelled"] >= 1
        assert stale_pending.status == OrderStatus.CANCELLED


class TestMonitoringServiceStaleOrderCleanup:
    """Test _cleanup_stale_orders() in MonitoringService."""

    @patch('src.core.monitoring_service.yaml')
    @patch('src.core.monitoring_service.MonitoringService._load_fundamental_config')
    @patch('src.core.monitoring_service.MonitoringService._load_stale_order_config')
    def test_cleanup_calls_order_monitor(self, mock_load_stale, mock_load_fund, mock_yaml, mock_etoro_client, mock_database):
        """_cleanup_stale_orders delegates to order_monitor.cancel_stale_orders with config values."""
        mock_load_fund.return_value = {'check_interval_hours': 24}
        mock_load_stale.return_value = {
            'enabled': True,
            'pending_timeout_hours': 24,
            'submitted_timeout_hours': 48,
        }

        service = MonitoringService(etoro_client=mock_etoro_client, db=mock_database)
        service.order_monitor = Mock()
        service.order_monitor.cancel_stale_orders.return_value = {
            "checked": 2, "cancelled_pending": 1, "cancelled_submitted": 1,
            "cancelled": 2, "failed": 0
        }

        result = service._cleanup_stale_orders()

        service.order_monitor.cancel_stale_orders.assert_called_once_with(
            pending_timeout_hours=24,
            submitted_timeout_hours=48,
        )
        assert result["cancelled"] == 2

    @patch('src.core.monitoring_service.yaml')
    @patch('src.core.monitoring_service.MonitoringService._load_fundamental_config')
    @patch('src.core.monitoring_service.MonitoringService._load_stale_order_config')
    def test_cleanup_disabled_in_config(self, mock_load_stale, mock_load_fund, mock_yaml, mock_etoro_client, mock_database):
        """When disabled in config, cleanup is skipped."""
        mock_load_fund.return_value = {'check_interval_hours': 24}
        mock_load_stale.return_value = {
            'enabled': False,
            'pending_timeout_hours': 24,
            'submitted_timeout_hours': 48,
        }

        service = MonitoringService(etoro_client=mock_etoro_client, db=mock_database)
        service.order_monitor = Mock()

        result = service._cleanup_stale_orders()

        assert result.get("skipped") is True
        service.order_monitor.cancel_stale_orders.assert_not_called()

    @patch('src.core.monitoring_service.yaml')
    @patch('src.core.monitoring_service.MonitoringService._load_fundamental_config')
    @patch('src.core.monitoring_service.MonitoringService._load_stale_order_config')
    def test_cleanup_handles_errors_gracefully(self, mock_load_stale, mock_load_fund, mock_yaml, mock_etoro_client, mock_database):
        """Errors in cleanup don't crash the service."""
        mock_load_fund.return_value = {'check_interval_hours': 24}
        mock_load_stale.return_value = {
            'enabled': True,
            'pending_timeout_hours': 24,
            'submitted_timeout_hours': 48,
        }

        service = MonitoringService(etoro_client=mock_etoro_client, db=mock_database)
        service.order_monitor = Mock()
        service.order_monitor.cancel_stale_orders.side_effect = Exception("DB connection lost")

        result = service._cleanup_stale_orders()

        assert "error" in result


class TestLoadStaleOrderConfig:
    """Test _load_stale_order_config reads YAML correctly."""

    @patch('src.core.monitoring_service.MonitoringService._load_fundamental_config')
    def test_loads_config_from_yaml(self, mock_load_fund, mock_etoro_client, mock_database):
        """Config values are read from the YAML file."""
        mock_load_fund.return_value = {'check_interval_hours': 24}

        yaml_content = {
            'position_management': {
                'order_management': {
                    'cancel_stale_orders': True,
                    'stale_order_timeout_hours_pending': 12,
                    'stale_order_timeout_hours_submitted': 36,
                }
            }
        }

        with patch('builtins.open', create=True) as mock_open:
            with patch('src.core.monitoring_service.yaml.safe_load', return_value=yaml_content):
                with patch('pathlib.Path.exists', return_value=True):
                    service = MonitoringService(etoro_client=mock_etoro_client, db=mock_database)

        assert service._stale_order_config['pending_timeout_hours'] == 12
        assert service._stale_order_config['submitted_timeout_hours'] == 36
        assert service._stale_order_config['enabled'] is True

    @patch('src.core.monitoring_service.MonitoringService._load_fundamental_config')
    def test_defaults_when_config_missing(self, mock_load_fund, mock_etoro_client, mock_database):
        """Falls back to defaults when config file is missing."""
        mock_load_fund.return_value = {'check_interval_hours': 24}

        with patch('pathlib.Path.exists', return_value=False):
            service = MonitoringService(etoro_client=mock_etoro_client, db=mock_database)

        assert service._stale_order_config['pending_timeout_hours'] == 24
        assert service._stale_order_config['submitted_timeout_hours'] == 48
        assert service._stale_order_config['enabled'] is True
