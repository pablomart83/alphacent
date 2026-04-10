"""Tests for strategy activation and deactivation functionality."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.strategy.strategy_engine import StrategyEngine
from src.models import (
    Strategy,
    StrategyStatus,
    RiskConfig,
    PerformanceMetrics,
    BacktestResults,
    TradingMode,
)


@pytest.fixture
def mock_llm_service():
    """Create mock LLM service."""
    return Mock()


@pytest.fixture
def mock_market_data():
    """Create mock market data manager."""
    return Mock()


@pytest.fixture
def strategy_engine(mock_llm_service, mock_market_data):
    """Create StrategyEngine with mocked dependencies."""
    with patch('src.strategy.strategy_engine.get_database'):
        engine = StrategyEngine(mock_llm_service, mock_market_data)
        engine._save_strategy = Mock()
        engine._load_strategy = Mock()
        engine._calculate_total_active_allocation = Mock(return_value=0.0)
        return engine


@pytest.fixture
def proposed_strategy():
    """Create a PROPOSED strategy for testing."""
    return Strategy(
        id="proposed-123",
        name="Proposed Strategy",
        description="A proposed strategy",
        status=StrategyStatus.PROPOSED,
        rules={"entry_conditions": ["MA crossover"]},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )


@pytest.fixture
def backtested_strategy():
    """Create a BACKTESTED strategy for testing."""
    return Strategy(
        id="backtested-123",
        name="Backtested Strategy",
        description="A backtested strategy",
        status=StrategyStatus.BACKTESTED,
        rules={"entry_conditions": ["MA crossover"]},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=0.0,
        performance=PerformanceMetrics(
            total_return=0.15,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=0.05,
            win_rate=0.65,
            total_trades=50
        ),
        backtest_results=BacktestResults(
            total_return=0.15,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=0.05,
            win_rate=0.65,
            avg_win=100.0,
            avg_loss=-50.0,
            total_trades=50
        )
    )


@pytest.fixture
def demo_strategy():
    """Create a DEMO (active) strategy for testing."""
    return Strategy(
        id="demo-123",
        name="Demo Strategy",
        description="An active demo strategy",
        status=StrategyStatus.DEMO,
        rules={"entry_conditions": ["MA crossover"]},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=30.0,
        activated_at=datetime.now(),
        performance=PerformanceMetrics()
    )


@pytest.fixture
def live_strategy():
    """Create a LIVE (active) strategy for testing."""
    return Strategy(
        id="live-123",
        name="Live Strategy",
        description="An active live strategy",
        status=StrategyStatus.LIVE,
        rules={"entry_conditions": ["MA crossover"]},
        symbols=["MSFT"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=40.0,
        activated_at=datetime.now(),
        performance=PerformanceMetrics()
    )


# ============================================================================
# Task 14.1.1: Test activation preconditions (must be BACKTESTED)
# ============================================================================

def test_activate_backtested_strategy_demo_mode(strategy_engine, backtested_strategy):
    """Test activating a BACKTESTED strategy in DEMO mode."""
    strategy_engine._load_strategy = Mock(return_value=backtested_strategy)
    
    # Should succeed
    strategy_engine.activate_strategy(
        backtested_strategy.id,
        TradingMode.DEMO,
        allocation_percent=30.0
    )
    
    # Verify status changed to DEMO
    assert backtested_strategy.status == StrategyStatus.DEMO
    assert backtested_strategy.activated_at is not None
    assert backtested_strategy.allocation_percent == 30.0
    
    # Verify strategy was saved
    strategy_engine._save_strategy.assert_called()


def test_activate_backtested_strategy_live_mode(strategy_engine, backtested_strategy):
    """Test activating a BACKTESTED strategy in LIVE mode."""
    strategy_engine._load_strategy = Mock(return_value=backtested_strategy)
    
    # Should succeed
    strategy_engine.activate_strategy(
        backtested_strategy.id,
        TradingMode.LIVE,
        allocation_percent=25.0
    )
    
    # Verify status changed to LIVE
    assert backtested_strategy.status == StrategyStatus.LIVE
    assert backtested_strategy.activated_at is not None
    assert backtested_strategy.allocation_percent == 25.0


def test_activate_proposed_strategy_fails(strategy_engine, proposed_strategy):
    """Test that activating a PROPOSED strategy fails."""
    strategy_engine._load_strategy = Mock(return_value=proposed_strategy)
    
    # Should raise ValueError
    with pytest.raises(ValueError, match="Cannot activate strategy in .*PROPOSED"):
        strategy_engine.activate_strategy(
            proposed_strategy.id,
            TradingMode.DEMO,
            allocation_percent=30.0
        )
    
    # Status should remain PROPOSED
    assert proposed_strategy.status == StrategyStatus.PROPOSED


def test_activate_demo_strategy_fails(strategy_engine, demo_strategy):
    """Test that activating an already active DEMO strategy fails."""
    strategy_engine._load_strategy = Mock(return_value=demo_strategy)
    
    # Should raise ValueError
    with pytest.raises(ValueError, match="Cannot activate strategy in .*DEMO"):
        strategy_engine.activate_strategy(
            demo_strategy.id,
            TradingMode.DEMO,
            allocation_percent=30.0
        )


def test_activate_live_strategy_fails(strategy_engine, live_strategy):
    """Test that activating an already active LIVE strategy fails."""
    strategy_engine._load_strategy = Mock(return_value=live_strategy)
    
    # Should raise ValueError
    with pytest.raises(ValueError, match="Cannot activate strategy in .*LIVE"):
        strategy_engine.activate_strategy(
            live_strategy.id,
            TradingMode.LIVE,
            allocation_percent=30.0
        )


def test_activate_retired_strategy_fails(strategy_engine):
    """Test that activating a RETIRED strategy fails."""
    retired_strategy = Strategy(
        id="retired-123",
        name="Retired Strategy",
        description="A retired strategy",
        status=StrategyStatus.RETIRED,
        rules={"entry_conditions": ["MA crossover"]},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        retired_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=retired_strategy)
    
    # Should raise ValueError
    with pytest.raises(ValueError, match="Cannot activate strategy in .*RETIRED"):
        strategy_engine.activate_strategy(
            retired_strategy.id,
            TradingMode.DEMO,
            allocation_percent=30.0
        )


def test_activate_nonexistent_strategy_fails(strategy_engine):
    """Test that activating a non-existent strategy fails."""
    strategy_engine._load_strategy = Mock(return_value=None)
    
    # Should raise ValueError
    with pytest.raises(ValueError, match="Strategy .* not found"):
        strategy_engine.activate_strategy(
            "nonexistent-123",
            TradingMode.DEMO,
            allocation_percent=30.0
        )


def test_activation_sets_timestamp(strategy_engine, backtested_strategy):
    """Test that activation sets the activated_at timestamp."""
    strategy_engine._load_strategy = Mock(return_value=backtested_strategy)
    
    # Verify no activation timestamp initially
    assert backtested_strategy.activated_at is None
    
    before_activation = datetime.now()
    
    strategy_engine.activate_strategy(
        backtested_strategy.id,
        TradingMode.DEMO,
        allocation_percent=30.0
    )
    
    after_activation = datetime.now()
    
    # Verify timestamp was set
    assert backtested_strategy.activated_at is not None
    assert before_activation <= backtested_strategy.activated_at <= after_activation


def test_activation_preserves_strategy_metadata(strategy_engine, backtested_strategy):
    """Test that activation preserves strategy metadata."""
    strategy_engine._load_strategy = Mock(return_value=backtested_strategy)
    
    original_id = backtested_strategy.id
    original_name = backtested_strategy.name
    original_description = backtested_strategy.description
    original_symbols = backtested_strategy.symbols.copy()
    original_rules = backtested_strategy.rules.copy()
    original_created_at = backtested_strategy.created_at
    
    strategy_engine.activate_strategy(
        backtested_strategy.id,
        TradingMode.DEMO,
        allocation_percent=30.0
    )
    
    # Verify metadata unchanged
    assert backtested_strategy.id == original_id
    assert backtested_strategy.name == original_name
    assert backtested_strategy.description == original_description
    assert backtested_strategy.symbols == original_symbols
    assert backtested_strategy.rules == original_rules
    assert backtested_strategy.created_at == original_created_at


# ============================================================================
# Task 14.1.2: Test allocation validation (max 100%)
# ============================================================================

def test_allocation_within_limit(strategy_engine, backtested_strategy):
    """Test activating strategy with allocation within 100% limit."""
    strategy_engine._load_strategy = Mock(return_value=backtested_strategy)
    strategy_engine._calculate_total_active_allocation = Mock(return_value=50.0)
    
    # Should succeed - 50% + 30% = 80% < 100%
    strategy_engine.activate_strategy(
        backtested_strategy.id,
        TradingMode.DEMO,
        allocation_percent=30.0
    )
    
    assert backtested_strategy.status == StrategyStatus.DEMO
    assert backtested_strategy.allocation_percent == 30.0


def test_allocation_exactly_100_percent(strategy_engine, backtested_strategy):
    """Test activating strategy that brings total allocation to exactly 100%."""
    strategy_engine._load_strategy = Mock(return_value=backtested_strategy)
    strategy_engine._calculate_total_active_allocation = Mock(return_value=70.0)
    
    # Should succeed - 70% + 30% = 100%
    strategy_engine.activate_strategy(
        backtested_strategy.id,
        TradingMode.DEMO,
        allocation_percent=30.0
    )
    
    assert backtested_strategy.status == StrategyStatus.DEMO


def test_allocation_exceeds_limit_fails(strategy_engine, backtested_strategy):
    """Test that activating strategy exceeding 100% allocation fails."""
    strategy_engine._load_strategy = Mock(return_value=backtested_strategy)
    strategy_engine._calculate_total_active_allocation = Mock(return_value=80.0)
    
    # Should fail - 80% + 30% = 110% > 100%
    with pytest.raises(ValueError, match="Total allocation would exceed 100%"):
        strategy_engine.activate_strategy(
            backtested_strategy.id,
            TradingMode.DEMO,
            allocation_percent=30.0
        )
    
    # Status should remain BACKTESTED
    assert backtested_strategy.status == StrategyStatus.BACKTESTED


def test_allocation_negative_value_fails(strategy_engine, backtested_strategy):
    """Test that negative allocation percentage fails."""
    strategy_engine._load_strategy = Mock(return_value=backtested_strategy)
    
    # Should fail - negative allocation
    with pytest.raises(ValueError, match="Invalid allocation_percent"):
        strategy_engine.activate_strategy(
            backtested_strategy.id,
            TradingMode.DEMO,
            allocation_percent=-10.0
        )


def test_allocation_over_100_percent_fails(strategy_engine, backtested_strategy):
    """Test that allocation over 100% for single strategy fails."""
    strategy_engine._load_strategy = Mock(return_value=backtested_strategy)
    
    # Should fail - single strategy allocation > 100%
    with pytest.raises(ValueError, match="Invalid allocation_percent"):
        strategy_engine.activate_strategy(
            backtested_strategy.id,
            TradingMode.DEMO,
            allocation_percent=150.0
        )


def test_allocation_zero_percent_allowed(strategy_engine, backtested_strategy):
    """Test that 0% allocation is allowed."""
    strategy_engine._load_strategy = Mock(return_value=backtested_strategy)
    
    # Should succeed - 0% allocation is valid
    strategy_engine.activate_strategy(
        backtested_strategy.id,
        TradingMode.DEMO,
        allocation_percent=0.0
    )
    
    assert backtested_strategy.status == StrategyStatus.DEMO
    assert backtested_strategy.allocation_percent == 0.0


def test_allocation_with_multiple_active_strategies(strategy_engine, backtested_strategy):
    """Test allocation calculation with multiple active strategies."""
    strategy_engine._load_strategy = Mock(return_value=backtested_strategy)
    # Simulate 3 active strategies with 20%, 30%, 25% = 75% total
    strategy_engine._calculate_total_active_allocation = Mock(return_value=75.0)
    
    # Should succeed - 75% + 20% = 95% < 100%
    strategy_engine.activate_strategy(
        backtested_strategy.id,
        TradingMode.DEMO,
        allocation_percent=20.0
    )
    
    assert backtested_strategy.status == StrategyStatus.DEMO


def test_allocation_error_message_includes_details(strategy_engine, backtested_strategy):
    """Test that allocation error message includes current and requested allocations."""
    strategy_engine._load_strategy = Mock(return_value=backtested_strategy)
    strategy_engine._calculate_total_active_allocation = Mock(return_value=85.0)
    
    # Should fail with detailed error message
    with pytest.raises(ValueError) as exc_info:
        strategy_engine.activate_strategy(
            backtested_strategy.id,
            TradingMode.DEMO,
            allocation_percent=20.0
        )
    
    error_message = str(exc_info.value)
    assert "85.0%" in error_message  # Current allocation
    assert "20.0%" in error_message  # Requested allocation
    assert "105.0%" in error_message  # Total would be


# ============================================================================
# Task 14.1.3: Test state transitions (BACKTESTED → DEMO/LIVE)
# ============================================================================

def test_state_transition_backtested_to_demo(strategy_engine, backtested_strategy):
    """Test state transition from BACKTESTED to DEMO."""
    strategy_engine._load_strategy = Mock(return_value=backtested_strategy)
    
    assert backtested_strategy.status == StrategyStatus.BACKTESTED
    
    strategy_engine.activate_strategy(
        backtested_strategy.id,
        TradingMode.DEMO,
        allocation_percent=30.0
    )
    
    assert backtested_strategy.status == StrategyStatus.DEMO


def test_state_transition_backtested_to_live(strategy_engine, backtested_strategy):
    """Test state transition from BACKTESTED to LIVE."""
    strategy_engine._load_strategy = Mock(return_value=backtested_strategy)
    
    assert backtested_strategy.status == StrategyStatus.BACKTESTED
    
    strategy_engine.activate_strategy(
        backtested_strategy.id,
        TradingMode.LIVE,
        allocation_percent=30.0
    )
    
    assert backtested_strategy.status == StrategyStatus.LIVE


def test_activation_adds_to_active_strategies(strategy_engine, backtested_strategy):
    """Test that activation adds strategy to active strategies dict."""
    strategy_engine._load_strategy = Mock(return_value=backtested_strategy)
    
    # Verify not in active strategies initially
    assert backtested_strategy.id not in strategy_engine._active_strategies
    
    strategy_engine.activate_strategy(
        backtested_strategy.id,
        TradingMode.DEMO,
        allocation_percent=30.0
    )
    
    # Verify added to active strategies
    assert backtested_strategy.id in strategy_engine._active_strategies
    assert strategy_engine._active_strategies[backtested_strategy.id] == backtested_strategy


def test_activation_persists_to_database(strategy_engine, backtested_strategy):
    """Test that activation persists changes to database."""
    strategy_engine._load_strategy = Mock(return_value=backtested_strategy)
    
    strategy_engine.activate_strategy(
        backtested_strategy.id,
        TradingMode.DEMO,
        allocation_percent=30.0
    )
    
    # Verify _save_strategy was called
    strategy_engine._save_strategy.assert_called_with(backtested_strategy)


def test_activation_with_different_modes(strategy_engine):
    """Test activating different strategies in different modes."""
    strategy1 = Strategy(
        id="strategy-1",
        name="Strategy 1",
        description="First strategy",
        status=StrategyStatus.BACKTESTED,
        rules={"entry_conditions": ["MA crossover"]},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    strategy2 = Strategy(
        id="strategy-2",
        name="Strategy 2",
        description="Second strategy",
        status=StrategyStatus.BACKTESTED,
        rules={"entry_conditions": ["RSI oversold"]},
        symbols=["MSFT"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    def load_strategy_side_effect(strategy_id):
        if strategy_id == "strategy-1":
            return strategy1
        elif strategy_id == "strategy-2":
            return strategy2
        return None
    
    strategy_engine._load_strategy = Mock(side_effect=load_strategy_side_effect)
    
    # Activate first in DEMO mode
    strategy_engine.activate_strategy(
        strategy1.id,
        TradingMode.DEMO,
        allocation_percent=30.0
    )
    
    # Activate second in LIVE mode
    strategy_engine.activate_strategy(
        strategy2.id,
        TradingMode.LIVE,
        allocation_percent=40.0
    )
    
    # Verify both activated with correct modes
    assert strategy1.status == StrategyStatus.DEMO
    assert strategy2.status == StrategyStatus.LIVE


# ============================================================================
# Task 14.1.4: Test deactivation (DEMO/LIVE → BACKTESTED)
# ============================================================================

def test_deactivate_demo_strategy(strategy_engine, demo_strategy):
    """Test deactivating a DEMO strategy."""
    strategy_engine._load_strategy = Mock(return_value=demo_strategy)
    strategy_engine._active_strategies[demo_strategy.id] = demo_strategy
    
    assert demo_strategy.status == StrategyStatus.DEMO
    
    strategy_engine.deactivate_strategy(demo_strategy.id)
    
    # Verify status changed to BACKTESTED
    assert demo_strategy.status == StrategyStatus.BACKTESTED
    
    # Verify removed from active strategies
    assert demo_strategy.id not in strategy_engine._active_strategies
    
    # Verify saved to database
    strategy_engine._save_strategy.assert_called()


def test_deactivate_live_strategy(strategy_engine, live_strategy):
    """Test deactivating a LIVE strategy."""
    strategy_engine._load_strategy = Mock(return_value=live_strategy)
    strategy_engine._active_strategies[live_strategy.id] = live_strategy
    
    assert live_strategy.status == StrategyStatus.LIVE
    
    strategy_engine.deactivate_strategy(live_strategy.id)
    
    # Verify status changed to BACKTESTED
    assert live_strategy.status == StrategyStatus.BACKTESTED


def test_deactivate_nonexistent_strategy_fails(strategy_engine):
    """Test that deactivating a non-existent strategy fails."""
    strategy_engine._load_strategy = Mock(return_value=None)
    
    # Should raise ValueError
    with pytest.raises(ValueError, match="Strategy .* not found"):
        strategy_engine.deactivate_strategy("nonexistent-123")


def test_deactivate_removes_from_active_strategies(strategy_engine, demo_strategy):
    """Test that deactivation removes strategy from active strategies dict."""
    strategy_engine._load_strategy = Mock(return_value=demo_strategy)
    strategy_engine._active_strategies[demo_strategy.id] = demo_strategy
    
    # Verify in active strategies
    assert demo_strategy.id in strategy_engine._active_strategies
    
    strategy_engine.deactivate_strategy(demo_strategy.id)
    
    # Verify removed
    assert demo_strategy.id not in strategy_engine._active_strategies


def test_deactivate_strategy_not_in_active_dict(strategy_engine, demo_strategy):
    """Test deactivating strategy that's not in active strategies dict."""
    strategy_engine._load_strategy = Mock(return_value=demo_strategy)
    # Don't add to _active_strategies
    
    # Should still succeed and update status
    strategy_engine.deactivate_strategy(demo_strategy.id)
    
    assert demo_strategy.status == StrategyStatus.BACKTESTED


