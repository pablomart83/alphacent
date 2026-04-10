"""Tests for BootstrapService."""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch

from src.strategy.bootstrap_service import BootstrapService, STRATEGY_TEMPLATES
from src.strategy.strategy_engine import StrategyEngine, BacktestResults
from src.models import (
    Strategy,
    StrategyStatus,
    RiskConfig,
    PerformanceMetrics,
    TradingMode,
    MarketData,
    DataSource,
)
from src.llm.llm_service import StrategyDefinition


@pytest.fixture
def mock_llm_service():
    """Create mock LLM service."""
    llm = Mock()
    
    # Mock strategy generation with different strategies for each call
    def generate_strategy_side_effect(prompt, constraints):
        # Determine strategy type from prompt
        if "momentum" in prompt.lower():
            name = "Momentum Strategy"
            desc = "A momentum-based trading strategy"
        elif "mean reversion" in prompt.lower():
            name = "Mean Reversion Strategy"
            desc = "A mean reversion trading strategy"
        elif "breakout" in prompt.lower():
            name = "Breakout Strategy"
            desc = "A breakout trading strategy"
        else:
            name = "Test Strategy"
            desc = "A test trading strategy"
        
        return StrategyDefinition(
            name=name,
            description=desc,
            rules={
                "entry_conditions": ["Condition 1"],
                "exit_conditions": ["Condition 2"],
                "indicators": ["SMA"],
                "timeframe": "1d"
            },
            symbols=constraints.get("available_symbols", ["AAPL"]),
            risk_params=RiskConfig()
        )
    
    llm.generate_strategy = Mock(side_effect=generate_strategy_side_effect)
    
    return llm


@pytest.fixture
def mock_market_data():
    """Create mock market data manager."""
    market_data = Mock()
    
    # Mock historical data
    def get_historical_data(symbol, start, end, interval="1d"):
        # Generate mock data for the requested period
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
            price *= 1.001  # Slight upward trend
        
        return data
    
    market_data.get_historical_data = Mock(side_effect=get_historical_data)
    
    return market_data


@pytest.fixture
def mock_strategy_engine(mock_llm_service, mock_market_data):
    """Create mock StrategyEngine."""
    with patch('src.strategy.strategy_engine.get_database'):
        engine = StrategyEngine(mock_llm_service, mock_market_data)
        
        # Mock database operations
        engine._save_strategy = Mock()
        engine._load_strategy = Mock()
        
        # Track generated strategies for testing
        engine._generated_strategies = []
        
        # Override generate_strategy to track created strategies
        original_generate = engine.generate_strategy
        def tracked_generate(prompt, constraints):
            strategy = original_generate(prompt, constraints)
            engine._generated_strategies.append(strategy)
            return strategy
        engine.generate_strategy = Mock(side_effect=tracked_generate)
        
        # Mock backtest_strategy to return realistic results
        def mock_backtest(strategy, start_date, end_date):
            # Return different results based on strategy name
            if "Momentum" in strategy.name:
                sharpe = 1.5
                total_return = 0.15
            elif "Mean Reversion" in strategy.name:
                sharpe = 0.8
                total_return = 0.08
            elif "Breakout" in strategy.name:
                sharpe = 1.2
                total_return = 0.12
            else:
                sharpe = 1.0
                total_return = 0.10
            
            # Create mock equity curve and trades
            dates = pd.date_range(start=start_date, end=end_date, freq='D')
            equity_curve = pd.Series(
                [100 * (1 + total_return * i / len(dates)) for i in range(len(dates))],
                index=dates
            )
            
            trades = pd.DataFrame({
                'entry_time': [start_date + timedelta(days=i*10) for i in range(5)],
                'exit_time': [start_date + timedelta(days=i*10+5) for i in range(5)],
                'pnl': [100, -50, 150, 80, -30],
                'return': [0.01, -0.005, 0.015, 0.008, -0.003]
            })
            
            results = BacktestResults(
                total_return=total_return,
                sharpe_ratio=sharpe,
                sortino_ratio=sharpe * 1.1,
                max_drawdown=0.05,
                win_rate=0.55,
                avg_win=0.02,
                avg_loss=0.01,
                total_trades=50,
                equity_curve=equity_curve,
                trades=trades
            )
            
            # Update strategy status and performance
            strategy.status = StrategyStatus.BACKTESTED
            strategy.performance = PerformanceMetrics(
                total_return=results.total_return,
                sharpe_ratio=results.sharpe_ratio,
                sortino_ratio=results.sortino_ratio,
                max_drawdown=results.max_drawdown,
                win_rate=results.win_rate,
                avg_win=results.avg_win,
                avg_loss=results.avg_loss,
                total_trades=results.total_trades
            )
            
            return results
        
        engine.backtest_strategy = Mock(side_effect=mock_backtest)
        
        # Mock activate_strategy
        def mock_activate(strategy_id, mode):
            # Find strategy and update status
            for s in engine._generated_strategies:
                if s.id == strategy_id:
                    s.status = StrategyStatus.DEMO if mode == TradingMode.DEMO else StrategyStatus.LIVE
                    s.activated_at = datetime.now()
                    break
        
        engine.activate_strategy = Mock(side_effect=mock_activate)
        
        return engine


