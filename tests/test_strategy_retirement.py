"""Tests for improved strategy retirement logic."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import yaml

from src.models import Strategy, StrategyStatus, PerformanceMetrics, RiskConfig
from src.strategy.strategy_engine import StrategyEngine


@pytest.fixture
def mock_market_data():
    """Mock market data manager."""
    return Mock()


@pytest.fixture
def strategy_engine(mock_market_data):
    """Create strategy engine for testing."""
    return StrategyEngine(llm_service=None, market_data=mock_market_data)


@pytest.fixture
def sample_strategy():
    """Create a sample strategy for testing."""
    return Strategy(
        id="test-strategy-1",
        name="Test Strategy",
        description="Test strategy for retirement logic",
        status=StrategyStatus.LIVE,
        rules={"entry": [], "exit": []},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now() - timedelta(days=60),
        activated_at=datetime.now() - timedelta(days=50),
        allocation_percent=5.0,
        performance=PerformanceMetrics(
            total_return=-0.05,
            sharpe_ratio=0.3,
            max_drawdown=0.18,
            win_rate=0.35,
            total_trades=100
        ),
        live_trade_count=25,
        retirement_evaluation_history=[],
        last_retirement_evaluation=None
    )


class TestMinimumTradeCount:
    """Test minimum trade count requirement."""
    
    def test_skip_evaluation_below_minimum(self, strategy_engine, sample_strategy):
        """Strategy with fewer than minimum live trades should not be evaluated."""
        # Set live trade count below minimum (default: 20)
        sample_strategy.live_trade_count = 15
        
        with patch.object(strategy_engine, '_load_strategy', return_value=sample_strategy):
            with patch.object(strategy_engine, '_save_strategy'):
                reason = strategy_engine.check_retirement_triggers(sample_strategy.id)
        
        # Should not retire
        assert reason is None
        # Should not record evaluation
        assert len(sample_strategy.retirement_evaluation_history) == 0
    
    def test_evaluate_at_minimum(self, strategy_engine, sample_strategy):
        """Strategy with exactly minimum live trades should be evaluated."""
        # Set live trade count to minimum (default: 20)
        sample_strategy.live_trade_count = 20
        
        with patch.object(strategy_engine, '_load_strategy', return_value=sample_strategy):
            with patch.object(strategy_engine, '_save_strategy'):
                reason = strategy_engine.check_retirement_triggers(sample_strategy.id)
        
        # Should evaluate (may or may not retire depending on metrics)
        # But evaluation should be recorded
        assert len(sample_strategy.retirement_evaluation_history) > 0
    
    def test_evaluate_above_minimum(self, strategy_engine, sample_strategy):
        """Strategy with more than minimum live trades should be evaluated."""
        # Set live trade count above minimum
        sample_strategy.live_trade_count = 50
        
        with patch.object(strategy_engine, '_load_strategy', return_value=sample_strategy):
            with patch.object(strategy_engine, '_save_strategy'):
                reason = strategy_engine.check_retirement_triggers(sample_strategy.id)
        
        # Should evaluate
        assert len(sample_strategy.retirement_evaluation_history) > 0


class TestProbationPeriod:
    """Test probation period for new strategies."""
    
    def test_skip_evaluation_in_probation(self, strategy_engine, sample_strategy):
        """Strategy in probation period should not be evaluated."""
        # Set activation date within probation period (default: 30 days)
        sample_strategy.activated_at = datetime.now() - timedelta(days=15)
        sample_strategy.live_trade_count = 25  # Above minimum
        
        with patch.object(strategy_engine, '_load_strategy', return_value=sample_strategy):
            with patch.object(strategy_engine, '_save_strategy'):
                reason = strategy_engine.check_retirement_triggers(sample_strategy.id)
        
        # Should not retire
        assert reason is None
        # Should not record evaluation
        assert len(sample_strategy.retirement_evaluation_history) == 0
    
    def test_evaluate_after_probation(self, strategy_engine, sample_strategy):
        """Strategy after probation period should be evaluated."""
        # Set activation date after probation period
        sample_strategy.activated_at = datetime.now() - timedelta(days=35)
        sample_strategy.live_trade_count = 25  # Above minimum
        
        with patch.object(strategy_engine, '_load_strategy', return_value=sample_strategy):
            with patch.object(strategy_engine, '_save_strategy'):
                reason = strategy_engine.check_retirement_triggers(sample_strategy.id)
        
        # Should evaluate
        assert len(sample_strategy.retirement_evaluation_history) > 0


class TestConsecutiveFailures:
    """Test consecutive failures requirement."""
    
    def test_no_retirement_on_first_failure(self, strategy_engine, sample_strategy):
        """Strategy should not retire on first evaluation failure."""
        sample_strategy.live_trade_count = 25
        sample_strategy.activated_at = datetime.now() - timedelta(days=35)
        
        with patch.object(strategy_engine, '_load_strategy', return_value=sample_strategy):
            with patch.object(strategy_engine, '_save_strategy'):
                reason = strategy_engine.check_retirement_triggers(sample_strategy.id)
        
        # Should not retire on first failure
        assert reason is None
        # Should record failure
        assert len(sample_strategy.retirement_evaluation_history) == 1
        assert not sample_strategy.retirement_evaluation_history[0]["passed"]
    
    def test_no_retirement_on_second_failure(self, strategy_engine, sample_strategy):
        """Strategy should not retire on second consecutive failure."""
        sample_strategy.live_trade_count = 25
        sample_strategy.activated_at = datetime.now() - timedelta(days=35)
        
        # Add first failure to history
        sample_strategy.retirement_evaluation_history = [
            {
                "timestamp": (datetime.now() - timedelta(days=1)).isoformat(),
                "passed": False,
                "failure_reasons": ["Low Sharpe ratio"],
                "metrics": {}
            }
        ]
        
        with patch.object(strategy_engine, '_load_strategy', return_value=sample_strategy):
            with patch.object(strategy_engine, '_save_strategy'):
                reason = strategy_engine.check_retirement_triggers(sample_strategy.id)
        
        # Should not retire on second failure (default requires 3)
        assert reason is None
        # Should record second failure
        assert len(sample_strategy.retirement_evaluation_history) == 2
    
    def test_retirement_on_third_failure(self, strategy_engine, sample_strategy):
        """Strategy should retire on third consecutive failure."""
        sample_strategy.live_trade_count = 25
        sample_strategy.activated_at = datetime.now() - timedelta(days=35)
        
        # Add two previous failures to history
        sample_strategy.retirement_evaluation_history = [
            {
                "timestamp": (datetime.now() - timedelta(days=2)).isoformat(),
                "passed": False,
                "failure_reasons": ["Low Sharpe ratio"],
                "metrics": {}
            },
            {
                "timestamp": (datetime.now() - timedelta(days=1)).isoformat(),
                "passed": False,
                "failure_reasons": ["Low Sharpe ratio"],
                "metrics": {}
            }
        ]
        
        with patch.object(strategy_engine, '_load_strategy', return_value=sample_strategy):
            with patch.object(strategy_engine, '_save_strategy'):
                reason = strategy_engine.check_retirement_triggers(sample_strategy.id)
        
        # Should retire on third consecutive failure
        assert reason is not None
        assert "Failed 3 consecutive retirement evaluations" in reason
    
    def test_reset_on_passing_evaluation(self, strategy_engine, sample_strategy):
        """Consecutive failure count should reset after passing evaluation."""
        sample_strategy.live_trade_count = 25
        sample_strategy.activated_at = datetime.now() - timedelta(days=35)
        
        # Improve performance to pass evaluation
        sample_strategy.performance = PerformanceMetrics(
            total_return=0.15,
            sharpe_ratio=1.5,
            max_drawdown=0.08,
            win_rate=0.60,
            total_trades=100
        )
        
        # Add two previous failures to history
        sample_strategy.retirement_evaluation_history = [
            {
                "timestamp": (datetime.now() - timedelta(days=2)).isoformat(),
                "passed": False,
                "failure_reasons": ["Low Sharpe ratio"],
                "metrics": {}
            },
            {
                "timestamp": (datetime.now() - timedelta(days=1)).isoformat(),
                "passed": False,
                "failure_reasons": ["Low Sharpe ratio"],
                "metrics": {}
            }
        ]
        
        with patch.object(strategy_engine, '_load_strategy', return_value=sample_strategy):
            with patch.object(strategy_engine, '_save_strategy'):
                reason = strategy_engine.check_retirement_triggers(sample_strategy.id)
        
        # Should not retire (passing evaluation resets count)
        assert reason is None
        # Should record passing evaluation
        assert len(sample_strategy.retirement_evaluation_history) == 3
        assert sample_strategy.retirement_evaluation_history[-1]["passed"]


class TestEvaluationHistory:
    """Test evaluation history tracking."""
    
    def test_records_evaluation_result(self, strategy_engine, sample_strategy):
        """Evaluation result should be recorded in history."""
        sample_strategy.live_trade_count = 25
        sample_strategy.activated_at = datetime.now() - timedelta(days=35)
        
        with patch.object(strategy_engine, '_load_strategy', return_value=sample_strategy):
            with patch.object(strategy_engine, '_save_strategy'):
                strategy_engine.check_retirement_triggers(sample_strategy.id)
        
        # Should record evaluation
        assert len(sample_strategy.retirement_evaluation_history) == 1
        
        eval_result = sample_strategy.retirement_evaluation_history[0]
        assert "timestamp" in eval_result
        assert "passed" in eval_result
        assert "failure_reasons" in eval_result
        assert "metrics" in eval_result
    
    def test_limits_history_size(self, strategy_engine, sample_strategy):
        """Evaluation history should be limited to recent evaluations."""
        sample_strategy.live_trade_count = 25
        sample_strategy.activated_at = datetime.now() - timedelta(days=35)
        
        # Add 10 old evaluations
        sample_strategy.retirement_evaluation_history = [
            {
                "timestamp": (datetime.now() - timedelta(days=i)).isoformat(),
                "passed": True,
                "failure_reasons": [],
                "metrics": {}
            }
            for i in range(10, 0, -1)
        ]
        
        with patch.object(strategy_engine, '_load_strategy', return_value=sample_strategy):
            with patch.object(strategy_engine, '_save_strategy'):
                strategy_engine.check_retirement_triggers(sample_strategy.id)
        
        # Should keep only last 10 evaluations
        assert len(sample_strategy.retirement_evaluation_history) == 10
    
    def test_updates_last_evaluation_timestamp(self, strategy_engine, sample_strategy):
        """Last evaluation timestamp should be updated."""
        sample_strategy.live_trade_count = 25
        sample_strategy.activated_at = datetime.now() - timedelta(days=35)
        sample_strategy.last_retirement_evaluation = None
        
        with patch.object(strategy_engine, '_load_strategy', return_value=sample_strategy):
            with patch.object(strategy_engine, '_save_strategy'):
                strategy_engine.check_retirement_triggers(sample_strategy.id)
        
        # Should update timestamp
        assert sample_strategy.last_retirement_evaluation is not None
        assert isinstance(sample_strategy.last_retirement_evaluation, datetime)


class TestRetirementTriggers:
    """Test individual retirement triggers."""
    
    def test_low_sharpe_ratio_trigger(self, strategy_engine, sample_strategy):
        """Low Sharpe ratio should trigger evaluation failure."""
        sample_strategy.live_trade_count = 25
        sample_strategy.activated_at = datetime.now() - timedelta(days=35)
        sample_strategy.performance.sharpe_ratio = 0.3  # Below 0.5 threshold
        
        with patch.object(strategy_engine, '_load_strategy', return_value=sample_strategy):
            with patch.object(strategy_engine, '_save_strategy'):
                strategy_engine.check_retirement_triggers(sample_strategy.id)
        
        eval_result = sample_strategy.retirement_evaluation_history[0]
        assert not eval_result["passed"]
        assert any("Sharpe ratio" in reason for reason in eval_result["failure_reasons"])
    
    def test_high_drawdown_trigger(self, strategy_engine, sample_strategy):
        """High drawdown should trigger evaluation failure."""
        sample_strategy.live_trade_count = 25
        sample_strategy.activated_at = datetime.now() - timedelta(days=35)
        sample_strategy.performance.max_drawdown = 0.20  # Above 0.15 threshold
        
        with patch.object(strategy_engine, '_load_strategy', return_value=sample_strategy):
            with patch.object(strategy_engine, '_save_strategy'):
                strategy_engine.check_retirement_triggers(sample_strategy.id)
        
        eval_result = sample_strategy.retirement_evaluation_history[0]
        assert not eval_result["passed"]
        assert any("drawdown" in reason for reason in eval_result["failure_reasons"])
    
    def test_low_win_rate_trigger(self, strategy_engine, sample_strategy):
        """Low win rate should trigger evaluation failure."""
        sample_strategy.live_trade_count = 25
        sample_strategy.activated_at = datetime.now() - timedelta(days=35)
        sample_strategy.performance.win_rate = 0.35  # Below 0.40 threshold
        
        with patch.object(strategy_engine, '_load_strategy', return_value=sample_strategy):
            with patch.object(strategy_engine, '_save_strategy'):
                strategy_engine.check_retirement_triggers(sample_strategy.id)
        
        eval_result = sample_strategy.retirement_evaluation_history[0]
        assert not eval_result["passed"]
        assert any("Win rate" in reason for reason in eval_result["failure_reasons"])
    
    def test_negative_return_trigger(self, strategy_engine, sample_strategy):
        """Negative return should trigger evaluation failure."""
        sample_strategy.live_trade_count = 25
        sample_strategy.activated_at = datetime.now() - timedelta(days=35)
        sample_strategy.performance.total_return = -0.05  # Negative
        
        with patch.object(strategy_engine, '_load_strategy', return_value=sample_strategy):
            with patch.object(strategy_engine, '_save_strategy'):
                strategy_engine.check_retirement_triggers(sample_strategy.id)
        
        eval_result = sample_strategy.retirement_evaluation_history[0]
        assert not eval_result["passed"]
        assert any("Negative total return" in reason for reason in eval_result["failure_reasons"])
