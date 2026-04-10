"""Tests for the Strategy Performance Feedback Loop (Task 11.7.3).

Tests cover:
1. TradeJournal.get_performance_feedback() — analyzes recent trades
2. StrategyProposer.apply_performance_feedback() — adjusts weights
3. Integration: feedback flows through _match_templates_to_symbols scoring
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch

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
):
    """Create a mock TradeJournalEntryORM with the given attributes."""
    t = Mock(spec=TradeJournalEntryORM)
    t.symbol = symbol
    t.pnl = pnl
    t.pnl_percent = pnl_percent
    t.market_regime = market_regime
    t.trade_metadata = {"template_type": template_type}
    t.entry_time = datetime.now() - timedelta(days=entry_days_ago)
    t.exit_time = datetime.now() - timedelta(days=entry_days_ago - 1)
    t.entry_slippage = None
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
# TradeJournal.get_performance_feedback
# ---------------------------------------------------------------------------

class TestGetPerformanceFeedback:

    def test_insufficient_data_returns_empty(self, trade_journal, mock_database):
        """When fewer trades than min_trades, has_sufficient_data is False."""
        _, session = mock_database
        query = session.query.return_value.filter.return_value
        query.all.return_value = [_make_trade_orm()]  # only 1 trade

        result = trade_journal.get_performance_feedback(lookback_days=60, min_trades=5)

        assert result["has_sufficient_data"] is False
        assert result["total_trades"] == 1
        assert result["template_performance"] == {}
        assert result["symbol_performance"] == {}
        assert result["regime_performance"] == {}

    def test_sufficient_data_returns_metrics(self, trade_journal, mock_database):
        """With enough trades, returns template, symbol, and regime metrics."""
        _, session = mock_database

        trades = [
            _make_trade_orm(symbol="AAPL", pnl=100, pnl_percent=2.0, template_type="mean_reversion", market_regime="trending_up"),
            _make_trade_orm(symbol="AAPL", pnl=50, pnl_percent=1.0, template_type="mean_reversion", market_regime="trending_up"),
            _make_trade_orm(symbol="AAPL", pnl=-30, pnl_percent=-0.5, template_type="mean_reversion", market_regime="trending_up"),
            _make_trade_orm(symbol="MSFT", pnl=200, pnl_percent=3.0, template_type="trend_following", market_regime="trending_up"),
            _make_trade_orm(symbol="MSFT", pnl=-100, pnl_percent=-2.0, template_type="trend_following", market_regime="ranging"),
            _make_trade_orm(symbol="MSFT", pnl=80, pnl_percent=1.5, template_type="trend_following", market_regime="ranging"),
            _make_trade_orm(symbol="MSFT", pnl=-50, pnl_percent=-1.0, template_type="trend_following", market_regime="ranging"),
            _make_trade_orm(symbol="MSFT", pnl=60, pnl_percent=1.2, template_type="trend_following", market_regime="ranging"),
        ]

        query = session.query.return_value.filter.return_value
        query.all.return_value = trades

        result = trade_journal.get_performance_feedback(lookback_days=60, min_trades=3)

        assert result["has_sufficient_data"] is True
        assert result["total_trades"] == 8

        # Template performance: mean_reversion has 3 trades (2 wins), trend_following has 5 (3 wins)
        tp = result["template_performance"]
        assert "mean_reversion" in tp
        assert tp["mean_reversion"]["total_trades"] == 3
        assert tp["mean_reversion"]["win_rate"] == pytest.approx(66.67, abs=0.1)

        assert "trend_following" in tp
        assert tp["trend_following"]["total_trades"] == 5
        assert tp["trend_following"]["win_rate"] == pytest.approx(60.0, abs=0.1)

        # Symbol performance: AAPL has 3 trades, MSFT has 5
        sp = result["symbol_performance"]
        assert "AAPL" in sp
        assert sp["AAPL"]["total_trades"] == 3
        assert "MSFT" in sp
        assert sp["MSFT"]["total_trades"] == 5

    def test_groups_below_min_trades_excluded(self, trade_journal, mock_database):
        """Groups with fewer trades than min_trades are excluded from results."""
        _, session = mock_database

        # 5 trades for mean_reversion, 2 for trend_following (below min_trades=3)
        trades = [
            _make_trade_orm(template_type="mean_reversion", pnl=100),
            _make_trade_orm(template_type="mean_reversion", pnl=50),
            _make_trade_orm(template_type="mean_reversion", pnl=-30),
            _make_trade_orm(template_type="mean_reversion", pnl=80),
            _make_trade_orm(template_type="mean_reversion", pnl=-20),
            _make_trade_orm(template_type="trend_following", pnl=100),
            _make_trade_orm(template_type="trend_following", pnl=-50),
        ]

        query = session.query.return_value.filter.return_value
        query.all.return_value = trades

        result = trade_journal.get_performance_feedback(lookback_days=60, min_trades=3)

        assert result["has_sufficient_data"] is True
        tp = result["template_performance"]
        assert "mean_reversion" in tp
        assert "trend_following" not in tp  # only 2 trades, below min_trades=3


# ---------------------------------------------------------------------------
# StrategyProposer.apply_performance_feedback
# ---------------------------------------------------------------------------

class TestApplyPerformanceFeedback:

    def _make_proposer(self):
        """Create a StrategyProposer with mocked dependencies."""
        from src.strategy.strategy_proposer import StrategyProposer

        with patch.object(StrategyProposer, '__init__', lambda self, *a, **kw: None):
            proposer = StrategyProposer.__new__(StrategyProposer)
            proposer._template_weights = {}
            proposer._symbol_scores = {}
            proposer._regime_template_preferences = {}
            return proposer

    def test_insufficient_data_clears_weights(self):
        """When feedback has insufficient data, weights are cleared."""
        proposer = self._make_proposer()
        proposer._template_weights = {"old": 1.5}

        proposer.apply_performance_feedback({"has_sufficient_data": False, "total_trades": 2})

        assert proposer._template_weights == {}
        assert proposer._symbol_scores == {}

    def test_template_weights_computed_from_win_rate(self):
        """Template weights scale linearly with win rate around 50% baseline."""
        proposer = self._make_proposer()

        feedback = {
            "has_sufficient_data": True,
            "total_trades": 20,
            "template_performance": {
                "mean_reversion": {"win_rate": 70.0, "total_trades": 10, "total_pnl": 500, "avg_return_pct": 2.0},
                "trend_following": {"win_rate": 30.0, "total_trades": 10, "total_pnl": -200, "avg_return_pct": -1.0},
            },
            "symbol_performance": {},
            "regime_performance": {},
        }

        proposer.apply_performance_feedback(feedback, max_weight=2.0, min_weight=0.3)

        # 70% win rate → 1.0 + (70-50)/50 = 1.4
        assert proposer._template_weights["mean_reversion"] == pytest.approx(1.4, abs=0.01)
        # 30% win rate → 1.0 + (30-50)/50 = 0.6
        assert proposer._template_weights["trend_following"] == pytest.approx(0.6, abs=0.01)

    def test_template_weights_clamped(self):
        """Template weights are clamped to [min_weight, max_weight]."""
        proposer = self._make_proposer()

        feedback = {
            "has_sufficient_data": True,
            "total_trades": 20,
            "template_performance": {
                "super_winner": {"win_rate": 95.0, "total_trades": 10, "total_pnl": 1000, "avg_return_pct": 5.0},
                "super_loser": {"win_rate": 5.0, "total_trades": 10, "total_pnl": -800, "avg_return_pct": -4.0},
            },
            "symbol_performance": {},
            "regime_performance": {},
        }

        proposer.apply_performance_feedback(feedback, max_weight=2.0, min_weight=0.3)

        # 95% → raw 1.9, clamped to 1.9 (within 2.0)
        assert proposer._template_weights["super_winner"] == pytest.approx(1.9, abs=0.01)
        # 5% → raw 0.1, clamped to 0.3
        assert proposer._template_weights["super_loser"] == pytest.approx(0.3, abs=0.01)

    def test_symbol_scores_computed(self):
        """Symbol scores combine win rate deviation and avg return."""
        proposer = self._make_proposer()

        feedback = {
            "has_sufficient_data": True,
            "total_trades": 20,
            "template_performance": {},
            "symbol_performance": {
                "AAPL": {"win_rate": 70.0, "total_trades": 10, "total_pnl": 500, "avg_return_pct": 2.0},
                "MSFT": {"win_rate": 30.0, "total_trades": 10, "total_pnl": -200, "avg_return_pct": -1.0},
            },
            "regime_performance": {},
        }

        proposer.apply_performance_feedback(feedback)

        # AAPL: (70-50)*0.5 + 2.0*10.0 = 10 + 20 = 30
        assert proposer._symbol_scores["AAPL"] == pytest.approx(30.0, abs=0.01)
        # MSFT: (30-50)*0.5 + (-1.0)*10.0 = -10 + -10 = -20
        assert proposer._symbol_scores["MSFT"] == pytest.approx(-20.0, abs=0.01)

    def test_regime_preferences_stored(self):
        """Regime-specific template preferences are stored."""
        proposer = self._make_proposer()

        feedback = {
            "has_sufficient_data": True,
            "total_trades": 20,
            "template_performance": {},
            "symbol_performance": {},
            "regime_performance": {
                "trending_up": {
                    "total_trades": 10,
                    "win_rate": 65.0,
                    "total_pnl": 300,
                    "best_template_win_rates": {"trend_following": 80.0, "mean_reversion": 40.0},
                },
            },
        }

        proposer.apply_performance_feedback(feedback)

        assert "trending_up" in proposer._regime_template_preferences
        assert proposer._regime_template_preferences["trending_up"]["trend_following"] == 80.0
