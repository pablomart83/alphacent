"""
Tests for strategy WebSocket broadcasting functionality.

Validates: Task 25.1 - Update StrategyEngine to broadcast updates
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from src.strategy.strategy_engine import StrategyEngine
from src.models import Strategy, StrategyStatus, PerformanceMetrics, RiskConfig, TradingMode


@pytest.fixture
def mock_llm_service():
    """Create mock LLM service."""
    return Mock()


@pytest.fixture
def mock_market_data():
    """Create mock market data manager."""
    return Mock()


@pytest.fixture
def mock_websocket_manager():
    """Create mock WebSocket manager."""
    ws_manager = Mock()
    ws_manager.broadcast_strategy_update = AsyncMock()
    return ws_manager


@pytest.fixture
def strategy_engine(mock_llm_service, mock_market_data, mock_websocket_manager):
    """Create StrategyEngine with mocked dependencies including WebSocket manager."""
    with patch('src.strategy.strategy_engine.get_database'):
        engine = StrategyEngine(mock_llm_service, mock_market_data, mock_websocket_manager)
        engine._save_strategy = Mock()
        engine._load_strategy = Mock()
        return engine


@pytest.fixture
def sample_strategy():
    """Create a sample strategy for testing."""
    return Strategy(
        id="test-strategy-123",
        name="Test Strategy",
        description="A test strategy",
        status=StrategyStatus.BACKTESTED,
        rules={"entry": "RSI < 30", "exit": "RSI > 70"},
        symbols=["AAPL", "GOOGL"],
        risk_params=RiskConfig(
            max_position_size_pct=0.1,
            stop_loss_pct=0.05,
            take_profit_pct=0.10,
            max_drawdown_pct=0.20
        ),
        allocation_percent=30.0,
        created_at=datetime.now(),
        performance=PerformanceMetrics(
            total_return=0.15,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=0.08,
            win_rate=0.65,
            avg_win=500.0,
            avg_loss=-200.0,
            total_trades=20
        )
    )


def test_broadcast_on_strategy_activation(strategy_engine, mock_websocket_manager, sample_strategy):
    """Test that strategy activation broadcasts update via WebSocket."""
    # Setup
    strategy_engine._load_strategy.return_value = sample_strategy
    strategy_engine._calculate_total_active_allocation = Mock(return_value=0.0)
    
    # Patch the sync wrapper to directly call the async method
    with patch.object(strategy_engine, '_broadcast_strategy_update_sync') as mock_broadcast_sync:
        # Execute
        strategy_engine.activate_strategy(sample_strategy.id, TradingMode.DEMO, allocation_percent=30.0)
        
        # Verify broadcast sync wrapper was called
        assert mock_broadcast_sync.called
        
        # Verify it was called with the strategy
        call_args = mock_broadcast_sync.call_args
        broadcasted_strategy = call_args[0][0]
        assert broadcasted_strategy.id == sample_strategy.id
        assert broadcasted_strategy.status == StrategyStatus.DEMO


def test_broadcast_on_strategy_deactivation(strategy_engine, mock_websocket_manager, sample_strategy):
    """Test that strategy deactivation broadcasts update via WebSocket."""
    # Setup - strategy is currently DEMO
    sample_strategy.status = StrategyStatus.DEMO
    strategy_engine._load_strategy.return_value = sample_strategy
    strategy_engine._active_strategies[sample_strategy.id] = sample_strategy
    
    # Patch the sync wrapper to verify it's called
    with patch.object(strategy_engine, '_broadcast_strategy_update_sync') as mock_broadcast_sync:
        # Execute
        strategy_engine.deactivate_strategy(sample_strategy.id)
        
        # Verify broadcast sync wrapper was called
        assert mock_broadcast_sync.called
        
        # Verify it was called with the strategy
        call_args = mock_broadcast_sync.call_args
        broadcasted_strategy = call_args[0][0]
        assert broadcasted_strategy.id == sample_strategy.id
        assert broadcasted_strategy.status == StrategyStatus.BACKTESTED


def test_broadcast_includes_performance_metrics(strategy_engine, mock_websocket_manager, sample_strategy):
    """Test that broadcast includes performance metrics."""
    # Setup
    strategy_engine._load_strategy.return_value = sample_strategy
    strategy_engine._calculate_total_active_allocation = Mock(return_value=0.0)
    
    # Test the _strategy_to_dict method directly
    strategy_dict = strategy_engine._strategy_to_dict(sample_strategy)
    
    # Verify performance metrics are included
    assert "performance" in strategy_dict
    assert strategy_dict["performance"]["total_return"] == 0.15
    assert strategy_dict["performance"]["sharpe_ratio"] == 1.5
    assert strategy_dict["performance"]["win_rate"] == 0.65


def test_broadcast_includes_risk_params(strategy_engine, mock_websocket_manager, sample_strategy):
    """Test that broadcast includes risk parameters."""
    # Test the _strategy_to_dict method directly
    strategy_dict = strategy_engine._strategy_to_dict(sample_strategy)
    
    # Verify risk params are included
    assert "risk_params" in strategy_dict
    assert strategy_dict["risk_params"]["max_position_size_pct"] == 0.1
    assert strategy_dict["risk_params"]["stop_loss_pct"] == 0.05


def test_no_broadcast_when_websocket_manager_is_none(mock_llm_service, mock_market_data, sample_strategy):
    """Test that no error occurs when WebSocket manager is None."""
    # Create engine without WebSocket manager
    with patch('src.strategy.strategy_engine.get_database'):
        engine = StrategyEngine(mock_llm_service, mock_market_data, websocket_manager=None)
        engine._save_strategy = Mock()
        engine._load_strategy = Mock(return_value=sample_strategy)
        engine._calculate_total_active_allocation = Mock(return_value=0.0)
        
        # Execute - should not raise any errors
        engine.activate_strategy(sample_strategy.id, TradingMode.DEMO, allocation_percent=30.0)
        
        # Verify no errors occurred
        assert True


def test_broadcast_error_handling(strategy_engine, mock_websocket_manager, sample_strategy):
    """Test that broadcast errors are handled gracefully."""
    # Setup - make broadcast raise an exception
    mock_websocket_manager.broadcast_strategy_update.side_effect = Exception("WebSocket error")
    strategy_engine._load_strategy.return_value = sample_strategy
    strategy_engine._calculate_total_active_allocation = Mock(return_value=0.0)
    
    # Execute - should not raise exception despite broadcast error
    strategy_engine.activate_strategy(sample_strategy.id, TradingMode.DEMO, allocation_percent=30.0)
    
    # Verify activation still completed successfully
    assert strategy_engine._save_strategy.called


def test_strategy_to_dict_conversion(strategy_engine, sample_strategy):
    """Test that _strategy_to_dict correctly converts Strategy to dict."""
    # Execute
    strategy_dict = strategy_engine._strategy_to_dict(sample_strategy)
    
    # Verify all required fields are present
    assert strategy_dict["id"] == sample_strategy.id
    assert strategy_dict["name"] == sample_strategy.name
    assert strategy_dict["description"] == sample_strategy.description
    assert strategy_dict["status"] == sample_strategy.status.value
    assert strategy_dict["symbols"] == sample_strategy.symbols
    assert strategy_dict["allocation_percent"] == sample_strategy.allocation_percent
    assert "created_at" in strategy_dict
    assert "performance" in strategy_dict
    assert "risk_params" in strategy_dict
    assert "rules" in strategy_dict
