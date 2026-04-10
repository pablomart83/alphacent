"""Tests for portfolio directional diversity enforcement at activation (Task 11.11.6)."""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

from src.models.dataclasses import Strategy, StrategyStatus, RiskConfig, PerformanceMetrics, BacktestResults


def _make_strategy(name, direction='LONG', sharpe=1.0, status=StrategyStatus.PROPOSED):
    """Helper to create a test strategy with given direction and Sharpe."""
    metadata = {'direction': direction.lower()}
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


class TestDetectStrategyDirection:
    """Tests for _detect_strategy_direction helper."""

    def setup_method(self):
        with patch('src.strategy.autonomous_strategy_manager.AutonomousStrategyManager.__init__', return_value=None):
            from src.strategy.autonomous_strategy_manager import AutonomousStrategyManager
            self.manager = AutonomousStrategyManager.__new__(AutonomousStrategyManager)

    def test_detects_long_from_metadata(self):
        s = _make_strategy("test", direction='LONG')
        assert self.manager._detect_strategy_direction(s) == 'LONG'

    def test_detects_short_from_metadata(self):
        s = _make_strategy("test", direction='SHORT')
        assert self.manager._detect_strategy_direction(s) == 'SHORT'

    def test_defaults_to_long_when_no_metadata(self):
        s = _make_strategy("test")
        s.metadata = {}
        assert self.manager._detect_strategy_direction(s) == 'LONG'

    def test_detects_short_from_entry_conditions_fallback(self):
        s = _make_strategy("test")
        s.metadata = {}
        s.rules = {'entry_conditions': ['RSI > 70 AND OVERBOUGHT']}
        assert self.manager._detect_strategy_direction(s) == 'SHORT'

    def test_detects_short_from_sell_keyword(self):
        s = _make_strategy("test")
        s.metadata = {}
        s.rules = {'entry_conditions': ['SELL signal when MACD crosses']}
        assert self.manager._detect_strategy_direction(s) == 'SHORT'

    def test_detects_short_from_short_keyword(self):
        s = _make_strategy("test")
        s.metadata = {}
        s.rules = {'entry_conditions': ['SHORT entry on breakdown']}
        assert self.manager._detect_strategy_direction(s) == 'SHORT'