@pytest.fixture
def bootstrap_service(mock_strategy_engine, mock_llm_service, mock_market_data):
    """Create BootstrapService with mocked dependencies."""
    return BootstrapService(
        strategy_engine=mock_strategy_engine,
        llm_service=mock_llm_service,
        market_data=mock_market_data
    )


# Task 4.1.1: Test strategy generation from templates
def test_strategy_generation_from_templates(bootstrap_service, mock_strategy_engine):
    """
    Test that bootstrap service generates strategies from predefined templates.
    
    Validates: Requirements 6.1, 6.6
    """
    # Bootstrap with all strategy types
    result = bootstrap_service.bootstrap_strategies(
        strategy_types=["momentum", "mean_reversion", "breakout"],
        auto_activate=False
    )
    
    # Verify strategies were generated
    assert len(result["strategies"]) == 3
    assert result["summary"]["total_generated"] == 3
    
    # Verify strategy names match templates
    strategy_names = [s.name for s in result["strategies"]]
    assert "Momentum Strategy" in strategy_names
    assert "Mean Reversion Strategy" in strategy_names
    assert "Breakout Strategy" in strategy_names
    
    # Verify each strategy has correct symbols from template
    for strategy in result["strategies"]:
        if "Momentum" in strategy.name:
            assert set(strategy.symbols) == set(STRATEGY_TEMPLATES["momentum"]["symbols"])
        elif "Mean Reversion" in strategy.name:
            assert set(strategy.symbols) == set(STRATEGY_TEMPLATES["mean_reversion"]["symbols"])
        elif "Breakout" in strategy.name:
            assert set(strategy.symbols) == set(STRATEGY_TEMPLATES["breakout"]["symbols"])
    
    # Verify LLM was called for each strategy
    assert mock_strategy_engine.generate_strategy.call_count == 3


def test_strategy_generation_single_template(bootstrap_service):
    """Test generating a single strategy type."""
    result = bootstrap_service.bootstrap_strategies(
        strategy_types=["momentum"],
        auto_activate=False
    )
    
    assert len(result["strategies"]) == 1
    assert result["strategies"][0].name == "Momentum Strategy"
    assert result["summary"]["total_generated"] == 1


def test_strategy_generation_default_templates(bootstrap_service):
    """Test that default behavior generates all template types."""
    result = bootstrap_service.bootstrap_strategies(auto_activate=False)
    
    # Should generate all 3 default templates
    assert len(result["strategies"]) == 3
    assert result["summary"]["total_generated"] == 3


def test_strategy_generation_invalid_template(bootstrap_service):
    """Test handling of invalid strategy types."""
    result = bootstrap_service.bootstrap_strategies(
        strategy_types=["invalid_type", "momentum"],
        auto_activate=False
    )
    
    # Should only generate valid template (momentum)
    assert len(result["strategies"]) == 1
    assert result["strategies"][0].name == "Momentum Strategy"


def test_strategy_generation_all_invalid_templates(bootstrap_service):
    """Test handling when all strategy types are invalid."""
    result = bootstrap_service.bootstrap_strategies(
        strategy_types=["invalid1", "invalid2"],
        auto_activate=False
    )
    
    # Should generate no strategies
    assert len(result["strategies"]) == 0
    assert result["summary"]["total_generated"] == 0
    assert len(result["summary"]["errors"]) > 0
    assert "No valid strategy types provided" in result["summary"]["errors"][0]


