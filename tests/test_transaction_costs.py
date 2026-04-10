"""Tests for transaction cost calculation in backtesting."""

import pytest
from datetime import datetime, timedelta
from src.models import Strategy, StrategyStatus, RiskConfig, PerformanceMetrics
from src.strategy.strategy_engine import StrategyEngine
from src.data.market_data_manager import MarketDataManager
from src.api.etoro_client import EToroAPIClient
from src.models import TradingMode


@pytest.fixture
def strategy_engine():
    """Create strategy engine for testing."""
    # Create real eToro client in DEMO mode
    from src.core.config import get_config
    config = get_config()
    
    credentials = config.load_credentials(TradingMode.DEMO)
    
    etoro_client = EToroAPIClient(
        public_key=credentials["public_key"],
        user_key=credentials["user_key"],
        mode=TradingMode.DEMO
    )
    market_data = MarketDataManager(etoro_client)
    return StrategyEngine(llm_service=None, market_data=market_data)


@pytest.fixture
def test_strategy():
    """Create a simple test strategy."""
    return Strategy(
        id="test-strategy-1",
        name="Test Strategy",
        description="Simple test strategy for transaction cost testing",
        status=StrategyStatus.PROPOSED,
        rules={
            "indicators": ["SMA:20", "SMA:50"],
            "entry_conditions": [
                {"type": "crossover", "indicator1": "SMA:20", "indicator2": "SMA:50"}
            ],
            "exit_conditions": [
                {"type": "crossunder", "indicator1": "SMA:20", "indicator2": "SMA:50"}
            ]
        },
        symbols=["AAPL"],
        risk_params=RiskConfig(
            max_position_size_pct=0.1,
            stop_loss_pct=0.02,
            take_profit_pct=0.04
        ),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )


def test_transaction_costs_applied(strategy_engine, test_strategy):
    """Test that transaction costs are applied to backtest results."""
    # Run backtest with known transaction costs
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    results = strategy_engine.backtest_strategy(
        test_strategy,
        start_date,
        end_date,
        commission=0.001,  # 0.1%
        slippage_bps=5.0   # 0.05%
    )
    
    # Verify transaction cost fields exist
    assert hasattr(results, 'gross_return')
    assert hasattr(results, 'net_return')
    assert hasattr(results, 'total_transaction_costs')
    assert hasattr(results, 'total_commission_cost')
    assert hasattr(results, 'total_slippage_cost')
    assert hasattr(results, 'total_spread_cost')
    
    # Verify costs are calculated if there are trades
    if results.total_trades > 0:
        assert results.total_transaction_costs > 0
        assert results.total_commission_cost >= 0
        assert results.total_slippage_cost >= 0
        assert results.total_spread_cost >= 0
        
        # Net return should be less than gross return (costs reduce returns)
        assert results.net_return <= results.gross_return
        
        # Total costs should equal sum of components
        expected_total = (
            results.total_commission_cost +
            results.total_slippage_cost +
            results.total_spread_cost
        )
        assert abs(results.total_transaction_costs - expected_total) < 0.01


def test_transaction_costs_from_config(strategy_engine, test_strategy):
    """Test that transaction costs are loaded from config when not specified."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    # Run backtest without specifying costs (should load from config)
    results = strategy_engine.backtest_strategy(
        test_strategy,
        start_date,
        end_date
    )
    
    # Verify transaction cost fields exist
    assert hasattr(results, 'gross_return')
    assert hasattr(results, 'net_return')
    assert hasattr(results, 'total_transaction_costs')


def test_negative_net_profit_flagged(strategy_engine, test_strategy):
    """Test that strategies with negative net profit are flagged."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    results = strategy_engine.backtest_strategy(
        test_strategy,
        start_date,
        end_date
    )
    
    # If net return is negative, it should be reflected in total_return
    if results.net_return < 0:
        assert results.total_return < 0
        # Strategy should not pass activation criteria
        from src.strategy.portfolio_manager import PortfolioManager
        portfolio_manager = PortfolioManager(strategy_engine)
        should_activate = portfolio_manager.evaluate_for_activation(
            test_strategy,
            results
        )
        # Negative returns should fail activation
        assert not should_activate


def test_transaction_costs_percentage_calculation(strategy_engine, test_strategy):
    """Test that transaction costs as percentage is calculated correctly."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    
    results = strategy_engine.backtest_strategy(
        test_strategy,
        start_date,
        end_date,
        commission=0.001,
        slippage_bps=5.0
    )
    
    if results.total_trades > 0:
        # Transaction costs percentage should be positive
        assert results.transaction_costs_pct >= 0
        
        # Should be reasonable (less than 50% of capital)
        assert results.transaction_costs_pct < 0.5