class TestEnforceDirectionalDiversity:
    """Tests for _enforce_directional_diversity."""

    def setup_method(self):
        with patch('src.strategy.autonomous_strategy_manager.AutonomousStrategyManager.__init__', return_value=None):
            from src.strategy.autonomous_strategy_manager import AutonomousStrategyManager
            self.manager = AutonomousStrategyManager.__new__(AutonomousStrategyManager)
        
        self.manager.strategy_engine = Mock()
        self.manager.portfolio_manager = Mock()
        self.manager.websocket_manager = Mock()
        self.manager.config = {"autonomous": {"max_active_strategies": 20}}
        # _safe_broadcast is a real method, but we mock it to avoid async issues
        self.manager._safe_broadcast = Mock()

    def test_skips_when_fewer_than_3_active(self):
        """No diversity check needed with < 3 active strategies."""
        self.manager.strategy_engine.get_active_strategies.return_value = [
            _make_strategy("s1", "SHORT", status=StrategyStatus.DEMO),
            _make_strategy("s2", "SHORT", status=StrategyStatus.DEMO),
        ]
        stats = {"strategies_activated": 2}
        self.manager._enforce_directional_diversity([], stats)
        self.manager.portfolio_manager.auto_activate_strategy.assert_not_called()

    def test_skips_when_already_diverse(self):
        """No action needed when both LONG and SHORT are present."""
        self.manager.strategy_engine.get_active_strategies.return_value = [
            _make_strategy("s1", "LONG", status=StrategyStatus.DEMO),
            _make_strategy("s2", "SHORT", status=StrategyStatus.DEMO),
            _make_strategy("s3", "SHORT", status=StrategyStatus.DEMO),
        ]
        stats = {"strategies_activated": 3}
        self.manager._enforce_directional_diversity([], stats)
        self.manager.portfolio_manager.auto_activate_strategy.assert_not_called()

    def test_force_activates_long_when_all_short(self):
        """When all active are SHORT, force-activate the best LONG candidate."""
        self.manager.strategy_engine.get_active_strategies.return_value = [
            _make_strategy("s1", "SHORT", status=StrategyStatus.DEMO),
            _make_strategy("s2", "SHORT", status=StrategyStatus.DEMO),
            _make_strategy("s3", "SHORT", status=StrategyStatus.DEMO),
        ]
        
        # Backtested candidates: one LONG with good Sharpe, one SHORT
        long_candidate = _make_strategy("long_candidate", "LONG", sharpe=0.5)
        short_candidate = _make_strategy("short_candidate", "SHORT", sharpe=0.8)
        
        stats = {"strategies_activated": 3}
        self.manager._enforce_directional_diversity(
            [long_candidate, short_candidate], stats
        )
        
        self.manager.portfolio_manager.auto_activate_strategy.assert_called_once_with(
            strategy=long_candidate, backtest_results=long_candidate.backtest_results
        )
        assert stats["strategies_activated"] == 4

    def test_force_activates_short_when_all_long(self):
        """When all active are LONG, force-activate the best SHORT candidate."""
        self.manager.strategy_engine.get_active_strategies.return_value = [
            _make_strategy("s1", "LONG", status=StrategyStatus.DEMO),
            _make_strategy("s2", "LONG", status=StrategyStatus.DEMO),
            _make_strategy("s3", "LONG", status=StrategyStatus.DEMO),
        ]
        
        short_candidate = _make_strategy("short_candidate", "SHORT", sharpe=0.3)
        
        stats = {"strategies_activated": 3}
        self.manager._enforce_directional_diversity([short_candidate], stats)
        
        self.manager.portfolio_manager.auto_activate_strategy.assert_called_once()
        assert stats["strategies_activated"] == 4

    def test_picks_highest_sharpe_candidate(self):
        """Should pick the candidate with the highest Sharpe ratio."""
        self.manager.strategy_engine.get_active_strategies.return_value = [
            _make_strategy("s1", "SHORT", status=StrategyStatus.DEMO),
            _make_strategy("s2", "SHORT", status=StrategyStatus.DEMO),
            _make_strategy("s3", "SHORT", status=StrategyStatus.DEMO),
        ]
        
        weak_long = _make_strategy("weak_long", "LONG", sharpe=0.1)
        strong_long = _make_strategy("strong_long", "LONG", sharpe=0.8)
        
        stats = {"strategies_activated": 3}
        self.manager._enforce_directional_diversity(
            [weak_long, strong_long], stats
        )
        
        self.manager.portfolio_manager.auto_activate_strategy.assert_called_once_with(
            strategy=strong_long, backtest_results=strong_long.backtest_results
        )

    def test_skips_negative_sharpe_candidates(self):
        """Should not force-activate strategies with Sharpe <= 0."""
        self.manager.strategy_engine.get_active_strategies.return_value = [
            _make_strategy("s1", "SHORT", status=StrategyStatus.DEMO),
            _make_strategy("s2", "SHORT", status=StrategyStatus.DEMO),
            _make_strategy("s3", "SHORT", status=StrategyStatus.DEMO),
        ]
        
        bad_long = _make_strategy("bad_long", "LONG", sharpe=-0.5)
        zero_long = _make_strategy("zero_long", "LONG", sharpe=0.0)
        
        stats = {"strategies_activated": 3}
        self.manager._enforce_directional_diversity(
            [bad_long, zero_long], stats
        )
        
        self.manager.portfolio_manager.auto_activate_strategy.assert_not_called()
        assert stats["strategies_activated"] == 3

    def test_skips_already_active_candidates(self):
        """Should not try to activate strategies that are already DEMO/LIVE."""
        self.manager.strategy_engine.get_active_strategies.return_value = [
            _make_strategy("s1", "SHORT", status=StrategyStatus.DEMO),
            _make_strategy("s2", "SHORT", status=StrategyStatus.DEMO),
            _make_strategy("s3", "SHORT", status=StrategyStatus.DEMO),
        ]
        
        already_active = _make_strategy("already_active", "LONG", sharpe=0.9, status=StrategyStatus.DEMO)
        
        stats = {"strategies_activated": 3}
        self.manager._enforce_directional_diversity([already_active], stats)
        
        self.manager.portfolio_manager.auto_activate_strategy.assert_not_called()

    def test_respects_max_strategies_limit(self):
        """Should not force-activate if already at max strategies."""
        self.manager.config = {"autonomous": {"max_active_strategies": 3}}
        self.manager.strategy_engine.get_active_strategies.return_value = [
            _make_strategy("s1", "SHORT", status=StrategyStatus.DEMO),
            _make_strategy("s2", "SHORT", status=StrategyStatus.DEMO),
            _make_strategy("s3", "SHORT", status=StrategyStatus.DEMO),
        ]
        
        long_candidate = _make_strategy("long_candidate", "LONG", sharpe=0.5)
        
        stats = {"strategies_activated": 3}
        self.manager._enforce_directional_diversity([long_candidate], stats)
        
        self.manager.portfolio_manager.auto_activate_strategy.assert_not_called()
