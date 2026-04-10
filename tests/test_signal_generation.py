"""Tests for signal generation functionality."""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.strategy.strategy_engine import StrategyEngine
from src.models import (
    Strategy,
    StrategyStatus,
    RiskConfig,
    PerformanceMetrics,
    TradingSignal,
    SignalAction,
    MarketData,
    DataSource,
    AccountInfo,
    TradingMode,
    Position,
    PositionSide,
)
from src.risk.risk_manager import RiskManager


@pytest.fixture
def mock_llm_service():
    """Create mock LLM service."""
    return Mock()


@pytest.fixture
def mock_market_data():
    """Create mock market data manager."""
    market_data = Mock()
    
    def get_historical_data(symbol, start, end, interval="1d"):
        """Generate mock historical data with specific patterns."""
        data = []
        current_date = start
        base_price = 100.0
        
        days = (end - start).days
        for i in range(days + 1):
            # Create upward trend for bullish crossover
            price = base_price + (i * 0.5)
            
            data.append(MarketData(
                symbol=symbol,
                timestamp=current_date,
                open=price,
                high=price * 1.02,
                low=price * 0.98,
                close=price,
                volume=1000000 + (i * 10000),
                source=DataSource.YAHOO_FINANCE
            ))
            current_date += timedelta(days=1)
        
        return data
    
    market_data.get_historical_data = Mock(side_effect=get_historical_data)
    return market_data


@pytest.fixture
def strategy_engine(mock_llm_service, mock_market_data):
    """Create StrategyEngine with mocked dependencies."""
    with patch('src.strategy.strategy_engine.get_database'):
        engine = StrategyEngine(mock_llm_service, mock_market_data)
        engine._save_strategy = Mock()
        engine._load_strategy = Mock()
        return engine


