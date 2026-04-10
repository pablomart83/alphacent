"""Tests for fundamental position monitoring (task 11.7.7)."""

import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.core.monitoring_service import MonitoringService
from src.models.orm import PositionORM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_position(symbol: str, side: str = "BUY", sector: str = "Technology") -> PositionORM:
    """Create a minimal PositionORM-like mock for testing."""
    pos = MagicMock(spec=PositionORM)
    pos.id = f"pos_{symbol.lower()}"
    pos.symbol = symbol
    pos.side = side
    pos.closed_at = None
    pos.pending_closure = False
    pos.closure_reason = None
    return pos


def _build_service(fundamental_config: dict = None) -> MonitoringService:
    """Build a MonitoringService with mocked dependencies."""
    config = fundamental_config or {
        "enabled": True,
        "check_interval_hours": 24,
        "earnings_miss_threshold": -0.05,
        "revenue_decline_exit": True,
        "sector_rotation_exit": True,
    }

    with patch("src.core.monitoring_service.yaml") as mock_yaml, \
         patch("src.core.monitoring_service.Database"), \
         patch("src.core.order_monitor.OrderMonitor"):
        mock_yaml.safe_load.return_value = {
            "alpha_edge": {"fundamental_monitoring": config}
        }
        mock_open = MagicMock()
        mock_yaml.safe_load.return_value = {
            "alpha_edge": {"fundamental_monitoring": config}
        }
        svc = MonitoringService.__new__(MonitoringService)
        svc.etoro_client = MagicMock()
        svc.db = MagicMock()
        svc.order_monitor = MagicMock()
        svc.pending_orders_interval = 5
        svc.order_status_interval = 30
        svc.position_sync_interval = 60
        svc.trailing_stops_interval = 5
        svc._running = False
        svc._task = None
        svc._last_pending_check = 0
        svc._last_order_check = 0
        svc._last_position_sync = 0
        svc._last_trailing_check = 0
        svc._last_fundamental_check = 0
        svc._fundamental_config = config
        svc._fundamental_check_interval = config.get("check_interval_hours", 24) * 3600
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCheckFundamentalExits:
    """Tests for MonitoringService._check_fundamental_exits()."""

    def test_disabled_config_skips_check(self):
        """When fundamental monitoring is disabled, no positions are checked."""
        svc = _build_service({"enabled": False})
        result = svc._check_fundamental_exits()
        assert result["checked"] == 0
        assert result["flagged"] == 0
        assert result.get("skipped_disabled") is True

    def test_no_open_positions(self):
        """When there are no open positions, returns zeros."""
        svc = _build_service()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        svc.db.get_session.return_value = mock_session

        result = svc._check_fundamental_exits()
        assert result["checked"] == 0
        assert result["flagged"] == 0

    @patch("src.core.monitoring_service.MonitoringService._get_regime_and_sectors")
    @patch("src.core.monitoring_service.MonitoringService._get_fundamental_provider")
    def test_earnings_miss_flags_position(self, mock_provider_fn, mock_regime_fn):
        """A position with earnings surprise < -5% is flagged for closure."""
        svc = _build_service()

        pos = _make_position("AAPL")
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [pos]
        svc.db.get_session.return_value = mock_session

        provider = MagicMock()
        provider.calculate_earnings_surprise.return_value = -0.10  # -10% miss
        provider.get_revenue_growth.return_value = 0.05  # positive — no issue
        mock_provider_fn.return_value = provider

        mock_regime_fn.return_value = ("ranging_low_vol", ["XLK", "XLF", "XLI"])

        result = svc._check_fundamental_exits()
        assert result["checked"] == 1
        assert result["flagged"] == 1
        assert pos.pending_closure is True
        assert "Earnings miss" in pos.closure_reason

    @patch("src.core.monitoring_service.MonitoringService._get_regime_and_sectors")
    @patch("src.core.monitoring_service.MonitoringService._get_fundamental_provider")
    def test_revenue_decline_flags_position(self, mock_provider_fn, mock_regime_fn):
        """A position with negative revenue growth is flagged for closure."""
        svc = _build_service()

        pos = _make_position("MSFT")
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [pos]
        svc.db.get_session.return_value = mock_session

        provider = MagicMock()
        provider.calculate_earnings_surprise.return_value = 0.02  # fine
        provider.get_revenue_growth.return_value = -0.03  # negative growth
        mock_provider_fn.return_value = provider

        mock_regime_fn.return_value = ("ranging_low_vol", ["XLK", "XLF", "XLI"])

        result = svc._check_fundamental_exits()
        assert result["flagged"] == 1
        assert pos.pending_closure is True
        assert "Revenue decline" in pos.closure_reason

    @patch("src.core.monitoring_service.MonitoringService._get_regime_and_sectors")
    @patch("src.core.monitoring_service.MonitoringService._get_fundamental_provider")
    def test_sector_rotation_flags_position(self, mock_provider_fn, mock_regime_fn):
        """A position whose sector is not in optimal sectors is flagged."""
        svc = _build_service()

        # XOM is Energy sector — if regime favors Tech/Finance/Industrials, it should be flagged
        pos = _make_position("XOM")
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [pos]
        svc.db.get_session.return_value = mock_session

        provider = MagicMock()
        provider.calculate_earnings_surprise.return_value = 0.05  # fine
        provider.get_revenue_growth.return_value = 0.10  # fine
        mock_provider_fn.return_value = provider

        # Regime favors Tech, Finance, Industrials — not Energy
        mock_regime_fn.return_value = ("ranging_low_vol", ["XLK", "XLF", "XLI"])

        result = svc._check_fundamental_exits()
        assert result["flagged"] == 1
        assert pos.pending_closure is True
        assert "Sector rotation" in pos.closure_reason

    @patch("src.core.monitoring_service.MonitoringService._get_regime_and_sectors")
    @patch("src.core.monitoring_service.MonitoringService._get_fundamental_provider")
    def test_healthy_position_not_flagged(self, mock_provider_fn, mock_regime_fn):
        """A position passing all checks is not flagged."""
        svc = _build_service()

        pos = _make_position("AAPL")  # Technology sector
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [pos]
        svc.db.get_session.return_value = mock_session

        provider = MagicMock()
        provider.calculate_earnings_surprise.return_value = 0.08  # beat
        provider.get_revenue_growth.return_value = 0.12  # growing
        mock_provider_fn.return_value = provider

        # Technology is in optimal sectors
        mock_regime_fn.return_value = ("ranging_low_vol", ["XLK", "XLF", "XLI"])

        result = svc._check_fundamental_exits()
        assert result["checked"] == 1
        assert result["flagged"] == 0
        assert pos.pending_closure is False

    @patch("src.core.monitoring_service.MonitoringService._get_regime_and_sectors")
    @patch("src.core.monitoring_service.MonitoringService._get_fundamental_provider")
    def test_skips_non_stock_positions(self, mock_provider_fn, mock_regime_fn):
        """Forex, crypto, ETF positions are skipped."""
        svc = _build_service()

        positions = [
            _make_position("EURUSD"),  # Forex
            _make_position("BTC"),     # Crypto
            _make_position("SPY"),     # Broad Market ETF
        ]
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = positions
        svc.db.get_session.return_value = mock_session

        provider = MagicMock()
        mock_provider_fn.return_value = provider
        mock_regime_fn.return_value = ("ranging_low_vol", ["XLK", "XLF", "XLI"])

        result = svc._check_fundamental_exits()
        assert result["checked"] == 0
        assert result["flagged"] == 0
        # Provider methods should never be called for non-stock symbols
        provider.calculate_earnings_surprise.assert_not_called()

    @patch("src.core.monitoring_service.MonitoringService._get_regime_and_sectors")
    @patch("src.core.monitoring_service.MonitoringService._get_fundamental_provider")
    def test_provider_unavailable_returns_gracefully(self, mock_provider_fn, mock_regime_fn):
        """If FundamentalDataProvider can't be created, check returns gracefully."""
        svc = _build_service()

        pos = _make_position("AAPL")
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [pos]
        svc.db.get_session.return_value = mock_session

        mock_provider_fn.return_value = None  # Provider unavailable

        result = svc._check_fundamental_exits()
        assert result["checked"] == 0
        assert result.get("error") == "provider_unavailable"

    @patch("src.core.monitoring_service.MonitoringService._get_regime_and_sectors")
    @patch("src.core.monitoring_service.MonitoringService._get_fundamental_provider")
    def test_multiple_exit_reasons_combined(self, mock_provider_fn, mock_regime_fn):
        """Multiple failing checks produce a combined closure reason."""
        svc = _build_service()

        pos = _make_position("XOM")  # Energy sector
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [pos]
        svc.db.get_session.return_value = mock_session

        provider = MagicMock()
        provider.calculate_earnings_surprise.return_value = -0.08  # miss
        provider.get_revenue_growth.return_value = -0.02  # decline
        mock_provider_fn.return_value = provider

        # Energy not in optimal sectors
        mock_regime_fn.return_value = ("trending_down", ["XLU", "XLP", "XLV"])

        result = svc._check_fundamental_exits()
        assert result["flagged"] == 1
        assert "Earnings miss" in pos.closure_reason
        assert "Revenue decline" in pos.closure_reason
        assert "Sector rotation" in pos.closure_reason

    @patch("src.core.monitoring_service.MonitoringService._get_regime_and_sectors")
    @patch("src.core.monitoring_service.MonitoringService._get_fundamental_provider")
    def test_api_error_is_tolerated(self, mock_provider_fn, mock_regime_fn):
        """If FMP throws an exception for one symbol, the check continues."""
        svc = _build_service()

        pos1 = _make_position("AAPL")
        pos2 = _make_position("MSFT")
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [pos1, pos2]
        svc.db.get_session.return_value = mock_session

        provider = MagicMock()
        # AAPL throws, MSFT has earnings miss
        provider.calculate_earnings_surprise.side_effect = [
            Exception("FMP down"), -0.10
        ]
        provider.get_revenue_growth.return_value = 0.05
        mock_provider_fn.return_value = provider

        mock_regime_fn.return_value = ("ranging_low_vol", ["XLK", "XLF", "XLI"])

        result = svc._check_fundamental_exits()
        assert result["checked"] == 2
        assert result["flagged"] == 1  # Only MSFT flagged
        assert pos1.pending_closure is False
        assert pos2.pending_closure is True


