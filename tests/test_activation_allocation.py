"""Tests for strategy activation allocation validation."""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock

from src.strategy.strategy_engine import StrategyEngine
from src.models.dataclasses import Strategy, RiskConfig, PerformanceMetrics
from src.models.enums import StrategyStatus, TradingMode
from src.models.orm import StrategyORM


@pytest.fixture
def strategy_engine():
    """Create a StrategyEngine instance with mocked dependencies."""
    llm_service = Mock()
    market_data = Mock()
    engine = StrategyEngine(llm_service, market_data)
    
    # Mock database methods
    engine._save_strategy = Mock()
    engine._load_strategy = Mock()
    
    return engine


def test_activate_strategy_with_allocation(strategy_engine):
    """Test strategy activation with allocation percentage."""
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.BACKTESTED,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=0.0,
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    strategy_engine._calculate_total_active_allocation = Mock(return_value=0.0)
    
    # Activate with 30% allocation
    strategy_engine.activate_strategy("test-123", TradingMode.DEMO, allocation_percent=30.0)
    
    assert strategy.status == StrategyStatus.DEMO
    assert strategy.allocation_percent == 30.0
    assert strategy.activated_at is not None
    strategy_engine._save_strategy.assert_called()


def test_activate_strategy_allocation_exceeds_limit(strategy_engine):
    """Test that activation fails when total allocation would exceed 100%."""
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.BACKTESTED,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=0.0,
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    # Mock that 80% is already allocated
    strategy_engine._calculate_total_active_allocation = Mock(return_value=80.0)
    
    # Try to activate with 30% allocation (would total 110%)
    with pytest.raises(ValueError, match="Total allocation would exceed 100%"):
        strategy_engine.activate_strategy("test-123", TradingMode.DEMO, allocation_percent=30.0)


def test_activate_strategy_allocation_exactly_100(strategy_engine):
    """Test that activation succeeds when total allocation equals exactly 100%."""
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.BACKTESTED,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=0.0,
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    # Mock that 70% is already allocated
    strategy_engine._calculate_total_active_allocation = Mock(return_value=70.0)
    
    # Activate with 30% allocation (exactly 100%)
    strategy_engine.activate_strategy("test-123", TradingMode.DEMO, allocation_percent=30.0)
    
    assert strategy.status == StrategyStatus.DEMO
    assert strategy.allocation_percent == 30.0


def test_activate_strategy_invalid_allocation_negative(strategy_engine):
    """Test that activation fails with negative allocation."""
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.BACKTESTED,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=0.0,
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    
    # Try to activate with negative allocation
    with pytest.raises(ValueError, match="Invalid allocation_percent"):
        strategy_engine.activate_strategy("test-123", TradingMode.DEMO, allocation_percent=-10.0)


def test_activate_strategy_invalid_allocation_over_100(strategy_engine):
    """Test that activation fails with allocation over 100%."""
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.BACKTESTED,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=0.0,
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    
    # Try to activate with allocation over 100%
    with pytest.raises(ValueError, match="Invalid allocation_percent"):
        strategy_engine.activate_strategy("test-123", TradingMode.DEMO, allocation_percent=150.0)


def test_activate_strategy_zero_allocation(strategy_engine):
    """Test that activation succeeds with zero allocation."""
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.BACKTESTED,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=0.0,
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    strategy_engine._calculate_total_active_allocation = Mock(return_value=50.0)
    
    # Activate with 0% allocation
    strategy_engine.activate_strategy("test-123", TradingMode.DEMO, allocation_percent=0.0)
    
    assert strategy.status == StrategyStatus.DEMO
    assert strategy.allocation_percent == 0.0


def test_calculate_total_active_allocation(strategy_engine):
    """Test calculation of total active allocation."""
    # Create mock session and query
    mock_session = MagicMock()
    mock_query = MagicMock()
    
    # Create mock active strategies
    strategy1 = Mock(spec=StrategyORM)
    strategy1.id = "strategy-1"
    strategy1.allocation_percent = 30.0
    
    strategy2 = Mock(spec=StrategyORM)
    strategy2.id = "strategy-2"
    strategy2.allocation_percent = 40.0
    
    # Setup query chain
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = [strategy1, strategy2]
    mock_session.query.return_value = mock_query
    
    # Mock database
    strategy_engine.db.get_session = Mock(return_value=mock_session)
    
    # Calculate total allocation
    total = strategy_engine._calculate_total_active_allocation()
    
    assert total == 70.0


def test_calculate_total_active_allocation_exclude_strategy(strategy_engine):
    """Test calculation of total active allocation excluding a specific strategy."""
    # Create mock session and query
    mock_session = MagicMock()
    mock_query = MagicMock()
    
    # Create mock active strategies
    strategy1 = Mock(spec=StrategyORM)
    strategy1.id = "strategy-1"
    strategy1.allocation_percent = 30.0
    
    strategy2 = Mock(spec=StrategyORM)
    strategy2.id = "strategy-2"
    strategy2.allocation_percent = 40.0
    
    # Setup query chain
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = [strategy1, strategy2]
    mock_session.query.return_value = mock_query
    
    # Mock database
    strategy_engine.db.get_session = Mock(return_value=mock_session)
    
    # Calculate total allocation excluding strategy-1
    total = strategy_engine._calculate_total_active_allocation(exclude_strategy_id="strategy-1")
    
    # Should only count strategy-2
    assert total == 40.0



def test_update_allocation_for_active_strategy(strategy_engine):
    """Test updating allocation for an active strategy."""
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.DEMO,  # Active strategy
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=30.0,
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    strategy_engine._calculate_total_active_allocation = Mock(return_value=20.0)  # Other strategies
    
    # Update allocation to 40%
    strategy.allocation_percent = 40.0
    strategy_engine._save_strategy(strategy)
    
    assert strategy.allocation_percent == 40.0
    strategy_engine._save_strategy.assert_called()


def test_update_allocation_exceeds_limit(strategy_engine):
    """Test that updating allocation fails when total would exceed 100%."""
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.DEMO,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=30.0,
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    # Mock that 80% is already allocated by other strategies
    strategy_engine._calculate_total_active_allocation = Mock(return_value=80.0)
    
    # Verify that 80% + 50% would exceed 100%
    new_allocation = 50.0
    current_total = strategy_engine._calculate_total_active_allocation(exclude_strategy_id=strategy.id)
    new_total = current_total + new_allocation
    
    assert new_total > 100.0


def test_update_allocation_to_zero(strategy_engine):
    """Test updating allocation to zero for an active strategy."""
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.DEMO,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=30.0,
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    strategy_engine._calculate_total_active_allocation = Mock(return_value=50.0)
    
    # Update allocation to 0%
    strategy.allocation_percent = 0.0
    strategy_engine._save_strategy(strategy)
    
    assert strategy.allocation_percent == 0.0


def test_update_allocation_for_inactive_strategy_should_fail(strategy_engine):
    """Test that updating allocation for inactive strategy should fail."""
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.BACKTESTED,  # Not active
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=0.0,
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    
    # Verify strategy is not active
    assert strategy.status not in [StrategyStatus.DEMO, StrategyStatus.LIVE]


def test_update_allocation_to_max_100(strategy_engine):
    """Test updating allocation to exactly 100% when no other strategies are active."""
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.DEMO,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=50.0,
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    # No other active strategies
    strategy_engine._calculate_total_active_allocation = Mock(return_value=0.0)
    
    # Update allocation to 100%
    strategy.allocation_percent = 100.0
    strategy_engine._save_strategy(strategy)
    
    assert strategy.allocation_percent == 100.0