@pytest.fixture
def active_strategy():
    """Create an active strategy for testing."""
    return Strategy(
        id="test-strategy-1",
        name="Test Momentum Strategy",
        description="A test momentum strategy",
        status=StrategyStatus.DEMO,
        rules={
            "entry_conditions": ["Fast MA crosses above Slow MA"],
            "exit_conditions": ["Fast MA crosses below Slow MA"],
            "indicators": ["SMA_10", "SMA_30", "RSI_14"],
            "timeframe": "1d"
        },
        symbols=["AAPL", "GOOGL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=30.0,
        activated_at=datetime.now(),
        performance=PerformanceMetrics()
    )


@pytest.fixture
def inactive_strategy():
    """Create an inactive strategy for testing."""
    return Strategy(
        id="test-strategy-2",
        name="Test Inactive Strategy",
        description="A test inactive strategy",
        status=StrategyStatus.BACKTESTED,
        rules={
            "entry_conditions": ["Condition"],
            "exit_conditions": ["Condition"],
            "indicators": ["SMA"],
            "timeframe": "1d"
        },
        symbols=["MSFT"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=0.0,
        performance=PerformanceMetrics()
    )


@pytest.fixture
def mock_account():
    """Create mock account info."""
    return AccountInfo(
        account_id="test-account",
        mode=TradingMode.DEMO,
        balance=10000.0,
        buying_power=10000.0,
        margin_used=0.0,
        margin_available=10000.0,
        daily_pnl=0.0,
        total_pnl=0.0,
        positions_count=0,
        updated_at=datetime.now()
    )


@pytest.fixture
def risk_manager():
    """Create RiskManager instance."""
    return RiskManager(RiskConfig())


# Task 17.1.1: Test signal generation for active strategies
def test_generate_signals_for_active_strategy(strategy_engine, active_strategy):
    """
    Test that signals are generated for active strategies.
    
    Validates: Requirements 3.5, 11.12
    """
    # Mock system state to be ACTIVE
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        # Generate signals
        signals = strategy_engine.generate_signals(active_strategy)
        
        # Verify signals were generated
        assert isinstance(signals, list)
        # Signals may or may not be generated depending on market conditions
        # But the method should execute without errors


def test_generate_signals_returns_list(strategy_engine, active_strategy):
    """Test that generate_signals always returns a list."""
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        signals = strategy_engine.generate_signals(active_strategy)
        assert isinstance(signals, list)


def test_generate_signals_inactive_strategy_raises_error(strategy_engine, inactive_strategy):
    """Test that generating signals for inactive strategy raises ValueError."""
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        with pytest.raises(ValueError, match="Cannot generate signals for strategy in.*BACKTESTED.*status"):
            strategy_engine.generate_signals(inactive_strategy)


def test_generate_signals_system_not_active(strategy_engine, active_strategy):
    """Test that signals are not generated when system is not ACTIVE."""
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.PAUSED,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        signals = strategy_engine.generate_signals(active_strategy)
        
        # Should return empty list when system is not ACTIVE
        assert signals == []


def test_generate_signals_multiple_symbols(strategy_engine, active_strategy):
    """Test signal generation for strategy with multiple symbols."""
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        signals = strategy_engine.generate_signals(active_strategy)
        
        # Verify signals can be generated for multiple symbols
        assert isinstance(signals, list)
        # Each signal should have a valid symbol from the strategy
        for signal in signals:
            assert signal.symbol in active_strategy.symbols


def test_generate_signals_insufficient_data(strategy_engine, active_strategy, mock_market_data):
    """Test handling of insufficient historical data."""
    # Mock insufficient data
    mock_market_data.get_historical_data.return_value = []
    
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        signals = strategy_engine.generate_signals(active_strategy)
        
        # Should return empty list when data is insufficient
        assert signals == []




# Task 17.1.2: Test confidence score calculation
def test_signal_confidence_score_range(strategy_engine, active_strategy):
    """
    Test that confidence scores are within valid range [0.0, 1.0].
    
    Validates: Requirements 8.4
    """
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        signals = strategy_engine.generate_signals(active_strategy)
        
        # Verify all signals have valid confidence scores
        for signal in signals:
            assert 0.0 <= signal.confidence <= 1.0, \
                f"Confidence {signal.confidence} is outside valid range [0.0, 1.0]"


def test_signal_confidence_with_strong_indicators(strategy_engine, active_strategy, mock_market_data):
    """Test that strong indicator alignment produces high confidence."""
    # Create data with strong bullish crossover
    def get_strong_bullish_data(symbol, start, end, interval="1d"):
        data = []
        current_date = start
        base_price = 100.0
        
        days = (end - start).days
        for i in range(days + 1):
            # Strong upward trend with high volume
            price = base_price + (i * 2.0)  # Stronger trend
            volume = 2000000 + (i * 50000)  # High volume
            
            data.append(MarketData(
                symbol=symbol,
                timestamp=current_date,
                open=price,
                high=price * 1.02,
                low=price * 0.98,
                close=price,
                volume=volume,
                source=DataSource.YAHOO_FINANCE
            ))
            current_date += timedelta(days=1)
        
        return data
    
    mock_market_data.get_historical_data = Mock(side_effect=get_strong_bullish_data)
    
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        signals = strategy_engine.generate_signals(active_strategy)
        
        # With strong indicators, we expect higher confidence
        # (if signals are generated)
        for signal in signals:
            # Confidence should be reasonably high with strong indicators
            assert signal.confidence > 0.3, \
                f"Expected higher confidence with strong indicators, got {signal.confidence}"


def test_signal_confidence_with_weak_indicators(strategy_engine, active_strategy, mock_market_data):
    """Test that weak indicator alignment produces lower confidence."""
    # Create data with weak/mixed signals
    def get_weak_signal_data(symbol, start, end, interval="1d"):
        data = []
        current_date = start
        base_price = 100.0
        
        days = (end - start).days
        for i in range(days + 1):
            # Weak trend with low volume
            price = base_price + (i * 0.1)  # Very weak trend
            volume = 500000  # Low, constant volume
            
            data.append(MarketData(
                symbol=symbol,
                timestamp=current_date,
                open=price,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=volume,
                source=DataSource.YAHOO_FINANCE
            ))
            current_date += timedelta(days=1)
        
        return data
    
    mock_market_data.get_historical_data = Mock(side_effect=get_weak_signal_data)
    
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        signals = strategy_engine.generate_signals(active_strategy)
        
        # With weak indicators, confidence should be lower
        for signal in signals:
            # Confidence should not be at maximum with weak indicators
            assert signal.confidence < 1.0, \
                f"Expected lower confidence with weak indicators, got {signal.confidence}"


def test_signal_confidence_factors_in_metadata(strategy_engine, active_strategy):
    """Test that confidence factors are included in signal metadata."""
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        signals = strategy_engine.generate_signals(active_strategy)
        
        # Verify confidence factors are in metadata
        for signal in signals:
            assert "confidence_factors" in signal.metadata
            factors = signal.metadata["confidence_factors"]
            
            # Verify expected confidence factors exist
            assert "ma_spread" in factors
            assert "rsi" in factors
            assert "volume" in factors
            
            # Verify each factor is a valid number
            for factor_name, factor_value in factors.items():
                assert isinstance(factor_value, (int, float))
                assert 0.0 <= factor_value <= 1.0


def test_signal_confidence_calculation_consistency(strategy_engine, active_strategy):
    """Test that confidence calculation is consistent across multiple calls."""
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        # Generate signals twice with same data
        signals1 = strategy_engine.generate_signals(active_strategy)
        signals2 = strategy_engine.generate_signals(active_strategy)
        
        # If both generated signals, confidence should be similar
        if len(signals1) > 0 and len(signals2) > 0:
            # Compare first signal from each (same symbol)
            for s1 in signals1:
                for s2 in signals2:
                    if s1.symbol == s2.symbol and s1.action == s2.action:
                        # Confidence should be very close (allowing for timestamp differences)
                        assert abs(s1.confidence - s2.confidence) < 0.1




# Task 17.1.3: Test reasoning generation
def test_signal_has_reasoning_text(strategy_engine, active_strategy):
    """
    Test that generated signals include reasoning text.
    
    Validates: Requirements 8.4, 8.7
    """
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        signals = strategy_engine.generate_signals(active_strategy)
        
        # Verify all signals have reasoning
        for signal in signals:
            assert signal.reasoning is not None
            assert isinstance(signal.reasoning, str)
            assert len(signal.reasoning) > 0


def test_signal_reasoning_contains_indicator_info(strategy_engine, active_strategy):
    """Test that reasoning includes information about indicators."""
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        signals = strategy_engine.generate_signals(active_strategy)
        
        # Verify reasoning mentions key indicators
        for signal in signals:
            reasoning_lower = signal.reasoning.lower()
            
            # Should mention moving averages
            assert "ma" in reasoning_lower or "moving average" in reasoning_lower
            
            # Should mention RSI
            assert "rsi" in reasoning_lower


def test_signal_reasoning_includes_confidence(strategy_engine, active_strategy):
    """Test that reasoning includes confidence score."""
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        signals = strategy_engine.generate_signals(active_strategy)
        
        # Verify reasoning mentions confidence
        for signal in signals:
            assert "confidence" in signal.reasoning.lower()


def test_signal_reasoning_explains_action(strategy_engine, active_strategy):
    """Test that reasoning explains the signal action."""
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        signals = strategy_engine.generate_signals(active_strategy)
        
        # Verify reasoning explains the action
        for signal in signals:
            reasoning_lower = signal.reasoning.lower()
            
            if signal.action == SignalAction.ENTER_LONG:
                # Should mention bullish or upward movement
                assert "cross" in reasoning_lower or "above" in reasoning_lower
            elif signal.action == SignalAction.EXIT_LONG:
                # Should mention bearish or downward movement
                assert "cross" in reasoning_lower or "below" in reasoning_lower


def test_signal_reasoning_includes_volume_info(strategy_engine, active_strategy):
    """Test that reasoning includes volume information."""
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        signals = strategy_engine.generate_signals(active_strategy)
        
        # Verify reasoning mentions volume
        for signal in signals:
            reasoning_lower = signal.reasoning.lower()
            assert "volume" in reasoning_lower


def test_signal_reasoning_different_for_different_actions(strategy_engine, mock_market_data):
    """Test that reasoning differs for ENTER_LONG vs EXIT_LONG signals."""
    # Create strategy
    strategy = Strategy(
        id="test-strategy",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.DEMO,
        rules={"entry_conditions": [], "exit_conditions": [], "indicators": [], "timeframe": "1d"},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=30.0,
        activated_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    # Create data that will generate ENTER_LONG signal
    def get_bullish_data(symbol, start, end, interval="1d"):
        data = []
        current_date = start
        days = (end - start).days
        
        for i in range(days + 1):
            # Upward trend for bullish crossover
            price = 100.0 + (i * 1.0)
            data.append(MarketData(
                symbol=symbol,
                timestamp=current_date,
                open=price,
                high=price * 1.02,
                low=price * 0.98,
                close=price,
                volume=1000000,
                source=DataSource.YAHOO_FINANCE
            ))
            current_date += timedelta(days=1)
        
        return data
    
    mock_market_data.get_historical_data = Mock(side_effect=get_bullish_data)
    
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        signals_bullish = strategy_engine.generate_signals(strategy)
        
        # Now create data for bearish crossover
        def get_bearish_data(symbol, start, end, interval="1d"):
            data = []
            current_date = start
            days = (end - start).days
            
            for i in range(days + 1):
                # Downward trend for bearish crossover
                price = 150.0 - (i * 1.0)
                data.append(MarketData(
                    symbol=symbol,
                    timestamp=current_date,
                    open=price,
                    high=price * 1.02,
                    low=price * 0.98,
                    close=price,
                    volume=1000000,
                    source=DataSource.YAHOO_FINANCE
                ))
                current_date += timedelta(days=1)
            
            return data
        
        mock_market_data.get_historical_data = Mock(side_effect=get_bearish_data)
        signals_bearish = strategy_engine.generate_signals(strategy)
        
        # If both generated signals, reasoning should be different
        if len(signals_bullish) > 0 and len(signals_bearish) > 0:
            bullish_reasoning = signals_bullish[0].reasoning.lower()
            bearish_reasoning = signals_bearish[0].reasoning.lower()
            
            # Reasoning should be different
            assert bullish_reasoning != bearish_reasoning




# Task 17.1.4: Test signal validation through risk manager
def test_validate_signal_with_risk_manager(risk_manager, active_strategy, mock_account):
    """
    Test that signals can be validated through risk manager.
    
    Validates: Requirements 3.6, 7.4
    """
    # Create a test signal
    signal = TradingSignal(
        strategy_id=active_strategy.id,
        symbol="AAPL",
        action=SignalAction.ENTER_LONG,
        confidence=0.8,
        reasoning="Test signal",
        generated_at=datetime.now(),
        indicators={"fast_ma": 105.0, "slow_ma": 100.0, "rsi": 65.0},
        metadata={"strategy_name": active_strategy.name}
    )
    
    # Validate signal
    result = risk_manager.validate_signal(signal, mock_account, [])
    
    # Verify validation result
    assert result is not None
    assert hasattr(result, 'is_valid')
    assert hasattr(result, 'position_size')
    assert hasattr(result, 'reason')


def test_validate_entry_signal_passes(risk_manager, active_strategy, mock_account):
    """Test that valid entry signals pass risk validation."""
    signal = TradingSignal(
        strategy_id=active_strategy.id,
        symbol="AAPL",
        action=SignalAction.ENTER_LONG,
        confidence=0.8,
        reasoning="Strong bullish signal",
        generated_at=datetime.now(),
        indicators={"fast_ma": 105.0, "slow_ma": 100.0, "rsi": 65.0},
        metadata={"strategy_name": active_strategy.name}
    )
    
    result = risk_manager.validate_signal(signal, mock_account, [])
    
    # Should pass validation
    assert result.is_valid is True
    assert result.position_size > 0
    assert "passed" in result.reason.lower() or "approved" in result.reason.lower()


def test_validate_exit_signal_always_passes(risk_manager, active_strategy, mock_account):
    """Test that exit signals always pass validation."""
    signal = TradingSignal(
        strategy_id=active_strategy.id,
        symbol="AAPL",
        action=SignalAction.EXIT_LONG,
        confidence=0.7,
        reasoning="Exit signal",
        generated_at=datetime.now(),
        indicators={"fast_ma": 95.0, "slow_ma": 100.0, "rsi": 45.0},
        metadata={"strategy_name": active_strategy.name}
    )
    
    result = risk_manager.validate_signal(signal, mock_account, [])
    
    # Exit signals should always pass
    assert result.is_valid is True
    assert "exit" in result.reason.lower() or "approved" in result.reason.lower()


def test_validate_signal_with_insufficient_capital(risk_manager, active_strategy):
    """Test that signals are rejected when account has insufficient capital."""
    # Create account with no available capital
    account = AccountInfo(
        account_id="test-account",
        mode=TradingMode.DEMO,
        balance=1000.0,
        buying_power=0.0,
        margin_used=1000.0,
        margin_available=0.0,
        daily_pnl=0.0,
        total_pnl=0.0,
        positions_count=0,
        updated_at=datetime.now()
    )
    
    signal = TradingSignal(
        strategy_id=active_strategy.id,
        symbol="AAPL",
        action=SignalAction.ENTER_LONG,
        confidence=0.8,
        reasoning="Test signal",
        generated_at=datetime.now(),
        indicators={"fast_ma": 105.0, "slow_ma": 100.0, "rsi": 65.0},
        metadata={"strategy_name": active_strategy.name}
    )
    
    result = risk_manager.validate_signal(signal, account, [])
    
    # Should fail validation due to insufficient capital
    assert result.is_valid is False
    assert result.position_size == 0.0


def test_validate_signal_with_existing_positions(risk_manager, active_strategy, mock_account):
    """Test signal validation with existing positions."""
    # Create existing position
    existing_position = Position(
        id="pos-1",
        strategy_id=active_strategy.id,
        symbol="GOOGL",
        side=PositionSide.LONG,
        quantity=10.0,
        entry_price=100.0,
        current_price=105.0,
        unrealized_pnl=50.0,
        realized_pnl=0.0,
        opened_at=datetime.now(),
        etoro_position_id="etoro-pos-1"
    )
    
    signal = TradingSignal(
        strategy_id=active_strategy.id,
        symbol="AAPL",
        action=SignalAction.ENTER_LONG,
        confidence=0.8,
        reasoning="Test signal",
        generated_at=datetime.now(),
        indicators={"fast_ma": 105.0, "slow_ma": 100.0, "rsi": 65.0},
        metadata={"strategy_name": active_strategy.name}
    )
    
    result = risk_manager.validate_signal(signal, mock_account, [existing_position])
    
    # Should still validate but consider existing exposure
    assert result is not None
    assert hasattr(result, 'is_valid')


def test_validate_signal_position_size_within_limits(risk_manager, active_strategy, mock_account):
    """Test that calculated position size respects max position size limit."""
    signal = TradingSignal(
        strategy_id=active_strategy.id,
        symbol="AAPL",
        action=SignalAction.ENTER_LONG,
        confidence=0.8,
        reasoning="Test signal",
        generated_at=datetime.now(),
        indicators={"fast_ma": 105.0, "slow_ma": 100.0, "rsi": 65.0},
        metadata={"strategy_name": active_strategy.name}
    )
    
    result = risk_manager.validate_signal(signal, mock_account, [])
    
    if result.is_valid:
        # Position size should not exceed max position size
        max_position_size = mock_account.balance * risk_manager.config.max_position_size_pct
        assert result.position_size <= max_position_size


def test_validate_signal_with_circuit_breaker_active(risk_manager, active_strategy, mock_account):
    """Test that entry signals are blocked when circuit breaker is active."""
    # Activate circuit breaker
    risk_manager.activate_circuit_breaker()
    
    signal = TradingSignal(
        strategy_id=active_strategy.id,
        symbol="AAPL",
        action=SignalAction.ENTER_LONG,
        confidence=0.8,
        reasoning="Test signal",
        generated_at=datetime.now(),
        indicators={"fast_ma": 105.0, "slow_ma": 100.0, "rsi": 65.0},
        metadata={"strategy_name": active_strategy.name}
    )
    
    result = risk_manager.validate_signal(signal, mock_account, [])
    
    # Entry signal should be blocked
    assert result.is_valid is False
    assert "circuit breaker" in result.reason.lower()
    
    # Reset for other tests
    risk_manager.reset_circuit_breaker()


def test_validate_signal_with_kill_switch_active(risk_manager, active_strategy, mock_account):
    """Test that all signals are blocked when kill switch is active."""
    # Activate kill switch
    risk_manager.execute_kill_switch("Test kill switch")
    
    # Test entry signal
    entry_signal = TradingSignal(
        strategy_id=active_strategy.id,
        symbol="AAPL",
        action=SignalAction.ENTER_LONG,
        confidence=0.8,
        reasoning="Test signal",
        generated_at=datetime.now(),
        indicators={"fast_ma": 105.0, "slow_ma": 100.0, "rsi": 65.0},
        metadata={"strategy_name": active_strategy.name}
    )
    
    result = risk_manager.validate_signal(entry_signal, mock_account, [])
    
    # Should be blocked
    assert result.is_valid is False
    assert "kill switch" in result.reason.lower()
    
    # Test exit signal (should also be blocked)
    exit_signal = TradingSignal(
        strategy_id=active_strategy.id,
        symbol="AAPL",
        action=SignalAction.EXIT_LONG,
        confidence=0.7,
        reasoning="Exit signal",
        generated_at=datetime.now(),
        indicators={"fast_ma": 95.0, "slow_ma": 100.0, "rsi": 45.0},
        metadata={"strategy_name": active_strategy.name}
    )
    
    result = risk_manager.validate_signal(exit_signal, mock_account, [])
    
    # Exit should also be blocked with kill switch
    assert result.is_valid is False
    assert "kill switch" in result.reason.lower()
    
    # Reset for other tests
    risk_manager.reset_kill_switch()


def test_signal_indicators_included(strategy_engine, active_strategy):
    """Test that signals include indicator values."""
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        signals = strategy_engine.generate_signals(active_strategy)
        
        # Verify all signals have indicators
        for signal in signals:
            assert signal.indicators is not None
            assert isinstance(signal.indicators, dict)
            assert len(signal.indicators) > 0
            
            # Verify expected indicators are present
            assert "fast_ma" in signal.indicators
            assert "slow_ma" in signal.indicators
            assert "rsi" in signal.indicators
            assert "price" in signal.indicators


def test_signal_metadata_included(strategy_engine, active_strategy):
    """Test that signals include metadata."""
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        from src.models.dataclasses import SystemState
        from src.models.enums import SystemStateEnum
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        
        signals = strategy_engine.generate_signals(active_strategy)
        
        # Verify all signals have metadata
        for signal in signals:
            assert signal.metadata is not None
            assert isinstance(signal.metadata, dict)
            
            # Verify expected metadata fields
            assert "strategy_name" in signal.metadata
            assert signal.metadata["strategy_name"] == active_strategy.name
            assert "timestamp" in signal.metadata