def test_deactivate_preserves_performance_metrics(strategy_engine, demo_strategy):
    """Test that deactivation preserves performance metrics."""
    strategy_engine._load_strategy = Mock(return_value=demo_strategy)
    strategy_engine._active_strategies[demo_strategy.id] = demo_strategy
    
    original_performance = demo_strategy.performance
    
    strategy_engine.deactivate_strategy(demo_strategy.id)
    
    # Performance metrics should be unchanged
    assert demo_strategy.performance == original_performance


def test_deactivate_preserves_allocation(strategy_engine, demo_strategy):
    """Test that deactivation preserves allocation percentage."""
    strategy_engine._load_strategy = Mock(return_value=demo_strategy)
    strategy_engine._active_strategies[demo_strategy.id] = demo_strategy
    
    original_allocation = demo_strategy.allocation_percent
    
    strategy_engine.deactivate_strategy(demo_strategy.id)
    
    # Allocation should be unchanged
    assert demo_strategy.allocation_percent == original_allocation


def test_deactivate_preserves_activated_timestamp(strategy_engine, demo_strategy):
    """Test that deactivation preserves activated_at timestamp."""
    strategy_engine._load_strategy = Mock(return_value=demo_strategy)
    strategy_engine._active_strategies[demo_strategy.id] = demo_strategy
    
    original_activated_at = demo_strategy.activated_at
    
    strategy_engine.deactivate_strategy(demo_strategy.id)
    
    # Timestamp should be unchanged
    assert demo_strategy.activated_at == original_activated_at


