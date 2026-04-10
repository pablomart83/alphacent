"""Tests for Portfolio Manager."""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

from src.models.dataclasses import (
    BacktestResults,
    PerformanceMetrics,
    RiskConfig,
    Strategy,
)
from src.models.enums import StrategyStatus, TradingMode
from src.strategy.portfolio_manager import PortfolioManager


@pytest.fixture
def mock_strategy_engine():
    """Create mock strategy engine."""
    engine = Mock()
    engine.db = Mock()
    engine.db.get_session = Mock()
    return engine


@pytest.fixture
def portfolio_manager(mock_strategy_engine):
    """Create portfolio manager instance."""
    return PortfolioManager(mock_strategy_engine)


@pytest.fixture
def sample_strategy():
    """Create sample strategy."""
    return Strategy(
        id="test-strategy-1",
        name="Test Strategy",
        description="Test strategy for portfolio manager",
        status=StrategyStatus.BACKTESTED,
        rules={"entry": ["RSI < 30"], "exit": ["RSI > 70"]},
        symbols=["AAPL", "GOOGL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics(
            total_return=0.15,
            sharpe_ratio=1.8,
            max_drawdown=0.10,
            win_rate=0.55,
            total_trades=50,
        ),
    )


@pytest.fixture
def good_backtest_results():
    """Create backtest results that pass activation criteria."""
    return BacktestResults(
        total_return=0.25,
        sharpe_ratio=2.0,
        sortino_ratio=2.5,
        max_drawdown=0.12,
        win_rate=0.60,
        avg_win=0.03,
        avg_loss=-0.015,
        total_trades=30,
    )


@pytest.fixture
def poor_backtest_results():
    """Create backtest results that fail activation criteria."""
    return BacktestResults(
        total_return=0.05,
        sharpe_ratio=0.8,
        sortino_ratio=1.0,
        max_drawdown=0.20,
        win_rate=0.40,
        avg_win=0.02,
        avg_loss=-0.02,
        total_trades=15,
    )


class TestEvaluateForActivation:
    """Tests for evaluate_for_activation method."""

    def test_passes_all_criteria(self, portfolio_manager, sample_strategy, good_backtest_results):
        """Test strategy that passes all activation criteria."""
        result = portfolio_manager.evaluate_for_activation(
            sample_strategy, good_backtest_results
        )
        assert result is True

    def test_fails_sharpe_ratio(self, portfolio_manager, sample_strategy):
        """Test strategy fails due to low Sharpe ratio."""
        backtest = BacktestResults(
            total_return=0.10,
            sharpe_ratio=1.2,  # <= 1.5
            sortino_ratio=1.5,
            max_drawdown=0.10,
            win_rate=0.55,
            avg_win=0.02,
            avg_loss=-0.01,
            total_trades=25,
        )
        result = portfolio_manager.evaluate_for_activation(sample_strategy, backtest)
        assert result is False

    def test_fails_max_drawdown(self, portfolio_manager, sample_strategy):
        """Test strategy fails due to high max drawdown."""
        backtest = BacktestResults(
            total_return=0.20,
            sharpe_ratio=2.0,
            sortino_ratio=2.5,
            max_drawdown=0.18,  # >= 0.15
            win_rate=0.55,
            avg_win=0.03,
            avg_loss=-0.015,
            total_trades=25,
        )
        result = portfolio_manager.evaluate_for_activation(sample_strategy, backtest)
        assert result is False

    def test_fails_win_rate(self, portfolio_manager, sample_strategy):
        """Test strategy fails due to low win rate."""
        backtest = BacktestResults(
            total_return=0.15,
            sharpe_ratio=1.8,
            sortino_ratio=2.0,
            max_drawdown=0.10,
            win_rate=0.45,  # <= 0.5
            avg_win=0.03,
            avg_loss=-0.015,
            total_trades=25,
        )
        result = portfolio_manager.evaluate_for_activation(sample_strategy, backtest)
        assert result is False

    def test_fails_insufficient_trades(self, portfolio_manager, sample_strategy):
        """Test strategy fails due to insufficient trades."""
        backtest = BacktestResults(
            total_return=0.20,
            sharpe_ratio=2.0,
            sortino_ratio=2.5,
            max_drawdown=0.10,
            win_rate=0.60,
            avg_win=0.03,
            avg_loss=-0.015,
            total_trades=15,  # <= 20
        )
        result = portfolio_manager.evaluate_for_activation(sample_strategy, backtest)
        assert result is False

    def test_edge_case_exact_thresholds(self, portfolio_manager, sample_strategy):
        """Test strategy at exact threshold values."""
        # Sharpe exactly 1.5 should fail (needs to be > 1.5)
        backtest = BacktestResults(
            total_return=0.15,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=0.10,
            win_rate=0.55,
            avg_win=0.02,
            avg_loss=-0.01,
            total_trades=25,
        )
        result = portfolio_manager.evaluate_for_activation(sample_strategy, backtest)
        assert result is False


