"""Tests for Alpha Edge-specific activation thresholds in PortfolioManager."""

import pytest
from datetime import datetime
from unittest.mock import Mock

from src.models.dataclasses import (
    BacktestResults,
    PerformanceMetrics,
    RiskConfig,
    Strategy,
)
from src.models.enums import StrategyStatus
from src.strategy.portfolio_manager import PortfolioManager


@pytest.fixture
def portfolio_manager():
    engine = Mock()
    engine.db = Mock()
    engine.db.get_session = Mock()
    return PortfolioManager(engine)


def _make_strategy(is_alpha_edge=False):
    metadata = {}
    if is_alpha_edge:
        metadata['strategy_category'] = 'alpha_edge'
    return Strategy(
        id="test-1",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.BACKTESTED,
        rules={"entry": ["RSI < 30"], "exit": ["RSI > 70"]},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics(
            total_return=0.10, sharpe_ratio=0.5, max_drawdown=0.10,
            win_rate=0.50, total_trades=20,
        ),
        metadata=metadata,
    )


def _make_backtest(sharpe=0.5, win_rate=0.50, max_drawdown=0.10, total_trades=20):
    return BacktestResults(
        total_return=0.10,
        sharpe_ratio=sharpe,
        sortino_ratio=sharpe * 1.2,
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        avg_win=0.03,
        avg_loss=-0.02,
        total_trades=total_trades,
    )


class TestAlphaEdgeActivationThresholds:
    """Alpha Edge strategies should use relaxed thresholds vs DSL strategies."""

    def test_dsl_rejects_sharpe_025(self, portfolio_manager):
        """DSL strategy with Sharpe 0.25 should be rejected (threshold 0.3)."""
        strategy = _make_strategy(is_alpha_edge=False)
        bt = _make_backtest(sharpe=0.25, win_rate=0.50, max_drawdown=0.10)
        assert portfolio_manager.evaluate_for_activation(strategy, bt) is False

    def test_alpha_edge_accepts_sharpe_025(self, portfolio_manager):
        """Alpha Edge strategy with Sharpe 0.25 should pass (threshold 0.2)."""
        strategy = _make_strategy(is_alpha_edge=True)
        bt = _make_backtest(sharpe=0.25, win_rate=0.50, max_drawdown=0.10)
        assert portfolio_manager.evaluate_for_activation(strategy, bt) is True

    def test_alpha_edge_rejects_sharpe_015(self, portfolio_manager):
        """Alpha Edge strategy with Sharpe 0.15 should still be rejected (below 0.2)."""
        strategy = _make_strategy(is_alpha_edge=True)
        bt = _make_backtest(sharpe=0.15, win_rate=0.50, max_drawdown=0.10)
        assert portfolio_manager.evaluate_for_activation(strategy, bt) is False

    def test_dsl_rejects_drawdown_025(self, portfolio_manager):
        """DSL strategy with 25% drawdown should be rejected (threshold 20%)."""
        strategy = _make_strategy(is_alpha_edge=False)
        bt = _make_backtest(sharpe=0.5, win_rate=0.50, max_drawdown=0.25)
        assert portfolio_manager.evaluate_for_activation(strategy, bt) is False

    def test_alpha_edge_accepts_drawdown_025(self, portfolio_manager):
        """Alpha Edge strategy with 25% drawdown should pass (threshold 30%)."""
        strategy = _make_strategy(is_alpha_edge=True)
        bt = _make_backtest(sharpe=0.5, win_rate=0.50, max_drawdown=0.25)
        assert portfolio_manager.evaluate_for_activation(strategy, bt) is True

    def test_dsl_rejects_win_rate_037(self, portfolio_manager):
        """DSL strategy with 37% win rate should be rejected (threshold 40%)."""
        strategy = _make_strategy(is_alpha_edge=False)
        bt = _make_backtest(sharpe=0.5, win_rate=0.37, max_drawdown=0.10)
        assert portfolio_manager.evaluate_for_activation(strategy, bt) is False

    def test_alpha_edge_accepts_win_rate_037(self, portfolio_manager):
        """Alpha Edge strategy with 37% win rate should pass (threshold 35%)."""
        strategy = _make_strategy(is_alpha_edge=True)
        bt = _make_backtest(sharpe=0.5, win_rate=0.37, max_drawdown=0.10)
        assert portfolio_manager.evaluate_for_activation(strategy, bt) is True

    def test_alpha_edge_rejects_win_rate_030(self, portfolio_manager):
        """Alpha Edge strategy with 30% win rate should be rejected (below 35%)."""
        strategy = _make_strategy(is_alpha_edge=True)
        bt = _make_backtest(sharpe=0.5, win_rate=0.30, max_drawdown=0.10)
        assert portfolio_manager.evaluate_for_activation(strategy, bt) is False