# Task 4.1.2: Test automatic backtesting
def test_automatic_backtesting(bootstrap_service, mock_strategy_engine):
    """
    Test that bootstrap service automatically backtests generated strategies.
    
    Validates: Requirements 6.2, 6.3, 6.6
    """
    result = bootstrap_service.bootstrap_strategies(
        strategy_types=["momentum", "mean_reversion"],
        auto_activate=False,
        backtest_days=90
    )
    
    # Verify all strategies were backtested
    assert result["summary"]["total_backtested"] == 2
    assert len(result["backtest_results"]) == 2
    
    # Verify backtest was called for each strategy
    assert mock_strategy_engine.backtest_strategy.call_count == 2
    
    # Verify backtest results contain performance metrics
    for strategy_id, backtest_result in result["backtest_results"].items():
        assert backtest_result.total_return is not None
        assert backtest_result.sharpe_ratio is not None
        assert backtest_result.sortino_ratio is not None
        assert backtest_result.max_drawdown is not None
        assert backtest_result.win_rate is not None
        assert backtest_result.total_trades > 0
    
    # Verify strategies have BACKTESTED status
    for strategy in result["strategies"]:
        assert strategy.status == StrategyStatus.BACKTESTED


def test_backtest_with_custom_period(bootstrap_service, mock_strategy_engine):
    """Test backtesting with custom time period."""
    result = bootstrap_service.bootstrap_strategies(
        strategy_types=["momentum"],
        auto_activate=False,
        backtest_days=60
    )
    
    # Verify backtest was called with correct date range
    call_args = mock_strategy_engine.backtest_strategy.call_args
    strategy, start_date, end_date = call_args[0]
    
    # Verify date range is approximately 60 days
    date_diff = (end_date - start_date).days
    assert 59 <= date_diff <= 61  # Allow 1 day tolerance


def test_backtest_results_display(bootstrap_service):
    """Test that backtest results are properly returned in summary."""
    result = bootstrap_service.bootstrap_strategies(
        strategy_types=["momentum"],
        auto_activate=False
    )
    
    strategy = result["strategies"][0]
    backtest_result = result["backtest_results"][strategy.id]
    
    # Verify performance metrics match
    assert strategy.performance.sharpe_ratio == backtest_result.sharpe_ratio
    assert strategy.performance.total_return == backtest_result.total_return
    assert strategy.performance.total_trades == backtest_result.total_trades


# Task 4.1.3: Test auto-activation logic
def test_auto_activation_above_threshold(bootstrap_service, mock_strategy_engine):
    """
    Test that strategies meeting performance threshold are auto-activated.
    
    Validates: Requirements 6.4
    """
    result = bootstrap_service.bootstrap_strategies(
        strategy_types=["momentum"],  # Sharpe = 1.5
        auto_activate=True,
        min_sharpe=1.0
    )
    
    # Verify strategy was activated
    assert len(result["activated"]) == 1
    assert result["summary"]["total_activated"] == 1
    
    # Verify activate_strategy was called
    mock_strategy_engine.activate_strategy.assert_called_once()
    
    # Verify strategy status is DEMO
    strategy = result["strategies"][0]
    assert strategy.status == StrategyStatus.DEMO
    assert strategy.activated_at is not None


def test_auto_activation_below_threshold(bootstrap_service, mock_strategy_engine):
    """Test that strategies below threshold are not auto-activated."""
    result = bootstrap_service.bootstrap_strategies(
        strategy_types=["mean_reversion"],  # Sharpe = 0.8
        auto_activate=True,
        min_sharpe=1.0
    )
    
    # Verify strategy was NOT activated
    assert len(result["activated"]) == 0
    assert result["summary"]["total_activated"] == 0
    
    # Verify activate_strategy was NOT called
    mock_strategy_engine.activate_strategy.assert_not_called()
    
    # Verify strategy status is still BACKTESTED
    strategy = result["strategies"][0]
    assert strategy.status == StrategyStatus.BACKTESTED


def test_auto_activation_mixed_performance(bootstrap_service, mock_strategy_engine):
    """Test auto-activation with mixed performance strategies."""
    result = bootstrap_service.bootstrap_strategies(
        strategy_types=["momentum", "mean_reversion", "breakout"],
        # Momentum: 1.5, Mean Reversion: 0.8, Breakout: 1.2
        auto_activate=True,
        min_sharpe=1.0
    )
    
    # Verify only strategies above threshold were activated
    # Momentum (1.5) and Breakout (1.2) should be activated
    assert len(result["activated"]) == 2
    assert result["summary"]["total_activated"] == 2
    
    # Verify correct strategies were activated
    activated_strategies = [s for s in result["strategies"] if s.status == StrategyStatus.DEMO]
    assert len(activated_strategies) == 2
    
    activated_names = [s.name for s in activated_strategies]
    assert "Momentum Strategy" in activated_names
    assert "Breakout Strategy" in activated_names
    assert "Mean Reversion Strategy" not in activated_names


