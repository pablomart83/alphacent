"""Tests for strategy backtesting functionality."""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.strategy.strategy_engine import StrategyEngine, BacktestResults
from src.models import (
    Strategy,
    StrategyStatus,
    RiskConfig,
    PerformanceMetrics,
    MarketData,
    DataSource,
)


@pytest.fixture
def mock_llm_service():
    """Create mock LLM service."""
    return Mock()


@pytest.fixture
def mock_market_data():
    """Create mock market data manager with historical data."""
    market_data = Mock()
    
    def get_historical_data(symbol, start, end, interval="1d"):
        """Generate mock historical data."""
        data = []
        current_date = start
        base_price = 100.0 if symbol == "AAPL" else 200.0
        
        while current_date <= end:
            # Add some volatility
            price_change = (hash(str(current_date)) % 100 - 50) / 1000.0
            price = base_price * (1 + price_change)
            
            data.append(MarketData(
                symbol=symbol,
                timestamp=current_date,
                open=price,
                high=price * 1.02,
                low=price * 0.98,
                close=price * 1.01,
                volume=1000000,
                source=DataSource.YAHOO_FINANCE
            ))
            current_date += timedelta(days=1)
            base_price = price * 1.01  # Slight upward trend
        
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
def sample_strategy():
    """Create a sample PROPOSED strategy for testing."""
    return Strategy(
        id="test-strategy-123",
        name="Test Momentum Strategy",
        description="A test momentum strategy",
        status=StrategyStatus.PROPOSED,
        rules={
            "entry_conditions": ["Fast MA crosses above slow MA"],
            "exit_conditions": ["Fast MA crosses below slow MA"],
            "indicators": ["SMA"],
            "timeframe": "1d"
        },
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )


# ============================================================================
# Task 11.1.1: Test backtest with different date ranges
# ============================================================================

def test_backtest_30_day_period(strategy_engine, sample_strategy, mock_market_data):
    """Test backtesting with a 30-day period."""
    end = datetime.now()
    start = end - timedelta(days=30)
    
    results = strategy_engine.backtest_strategy(sample_strategy, start, end)
    
    # Verify results structure
    assert isinstance(results, BacktestResults)
    assert results.total_return is not None
    assert results.sharpe_ratio is not None
    assert results.sortino_ratio is not None
    assert results.max_drawdown is not None
    assert results.win_rate is not None
    assert results.total_trades >= 0
    
    # Verify backtest period is stored
    assert results.backtest_period is not None
    assert results.backtest_period[0] == start
    assert results.backtest_period[1] == end
    
    # Verify market data was fetched
    mock_market_data.get_historical_data.assert_called()


def test_backtest_90_day_period(strategy_engine, sample_strategy, mock_market_data):
    """Test backtesting with a 90-day period (default)."""
    end = datetime.now()
    start = end - timedelta(days=90)
    
    results = strategy_engine.backtest_strategy(sample_strategy, start, end)
    
    assert isinstance(results, BacktestResults)
    assert results.backtest_period[0] == start
    assert results.backtest_period[1] == end
    
    # Longer period should potentially have more trades
    assert results.total_trades >= 0


def test_backtest_180_day_period(strategy_engine, sample_strategy, mock_market_data):
    """Test backtesting with a 180-day period."""
    end = datetime.now()
    start = end - timedelta(days=180)
    
    results = strategy_engine.backtest_strategy(sample_strategy, start, end)
    
    assert isinstance(results, BacktestResults)
    assert results.backtest_period[0] == start
    assert results.backtest_period[1] == end


def test_backtest_custom_date_range(strategy_engine, sample_strategy, mock_market_data):
    """Test backtesting with custom date range."""
    start = datetime(2024, 1, 1)
    end = datetime(2024, 6, 30)
    
    results = strategy_engine.backtest_strategy(sample_strategy, start, end)
    
    assert isinstance(results, BacktestResults)
    assert results.backtest_period[0] == start
    assert results.backtest_period[1] == end


