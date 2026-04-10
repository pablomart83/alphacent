"""
Test timeframe-aware signal generation (Task 3.3).

Validates that generate_signals detects strategy interval and passes it to data fetch.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import pandas as pd

from src.strategy.strategy_engine import StrategyEngine
from src.models.dataclasses import Strategy, RiskConfig, BacktestResults, SystemState
from src.models.enums import StrategyStatus, SystemStateEnum


@pytest.fixture(autouse=True)
def clear_historical_cache():
    """Clear the global historical data cache between tests to prevent leakage."""
    import src.data.market_data_manager as mdm
    mdm._historical_cache = None
    yield
    mdm._historical_cache = None


@pytest.fixture
def mock_database():
    """Mock database."""
    db = Mock()
    session = Mock()
    session.query.return_value.filter.return_value.all.return_value = []
    session.query.return_value.filter.return_value.first.return_value = None
    session.close = Mock()
    db.get_session.return_value = session
    return db


@pytest.fixture
def mock_market_data():
    """Mock market data manager."""
    market_data = Mock()
    
    # Create sample OHLCV data
    dates = pd.date_range(end=datetime.now(), periods=100, freq='1h')
    data = []
    for date in dates:
        point = Mock()
        point.timestamp = date
        point.open = 100.0
        point.high = 101.0
        point.low = 99.0
        point.close = 100.5
        point.volume = 1000000
        data.append(point)
    
    market_data.get_historical_data.return_value = data
    return market_data


@pytest.fixture
def strategy_engine(mock_database, mock_market_data):
    """Create strategy engine with mocked dependencies."""
    engine = StrategyEngine(mock_database, mock_market_data)
    return engine


@pytest.fixture
def mock_system_state():
    """Mock system state manager."""
    with patch('src.core.system_state_manager.get_system_state_manager') as mock_state_mgr:
        mock_state_mgr.return_value.get_current_state.return_value = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="Test"
        )
        yield mock_state_mgr


def test_hourly_strategy_detects_interval_from_metadata(strategy_engine, mock_market_data, mock_system_state):
    """Test that hourly strategy interval is detected from metadata."""
    # Create hourly strategy with interval in metadata
    strategy = Strategy(
        id="test-hourly-1",
        name="Hourly Test Strategy",
        description="Test hourly strategy",
        symbols=["AAPL"],
        status=StrategyStatus.LIVE,
        rules={
            "entry_conditions": ["RSI(14) < 30"],
            "exit_conditions": ["RSI(14) > 70"],
            "indicators": ["RSI:14"]
        },
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        metadata={
            "interval": "1h",
            "intraday": True
        }
    )
    
    # Mock the indicator calculation and signal generation
    with patch.object(strategy_engine, '_calculate_indicators_from_strategy') as mock_calc:
        mock_calc.return_value = {"RSI": pd.Series([25.0] * 100)}
        
        with patch.object(strategy_engine, '_parse_strategy_rules') as mock_parse:
            mock_parse.return_value = (
                pd.Series([True] * 100),  # entries
                pd.Series([False] * 100)  # exits
            )
            
            # Generate signals
            signals = strategy_engine.generate_signals(strategy)
            
            # Verify that get_historical_data was called with interval='1h'
            calls = mock_market_data.get_historical_data.call_args_list
            assert len(calls) > 0, "get_historical_data should have been called"
            
            # Check the interval parameter in the call
            call_kwargs = calls[0][1]
            assert 'interval' in call_kwargs, "interval parameter should be passed"
            assert call_kwargs['interval'] == '1h', f"Expected interval='1h', got {call_kwargs['interval']}"


def test_hourly_strategy_detects_interval_from_backtest_results(strategy_engine, mock_market_data, mock_system_state):
    """Test that hourly strategy interval is detected from backtest_results metadata."""
    # Create hourly strategy with interval in backtest_results
    backtest_results = BacktestResults(
        total_return=0.15,
        sharpe_ratio=0.75,
        sortino_ratio=0.85,
        max_drawdown=0.10,
        win_rate=0.72,
        avg_win=0.02,
        avg_loss=0.01,
        total_trades=50,
        metadata={"interval": "1h"}
    )
    
    strategy = Strategy(
        id="test-hourly-2",
        name="Hourly Test Strategy 2",
        description="Test hourly strategy 2",
        symbols=["AAPL"],
        status=StrategyStatus.LIVE,
        rules={
            "entry_conditions": ["RSI(14) < 30"],
            "exit_conditions": ["RSI(14) > 70"],
            "indicators": ["RSI:14"]
        },
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        backtest_results=backtest_results
    )
    
    # Mock the indicator calculation and signal generation
    with patch.object(strategy_engine, '_calculate_indicators_from_strategy') as mock_calc:
        mock_calc.return_value = {"RSI": pd.Series([25.0] * 100)}
        
        with patch.object(strategy_engine, '_parse_strategy_rules') as mock_parse:
            mock_parse.return_value = (
                pd.Series([True] * 100),  # entries
                pd.Series([False] * 100)  # exits
            )
            
            # Generate signals
            signals = strategy_engine.generate_signals(strategy)
            
            # Verify that get_historical_data was called with interval='1h'
            calls = mock_market_data.get_historical_data.call_args_list
            assert len(calls) > 0, "get_historical_data should have been called"
            
            # Check the interval parameter in the call
            call_kwargs = calls[0][1]
            assert 'interval' in call_kwargs, "interval parameter should be passed"
            assert call_kwargs['interval'] == '1h', f"Expected interval='1h', got {call_kwargs['interval']}"


def test_daily_strategy_uses_daily_interval(strategy_engine, mock_market_data, mock_system_state):
    """Test that daily strategy uses daily interval (preservation test)."""
    # Create daily strategy
    strategy = Strategy(
        id="test-daily-1",
        name="Daily Test Strategy",
        description="Test daily strategy",
        symbols=["AAPL"],
        status=StrategyStatus.LIVE,
        rules={
            "entry_conditions": ["RSI(14) < 30"],
            "exit_conditions": ["RSI(14) > 70"],
            "indicators": ["RSI:14"],
            "interval": "1d"
        },
        risk_params=RiskConfig(),
        created_at=datetime.now()
    )
    
    # Mock the indicator calculation and signal generation
    with patch.object(strategy_engine, '_calculate_indicators_from_strategy') as mock_calc:
        mock_calc.return_value = {"RSI": pd.Series([25.0] * 100)}
        
        with patch.object(strategy_engine, '_parse_strategy_rules') as mock_parse:
            mock_parse.return_value = (
                pd.Series([True] * 100),  # entries
                pd.Series([False] * 100)  # exits
            )
            
            # Generate signals
            signals = strategy_engine.generate_signals(strategy)
            
            # Verify that get_historical_data was called with interval='1d'
            calls = mock_market_data.get_historical_data.call_args_list
            assert len(calls) > 0, "get_historical_data should have been called"
            
            # Check the interval parameter in the call
            call_kwargs = calls[0][1]
            assert 'interval' in call_kwargs, "interval parameter should be passed"
            assert call_kwargs['interval'] == '1d', f"Expected interval='1d', got {call_kwargs['interval']}"


def test_hourly_strategy_logs_interval(strategy_engine, mock_market_data, mock_system_state, caplog):
    """Test that hourly strategy logs the interval being used."""
    import logging
    
    caplog.set_level(logging.INFO)
    
    # Create hourly strategy
    strategy = Strategy(
        id="test-hourly-3",
        name="Hourly Test Strategy 3",
        description="Test hourly strategy 3",
        symbols=["AAPL"],
        status=StrategyStatus.LIVE,
        rules={
            "entry_conditions": ["RSI(14) < 30"],
            "exit_conditions": ["RSI(14) > 70"],
            "indicators": ["RSI:14"]
        },
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        metadata={
            "interval": "1h",
            "intraday": True
        }
    )
    
    # Mock the indicator calculation and signal generation
    with patch.object(strategy_engine, '_calculate_indicators_from_strategy') as mock_calc:
        mock_calc.return_value = {"RSI": pd.Series([25.0] * 100)}
        
        with patch.object(strategy_engine, '_parse_strategy_rules') as mock_parse:
            mock_parse.return_value = (
                pd.Series([True] * 100),  # entries
                pd.Series([False] * 100)  # exits
            )
            
            # Generate signals
            signals = strategy_engine.generate_signals(strategy)
            
            # Check that the log message was generated
            log_messages = [record.message for record in caplog.records]
            assert any("Generating signals for hourly strategy" in msg and "using 1h bars" in msg 
                      for msg in log_messages), \
                f"Expected log message about hourly strategy, got: {log_messages}"

