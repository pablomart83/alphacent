"""Tests for eliminating redundant DSL rule validation (11.11.9).

Walk-forward validated strategies should skip rule/signal validation
in _backtest_proposals since they've already been validated on
out-of-sample data.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class MockBacktestResults:
    sharpe_ratio: float = 0.5
    total_return: float = 0.08
    max_drawdown: float = -0.12
    win_rate: float = 0.55
    total_trades: int = 20
    sortino_ratio: float = 0.6
    avg_win: float = 0.03
    avg_loss: float = 0.02


class MockStrategy:
    """Minimal strategy mock for testing _backtest_proposals."""
    def __init__(self, name, walk_forward_validated=False, is_alpha_edge=False):
        self.id = f"test-{name}"
        self.name = name
        self.symbols = ["AAPL"]
        self.metadata = {
            'walk_forward_validated': walk_forward_validated,
        }
        if is_alpha_edge:
            self.metadata['strategy_category'] = 'alpha_edge'
        self.backtest_results = MockBacktestResults() if walk_forward_validated else None
        self.status = MagicMock()
        self.status.value = "PROPOSED"
        self.rules = {'entry_conditions': [], 'exit_conditions': []}
        self.risk_params = {}


class TestRedundantDSLValidationSkip:
    """Test that walk-forward validated strategies skip rule/signal validation."""

    @pytest.fixture
    def manager(self):
        """Create a minimal AutonomousStrategyManager with mocked dependencies."""
        with patch('src.strategy.autonomous_strategy_manager.AutonomousStrategyManager.__init__', return_value=None):
            from src.strategy.autonomous_strategy_manager import AutonomousStrategyManager
            mgr = AutonomousStrategyManager.__new__(AutonomousStrategyManager)
            
            # Set up minimal required attributes
            mgr.config = {
                'backtest': {'days': 1825},
            }
            mgr.strategy_engine = MagicMock()
            mgr.strategy_proposer = MagicMock()
            mgr.websocket_manager = MagicMock()
            mgr._safe_broadcast = MagicMock()
            mgr._emit_stage_event = MagicMock()
            
            # Default mock returns for validation
            mgr.strategy_engine.validate_strategy_rules.return_value = {
                'is_valid': True,
                'overlap_percentage': 5.0,
                'entry_only_percentage': 2.0,
                'errors': [],
                'suggestions': [],
            }
            mgr.strategy_engine.validate_strategy_signals.return_value = {
                'is_valid': True,
                'entry_signals': 10,
                'exit_signals': 8,
                'errors': [],
            }
            mgr.strategy_engine.backtest_strategy.return_value = MockBacktestResults()
            
            return mgr

    def test_walk_forward_validated_skips_rule_validation(self, manager):
        """Walk-forward validated DSL strategies should NOT call validate_strategy_rules."""
        strategy = MockStrategy("WF-Validated-RSI", walk_forward_validated=True)
        stats = {"proposals_backtested": 0, "errors": []}

        result = manager._backtest_proposals([strategy], stats)

        # Should NOT have called rule or signal validation
        manager.strategy_engine.validate_strategy_rules.assert_not_called()
        manager.strategy_engine.validate_strategy_signals.assert_not_called()
        
        # Should still be in the results (not rejected)
        assert len(result) == 1
        assert stats["proposals_backtested"] == 1

    def test_walk_forward_validated_skips_signal_validation(self, manager):
        """Walk-forward validated DSL strategies should NOT call validate_strategy_signals."""
        strategy = MockStrategy("WF-Validated-MACD", walk_forward_validated=True)
        stats = {"proposals_backtested": 0, "errors": []}

        manager._backtest_proposals([strategy], stats)

        manager.strategy_engine.validate_strategy_signals.assert_not_called()

    def test_walk_forward_validated_uses_existing_backtest_results(self, manager):
        """Walk-forward validated strategies should use their existing backtest results."""
        strategy = MockStrategy("WF-Validated-BB", walk_forward_validated=True)
        stats = {"proposals_backtested": 0, "errors": []}

        result = manager._backtest_proposals([strategy], stats)

        # Should NOT run a new backtest
        manager.strategy_engine.backtest_strategy.assert_not_called()
        
        # Should use the existing results
        assert result[0].backtest_results.sharpe_ratio == 0.5

    def test_non_walk_forward_runs_rule_validation(self, manager):
        """Non-walk-forward strategies should still go through rule validation."""
        strategy = MockStrategy("Regular-RSI", walk_forward_validated=False)
        stats = {"proposals_backtested": 0, "errors": []}

        manager._backtest_proposals([strategy], stats)

        manager.strategy_engine.validate_strategy_rules.assert_called_once()
        manager.strategy_engine.validate_strategy_signals.assert_called_once()

    def test_non_walk_forward_runs_signal_validation(self, manager):
        """Non-walk-forward strategies should still go through signal validation."""
        strategy = MockStrategy("Regular-MACD", walk_forward_validated=False)
        stats = {"proposals_backtested": 0, "errors": []}

        manager._backtest_proposals([strategy], stats)

        manager.strategy_engine.validate_strategy_signals.assert_called_once()

    def test_mixed_proposals_selective_validation(self, manager):
        """Mix of walk-forward and non-walk-forward strategies: only non-WF get validated."""
        wf_strategy = MockStrategy("WF-Strategy", walk_forward_validated=True)
        regular_strategy = MockStrategy("Regular-Strategy", walk_forward_validated=False)
        stats = {"proposals_backtested": 0, "errors": []}

        result = manager._backtest_proposals([wf_strategy, regular_strategy], stats)

        # Rule validation called once (for regular strategy only)
        assert manager.strategy_engine.validate_strategy_rules.call_count == 1
        assert manager.strategy_engine.validate_strategy_signals.call_count == 1
        
        # Both should be in results
        assert len(result) == 2
        assert stats["proposals_backtested"] == 2

    def test_alpha_edge_still_uses_fundamental_validation(self, manager):
        """Alpha Edge strategies should still use their own validation path, not DSL."""
        strategy = MockStrategy("Alpha-Earnings", is_alpha_edge=True)
        manager.strategy_engine.validate_alpha_edge_strategy.return_value = {
            'is_valid': True, 'errors': [], 'warnings': []
        }
        manager.strategy_engine.backtest_alpha_edge_strategy.return_value = MockBacktestResults()
        stats = {"proposals_backtested": 0, "errors": []}

        result = manager._backtest_proposals([strategy], stats)

        # Alpha Edge uses its own validation, not DSL
        manager.strategy_engine.validate_alpha_edge_strategy.assert_called_once()
        manager.strategy_engine.validate_strategy_rules.assert_not_called()
        assert len(result) == 1