class TestAutoActivateStrategy:
    """Tests for auto_activate_strategy method."""

    def test_activates_with_calculated_allocation(
        self, portfolio_manager, sample_strategy, mock_strategy_engine
    ):
        """Test auto-activation with calculated allocation."""
        # Mock 2 active strategies
        mock_strategy_engine.get_active_strategies.return_value = [Mock(), Mock()]

        portfolio_manager.auto_activate_strategy(sample_strategy)

        # Should calculate 100 / 3 = 33.33% allocation
        mock_strategy_engine.activate_strategy.assert_called_once()
        call_args = mock_strategy_engine.activate_strategy.call_args
        assert call_args[1]["strategy_id"] == sample_strategy.id
        assert call_args[1]["mode"] == TradingMode.DEMO
        assert abs(call_args[1]["allocation_percent"] - 33.33) < 0.01

    def test_activates_with_custom_allocation(
        self, portfolio_manager, sample_strategy, mock_strategy_engine
    ):
        """Test auto-activation with custom allocation."""
        mock_strategy_engine.get_active_strategies.return_value = []

        portfolio_manager.auto_activate_strategy(sample_strategy, allocation_pct=15.0)

        mock_strategy_engine.activate_strategy.assert_called_once_with(
            strategy_id=sample_strategy.id, mode=TradingMode.DEMO, allocation_percent=15.0
        )

    def test_fails_at_max_strategies(
        self, portfolio_manager, sample_strategy, mock_strategy_engine
    ):
        """Test activation fails when at maximum strategies."""
        # Mock 10 active strategies (max)
        mock_strategy_engine.get_active_strategies.return_value = [Mock()] * 10

        with pytest.raises(ValueError, match="already at maximum of 10 active strategies"):
            portfolio_manager.auto_activate_strategy(sample_strategy)

    def test_first_strategy_gets_100_percent(
        self, portfolio_manager, sample_strategy, mock_strategy_engine
    ):
        """Test first strategy gets 100% allocation."""
        mock_strategy_engine.get_active_strategies.return_value = []

        portfolio_manager.auto_activate_strategy(sample_strategy)

        call_args = mock_strategy_engine.activate_strategy.call_args
        assert call_args[1]["allocation_percent"] == 100.0


