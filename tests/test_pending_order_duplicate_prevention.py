"""
Unit tests for pending order duplicate prevention in signal coordination.

Tests the _coordinate_signals method to ensure it properly filters signals
when strategies already have pending orders for the same symbol/side.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock
from src.core.trading_scheduler import TradingScheduler
from src.models.dataclasses import TradingSignal, Strategy, RiskConfig, PerformanceMetrics
from src.models.enums import SignalAction, OrderStatus, OrderSide, OrderType, StrategyStatus
from src.models.orm import OrderORM


@pytest.fixture
def mock_components():
    """Create mock components for TradingScheduler."""
    scheduler = TradingScheduler()
    return scheduler


@pytest.fixture
def sample_strategy():
    """Create a sample strategy for testing."""
    return Strategy(
        id="test_strategy_auto",
        name="Test Strategy",
        description="Test strategy for unit tests",
        status=StrategyStatus.DEMO,
        symbols=["SPY"],
        allocation_percent=10.0,
        risk_params=RiskConfig(
            stop_loss_pct=0.02,
            take_profit_pct=0.05,
            max_position_size_pct=0.05
        ),
        rules={"entry": [], "exit": []},
        created_at=datetime.now()
    )


@pytest.fixture
def sample_signal():
    """Create a sample signal for testing."""
    return TradingSignal(
        strategy_id="test_strategy_auto",
        symbol="SPY",
        action=SignalAction.ENTER_LONG,
        confidence=0.85,
        reasoning="Test signal",
        indicators={},
        generated_at=datetime.now()
    )


def test_coordinate_signals_filters_pending_orders(mock_components, sample_strategy, sample_signal):
    """Test that signals are filtered when strategy has pending orders."""
    # Create a pending order for the same strategy-symbol-side
    pending_order = OrderORM(
        id="order_1",
        strategy_id="test_strategy_auto",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=OrderStatus.PENDING,
        submitted_at=datetime.now()
    )
    
    # Prepare batch results with one signal
    batch_results = {
        "test_strategy_auto": [sample_signal]
    }
    
    # Prepare strategy map
    strategy_map = {
        "test_strategy_auto": (sample_strategy, Mock())
    }
    
    # Call _coordinate_signals with pending order
    result = mock_components._coordinate_signals(
        batch_results=batch_results,
        strategy_map=strategy_map,
        existing_positions=[],
        pending_orders=[pending_order]
    )
    
    # Assert signal was filtered
    assert len(result) == 0, "Signal should be filtered due to pending order"


def test_coordinate_signals_allows_different_strategy_pending_orders(mock_components, sample_signal):
    """Test that signals are allowed when pending order is from different strategy."""
    # Create strategies
    strategy_1 = Strategy(
        id="test_strategy_auto",
        name="Strategy 1",
        description="Test strategy 1",
        status=StrategyStatus.DEMO,
        symbols=["SPY"],
        allocation_percent=10.0,
        risk_params=RiskConfig(stop_loss_pct=0.02, take_profit_pct=0.05, max_position_size_pct=0.05),
        rules={"entry": [], "exit": []},
        created_at=datetime.now()
    )
    
    strategy_2 = Strategy(
        id="test_strategy_auto_2",
        name="Strategy 2",
        description="Test strategy 2",
        status=StrategyStatus.DEMO,
        symbols=["SPY"],
        allocation_percent=10.0,
        risk_params=RiskConfig(stop_loss_pct=0.02, take_profit_pct=0.05, max_position_size_pct=0.05),
        rules={"entry": [], "exit": []},
        created_at=datetime.now()
    )
    
    # Create a pending order for strategy_2
    pending_order = OrderORM(
        id="order_1",
        strategy_id="test_strategy_auto_2",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=OrderStatus.PENDING,
        submitted_at=datetime.now()
    )
    
    # Create signal for strategy_1
    signal_1 = TradingSignal(
        strategy_id="test_strategy_auto",
        symbol="SPY",
        action=SignalAction.ENTER_LONG,
        confidence=0.85,
        reasoning="Test signal",
        indicators={},
        generated_at=datetime.now()
    )
    
    # Prepare batch results
    batch_results = {
        "test_strategy_auto": [signal_1]
    }
    
    # Prepare strategy map
    strategy_map = {
        "test_strategy_auto": (strategy_1, Mock()),
        "test_strategy_auto_2": (strategy_2, Mock())
    }
    
    # Call _coordinate_signals
    result = mock_components._coordinate_signals(
        batch_results=batch_results,
        strategy_map=strategy_map,
        existing_positions=[],
        pending_orders=[pending_order]
    )
    
    # Assert signal was NOT filtered (different strategy)
    assert "test_strategy_auto" in result, "Signal should be allowed (different strategy has pending order)"
    assert len(result["test_strategy_auto"]) == 1


def test_coordinate_signals_filters_submitted_orders(mock_components, sample_strategy, sample_signal):
    """Test that signals are filtered when strategy has SUBMITTED orders."""
    # Create a submitted order (not just pending)
    submitted_order = OrderORM(
        id="order_1",
        strategy_id="test_strategy_auto",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=OrderStatus.PENDING,
        submitted_at=datetime.now()
    )
    
    # Prepare batch results
    batch_results = {
        "test_strategy_auto": [sample_signal]
    }
    
    # Prepare strategy map
    strategy_map = {
        "test_strategy_auto": (sample_strategy, Mock())
    }
    
    # Call _coordinate_signals
    result = mock_components._coordinate_signals(
        batch_results=batch_results,
        strategy_map=strategy_map,
        existing_positions=[],
        pending_orders=[submitted_order]
    )
    
    # Assert signal was filtered
    assert len(result) == 0, "Signal should be filtered due to submitted order"


def test_coordinate_signals_allows_filled_orders(mock_components, sample_strategy, sample_signal):
    """Test that signals are allowed when order is already FILLED."""
    # Create a filled order (should not block new signals)
    filled_order = OrderORM(
        id="order_1",
        strategy_id="test_strategy_auto",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=OrderStatus.FILLED,
        submitted_at=datetime.now(),
        filled_at=datetime.now()
    )
    
    # Prepare batch results
    batch_results = {
        "test_strategy_auto": [sample_signal]
    }
    
    # Prepare strategy map
    strategy_map = {
        "test_strategy_auto": (sample_strategy, Mock())
    }
    
    # Call _coordinate_signals
    result = mock_components._coordinate_signals(
        batch_results=batch_results,
        strategy_map=strategy_map,
        existing_positions=[],
        pending_orders=[filled_order]
    )
    
    # Assert signal was NOT filtered (filled order doesn't block)
    assert "test_strategy_auto" in result, "Signal should be allowed (order is filled)"
    assert len(result["test_strategy_auto"]) == 1


def test_coordinate_signals_allows_opposite_direction(mock_components, sample_strategy):
    """Test that signals are allowed for opposite direction even with pending order."""
    # Create a pending BUY order
    pending_order = OrderORM(
        id="order_1",
        strategy_id="test_strategy_auto",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=OrderStatus.PENDING,
        submitted_at=datetime.now()
    )
    
    # Create a SHORT signal (opposite direction)
    short_signal = TradingSignal(
        strategy_id="test_strategy_auto",
        symbol="SPY",
        action=SignalAction.ENTER_SHORT,
        confidence=0.85,
        reasoning="Test short signal",
        indicators={},
        generated_at=datetime.now()
    )
    
    # Prepare batch results
    batch_results = {
        "test_strategy_auto": [short_signal]
    }
    
    # Prepare strategy map
    strategy_map = {
        "test_strategy_auto": (sample_strategy, Mock())
    }
    
    # Call _coordinate_signals
    result = mock_components._coordinate_signals(
        batch_results=batch_results,
        strategy_map=strategy_map,
        existing_positions=[],
        pending_orders=[pending_order]
    )
    
    # Assert signal was NOT filtered (opposite direction)
    assert "test_strategy_auto" in result, "Signal should be allowed (opposite direction)"
    assert len(result["test_strategy_auto"]) == 1


def test_coordinate_signals_filters_multiple_strategies_with_pending_orders(mock_components):
    """Test that multiple strategies with pending orders are all filtered correctly."""
    # Create two strategies
    strategy_1 = Strategy(
        id="test_strategy_auto",
        name="Strategy 1",
        description="Test strategy 1",
        status=StrategyStatus.DEMO,
        symbols=["SPY"],
        allocation_percent=10.0,
        risk_params=RiskConfig(stop_loss_pct=0.02, take_profit_pct=0.05, max_position_size_pct=0.05),
        rules={"entry": [], "exit": []},
        created_at=datetime.now()
    )
    
    strategy_2 = Strategy(
        id="test_strategy_auto_2",
        name="Strategy 2",
        description="Test strategy 2",
        status=StrategyStatus.DEMO,
        symbols=["SPY"],
        allocation_percent=10.0,
        risk_params=RiskConfig(stop_loss_pct=0.02, take_profit_pct=0.05, max_position_size_pct=0.05),
        rules={"entry": [], "exit": []},
        created_at=datetime.now()
    )
    
    # Create pending orders for both strategies
    pending_order_1 = OrderORM(
        id="order_1",
        strategy_id="test_strategy_auto",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=OrderStatus.PENDING,
        submitted_at=datetime.now()
    )
    
    pending_order_2 = OrderORM(
        id="order_2",
        strategy_id="test_strategy_auto_2",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=OrderStatus.PENDING,
        submitted_at=datetime.now()
    )
    
    # Create signals for both strategies
    signal_1 = TradingSignal(
        strategy_id="test_strategy_auto",
        symbol="SPY",
        action=SignalAction.ENTER_LONG,
        confidence=0.85,
        reasoning="Test signal 1",
        indicators={},
        generated_at=datetime.now()
    )
    
    signal_2 = TradingSignal(
        strategy_id="test_strategy_auto_2",
        symbol="SPY",
        action=SignalAction.ENTER_LONG,
        confidence=0.90,
        reasoning="Test signal 2",
        indicators={},
        generated_at=datetime.now()
    )
    
    # Prepare batch results
    batch_results = {
        "test_strategy_auto": [signal_1],
        "test_strategy_auto_2": [signal_2]
    }
    
    # Prepare strategy map
    strategy_map = {
        "test_strategy_auto": (strategy_1, Mock()),
        "test_strategy_auto_2": (strategy_2, Mock())
    }
    
    # Call _coordinate_signals
    result = mock_components._coordinate_signals(
        batch_results=batch_results,
        strategy_map=strategy_map,
        existing_positions=[],
        pending_orders=[pending_order_1, pending_order_2]
    )
    
    # Assert both signals were filtered
    assert len(result) == 0, "Both signals should be filtered due to pending orders"


def test_coordinate_signals_allows_different_symbols(mock_components, sample_strategy):
    """Test that signals for different symbols are allowed even with pending orders."""
    # Create a pending order for SPY
    pending_order = OrderORM(
        id="order_1",
        strategy_id="test_strategy_auto",
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=OrderStatus.PENDING,
        submitted_at=datetime.now()
    )
    
    # Create a signal for QQQ (different symbol)
    qqq_signal = TradingSignal(
        strategy_id="test_strategy_auto",
        symbol="QQQ",
        action=SignalAction.ENTER_LONG,
        confidence=0.85,
        reasoning="Test QQQ signal",
        indicators={},
        generated_at=datetime.now()
    )
    
    # Prepare batch results
    batch_results = {
        "test_strategy_auto": [qqq_signal]
    }
    
    # Prepare strategy map
    strategy_map = {
        "test_strategy_auto": (sample_strategy, Mock())
    }
    
    # Call _coordinate_signals
    result = mock_components._coordinate_signals(
        batch_results=batch_results,
        strategy_map=strategy_map,
        existing_positions=[],
        pending_orders=[pending_order]
    )
    
    # Assert signal was NOT filtered (different symbol)
    assert "test_strategy_auto" in result, "Signal should be allowed (different symbol)"
    assert len(result["test_strategy_auto"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
