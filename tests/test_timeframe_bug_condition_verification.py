"""
Bug condition verification tests (Task 3.5).

Verifies that the bug conditions from bugfix.md are now fixed:
- Hourly strategies with Sharpe 0.68-0.81 are no longer rejected
- Intraday strategies with 40-50% degradation are no longer marked overfitted
- Hourly strategies with Sharpe 0.18 are no longer prematurely retired
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.models.dataclasses import (
    Strategy, BacktestResults, RiskConfig, PerformanceMetrics
)
from src.models.enums import StrategyStatus


class TestBugConditionFixed:
    """Verify the original bug conditions are now fixed."""

    def _load_config_thresholds(self):
        """Load actual config thresholds."""
        import yaml
        from pathlib import Path
        config_path = Path("config/autonomous_trading.yaml")
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config.get('activation_thresholds', {})

    # --- Bug 1.1: Hourly activation rejection ---

    def test_hourly_strategy_sharpe_075_no_longer_rejected(self):
        """Bug 1.1: Hourly strategy with Sharpe 0.75 should now activate."""
        from src.strategy.portfolio_manager import PortfolioManager

        pm = PortfolioManager(strategy_engine=Mock())

        strategy = Mock(spec=Strategy)
        strategy.name = "Hourly-RSI-AAPL"
        strategy.symbols = ["AAPL"]
        strategy.metadata = {"interval": "1h", "intraday": True}

        backtest = Mock(spec=BacktestResults)
        backtest.sharpe_ratio = 0.75
        backtest.win_rate = 0.72
        backtest.max_drawdown = 0.10
        backtest.total_trades = 25
        backtest.metadata = {"interval": "1h"}

        should_activate, reason = pm.evaluate_for_activation(
            strategy, backtest, market_context=None
        )

        # With fix: stock hourly threshold = 0.8 * 0.67 = 0.536
        # Sharpe 0.75 > 0.536 → should activate
        assert should_activate is True, (
            f"Hourly strategy with Sharpe 0.75 should activate. Reason: {reason}"
        )

    def test_hourly_strategy_sharpe_068_no_longer_rejected(self):
        """Bug 1.1: Hourly strategy with Sharpe 0.68 should now activate."""
        from src.strategy.portfolio_manager import PortfolioManager

        pm = PortfolioManager(strategy_engine=Mock())

        strategy = Mock(spec=Strategy)
        strategy.name = "Hourly-MACD-MSFT"
        strategy.symbols = ["MSFT"]
        strategy.metadata = {"interval": "1h", "intraday": True}

        backtest = Mock(spec=BacktestResults)
        backtest.sharpe_ratio = 0.68
        backtest.win_rate = 0.75
        backtest.max_drawdown = 0.08
        backtest.total_trades = 30
        backtest.metadata = {"interval": "1h"}

        should_activate, reason = pm.evaluate_for_activation(
            strategy, backtest, market_context=None
        )

        assert should_activate is True, (
            f"Hourly strategy with Sharpe 0.68 should activate. Reason: {reason}"
        )

    # --- Bug 1.5: Hourly premature retirement ---

    def test_hourly_strategy_sharpe_018_not_retired(self):
        """Bug 1.5: Hourly strategy with Sharpe 0.18 should NOT be retired."""
        from src.strategy.portfolio_manager import PortfolioManager

        pm = PortfolioManager(strategy_engine=Mock())

        strategy = Mock(spec=Strategy)
        strategy.name = "Hourly-RSI-AAPL"
        strategy.symbols = ["AAPL"]
        strategy.metadata = {"interval": "1h"}
        strategy.backtest_results = None
        strategy.risk_params = RiskConfig()

        perf = PerformanceMetrics()
        perf.sharpe_ratio = 0.18
        perf.win_rate = 0.45
        perf.max_drawdown = 0.12
        perf.total_trades = 35
        perf.avg_loss = -0.02
        strategy.performance = perf

        reason = pm.check_retirement_triggers(strategy)

        # With fix: hourly Sharpe threshold = 0.15
        # Sharpe 0.18 > 0.15 → should NOT retire
        assert reason is None, (
            f"Hourly strategy with Sharpe 0.18 should NOT be retired. Got: {reason}"
        )

    def test_hourly_strategy_sharpe_012_is_retired(self):
        """Hourly strategy with Sharpe 0.12 SHOULD be retired (below 0.15)."""
        from src.strategy.portfolio_manager import PortfolioManager

        pm = PortfolioManager(strategy_engine=Mock())

        strategy = Mock(spec=Strategy)
        strategy.name = "Hourly-Bad"
        strategy.symbols = ["AAPL"]
        strategy.metadata = {"interval": "1h"}
        strategy.backtest_results = None
        strategy.risk_params = RiskConfig()

        perf = PerformanceMetrics()
        perf.sharpe_ratio = 0.12
        perf.win_rate = 0.45
        perf.max_drawdown = 0.12
        perf.total_trades = 35
        perf.avg_loss = -0.02
        strategy.performance = perf

        reason = pm.check_retirement_triggers(strategy)

        assert reason is not None, (
            "Hourly strategy with Sharpe 0.12 should be retired (below 0.15)"
        )

    # --- Preservation: Daily strategies unchanged ---

    def test_daily_strategy_sharpe_019_still_retired(self):
        """Preservation: Daily strategy with Sharpe 0.19 should still be retired."""
        from src.strategy.portfolio_manager import PortfolioManager

        pm = PortfolioManager(strategy_engine=Mock())

        strategy = Mock(spec=Strategy)
        strategy.name = "Daily-Bad"
        strategy.symbols = ["AAPL"]
        strategy.metadata = {"interval": "1d"}
        strategy.backtest_results = None
        strategy.risk_params = RiskConfig()

        perf = PerformanceMetrics()
        perf.sharpe_ratio = 0.19
        perf.win_rate = 0.45
        perf.max_drawdown = 0.12
        perf.total_trades = 35
        perf.avg_loss = -0.02
        strategy.performance = perf

        reason = pm.check_retirement_triggers(strategy)

        assert reason is not None, (
            "Daily strategy with Sharpe 0.19 should still be retired (threshold 0.2)"
        )

    def test_4h_strategy_unchanged(self):
        """Preservation: 4H strategy retirement thresholds unchanged."""
        from src.strategy.portfolio_manager import PortfolioManager

        pm = PortfolioManager(strategy_engine=Mock())

        strategy = Mock(spec=Strategy)
        strategy.name = "4H-Strategy"
        strategy.symbols = ["AAPL"]
        strategy.metadata = {"interval": "4h"}
        strategy.backtest_results = None
        strategy.risk_params = RiskConfig()

        perf = PerformanceMetrics()
        perf.sharpe_ratio = 0.19
        perf.win_rate = 0.45
        perf.max_drawdown = 0.12
        perf.total_trades = 35
        perf.avg_loss = -0.02
        strategy.performance = perf

        reason = pm.check_retirement_triggers(strategy)

        assert reason is not None, (
            "4H strategy with Sharpe 0.19 should still be retired (threshold 0.2)"
        )