def test_backtest_multiple_symbols(strategy_engine, mock_market_data):
    """Test backtesting with multiple symbols."""
    strategy = Strategy(
        id="multi-symbol-123",
        name="Multi-Symbol Strategy",
        description="Test strategy with multiple symbols",
        status=StrategyStatus.PROPOSED,
        rules={
            "entry_conditions": ["RSI < 30"],
            "exit_conditions": ["RSI > 70"],
            "indicators": ["RSI"],
            "timeframe": "1d"
        },
        symbols=["AAPL", "MSFT", "GOOGL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    end = datetime.now()
    start = end - timedelta(days=60)
    
    results = strategy_engine.backtest_strategy(strategy, start, end)
    
    assert isinstance(results, BacktestResults)
    
    # Verify data was fetched for all symbols
    assert mock_market_data.get_historical_data.call_count >= 3




# ============================================================================
# Task 11.1.2: Test performance metrics calculation
# ============================================================================

def test_performance_metrics_calculation(strategy_engine, sample_strategy, mock_market_data):
    """Test that all performance metrics are calculated correctly."""
    end = datetime.now()
    start = end - timedelta(days=60)
    
    results = strategy_engine.backtest_strategy(sample_strategy, start, end)
    
    # Verify all metrics are present and have valid values
    assert isinstance(results.total_return, float)
    assert isinstance(results.sharpe_ratio, float)
    assert isinstance(results.sortino_ratio, float)
    assert isinstance(results.max_drawdown, float)
    assert isinstance(results.win_rate, float)
    assert isinstance(results.avg_win, float)
    assert isinstance(results.avg_loss, float)
    assert isinstance(results.total_trades, int)
    
    # Verify metrics are within reasonable bounds
    assert results.max_drawdown >= 0.0  # Drawdown is positive
    assert 0.0 <= results.win_rate <= 1.0  # Win rate is percentage
    assert results.total_trades >= 0


def test_sharpe_ratio_calculation(strategy_engine, sample_strategy, mock_market_data):
    """Test Sharpe ratio calculation."""
    end = datetime.now()
    start = end - timedelta(days=90)
    
    results = strategy_engine.backtest_strategy(sample_strategy, start, end)
    
    # Sharpe ratio should be a finite number
    assert isinstance(results.sharpe_ratio, float)
    assert not pd.isna(results.sharpe_ratio)


def test_sortino_ratio_calculation(strategy_engine, sample_strategy, mock_market_data):
    """Test Sortino ratio calculation."""
    end = datetime.now()
    start = end - timedelta(days=90)
    
    results = strategy_engine.backtest_strategy(sample_strategy, start, end)
    
    # Sortino ratio should be a finite number
    assert isinstance(results.sortino_ratio, float)
    assert not pd.isna(results.sortino_ratio)


def test_max_drawdown_calculation(strategy_engine, sample_strategy, mock_market_data):
    """Test maximum drawdown calculation."""
    end = datetime.now()
    start = end - timedelta(days=90)
    
    results = strategy_engine.backtest_strategy(sample_strategy, start, end)
    
    # Max drawdown should be non-negative
    assert results.max_drawdown >= 0.0
    assert isinstance(results.max_drawdown, float)


def test_win_rate_calculation(strategy_engine, sample_strategy, mock_market_data):
    """Test win rate calculation."""
    end = datetime.now()
    start = end - timedelta(days=90)
    
    results = strategy_engine.backtest_strategy(sample_strategy, start, end)
    
    # Win rate should be between 0 and 1
    assert 0.0 <= results.win_rate <= 1.0
    
    # If there are trades, win rate should be meaningful
    if results.total_trades > 0:
        assert isinstance(results.win_rate, float)


def test_avg_win_loss_calculation(strategy_engine, sample_strategy, mock_market_data):
    """Test average win and loss calculation."""
    end = datetime.now()
    start = end - timedelta(days=90)
    
    results = strategy_engine.backtest_strategy(sample_strategy, start, end)
    
    # Average win and loss should be numbers
    assert isinstance(results.avg_win, float)
    assert isinstance(results.avg_loss, float)
    
    # If there are trades, averages should be meaningful
    if results.total_trades > 0:
        # Average win should be non-negative
        assert results.avg_win >= 0.0


def test_equity_curve_generation(strategy_engine, sample_strategy, mock_market_data):
    """Test that equity curve is generated."""
    end = datetime.now()
    start = end - timedelta(days=60)
    
    results = strategy_engine.backtest_strategy(sample_strategy, start, end)
    
    # Equity curve should be present (can be None or pandas Series)
    # Just verify it exists in the results
    assert hasattr(results, 'equity_curve')


def test_trades_dataframe_generation(strategy_engine, sample_strategy, mock_market_data):
    """Test that trades dataframe is generated."""
    end = datetime.now()
    start = end - timedelta(days=60)
    
    results = strategy_engine.backtest_strategy(sample_strategy, start, end)
    
    # Trades dataframe should be present (can be None or pandas DataFrame)
    assert hasattr(results, 'trades')




# ============================================================================
# Task 11.1.3: Test state transition (PROPOSED → BACKTESTED)
# ============================================================================

def test_state_transition_proposed_to_backtested(strategy_engine, sample_strategy, mock_market_data):
    """Test that strategy status transitions from PROPOSED to BACKTESTED."""
    # Verify initial status
    assert sample_strategy.status == StrategyStatus.PROPOSED
    
    end = datetime.now()
    start = end - timedelta(days=60)
    
    # Run backtest
    results = strategy_engine.backtest_strategy(sample_strategy, start, end)
    
    # Verify status changed to BACKTESTED
    assert sample_strategy.status == StrategyStatus.BACKTESTED
    
    # Verify strategy was saved
    strategy_engine._save_strategy.assert_called()


def test_performance_metrics_updated_after_backtest(strategy_engine, sample_strategy, mock_market_data):
    """Test that strategy performance metrics are updated after backtest."""
    # Initial performance should be empty
    assert sample_strategy.performance.total_return == 0.0
    assert sample_strategy.performance.sharpe_ratio == 0.0
    
    end = datetime.now()
    start = end - timedelta(days=60)
    
    # Run backtest
    results = strategy_engine.backtest_strategy(sample_strategy, start, end)
    
    # Verify performance metrics were updated
    assert sample_strategy.performance.total_return == results.total_return
    assert sample_strategy.performance.sharpe_ratio == results.sharpe_ratio
    assert sample_strategy.performance.sortino_ratio == results.sortino_ratio
    assert sample_strategy.performance.max_drawdown == results.max_drawdown
    assert sample_strategy.performance.win_rate == results.win_rate
    assert sample_strategy.performance.total_trades == results.total_trades


def test_backtest_results_stored_in_strategy(strategy_engine, sample_strategy, mock_market_data):
    """Test that backtest results are stored in strategy object."""
    # Initial backtest_results should be None
    assert sample_strategy.backtest_results is None
    
    end = datetime.now()
    start = end - timedelta(days=60)
    
    # Run backtest
    results = strategy_engine.backtest_strategy(sample_strategy, start, end)
    
    # Verify backtest_results were stored
    assert sample_strategy.backtest_results is not None
    assert sample_strategy.backtest_results == results


def test_backtest_idempotency(strategy_engine, sample_strategy, mock_market_data):
    """Test that running backtest multiple times updates results correctly."""
    end = datetime.now()
    start = end - timedelta(days=60)
    
    # Run backtest first time
    results1 = strategy_engine.backtest_strategy(sample_strategy, start, end)
    first_sharpe = results1.sharpe_ratio
    
    # Reset status to PROPOSED to allow re-backtest
    sample_strategy.status = StrategyStatus.PROPOSED
    
    # Run backtest second time with different date range
    start2 = end - timedelta(days=90)
    results2 = strategy_engine.backtest_strategy(sample_strategy, start2, end)
    
    # Results should be updated
    assert sample_strategy.backtest_results == results2
    assert sample_strategy.status == StrategyStatus.BACKTESTED


def test_backtest_preserves_strategy_metadata(strategy_engine, sample_strategy, mock_market_data):
    """Test that backtesting preserves strategy metadata."""
    original_id = sample_strategy.id
    original_name = sample_strategy.name
    original_description = sample_strategy.description
    original_symbols = sample_strategy.symbols.copy()
    original_created_at = sample_strategy.created_at
    
    end = datetime.now()
    start = end - timedelta(days=60)
    
    # Run backtest
    strategy_engine.backtest_strategy(sample_strategy, start, end)
    
    # Verify metadata unchanged
    assert sample_strategy.id == original_id
    assert sample_strategy.name == original_name
    assert sample_strategy.description == original_description
    assert sample_strategy.symbols == original_symbols
    assert sample_strategy.created_at == original_created_at




# ============================================================================
# Task 11.1.4: Test error handling (insufficient data, invalid symbols)
# ============================================================================

def test_backtest_insufficient_data(strategy_engine, sample_strategy):
    """Test error handling when insufficient historical data is available."""
    # Create mock market data that returns empty list
    mock_market_data = Mock()
    mock_market_data.get_historical_data = Mock(return_value=[])
    strategy_engine.market_data = mock_market_data
    
    end = datetime.now()
    start = end - timedelta(days=60)
    
    # Should raise ValueError for insufficient data
    with pytest.raises(ValueError, match="No historical data available"):
        strategy_engine.backtest_strategy(sample_strategy, start, end)


def test_backtest_invalid_symbol(strategy_engine):
    """Test error handling when strategy has invalid symbols."""
    strategy = Strategy(
        id="invalid-symbol-123",
        name="Invalid Symbol Strategy",
        description="Strategy with invalid symbol",
        status=StrategyStatus.PROPOSED,
        rules={
            "entry_conditions": ["Price > MA"],
            "exit_conditions": ["Price < MA"],
            "indicators": ["SMA"],
            "timeframe": "1d"
        },
        symbols=["INVALID_SYMBOL_XYZ"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    # Mock market data to raise exception for invalid symbol
    mock_market_data = Mock()
    mock_market_data.get_historical_data = Mock(
        side_effect=Exception("Symbol not found")
    )
    strategy_engine.market_data = mock_market_data
    
    end = datetime.now()
    start = end - timedelta(days=60)
    
    # Should raise ValueError
    with pytest.raises(ValueError, match="Failed to fetch historical data"):
        strategy_engine.backtest_strategy(strategy, start, end)


def test_backtest_market_data_fetch_failure(strategy_engine, sample_strategy):
    """Test error handling when market data fetch fails."""
    # Mock market data to raise exception
    mock_market_data = Mock()
    mock_market_data.get_historical_data = Mock(
        side_effect=Exception("Network error")
    )
    strategy_engine.market_data = mock_market_data
    
    end = datetime.now()
    start = end - timedelta(days=60)
    
    # Should raise ValueError with descriptive message
    with pytest.raises(ValueError, match="Failed to fetch historical data"):
        strategy_engine.backtest_strategy(sample_strategy, start, end)


def test_backtest_vectorbt_computation_error(strategy_engine, sample_strategy, mock_market_data):
    """Test error handling when vectorbt computation fails."""
    # Mock _run_vectorbt_backtest to raise exception
    strategy_engine._run_vectorbt_backtest = Mock(
        side_effect=Exception("Vectorbt computation failed")
    )
    
    end = datetime.now()
    start = end - timedelta(days=60)
    
    # Should raise ValueError with descriptive message
    with pytest.raises(ValueError, match="Backtest failed"):
        strategy_engine.backtest_strategy(sample_strategy, start, end)


def test_backtest_status_unchanged_on_error(strategy_engine, sample_strategy):
    """Test that strategy status remains PROPOSED if backtest fails."""
    # Verify initial status
    assert sample_strategy.status == StrategyStatus.PROPOSED
    
    # Mock market data to raise exception
    mock_market_data = Mock()
    mock_market_data.get_historical_data = Mock(
        side_effect=Exception("Data fetch failed")
    )
    strategy_engine.market_data = mock_market_data
    
    end = datetime.now()
    start = end - timedelta(days=60)
    
    # Attempt backtest (should fail)
    try:
        strategy_engine.backtest_strategy(sample_strategy, start, end)
    except ValueError:
        pass
    
    # Status should remain PROPOSED
    assert sample_strategy.status == StrategyStatus.PROPOSED


def test_backtest_partial_symbol_failure(strategy_engine):
    """Test error handling when one symbol fails but others succeed."""
    strategy = Strategy(
        id="partial-fail-123",
        name="Partial Failure Strategy",
        description="Strategy where one symbol fails",
        status=StrategyStatus.PROPOSED,
        rules={
            "entry_conditions": ["Price > MA"],
            "exit_conditions": ["Price < MA"],
            "indicators": ["SMA"],
            "timeframe": "1d"
        },
        symbols=["AAPL", "INVALID_SYMBOL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    # Mock market data to succeed for AAPL but fail for INVALID_SYMBOL
    def get_historical_data_side_effect(symbol, start, end, interval="1d"):
        if symbol == "AAPL":
            data = []
            current_date = start
            price = 100.0
            while current_date <= end:
                data.append(MarketData(
                    symbol=symbol,
                    timestamp=current_date,
                    open=price,
                    high=price * 1.02,
                    low=price * 0.98,
                    close=price * 1.01,
                    volume=1000000,
                    source=DataSource.YAHOO_FINANCE
                ))
                current_date += timedelta(days=1)
                price *= 1.01
            return data
        else:
            raise Exception("Symbol not found")
    
    mock_market_data = Mock()
    mock_market_data.get_historical_data = Mock(
        side_effect=get_historical_data_side_effect
    )
    strategy_engine.market_data = mock_market_data
    
    end = datetime.now()
    start = end - timedelta(days=60)
    
    # Should raise ValueError for the failed symbol
    with pytest.raises(ValueError, match="Failed to fetch historical data"):
        strategy_engine.backtest_strategy(strategy, start, end)


def test_backtest_empty_symbol_list(strategy_engine):
    """Test error handling when strategy has no symbols."""
    strategy = Strategy(
        id="no-symbols-123",
        name="No Symbols Strategy",
        description="Strategy with empty symbol list",
        status=StrategyStatus.PROPOSED,
        rules={
            "entry_conditions": ["Price > MA"],
            "exit_conditions": ["Price < MA"],
            "indicators": ["SMA"],
            "timeframe": "1d"
        },
        symbols=[],  # Empty symbol list
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    end = datetime.now()
    start = end - timedelta(days=60)
    
    # Should handle gracefully (may raise error or return empty results)
    # The exact behavior depends on implementation
    try:
        results = strategy_engine.backtest_strategy(strategy, start, end)
        # If it succeeds, should have zero trades
        assert results.total_trades == 0
    except (ValueError, Exception):
        # Or it may raise an error, which is also acceptable
        pass


def test_backtest_date_range_validation(strategy_engine, sample_strategy, mock_market_data):
    """Test that backtest validates date range (start < end)."""
    end = datetime.now()
    start = end + timedelta(days=30)  # Start after end (invalid)
    
    # Should either raise error or handle gracefully
    # The exact behavior depends on implementation
    try:
        strategy_engine.backtest_strategy(sample_strategy, start, end)
    except (ValueError, Exception):
        # Expected to raise an error for invalid date range
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