class TestCheckRetirementTriggers:
    """Tests for check_retirement_triggers method (live-data based)."""

    def _mock_positions(self, portfolio_manager, closed=None, open_pos=None):
        """Helper to mock DB session returning positions."""
        closed = closed or []
        open_pos = open_pos or []
        all_positions = closed + open_pos
        mock_session = Mock()
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.all.return_value = all_positions
        mock_query.filter.return_value = mock_filter
        mock_session.query.return_value = mock_query
        portfolio_manager.strategy_engine.db.get_session.return_value = mock_session

    def _make_position(self, pnl, closed=True, invested=1000):
        """Create a mock position."""
        p = Mock()
        p.strategy_id = "test-strategy-1"
        p.realized_pnl = pnl if closed else 0
        p.unrealized_pnl = 0 if closed else pnl
        p.closed_at = datetime.now() if closed else None
        p.invested_amount = invested
        p.quantity = invested
        return p

    def test_no_retirement_no_positions(self, portfolio_manager, sample_strategy):
        """No positions → no retirement."""
        sample_strategy.activated_at = datetime.now() - __import__('datetime').timedelta(days=30)
        self._mock_positions(portfolio_manager)
        result = portfolio_manager.check_retirement_triggers(sample_strategy)
        assert result is None

    def test_no_retirement_probation_period(self, portfolio_manager, sample_strategy):
        """Strategy within 14-day probation → no retirement."""
        sample_strategy.activated_at = datetime.now() - __import__('datetime').timedelta(days=5)
        closed = [self._make_position(-100) for _ in range(5)]
        self._mock_positions(portfolio_manager, closed=closed)
        result = portfolio_manager.check_retirement_triggers(sample_strategy)
        assert result is None

    def test_no_retirement_too_few_closed(self, portfolio_manager, sample_strategy):
        """Less than 3 closed trades → no retirement."""
        sample_strategy.activated_at = datetime.now() - __import__('datetime').timedelta(days=30)
        closed = [self._make_position(-100), self._make_position(50)]
        self._mock_positions(portfolio_manager, closed=closed)
        result = portfolio_manager.check_retirement_triggers(sample_strategy)
        assert result is None

    def test_retirement_all_losers(self, portfolio_manager, sample_strategy):
        """3+ closed trades, all losers → retire."""
        sample_strategy.activated_at = datetime.now() - __import__('datetime').timedelta(days=30)
        closed = [self._make_position(-100) for _ in range(4)]
        self._mock_positions(portfolio_manager, closed=closed)
        result = portfolio_manager.check_retirement_triggers(sample_strategy)
        assert result is not None
        assert "0% win rate" in result

    def test_retirement_deep_loss(self, portfolio_manager, sample_strategy):
        """Live return < -10% → retire."""
        sample_strategy.activated_at = datetime.now() - __import__('datetime').timedelta(days=30)
        # Mix of wins and losses but net deeply negative: 1 win +$20, 4 losses -$300 each
        # Total P&L = +20 - 1200 = -$1180 on $5000 invested = -23.6%
        closed = [self._make_position(20, invested=1000)] + [self._make_position(-300, invested=1000) for _ in range(4)]
        self._mock_positions(portfolio_manager, closed=closed)
        result = portfolio_manager.check_retirement_triggers(sample_strategy)
        assert result is not None
        assert "Live return" in result

    def test_retirement_low_win_rate(self, portfolio_manager, sample_strategy):
        """10+ closed trades with low win rate → retire."""
        sample_strategy.activated_at = datetime.now() - __import__('datetime').timedelta(days=30)
        # 2 wins, 9 losses = 18% win rate
        closed = [self._make_position(50) for _ in range(2)] + [self._make_position(-30) for _ in range(9)]
        self._mock_positions(portfolio_manager, closed=closed)
        result = portfolio_manager.check_retirement_triggers(sample_strategy)
        assert result is not None
        assert "win rate" in result.lower()

    def test_no_retirement_good_performance(self, portfolio_manager, sample_strategy):
        """Profitable strategy → no retirement."""
        sample_strategy.activated_at = datetime.now() - __import__('datetime').timedelta(days=30)
        # 7 wins, 3 losses = 70% win rate, positive P&L
        closed = [self._make_position(100) for _ in range(7)] + [self._make_position(-50) for _ in range(3)]
        self._mock_positions(portfolio_manager, closed=closed)
        result = portfolio_manager.check_retirement_triggers(sample_strategy)
        assert result is None

    def test_retirement_all_open_underwater(self, portfolio_manager, sample_strategy):
        """All open positions underwater with >5% loss → retire."""
        sample_strategy.activated_at = datetime.now() - __import__('datetime').timedelta(days=30)
        closed = [self._make_position(50) for _ in range(3)]  # Some closed wins
        # 3 open positions each losing $200 on $1000 = -$600 unrealized on $6000 total = -10%
        open_pos = [self._make_position(-200, closed=False, invested=1000) for _ in range(3)]
        self._mock_positions(portfolio_manager, closed=closed, open_pos=open_pos)
        result = portfolio_manager.check_retirement_triggers(sample_strategy)
        assert result is not None
        assert "underwater" in result


