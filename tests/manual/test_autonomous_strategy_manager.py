"""Tests for Autonomous Strategy Manager."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch

from src.models.dataclasses import (
    BacktestResults,
    PerformanceMetrics,
    RiskConfig,
    Strategy,
)
from src.models.enums import StrategyStatus
from src.strategy.autonomous_strategy_manager import AutonomousStrategyManager
from src.strategy.strategy_proposer import MarketRegime


@pytest.fixture
def mock_llm_service():
    """Create mock LLM service."""
    return Mock()


@pytest.fixture
def mock_market_data():
    """Create mock market data manager."""
    return Mock()


@pytest.fixture
def mock_strategy_engine():
    """Create mock strategy engine."""
    engine = Mock()
    engine.get_active_strategies = Mock(return_value=[])
    engine.get_all_strategies = Mock(return_value=[])
    return engine


@pytest.fixture
def autonomous_manager(mock_llm_service, mock_market_data, mock_strategy_engine):
    """Create AutonomousStrategyManager instance."""
    return AutonomousStrategyManager(
        llm_service=mock_llm_service,
        market_data=mock_market_data,
        strategy_engine=mock_strategy_engine,
    )


@pytest.fixture
def sample_strategy():
    """Create a sample strategy for testing."""
    return Strategy(
        id="test-strategy-1",
        name="Test Momentum Strategy",
        description="A test strategy",
        status=StrategyStatus.PROPOSED,
        rules={"entry": ["RSI < 30"], "exit": ["RSI > 70"]},
        symbols=["AAPL", "GOOGL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics(),
    )


@pytest.fixture
def sample_backtest_results():
    """Create sample backtest results."""
    return BacktestResults(
        total_return=0.25,
        sharpe_ratio=2.0,
        sortino_ratio=2.5,
        max_drawdown=0.10,
        win_rate=0.60,
        avg_win=0.02,
        avg_loss=-0.01,
        total_trades=50,
    )


class TestAutonomousStrategyManagerInit:
    """Tests for AutonomousStrategyManager initialization."""

    def test_initializes_with_default_config(
        self, mock_llm_service, mock_market_data, mock_strategy_engine
    ):
        """Test initialization with default configuration."""
        manager = AutonomousStrategyManager(
            llm_service=mock_llm_service,
            market_data=mock_market_data,
            strategy_engine=mock_strategy_engine,
        )

        assert manager.config is not None
        assert manager.config["autonomous"]["enabled"] is True
        assert manager.config["autonomous"]["proposal_frequency"] == "weekly"
        assert manager.config["autonomous"]["max_active_strategies"] == 10
        assert manager.last_run_time is None

    def test_initializes_with_custom_config(
        self, mock_llm_service, mock_market_data, mock_strategy_engine
    ):
        """Test initialization with custom configuration."""
        custom_config = {
            "autonomous": {
                "enabled": False,
                "proposal_frequency": "daily",
                "max_active_strategies": 5,
                "proposal_count": 3,
            }
        }

        manager = AutonomousStrategyManager(
            llm_service=mock_llm_service,
            market_data=mock_market_data,
            strategy_engine=mock_strategy_engine,
            config=custom_config,
        )

        assert manager.config["autonomous"]["enabled"] is False
        assert manager.config["autonomous"]["proposal_frequency"] == "daily"
        assert manager.config["autonomous"]["max_active_strategies"] == 5


class TestRunStrategyCycle:
    """Tests for run_strategy_cycle method."""

    def test_runs_complete_cycle_successfully(
        self, autonomous_manager, sample_strategy, sample_backtest_results
    ):
        """Test complete autonomous cycle runs successfully."""
        # Mock strategy proposer
        autonomous_manager.strategy_proposer.propose_strategies = Mock(
            return_value=[sample_strategy]
        )

        # Mock backtest
        sample_strategy.backtest_results = sample_backtest_results
        autonomous_manager.strategy_engine.backtest_strategy = Mock(
            return_value=sample_backtest_results
        )

        # Mock evaluation (passes)
        autonomous_manager.portfolio_manager.evaluate_for_activation = Mock(
            return_value=True
        )

        # Mock activation
        autonomous_manager.portfolio_manager.auto_activate_strategy = Mock()

        # Mock retirement check (no retirements)
        autonomous_manager.strategy_engine.get_active_strategies = Mock(return_value=[])

        # Run cycle
        stats = autonomous_manager.run_strategy_cycle()

        # Verify stats
        assert stats["proposals_generated"] == 1
        assert stats["proposals_backtested"] == 1
        assert stats["strategies_activated"] == 1
        assert stats["strategies_retired"] == 0
        assert len(stats["errors"]) == 0

        # Verify methods were called
        autonomous_manager.strategy_proposer.propose_strategies.assert_called_once()
        autonomous_manager.strategy_engine.backtest_strategy.assert_called_once()
        autonomous_manager.portfolio_manager.evaluate_for_activation.assert_called_once()
        autonomous_manager.portfolio_manager.auto_activate_strategy.assert_called_once()

    def test_handles_proposal_failure(self, autonomous_manager):
        """Test cycle handles proposal failure gracefully."""
        # Mock proposal failure
        autonomous_manager.strategy_proposer.propose_strategies = Mock(
            side_effect=Exception("Proposal failed")
        )

        # Run cycle
        stats = autonomous_manager.run_strategy_cycle()

        # Verify stats
        assert stats["proposals_generated"] == 0
        assert stats["proposals_backtested"] == 0
        assert len(stats["errors"]) > 0
        assert stats["errors"][0]["step"] == "propose"

    def test_handles_backtest_failure(
        self, autonomous_manager, sample_strategy
    ):
        """Test cycle handles backtest failure gracefully."""
        # Mock proposal success
        autonomous_manager.strategy_proposer.propose_strategies = Mock(
            return_value=[sample_strategy]
        )

        # Mock backtest failure
        autonomous_manager.strategy_engine.backtest_strategy = Mock(
            side_effect=Exception("Backtest failed")
        )

        # Run cycle
        stats = autonomous_manager.run_strategy_cycle()

        # Verify stats
        assert stats["proposals_generated"] == 1
        assert stats["proposals_backtested"] == 0
        assert len(stats["errors"]) > 0
        assert stats["errors"][0]["step"] == "backtest"

    def test_skips_activation_when_criteria_not_met(
        self, autonomous_manager, sample_strategy, sample_backtest_results
    ):
        """Test cycle skips activation when criteria not met."""
        # Mock proposal and backtest
        autonomous_manager.strategy_proposer.propose_strategies = Mock(
            return_value=[sample_strategy]
        )
        sample_strategy.backtest_results = sample_backtest_results
        autonomous_manager.strategy_engine.backtest_strategy = Mock(
            return_value=sample_backtest_results
        )

        # Mock evaluation (fails)
        autonomous_manager.portfolio_manager.evaluate_for_activation = Mock(
            return_value=False
        )

        # Run cycle
        stats = autonomous_manager.run_strategy_cycle()

        # Verify no activation
        assert stats["strategies_activated"] == 0

    def test_retires_underperforming_strategies(
        self, autonomous_manager, sample_strategy
    ):
        """Test cycle retires underperforming strategies."""
        # Mock no proposals
        autonomous_manager.strategy_proposer.propose_strategies = Mock(
            return_value=[]
        )

        # Mock active strategy with poor performance
        poor_strategy = sample_strategy
        poor_strategy.status = StrategyStatus.DEMO
        poor_strategy.performance = PerformanceMetrics(
            sharpe_ratio=0.3,  # Below threshold
            total_trades=50,
        )

        autonomous_manager.strategy_engine.get_active_strategies = Mock(
            return_value=[poor_strategy]
        )

        # Mock retirement check (should retire)
        autonomous_manager.portfolio_manager.check_retirement_triggers = Mock(
            return_value="Sharpe ratio 0.3 < 0.5"
        )

        # Mock retirement
        autonomous_manager.portfolio_manager.auto_retire_strategy = Mock()

        # Run cycle
        stats = autonomous_manager.run_strategy_cycle()

        # Verify retirement
        assert stats["strategies_retired"] == 1
        autonomous_manager.portfolio_manager.auto_retire_strategy.assert_called_once()

    def test_respects_max_active_strategies_limit(
        self, autonomous_manager, sample_strategy, sample_backtest_results
    ):
        """Test cycle respects max active strategies limit."""
        # Set max to 2
        autonomous_manager.config["autonomous"]["max_active_strategies"] = 2

        # Mock proposal and backtest
        autonomous_manager.strategy_proposer.propose_strategies = Mock(
            return_value=[sample_strategy]
        )
        sample_strategy.backtest_results = sample_backtest_results
        autonomous_manager.strategy_engine.backtest_strategy = Mock(
            return_value=sample_backtest_results
        )

        # Mock evaluation (passes)
        autonomous_manager.portfolio_manager.evaluate_for_activation = Mock(
            return_value=True
        )

        # Mock already at max strategies
        existing_strategies = [
            Mock(status=StrategyStatus.DEMO),
            Mock(status=StrategyStatus.DEMO),
        ]
        autonomous_manager.strategy_engine.get_active_strategies = Mock(
            return_value=existing_strategies
        )

        # Run cycle
        stats = autonomous_manager.run_strategy_cycle()

        # Verify no activation (at max)
        assert stats["strategies_activated"] == 0


class TestGetStatus:
    """Tests for get_status method."""

    def test_returns_complete_status(self, autonomous_manager):
        """Test get_status returns complete system status."""
        # Mock strategies
        active_strategy = Mock(status=StrategyStatus.DEMO)
        proposed_strategy = Mock(status=StrategyStatus.PROPOSED)

        autonomous_manager.strategy_engine.get_active_strategies = Mock(
            return_value=[active_strategy]
        )
        autonomous_manager.strategy_engine.get_all_strategies = Mock(
            return_value=[active_strategy, proposed_strategy]
        )

        # Mock market regime
        autonomous_manager.strategy_proposer.analyze_market_conditions = Mock(
            return_value=MarketRegime.TRENDING_UP
        )

        # Get status
        status = autonomous_manager.get_status()

        # Verify status
        assert status["enabled"] is True
        assert status["market_regime"] == "trending_up"
        assert status["active_strategies_count"] == 1
        assert status["total_strategies_count"] == 2
        assert "config" in status


class TestShouldRunCycle:
    """Tests for should_run_cycle method."""

    def test_returns_true_when_never_run(self, autonomous_manager):
        """Test returns True when cycle has never run."""
        assert autonomous_manager.should_run_cycle() is True

    def test_returns_false_when_disabled(self, autonomous_manager):
        """Test returns False when autonomous mode is disabled."""
        autonomous_manager.config["autonomous"]["enabled"] = False
        assert autonomous_manager.should_run_cycle() is False

    def test_returns_true_when_daily_frequency_elapsed(self, autonomous_manager):
        """Test returns True when daily frequency has elapsed."""
        autonomous_manager.config["autonomous"]["proposal_frequency"] = "daily"
        autonomous_manager.last_run_time = datetime.now() - timedelta(days=2)

        assert autonomous_manager.should_run_cycle() is True

    def test_returns_false_when_daily_frequency_not_elapsed(self, autonomous_manager):
        """Test returns False when daily frequency has not elapsed."""
        autonomous_manager.config["autonomous"]["proposal_frequency"] = "daily"
        autonomous_manager.last_run_time = datetime.now() - timedelta(hours=12)

        assert autonomous_manager.should_run_cycle() is False

    def test_returns_true_when_weekly_frequency_elapsed(self, autonomous_manager):
        """Test returns True when weekly frequency has elapsed."""
        autonomous_manager.config["autonomous"]["proposal_frequency"] = "weekly"
        autonomous_manager.last_run_time = datetime.now() - timedelta(weeks=2)

        assert autonomous_manager.should_run_cycle() is True

    def test_returns_false_when_weekly_frequency_not_elapsed(self, autonomous_manager):
        """Test returns False when weekly frequency has not elapsed."""
        autonomous_manager.config["autonomous"]["proposal_frequency"] = "weekly"
        autonomous_manager.last_run_time = datetime.now() - timedelta(days=3)

        assert autonomous_manager.should_run_cycle() is False


class TestRunScheduledCycle:
    """Tests for run_scheduled_cycle method."""

    def test_runs_cycle_when_scheduled(self, autonomous_manager):
        """Test runs cycle when schedule indicates it should."""
        # Set last run to 2 weeks ago
        autonomous_manager.last_run_time = datetime.now() - timedelta(weeks=2)

        # Mock run_strategy_cycle
        autonomous_manager.run_strategy_cycle = Mock(return_value={"test": "stats"})

        # Run scheduled cycle
        result = autonomous_manager.run_scheduled_cycle()

        # Verify cycle ran
        assert result is not None
        autonomous_manager.run_strategy_cycle.assert_called_once()

    def test_skips_cycle_when_not_scheduled(self, autonomous_manager):
        """Test skips cycle when schedule indicates it shouldn't run."""
        # Set last run to 1 day ago (weekly frequency)
        autonomous_manager.last_run_time = datetime.now() - timedelta(days=1)

        # Mock run_strategy_cycle
        autonomous_manager.run_strategy_cycle = Mock()

        # Run scheduled cycle
        result = autonomous_manager.run_scheduled_cycle()

        # Verify cycle was skipped
        assert result is None
        autonomous_manager.run_strategy_cycle.assert_not_called()
