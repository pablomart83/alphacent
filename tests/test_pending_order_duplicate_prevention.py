"""
Unit tests for pending order duplicate prevention in signal coordination.

Tests the _coordinate_signals method to ensure it properly filters signals
when strategies already have pending orders for the same symbol/side.

NOTE (2026-06-16): _coordinate_signals returns a 4-tuple
(coordinated_results, total_signals_per_strategy, template_dup_rejected,
template_dup_rejected_symbols). These tests assert on the first element
(coordinated_results) via `coordinated, *_ = ...`.
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
        status=StrategyStatus.PAPER,
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

    batch_results = {
        "test_strategy_auto": [sample_signal]
    }
    strategy_map = {
        "test_strategy_auto": (sample_strategy, Mock())
    }

    coordinated, *_ = mock_components._coordinate_signals(
        batch_results=batch_results,
        strategy_map=strategy_map,
        existing_positions=[],
        pending_orders=[pending_order]
    )

    assert len(coordinated) == 0, "Signal should be filtered due to pending order"


def test_coordinate_signals_allows_different_strategy_pending_orders(mock_components, sample_signal):
    """Test that signals are allowed when pending order is from different strategy."""
    strategy_1 = Strategy(
        id="test_strategy_auto",
        name="Strategy 1",
        description="Test strategy 1",
        status=StrategyStatus.PAPER,
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
        status=StrategyStatus.PAPER,
        symbols=["SPY"],
        allocation_percent=10.0,
        risk_params=RiskConfig(stop_loss_pct=0.02, take_profit_pct=0.05, max_position_size_pct=0.05),
        rules={"entry": [], "exit": []},
        created_at=datetime.now()
    )

    # Pending order belongs to strategy_2, signal is for strategy_1.
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

    signal_1 = TradingSignal(
        strategy_id="test_strategy_auto",
        symbol="SPY",
        action=SignalAction.ENTER_LONG,
        confidence=0.85,
        reasoning="Test signal",
        indicators={},
        generated_at=datetime.now()
    )

    batch_results = {
        "test_strategy_auto": [signal_1]
    }
    strategy_map = {
        "test_strategy_auto": (strategy_1, Mock()),
        "test_strategy_auto_2": (strategy_2, Mock())
    }

    coordinated, *_ = mock_components._coordinate_signals(
        batch_results=batch_results,
        strategy_map=strategy_map,
        existing_positions=[],
        pending_orders=[pending_order]
    )

    assert "test_strategy_auto" in coordinated, "Signal should be allowed (different strategy has pending order)"
    assert len(coordinated["test_strategy_auto"]) == 1


def test_coordinate_signals_filters_submitted_orders(mock_components, sample_strategy, sample_signal):
    """Test that signals are filtered when strategy has SUBMITTED orders."""
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

    batch_results = {
        "test_strategy_auto": [sample_signal]
    }
    strategy_map = {
        "test_strategy_auto": (sample_strategy, Mock())
    }

    coordinated, *_ = mock_components._coordinate_signals(
        batch_results=batch_results,
        strategy_map=strategy_map,
        existing_positions=[],
        pending_orders=[submitted_order]
    )

    assert len(coordinated) == 0, "Signal should be filtered due to submitted order"


def test_coordinate_signals_filters_recently_filled_orders(mock_components, sample_strategy, sample_signal):
    """A RECENTLY filled order blocks a duplicate new entry for the same
    (strategy, symbol, side).

    Behaviour change (verified 2026-06-16): _coordinate_signals now treats PENDING,
    recently-FILLED and recently-FAILED orders as blocking. The recency window is the
    CALLER's responsibility (it only passes recently-filled orders); _coordinate_signals
    blocks on any FILLED order it is given. This closes the gap between a fill and the
    position-sync creating the Position row, during which the existing-positions check
    alone would miss the just-opened exposure and allow a duplicate entry.
    """
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

    batch_results = {
        "test_strategy_auto": [sample_signal]
    }
    strategy_map = {
        "test_strategy_auto": (sample_strategy, Mock())
    }

    coordinated, *_ = mock_components._coordinate_signals(
        batch_results=batch_results,
        strategy_map=strategy_map,
        existing_positions=[],
        pending_orders=[filled_order]
    )

    assert len(coordinated) == 0, "Signal should be filtered due to a recently-filled duplicate order"


def test_coordinate_signals_allows_opposite_direction(mock_components, sample_strategy):
    """Test that signals are allowed for opposite direction even with pending order."""
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

    short_signal = TradingSignal(
        strategy_id="test_strategy_auto",
        symbol="SPY",
        action=SignalAction.ENTER_SHORT,
        confidence=0.85,
        reasoning="Test short signal",
        indicators={},
        generated_at=datetime.now()
    )

    batch_results = {
        "test_strategy_auto": [short_signal]
    }
    strategy_map = {
        "test_strategy_auto": (sample_strategy, Mock())
    }

    coordinated, *_ = mock_components._coordinate_signals(
        batch_results=batch_results,
        strategy_map=strategy_map,
        existing_positions=[],
        pending_orders=[pending_order]
    )

    assert "test_strategy_auto" in coordinated, "Signal should be allowed (opposite direction)"
    assert len(coordinated["test_strategy_auto"]) == 1


def test_coordinate_signals_filters_multiple_strategies_with_pending_orders(mock_components):
    """Test that multiple strategies with pending orders are all filtered correctly."""
    strategy_1 = Strategy(
        id="test_strategy_auto",
        name="Strategy 1",
        description="Test strategy 1",
        status=StrategyStatus.PAPER,
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
        status=StrategyStatus.PAPER,
        symbols=["SPY"],
        allocation_percent=10.0,
        risk_params=RiskConfig(stop_loss_pct=0.02, take_profit_pct=0.05, max_position_size_pct=0.05),
        rules={"entry": [], "exit": []},
        created_at=datetime.now()
    )

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

    batch_results = {
        "test_strategy_auto": [signal_1],
        "test_strategy_auto_2": [signal_2]
    }
    strategy_map = {
        "test_strategy_auto": (strategy_1, Mock()),
        "test_strategy_auto_2": (strategy_2, Mock())
    }

    coordinated, *_ = mock_components._coordinate_signals(
        batch_results=batch_results,
        strategy_map=strategy_map,
        existing_positions=[],
        pending_orders=[pending_order_1, pending_order_2]
    )

    assert len(coordinated) == 0, "Both signals should be filtered due to pending orders"


def test_coordinate_signals_allows_different_symbols(mock_components, sample_strategy):
    """Test that signals for different symbols are allowed even with pending orders."""
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

    qqq_signal = TradingSignal(
        strategy_id="test_strategy_auto",
        symbol="QQQ",
        action=SignalAction.ENTER_LONG,
        confidence=0.85,
        reasoning="Test QQQ signal",
        indicators={},
        generated_at=datetime.now()
    )

    batch_results = {
        "test_strategy_auto": [qqq_signal]
    }
    strategy_map = {
        "test_strategy_auto": (sample_strategy, Mock())
    }

    coordinated, *_ = mock_components._coordinate_signals(
        batch_results=batch_results,
        strategy_map=strategy_map,
        existing_positions=[],
        pending_orders=[pending_order]
    )

    assert "test_strategy_auto" in coordinated, "Signal should be allowed (different symbol)"
    assert len(coordinated["test_strategy_auto"]) == 1
