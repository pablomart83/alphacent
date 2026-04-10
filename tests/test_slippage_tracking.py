"""Tests for Slippage Tracking in Trade Journal (Task 11.8.9).

Tests cover:
1. Slippage calculation on trade entry (buy and sell sides)
2. Slippage analytics in get_performance_feedback()
3. Metadata enrichment with slippage data
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock

from src.analytics.trade_journal import TradeJournal, TradeJournalEntryORM
from src.models.database import Database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trade_orm(
    symbol="AAPL",
    pnl=100.0,
    pnl_percent=2.0,
    market_regime="trending_up",
    template_type="mean_reversion",
    entry_days_ago=10,
    entry_slippage=None,
    entry_hour=14,
):
    """Create a mock TradeJournalEntryORM with slippage data."""
    t = Mock(spec=TradeJournalEntryORM)
    t.symbol = symbol
    t.pnl = pnl
    t.pnl_percent = pnl_percent
    t.market_regime = market_regime
    t.trade_metadata = {"template_type": template_type}
    t.entry_time = datetime.now().replace(hour=entry_hour) - timedelta(days=entry_days_ago)
    t.exit_time = datetime.now() - timedelta(days=entry_days_ago - 1)
    t.entry_slippage = entry_slippage
    return t


@pytest.fixture
def mock_database():
    db = Mock(spec=Database)
    session = MagicMock()
    db.get_session.return_value = session
    return db, session


@pytest.fixture
def trade_journal(mock_database):
    db, _ = mock_database
    return TradeJournal(db)


# ---------------------------------------------------------------------------
# Slippage Calculation on Entry
# ---------------------------------------------------------------------------

class TestSlippageCalculation:
    """Test slippage calculation when logging trade entries."""

    def test_buy_slippage_positive_when_filled_higher(self, trade_journal, mock_database):
        """Buy filled at higher price than expected = positive (bad) slippage."""
        _, session = mock_database

        trade_journal.log_entry(
            trade_id="trade_001",
            strategy_id="strat_001",
            symbol="AAPL",
            entry_time=datetime.now(),
            entry_price=151.0,  # filled higher
            entry_size=100.0,
            entry_reason="Long entry",
            expected_price=150.0,
            order_side="BUY",
        )

        added_entry = session.add.call_args[0][0]
        # (151 - 150) / 150 = 0.00667
        assert added_entry.entry_slippage == pytest.approx(0.00667, rel=0.01)

    def test_buy_slippage_negative_when_filled_lower(self, trade_journal, mock_database):
        """Buy filled at lower price than expected = negative (good) slippage."""
        _, session = mock_database

        trade_journal.log_entry(
            trade_id="trade_002",
            strategy_id="strat_001",
            symbol="AAPL",
            entry_time=datetime.now(),
            entry_price=149.0,  # filled lower
            entry_size=100.0,
            entry_reason="Long entry",
            expected_price=150.0,
            order_side="BUY",
        )

        added_entry = session.add.call_args[0][0]
        # (149 - 150) / 150 = -0.00667
        assert added_entry.entry_slippage == pytest.approx(-0.00667, rel=0.01)

    def test_sell_slippage_positive_when_filled_lower(self, trade_journal, mock_database):
        """Sell filled at lower price than expected = positive (bad) slippage."""
        _, session = mock_database

        trade_journal.log_entry(
            trade_id="trade_003",
            strategy_id="strat_001",
            symbol="AAPL",
            entry_time=datetime.now(),
            entry_price=149.0,  # filled lower
            entry_size=100.0,
            entry_reason="Short entry",
            expected_price=150.0,
            order_side="SELL",
        )

        added_entry = session.add.call_args[0][0]
        # (150 - 149) / 150 = 0.00667
        assert added_entry.entry_slippage == pytest.approx(0.00667, rel=0.01)

    def test_sell_slippage_negative_when_filled_higher(self, trade_journal, mock_database):
        """Sell filled at higher price than expected = negative (good) slippage."""
        _, session = mock_database

        trade_journal.log_entry(
            trade_id="trade_004",
            strategy_id="strat_001",
            symbol="AAPL",
            entry_time=datetime.now(),
            entry_price=151.0,  # filled higher
            entry_size=100.0,
            entry_reason="Short entry",
            expected_price=150.0,
            order_side="SELL",
        )

        added_entry = session.add.call_args[0][0]
        # (150 - 151) / 150 = -0.00667
        assert added_entry.entry_slippage == pytest.approx(-0.00667, rel=0.01)

    def test_no_slippage_when_no_expected_price(self, trade_journal, mock_database):
        """No slippage calculated when expected_price is not provided."""
        _, session = mock_database

        trade_journal.log_entry(
            trade_id="trade_005",
            strategy_id="strat_001",
            symbol="AAPL",
            entry_time=datetime.now(),
            entry_price=150.0,
            entry_size=100.0,
            entry_reason="Long entry",
        )

        added_entry = session.add.call_args[0][0]
        assert added_entry.entry_slippage is None

    def test_zero_slippage_when_prices_match(self, trade_journal, mock_database):
        """Zero slippage when filled at expected price."""
        _, session = mock_database

        trade_journal.log_entry(
            trade_id="trade_006",
            strategy_id="strat_001",
            symbol="AAPL",
            entry_time=datetime.now(),
            entry_price=150.0,
            entry_size=100.0,
            entry_reason="Long entry",
            expected_price=150.0,
            order_side="BUY",
        )

        added_entry = session.add.call_args[0][0]
        assert added_entry.entry_slippage == pytest.approx(0.0)

    def test_metadata_enriched_with_slippage(self, trade_journal, mock_database):
        """Metadata should contain slippage info."""
        _, session = mock_database

        trade_journal.log_entry(
            trade_id="trade_007",
            strategy_id="strat_001",
            symbol="AAPL",
            entry_time=datetime.now(),
            entry_price=151.0,
            entry_size=100.0,
            entry_reason="Long entry",
            expected_price=150.0,
            order_side="BUY",
            metadata={"template_type": "momentum"},
        )

        added_entry = session.add.call_args[0][0]
        meta = added_entry.trade_metadata
        assert "entry_slippage_pct" in meta
        assert "expected_price" in meta
        assert "order_side" in meta
        assert meta["expected_price"] == 150.0
        assert meta["order_side"] == "BUY"
        # Original metadata preserved
        assert meta["template_type"] == "momentum"


# ---------------------------------------------------------------------------
# Slippage Analytics in get_performance_feedback
# ---------------------------------------------------------------------------

class TestSlippageAnalytics:
    """Test slippage analytics in get_performance_feedback."""

    def test_slippage_analytics_with_data(self, trade_journal, mock_database):
        """Slippage analytics computed when trades have slippage data."""
        _, session = mock_database

        trades = [
            _make_trade_orm(symbol="AAPL", entry_slippage=0.001, entry_hour=10, pnl=100, pnl_percent=2.0),
            _make_trade_orm(symbol="AAPL", entry_slippage=0.002, entry_hour=10, pnl=50, pnl_percent=1.0),
            _make_trade_orm(symbol="MSFT", entry_slippage=0.003, entry_hour=14, pnl=-30, pnl_percent=-0.5),
            _make_trade_orm(symbol="MSFT", entry_slippage=0.001, entry_hour=14, pnl=80, pnl_percent=1.5),
            _make_trade_orm(symbol="GOOGL", entry_slippage=0.005, entry_hour=16, pnl=200, pnl_percent=3.0),
        ]

        query = session.query.return_value.filter.return_value
        query.all.return_value = trades

        result = trade_journal.get_performance_feedback(lookback_days=60, min_trades=3)

        assert result["has_sufficient_data"] is True
        slippage = result["slippage_analytics"]

        # Average slippage: (0.001 + 0.002 + 0.003 + 0.001 + 0.005) / 5 = 0.0024
        assert slippage["avg_slippage_pct"] == pytest.approx(0.0024)
        assert slippage["trades_with_slippage"] == 5

        # By symbol
        assert slippage["slippage_by_symbol"]["AAPL"] == pytest.approx(0.0015)  # (0.001+0.002)/2
        assert slippage["slippage_by_symbol"]["MSFT"] == pytest.approx(0.002)   # (0.003+0.001)/2
        assert slippage["slippage_by_symbol"]["GOOGL"] == pytest.approx(0.005)

        # By hour
        assert 10 in slippage["slippage_by_hour"]
        assert 14 in slippage["slippage_by_hour"]
        assert 16 in slippage["slippage_by_hour"]

    def test_slippage_analytics_no_slippage_data(self, trade_journal, mock_database):
        """Slippage analytics returns zeros when no trades have slippage."""
        _, session = mock_database

        trades = [
            _make_trade_orm(entry_slippage=None),
            _make_trade_orm(entry_slippage=None),
            _make_trade_orm(entry_slippage=None),
            _make_trade_orm(entry_slippage=None),
            _make_trade_orm(entry_slippage=None),
        ]

        query = session.query.return_value.filter.return_value
        query.all.return_value = trades

        result = trade_journal.get_performance_feedback(lookback_days=60, min_trades=3)

        slippage = result["slippage_analytics"]
        assert slippage["avg_slippage_pct"] == 0.0
        assert slippage["trades_with_slippage"] == 0
        assert slippage["slippage_by_symbol"] == {}
        assert slippage["slippage_by_hour"] == {}

    def test_slippage_cost_as_pct_of_returns(self, trade_journal, mock_database):
        """Total slippage cost calculated as % of gross returns."""
        _, session = mock_database

        trades = [
            _make_trade_orm(entry_slippage=0.01, pnl=100, pnl_percent=5.0),
            _make_trade_orm(entry_slippage=0.02, pnl=-50, pnl_percent=-2.5),
            _make_trade_orm(entry_slippage=0.01, pnl=80, pnl_percent=4.0),
            _make_trade_orm(entry_slippage=0.005, pnl=60, pnl_percent=3.0),
            _make_trade_orm(entry_slippage=0.015, pnl=-20, pnl_percent=-1.0),
        ]

        query = session.query.return_value.filter.return_value
        query.all.return_value = trades

        result = trade_journal.get_performance_feedback(lookback_days=60, min_trades=3)

        slippage = result["slippage_analytics"]
        # Total abs slippage: 0.01 + 0.02 + 0.01 + 0.005 + 0.015 = 0.06
        # Gross returns: |5.0| + |2.5| + |4.0| + |3.0| + |1.0| = 15.5
        # Cost pct: 0.06 / 15.5 * 100 = 0.387%
        assert slippage["total_slippage_cost_pct"] == pytest.approx(0.387, rel=0.01)

    def test_insufficient_data_returns_no_slippage(self, trade_journal, mock_database):
        """When insufficient data, slippage_analytics not in result."""
        _, session = mock_database

        query = session.query.return_value.filter.return_value
        query.all.return_value = [_make_trade_orm()]  # only 1 trade

        result = trade_journal.get_performance_feedback(lookback_days=60, min_trades=5)

        assert result["has_sufficient_data"] is False
        # No slippage_analytics key when insufficient data
        assert "slippage_analytics" not in result