class TestFundamentalCheckInterval:
    """Tests for the daily timer integration."""

    def test_fundamental_check_interval_default(self):
        """Default interval is 24 hours."""
        svc = _build_service()
        assert svc._fundamental_check_interval == 24 * 3600

    def test_fundamental_check_interval_custom(self):
        """Custom interval from config."""
        svc = _build_service({"enabled": True, "check_interval_hours": 12})
        assert svc._fundamental_check_interval == 12 * 3600


class TestGetRevenueGrowth:
    """Tests for FundamentalDataProvider.get_revenue_growth()."""

    def test_returns_revenue_growth(self):
        """Returns revenue growth from cached fundamental data."""
        from src.data.fundamental_data_provider import FundamentalData, FundamentalDataProvider

        provider = MagicMock(spec=FundamentalDataProvider)
        provider.get_revenue_growth = FundamentalDataProvider.get_revenue_growth.__get__(provider)

        mock_data = MagicMock(spec=FundamentalData)
        mock_data.revenue_growth = 0.15
        provider.get_fundamental_data.return_value = mock_data

        result = provider.get_revenue_growth("AAPL")
        assert result == 0.15
        provider.get_fundamental_data.assert_called_once_with("AAPL", use_cache=True)

    def test_returns_none_when_no_data(self):
        """Returns None when fundamental data is unavailable."""
        from src.data.fundamental_data_provider import FundamentalDataProvider

        provider = MagicMock(spec=FundamentalDataProvider)
        provider.get_revenue_growth = FundamentalDataProvider.get_revenue_growth.__get__(provider)
        provider.get_fundamental_data.return_value = None

        result = provider.get_revenue_growth("UNKNOWN")
        assert result is None

    def test_returns_none_on_exception(self):
        """Returns None gracefully on exception."""
        from src.data.fundamental_data_provider import FundamentalDataProvider

        provider = MagicMock(spec=FundamentalDataProvider)
        provider.get_revenue_growth = FundamentalDataProvider.get_revenue_growth.__get__(provider)
        provider.get_fundamental_data.side_effect = Exception("DB error")

        result = provider.get_revenue_growth("AAPL")
        assert result is None
