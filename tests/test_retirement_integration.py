"""Integration test for strategy retirement logic."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

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


def test_full_retirement_flow(strategy_engine):
    """Test complete retirement flow from evaluation to retirement."""
    # Create a poorly performing strategy
    strategy = Strategy(
        id="test-retirement-flow",
        name="Test Retirement Flow",
        description="Strategy to test full retirement flow",
        status=StrategyStatus.LIVE,
        rules={"entry": [], "exit": []},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now() - timedelta(days=60),
        activated_at=datetime.now() - timedelta(days=50),
        allocation_percent=5.0,
        performance=PerformanceMetrics(
            total_return=-0.10,
            sharpe_ratio=0.2,
            max_drawdown=0.20,
            win_rate=0.30,
            total_trades=100
        ),
        live_trade_count=30,
        retirement_evaluation_history=[],
        last_retirement_evaluation=None
    )
    
    with patch.object(strategy_engine, '_load_strategy', return_value=strategy):
        with patch.object(strategy_engine, '_save_strategy'):
            # First evaluation - should fail but not retire
            reason1 = strategy_engine.check_retirement_triggers(strategy.id)
            assert reason1 is None
            assert len(strategy.retirement_evaluation_history) == 1
            assert not strategy.retirement_evaluation_history[0]["passed"]
            
            # Second evaluation - should fail but not retire
            reason2 = strategy_engine.check_retirement_triggers(strategy.id)
            assert reason2 is None
            assert len(strategy.retirement_evaluation_history) == 2
            
            # Third evaluation - should fail and retire
            reason3 = strategy_engine.check_retirement_triggers(strategy.id)
            assert reason3 is not None
            assert "Failed 3 consecutive retirement evaluations" in reason3
            assert len(strategy.retirement_evaluation_history) == 3


def test_retirement_recovery(strategy_engine):
    """Test that strategy can recover from failures."""
    # Create a strategy that initially fails but then improves
    strategy = Strategy(
        id="test-recovery",
        name="Test Recovery",
        description="Strategy to test recovery from failures",
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
        live_trade_count=30,
        retirement_evaluation_history=[],
        last_retirement_evaluation=None
    )
    
    with patch.object(strategy_engine, '_load_strategy', return_value=strategy):
        with patch.object(strategy_engine, '_save_strategy'):
            # First two evaluations fail
            strategy_engine.check_retirement_triggers(strategy.id)
            strategy_engine.check_retirement_triggers(strategy.id)
            assert len(strategy.retirement_evaluation_history) == 2
            
            # Improve performance
            strategy.performance = PerformanceMetrics(
                total_return=0.15,
                sharpe_ratio=1.5,
                max_drawdown=0.08,
                win_rate=0.60,
                total_trades=100
            )
            
            # Third evaluation passes - should reset consecutive failures
            reason = strategy_engine.check_retirement_triggers(strategy.id)
            assert reason is None
            assert len(strategy.retirement_evaluation_history) == 3
            assert strategy.retirement_evaluation_history[-1]["passed"]
            
            # Performance degrades again
            strategy.performance = PerformanceMetrics(
                total_return=-0.05,
                sharpe_ratio=0.3,
                max_drawdown=0.18,
                win_rate=0.35,
                total_trades=100
            )
            
            # Should need 3 more consecutive failures to retire
            strategy_engine.check_retirement_triggers(strategy.id)
            strategy_engine.check_retirement_triggers(strategy.id)
            reason = strategy_engine.check_retirement_triggers(strategy.id)
            
            # Should retire after 3 new consecutive failures
            assert reason is not None


def test_configuration_loading(strategy_engine):
    """Test that retirement configuration is loaded correctly."""
    strategy = Strategy(
        id="test-config",
        name="Test Config",
        description="Test configuration loading",
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
        live_trade_count=30,
        retirement_evaluation_history=[],
        last_retirement_evaluation=None
    )
    
    with patch.object(strategy_engine, '_load_strategy', return_value=strategy):
        with patch.object(strategy_engine, '_save_strategy'):
            # Should use configured values from autonomous_trading.yaml
            # min_live_trades_before_evaluation: 20
            # probation_period_days: 30
            # consecutive_failures_required: 3
            
            # Test with 19 live trades (below minimum)
            strategy.live_trade_count = 19
            reason = strategy_engine.check_retirement_triggers(strategy.id)
            assert reason is None
            assert len(strategy.retirement_evaluation_history) == 0
            
            # Test with 20 live trades (at minimum)
            strategy.live_trade_count = 20
            reason = strategy_engine.check_retirement_triggers(strategy.id)
            assert reason is None
            assert len(strategy.retirement_evaluation_history) == 1