class TestAutoRetireStrategy:
    """Tests for auto_retire_strategy method."""

    def test_retires_strategy_successfully(
        self, portfolio_manager, sample_strategy, mock_strategy_engine
    ):
        """Test successful strategy retirement."""
        # Mock database session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_strategy_engine.db.get_session.return_value = mock_session

        reason = "Low Sharpe ratio"
        portfolio_manager.auto_retire_strategy(sample_strategy, reason)

        # Verify deactivation and retirement were called
        mock_strategy_engine.deactivate_strategy.assert_called_once_with(sample_strategy.id)
        mock_strategy_engine.retire_strategy.assert_called_once_with(
            sample_strategy.id, reason
        )

    def test_closes_open_positions(self, portfolio_manager, sample_strategy, mock_strategy_engine):
        """Test that open positions are closed during retirement."""
        # Mock database session with open positions
        mock_position1 = Mock()
        mock_position1.id = "pos-1"
        mock_position1.symbol = "AAPL"
        mock_position1.quantity = 10
        mock_position1.side = "LONG"

        mock_position2 = Mock()
        mock_position2.id = "pos-2"
        mock_position2.symbol = "GOOGL"
        mock_position2.quantity = 5
        mock_position2.side = "LONG"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [
            mock_position1,
            mock_position2,
        ]
        mock_strategy_engine.db.get_session.return_value = mock_session

        reason = "High drawdown"
        portfolio_manager.auto_retire_strategy(sample_strategy, reason)

        # Verify positions were queried
        mock_session.query.assert_called()

    def test_handles_no_open_positions(
        self, portfolio_manager, sample_strategy, mock_strategy_engine
    ):
        """Test retirement when no open positions exist."""
        # Mock database session with no positions
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_strategy_engine.db.get_session.return_value = mock_session

        reason = "Low win rate"
        portfolio_manager.auto_retire_strategy(sample_strategy, reason)

        # Should still deactivate and retire
        mock_strategy_engine.deactivate_strategy.assert_called_once()
        mock_strategy_engine.retire_strategy.assert_called_once()


class TestIntegration:
    """Integration tests for portfolio manager workflows."""

    def test_full_activation_workflow(
        self, portfolio_manager, sample_strategy, good_backtest_results, mock_strategy_engine
    ):
        """Test complete activation workflow."""
        mock_strategy_engine.get_active_strategies.return_value = []

        # Evaluate
        should_activate = portfolio_manager.evaluate_for_activation(
            sample_strategy, good_backtest_results
        )
        assert should_activate is True

        # Activate
        portfolio_manager.auto_activate_strategy(sample_strategy)

        # Verify activation was called
        mock_strategy_engine.activate_strategy.assert_called_once()

    def test_full_retirement_workflow(
        self, portfolio_manager, sample_strategy, mock_strategy_engine
    ):
        """Test complete retirement workflow."""
        # Set up poor performance
        sample_strategy.performance.sharpe_ratio = 0.3
        sample_strategy.performance.total_trades = 40

        # Mock database
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_strategy_engine.db.get_session.return_value = mock_session

        # Check trigger
        reason = portfolio_manager.check_retirement_triggers(sample_strategy)
        assert reason is not None

        # Retire
        portfolio_manager.auto_retire_strategy(sample_strategy, reason)

        # Verify retirement was called
        mock_strategy_engine.retire_strategy.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
