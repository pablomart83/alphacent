"""Tests for Alpha Edge fallback activation (Task 11.11.10)."""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from src.models.dataclasses import Strategy, StrategyStatus, RiskConfig, BacktestResults


def _make_strategy(name, sharpe=1.0, is_alpha_edge=False, status=StrategyStatus.PROPOSED):
    """Helper to create a test strategy."""
    metadata = {'direction': 'long'}
    if is_alpha_edge:
        metadata['strategy_category'] = 'alpha_edge'
    bt = BacktestResults(
        total_return=0.1, sharpe_ratio=sharpe, sortino_ratio=0.5,
        max_drawdown=0.1, win_rate=0.5, avg_win=0.02, avg_loss=0.01,
        total_trades=20,
    )
    return Strategy(
        id=f"strat-{name}",
        name=name,
        description="test",
        status=status,
        rules={'entry_conditions': []},
        symbols=['AAPL'],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        backtest_results=bt,
        metadata=metadata,
    )


class TestAlphaEdgeFallbackActivation:
    """Tests for _alpha_edge_fallback_activation."""

    def setup_method(self):
        with patch('src.strategy.autonomous_strategy_manager.AutonomousStrategyManager.__init__', return_value=None):
            from src.strategy.autonomous_strategy_manager import AutonomousStrategyManager
            self.manager = AutonomousStrategyManager.__new__(AutonomousStrategyManager)

        self.manager.strategy_engine = Mock()
        self.manager.portfolio_manager = Mock()
        self.manager.websocket_manager = Mock()
        self.manager.config = {"autonomous": {"max_active_strategies": 20}}
        self.manager._safe_broadcast = Mock()

    def test_skips_when_alpha_edge_already_active(self):
        """No fallback needed when Alpha Edge strategies are already active."""
        active_ae = _make_strategy("AE1", is_alpha_edge=True, status=StrategyStatus.DEMO)
        self.manager.strategy_engine.get_active_strategies.return_value = [active_ae]

        stats = {"strategies_activated": 1}
        self.manager._alpha_edge_fallback_activation([], stats)
        self.manager.portfolio_manager.auto_activate_strategy.assert_not_called()

    def test_force_activates_best_alpha_edge(self):
        """When no Alpha Edge is active, force-activate the best one with Sharpe > 0."""
        # No Alpha Edge among active strategies
        dsl_active = _make_strategy("DSL1", status=StrategyStatus.DEMO)
        self.manager.strategy_engine.get_active_strategies.return_value = [dsl_active]

        # Backtested Alpha Edge candidates
        ae_weak = _make_strategy("AE_weak", sharpe=0.2, is_alpha_edge=True)
        ae_strong = _make_strategy("AE_strong", sharpe=0.8, is_alpha_edge=True)

        stats = {"strategies_activated": 1}
        self.manager._alpha_edge_fallback_activation([ae_weak, ae_strong], stats)

        self.manager.portfolio_manager.auto_activate_strategy.assert_called_once_with(
            strategy=ae_strong, backtest_results=ae_strong.backtest_results
        )
        assert stats["strategies_activated"] == 2

    def test_skips_negative_sharpe_alpha_edge(self):
        """Should not force-activate Alpha Edge with Sharpe <= 0."""
        self.manager.strategy_engine.get_active_strategies.return_value = [
            _make_strategy("DSL1", status=StrategyStatus.DEMO)
        ]

        ae_bad = _make_strategy("AE_bad", sharpe=-0.5, is_alpha_edge=True)
        ae_zero = _make_strategy("AE_zero", sharpe=0.0, is_alpha_edge=True)

        stats = {"strategies_activated": 1}
        self.manager._alpha_edge_fallback_activation([ae_bad, ae_zero], stats)

        self.manager.portfolio_manager.auto_activate_strategy.assert_not_called()
        assert stats["strategies_activated"] == 1

    def test_skips_non_alpha_edge_strategies(self):
        """Should only consider Alpha Edge strategies, not DSL ones."""
        self.manager.strategy_engine.get_active_strategies.return_value = [
            _make_strategy("DSL1", status=StrategyStatus.DEMO)
        ]

        dsl_good = _make_strategy("DSL_good", sharpe=1.5, is_alpha_edge=False)

        stats = {"strategies_activated": 1}
        self.manager._alpha_edge_fallback_activation([dsl_good], stats)

        self.manager.portfolio_manager.auto_activate_strategy.assert_not_called()

    def test_skips_already_active_alpha_edge(self):
        """Should not try to activate Alpha Edge that's already DEMO/LIVE."""
        self.manager.strategy_engine.get_active_strategies.return_value = [
            _make_strategy("DSL1", status=StrategyStatus.DEMO)
        ]

        ae_already_active = _make_strategy(
            "AE_active", sharpe=0.9, is_alpha_edge=True, status=StrategyStatus.DEMO
        )

        stats = {"strategies_activated": 1}
        self.manager._alpha_edge_fallback_activation([ae_already_active], stats)

        self.manager.portfolio_manager.auto_activate_strategy.assert_not_called()

    def test_respects_max_strategies_limit(self):
        """Should not force-activate if already at max strategies."""
        self.manager.config = {"autonomous": {"max_active_strategies": 1}}
        self.manager.strategy_engine.get_active_strategies.return_value = [
            _make_strategy("DSL1", status=StrategyStatus.DEMO)
        ]

        ae_good = _make_strategy("AE_good", sharpe=0.5, is_alpha_edge=True)

        stats = {"strategies_activated": 1}
        self.manager._alpha_edge_fallback_activation([ae_good], stats)

        self.manager.portfolio_manager.auto_activate_strategy.assert_not_called()

    def test_handles_no_backtest_results(self):
        """Should skip strategies without backtest results."""
        self.manager.strategy_engine.get_active_strategies.return_value = [
            _make_strategy("DSL1", status=StrategyStatus.DEMO)
        ]

        ae_no_bt = _make_strategy("AE_no_bt", sharpe=0.5, is_alpha_edge=True)
        ae_no_bt.backtest_results = None

        stats = {"strategies_activated": 1}
        self.manager._alpha_edge_fallback_activation([ae_no_bt], stats)

        self.manager.portfolio_manager.auto_activate_strategy.assert_not_called()

    def test_picks_highest_sharpe_among_alpha_edge(self):
        """Should pick the Alpha Edge with the highest Sharpe ratio."""
        self.manager.strategy_engine.get_active_strategies.return_value = [
            _make_strategy("DSL1", status=StrategyStatus.DEMO)
        ]

        ae1 = _make_strategy("AE1", sharpe=0.3, is_alpha_edge=True)
        ae2 = _make_strategy("AE2", sharpe=0.9, is_alpha_edge=True)
        ae3 = _make_strategy("AE3", sharpe=0.5, is_alpha_edge=True)

        stats = {"strategies_activated": 1}
        self.manager._alpha_edge_fallback_activation([ae1, ae2, ae3], stats)

        self.manager.portfolio_manager.auto_activate_strategy.assert_called_once_with(
            strategy=ae2, backtest_results=ae2.backtest_results
        )