def test_auto_activation_disabled(bootstrap_service, mock_strategy_engine):
    """Test that auto-activation can be disabled."""
    result = bootstrap_service.bootstrap_strategies(
        strategy_types=["momentum"],  # High Sharpe
        auto_activate=False,
        min_sharpe=0.5
    )
    
    # Verify no strategies were activated
    assert len(result["activated"]) == 0
    assert result["summary"]["total_activated"] == 0
    
    # Verify activate_strategy was NOT called
    mock_strategy_engine.activate_strategy.assert_not_called()


# Task 4.1.4: Test error handling (LLM unavailable, backtest failures)
def test_error_handling_llm_unavailable(bootstrap_service, mock_strategy_engine):
    """
    Test error handling when LLM service is unavailable.
    
    Validates: Requirements 6.6
    """
    # Make generate_strategy raise an exception
    mock_strategy_engine.generate_strategy.side_effect = ConnectionError("LLM service unavailable")
    
    result = bootstrap_service.bootstrap_strategies(
        strategy_types=["momentum"],
        auto_activate=False
    )
    
    # Verify no strategies were created
    assert len(result["strategies"]) == 0
    assert result["summary"]["total_generated"] == 0
    
    # Verify error was captured
    assert len(result["summary"]["errors"]) > 0
    assert "LLM service unavailable" in result["summary"]["errors"][0]


def test_error_handling_backtest_failure(bootstrap_service, mock_strategy_engine):
    """Test error handling when backtest fails."""
    # Make backtest_strategy raise an exception
    mock_strategy_engine.backtest_strategy.side_effect = ValueError("Insufficient historical data")
    
    result = bootstrap_service.bootstrap_strategies(
        strategy_types=["momentum"],
        auto_activate=False
    )
    
    # Verify strategy was generated but not backtested
    assert len(result["strategies"]) == 1
    assert result["summary"]["total_generated"] == 1
    assert result["summary"]["total_backtested"] == 0
    
    # Verify error was captured
    assert len(result["summary"]["errors"]) > 0
    assert "Insufficient historical data" in result["summary"]["errors"][0]


def test_error_handling_activation_failure(bootstrap_service, mock_strategy_engine):
    """Test error handling when activation fails."""
    # Make activate_strategy raise an exception
    mock_strategy_engine.activate_strategy.side_effect = ValueError("Allocation exceeds 100%")
    
    result = bootstrap_service.bootstrap_strategies(
        strategy_types=["momentum"],
        auto_activate=True,
        min_sharpe=1.0
    )
    
    # Verify strategy was generated and backtested but not activated
    assert len(result["strategies"]) == 1
    assert result["summary"]["total_generated"] == 1
    assert result["summary"]["total_backtested"] == 1
    assert result["summary"]["total_activated"] == 0
    
    # Verify error was captured
    assert len(result["summary"]["errors"]) > 0
    assert "Allocation exceeds 100%" in result["summary"]["errors"][0]


def test_error_handling_partial_failure(bootstrap_service, mock_strategy_engine):
    """Test that partial failures don't stop the entire bootstrap process."""
    # Make generate_strategy fail for mean_reversion only
    call_count = [0]
    original_generate = mock_strategy_engine.generate_strategy.side_effect
    
    def selective_failure(prompt, constraints):
        if "mean reversion" in prompt.lower():
            raise ValueError("Strategy generation failed")
        # Call original for other strategies
        return original_generate(prompt, constraints)
    
    # Reset the mock to use selective failure
    mock_strategy_engine.generate_strategy.side_effect = selective_failure
    
    result = bootstrap_service.bootstrap_strategies(
        strategy_types=["momentum", "mean_reversion", "breakout"],
        auto_activate=False
    )
    
    # Verify 2 strategies succeeded, 1 failed
    assert len(result["strategies"]) == 2
    assert result["summary"]["total_generated"] == 2
    
    # Verify error was captured for the failed strategy
    assert len(result["summary"]["errors"]) >= 1
    # Check that at least one error mentions mean_reversion
    error_messages = " ".join(result["summary"]["errors"])
    assert "mean_reversion" in error_messages or "Mean Reversion" in error_messages


def test_error_handling_empty_strategy_types(bootstrap_service):
    """Test handling of empty strategy types list."""
    result = bootstrap_service.bootstrap_strategies(
        strategy_types=[],
        auto_activate=False
    )
    
    # Should return empty results with error
    assert len(result["strategies"]) == 0
    assert result["summary"]["total_generated"] == 0
    assert len(result["summary"]["errors"]) > 0