def test_deactivate_persists_to_database(strategy_engine, demo_strategy):
    """Test that deactivation persists changes to database."""
    strategy_engine._load_strategy = Mock(return_value=demo_strategy)
    strategy_engine._active_strategies[demo_strategy.id] = demo_strategy
    
    strategy_engine.deactivate_strategy(demo_strategy.id)
    
    # Verify _save_strategy was called
    strategy_engine._save_strategy.assert_called_with(demo_strategy)


def test_activate_then_deactivate_cycle(strategy_engine, backtested_strategy):
    """Test full activation and deactivation cycle."""
    strategy_engine._load_strategy = Mock(return_value=backtested_strategy)
    
    # Initial state
    assert backtested_strategy.status == StrategyStatus.BACKTESTED
    
    # Activate
    strategy_engine.activate_strategy(
        backtested_strategy.id,
        TradingMode.DEMO,
        allocation_percent=30.0
    )
    
    assert backtested_strategy.status == StrategyStatus.DEMO
    assert backtested_strategy.id in strategy_engine._active_strategies
    
    # Deactivate
    strategy_engine.deactivate_strategy(backtested_strategy.id)
    
    assert backtested_strategy.status == StrategyStatus.BACKTESTED
    assert backtested_strategy.id not in strategy_engine._active_strategies


def test_deactivate_multiple_strategies(strategy_engine, demo_strategy, live_strategy):
    """Test deactivating multiple strategies."""
    def load_strategy_side_effect(strategy_id):
        if strategy_id == demo_strategy.id:
            return demo_strategy
        elif strategy_id == live_strategy.id:
            return live_strategy
        return None
    
    strategy_engine._load_strategy = Mock(side_effect=load_strategy_side_effect)
    strategy_engine._active_strategies[demo_strategy.id] = demo_strategy
    strategy_engine._active_strategies[live_strategy.id] = live_strategy
    
    # Deactivate first strategy
    strategy_engine.deactivate_strategy(demo_strategy.id)
    assert demo_strategy.status == StrategyStatus.BACKTESTED
    assert demo_strategy.id not in strategy_engine._active_strategies
    
    # Deactivate second strategy
    strategy_engine.deactivate_strategy(live_strategy.id)
    assert live_strategy.status == StrategyStatus.BACKTESTED
    assert live_strategy.id not in strategy_engine._active_strategies
    
    # Both should be deactivated
    assert len(strategy_engine._active_strategies) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
