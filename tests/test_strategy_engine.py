"""Tests for StrategyEngine."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch

from src.strategy.strategy_engine import StrategyEngine, BacktestResults
from src.models import (
    Strategy,
    StrategyStatus,
    RiskConfig,
    PerformanceMetrics,
    TradingMode,
    Position,
    PositionSide,
)
from src.llm.llm_service import StrategyDefinition


@pytest.fixture
def mock_llm_service():
    """Create mock LLM service."""
    llm = Mock()
    
    # Mock strategy generation
    strategy_def = StrategyDefinition(
        name="Test Strategy",
        description="A test momentum strategy",
        rules={
            "entry_conditions": ["Fast MA crosses above slow MA"],
            "exit_conditions": ["Fast MA crosses below slow MA"],
            "indicators": ["SMA"],
            "timeframe": "1d"
        },
        symbols=["AAPL"],
        risk_params=RiskConfig()
    )
    llm.generate_strategy = Mock(return_value=strategy_def)
    
    return llm


@pytest.fixture
def mock_market_data():
    """Create mock market data manager."""
    from src.models import MarketData, DataSource
    
    market_data = Mock()
    
    # Mock historical data
    def get_historical_data(symbol, start, end, interval="1d"):
        # Generate 60 days of mock data
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
def strategy_engine(mock_llm_service, mock_market_data):
    """Create StrategyEngine with mocked dependencies."""
    with patch('src.strategy.strategy_engine.get_database'):
        engine = StrategyEngine(mock_llm_service, mock_market_data)
        # Mock database operations
        engine._save_strategy = Mock()
        engine._load_strategy = Mock()
        return engine


def test_generate_strategy(strategy_engine, mock_llm_service):
    """Test strategy generation."""
    prompt = "Create a momentum strategy for tech stocks"
    constraints = {
        "risk_config": RiskConfig(),
        "available_symbols": ["AAPL", "MSFT", "GOOGL"]
    }
    
    strategy = strategy_engine.generate_strategy(prompt, constraints)
    
    assert strategy is not None
    assert strategy.name == "Test Strategy"
    assert strategy.status == StrategyStatus.PROPOSED
    assert "AAPL" in strategy.symbols
    assert strategy.id is not None
    
    # Verify LLM was called
    mock_llm_service.generate_strategy.assert_called_once_with(prompt, constraints)
    
    # Verify strategy was saved
    strategy_engine._save_strategy.assert_called_once()


def test_activate_strategy(strategy_engine):
    """Test strategy activation."""
    # Create a backtested strategy
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.BACKTESTED,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    
    # Activate in demo mode
    strategy_engine.activate_strategy("test-123", TradingMode.DEMO)
    
    assert strategy.status == StrategyStatus.DEMO
    assert strategy.activated_at is not None
    strategy_engine._save_strategy.assert_called()


def test_activate_strategy_invalid_status(strategy_engine):
    """Test that activating a non-backtested strategy raises error."""
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.PROPOSED,  # Not backtested
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    
    with pytest.raises(ValueError, match="must be BACKTESTED"):
        strategy_engine.activate_strategy("test-123", TradingMode.DEMO)


def test_deactivate_strategy(strategy_engine):
    """Test strategy deactivation."""
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.LIVE,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        activated_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    strategy_engine._active_strategies["test-123"] = strategy
    
    strategy_engine.deactivate_strategy("test-123")
    
    assert strategy.status == StrategyStatus.BACKTESTED
    assert "test-123" not in strategy_engine._active_strategies
    strategy_engine._save_strategy.assert_called()


def test_optimize_allocations_equal_sharpe(strategy_engine):
    """Test allocation optimization with equal Sharpe ratios."""
    strategies = [
        Strategy(
            id="strat-1",
            name="Strategy 1",
            description="Test",
            status=StrategyStatus.LIVE,
            rules={},
            symbols=["AAPL"],
            risk_params=RiskConfig(),
            created_at=datetime.now(),
            performance=PerformanceMetrics(sharpe_ratio=1.5)
        ),
        Strategy(
            id="strat-2",
            name="Strategy 2",
            description="Test",
            status=StrategyStatus.LIVE,
            rules={},
            symbols=["MSFT"],
            risk_params=RiskConfig(),
            created_at=datetime.now(),
            performance=PerformanceMetrics(sharpe_ratio=1.5)
        )
    ]
    
    allocations = strategy_engine.optimize_allocations(strategies)
    
    assert len(allocations) == 2
    assert abs(allocations["strat-1"] - 0.5) < 0.01  # Should be ~50%
    assert abs(allocations["strat-2"] - 0.5) < 0.01  # Should be ~50%
    assert abs(sum(allocations.values()) - 1.0) < 0.001  # Should sum to 100%


def test_optimize_allocations_different_sharpe(strategy_engine):
    """Test allocation optimization with different Sharpe ratios."""
    strategies = [
        Strategy(
            id="strat-1",
            name="Strategy 1",
            description="Test",
            status=StrategyStatus.LIVE,
            rules={},
            symbols=["AAPL"],
            risk_params=RiskConfig(),
            created_at=datetime.now(),
            performance=PerformanceMetrics(sharpe_ratio=2.0)
        ),
        Strategy(
            id="strat-2",
            name="Strategy 2",
            description="Test",
            status=StrategyStatus.LIVE,
            rules={},
            symbols=["MSFT"],
            risk_params=RiskConfig(),
            created_at=datetime.now(),
            performance=PerformanceMetrics(sharpe_ratio=1.0)
        )
    ]
    
    allocations = strategy_engine.optimize_allocations(strategies)
    
    assert len(allocations) == 2
    # Strategy 1 should get more allocation (2x Sharpe ratio)
    assert allocations["strat-1"] > allocations["strat-2"]
    assert abs(sum(allocations.values()) - 1.0) < 0.001  # Should sum to 100%


def test_check_retirement_triggers_low_sharpe(strategy_engine):
    """Test retirement trigger for low Sharpe ratio."""
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.LIVE,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics(
            sharpe_ratio=0.3,  # Below 0.5 threshold
            total_trades=35  # Above 30 threshold
        )
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    
    reason = strategy_engine.check_retirement_triggers("test-123")
    
    assert reason is not None
    assert "Sharpe ratio" in reason


def test_check_retirement_triggers_high_drawdown(strategy_engine):
    """Test retirement trigger for high drawdown."""
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.LIVE,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics(
            max_drawdown=0.20,  # Above 15% threshold
            total_trades=10
        )
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    
    reason = strategy_engine.check_retirement_triggers("test-123")
    
    assert reason is not None
    assert "drawdown" in reason


def test_check_retirement_triggers_no_trigger(strategy_engine):
    """Test that good performance doesn't trigger retirement."""
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.LIVE,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics(
            sharpe_ratio=1.5,
            max_drawdown=0.08,
            win_rate=0.55,
            total_return=1000.0,
            total_trades=50
        )
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    
    reason = strategy_engine.check_retirement_triggers("test-123")
    
    assert reason is None


def test_retire_strategy(strategy_engine):
    """Test strategy retirement."""
    strategy = Strategy(
        id="test-123",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.LIVE,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    strategy_engine._active_strategies["test-123"] = strategy
    
    # Mock database session
    with patch('src.strategy.strategy_engine.get_database'):
        mock_session = Mock()
        mock_session.query().filter().all.return_value = []
        strategy_engine.db.get_session = Mock(return_value=mock_session)
        
        strategy_engine.retire_strategy("test-123", "Poor performance")
    
    assert strategy.status == StrategyStatus.RETIRED
    assert strategy.retired_at is not None
    assert "test-123" not in strategy_engine._active_strategies
    strategy_engine._save_strategy.assert_called()


def test_rebalance_portfolio(strategy_engine):
    """Test portfolio rebalancing."""
    # Create mock positions
    positions = [
        Position(
            id="pos-1",
            strategy_id="strat-1",
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=10,
            entry_price=100.0,
            current_price=110.0,
            unrealized_pnl=100.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro-1",
            closed_at=None
        )
    ]
    
    # Current allocation: strat-1 has $1100 (10 * 110)
    # Account balance: $10000
    # Current allocation: 11%
    # Target allocation: 30%
    # Should generate buy order for ~$1900
    
    target_allocations = {
        "strat-1": 0.30,  # 30%
        "strat-2": 0.70   # 70%
    }
    
    # Mock strategy loading
    strategy1 = Strategy(
        id="strat-1",
        name="Strategy 1",
        description="Test",
        status=StrategyStatus.LIVE,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    strategy2 = Strategy(
        id="strat-2",
        name="Strategy 2",
        description="Test",
        status=StrategyStatus.LIVE,
        rules={},
        symbols=["MSFT"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    def load_strategy_side_effect(strategy_id):
        if strategy_id == "strat-1":
            return strategy1
        elif strategy_id == "strat-2":
            return strategy2
        return None
    
    strategy_engine._load_strategy = Mock(side_effect=load_strategy_side_effect)
    
    orders = strategy_engine.rebalance_portfolio(
        target_allocations,
        account_balance=10000.0,
        current_positions=positions
    )
    
    # Should generate rebalancing orders
    assert len(orders) > 0
    
    # Check that orders have required fields
    for order in orders:
        assert "strategy_id" in order
        assert "symbol" in order
        assert "action" in order
        assert "value" in order
        assert "reason" in order


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_compare_to_benchmark(strategy_engine, mock_market_data):
    """Test benchmark comparison functionality."""
    from src.models import MarketData, DataSource
    from src.models.orm import PositionORM
    
    # Create a mock strategy
    strategy = Strategy(
        id="test-strategy-1",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.LIVE,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now() - timedelta(days=60),
        activated_at=datetime.now() - timedelta(days=60),
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    
    # Mock benchmark data
    start = datetime.now() - timedelta(days=60)
    end = datetime.now()
    
    benchmark_data = []
    current_date = start
    price = 400.0  # SPY starting price
    
    while current_date <= end:
        benchmark_data.append(MarketData(
            symbol="SPY",
            timestamp=current_date,
            open=price,
            high=price * 1.01,
            low=price * 0.99,
            close=price,
            volume=10000000,
            source=DataSource.YAHOO_FINANCE
        ))
        current_date += timedelta(days=1)
        price *= 1.002  # 0.2% daily growth
    
    mock_market_data.get_historical_data = Mock(return_value=benchmark_data)
    
    # Mock database session with positions
    mock_session = Mock()
    mock_positions = [
        Mock(
            strategy_id="test-strategy-1",
            opened_at=start + timedelta(days=10),
            closed_at=start + timedelta(days=20),
            realized_pnl=1000.0,
            unrealized_pnl=0.0
        ),
        Mock(
            strategy_id="test-strategy-1",
            opened_at=start + timedelta(days=30),
            closed_at=start + timedelta(days=40),
            realized_pnl=1500.0,
            unrealized_pnl=0.0
        )
    ]
    
    mock_query = Mock()
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = mock_positions
    mock_session.query.return_value = mock_query
    
    strategy_engine.db.get_session = Mock(return_value=mock_session)
    
    # Run benchmark comparison
    result = strategy_engine.compare_to_benchmark("test-strategy-1", "SPY")
    
    # Verify results
    assert "strategy_return" in result
    assert "benchmark_return" in result
    assert "relative_performance" in result
    assert "alpha" in result
    assert "beta" in result
    
    # Strategy should have positive return from positions
    assert result["strategy_return"] > 0
    
    # Benchmark should have positive return (0.2% daily growth)
    assert result["benchmark_return"] > 0
    
    # Relative performance is strategy - benchmark
    assert result["relative_performance"] == pytest.approx(
        result["strategy_return"] - result["benchmark_return"],
        rel=0.01
    )


def test_attribute_pnl_by_strategy(strategy_engine):
    """Test P&L attribution by strategy."""
    from src.models.orm import PositionORM
    
    # Create mock strategies
    strategy1 = Strategy(
        id="strategy-1",
        name="Strategy 1",
        description="Test",
        status=StrategyStatus.LIVE,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    strategy2 = Strategy(
        id="strategy-2",
        name="Strategy 2",
        description="Test",
        status=StrategyStatus.LIVE,
        rules={},
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
    
    # Mock database session with positions
    start = datetime.now() - timedelta(days=30)
    end = datetime.now()
    
    mock_session = Mock()
    mock_positions = [
        Mock(
            id="pos-1",
            strategy_id="strategy-1",
            symbol="AAPL",
            opened_at=start + timedelta(days=5),
            closed_at=start + timedelta(days=10),
            realized_pnl=500.0,
            unrealized_pnl=0.0,
            quantity=10,
            entry_price=150.0,
            current_price=155.0
        ),
        Mock(
            id="pos-2",
            strategy_id="strategy-1",
            symbol="AAPL",
            opened_at=start + timedelta(days=15),
            closed_at=start + timedelta(days=20),
            realized_pnl=300.0,
            unrealized_pnl=0.0,
            quantity=10,
            entry_price=155.0,
            current_price=158.0
        ),
        Mock(
            id="pos-3",
            strategy_id="strategy-2",
            symbol="MSFT",
            opened_at=start + timedelta(days=10),
            closed_at=start + timedelta(days=25),
            realized_pnl=1200.0,
            unrealized_pnl=0.0,
            quantity=20,
            entry_price=300.0,
            current_price=306.0
        )
    ]
    
    mock_query = Mock()
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = mock_positions
    mock_session.query.return_value = mock_query
    
    strategy_engine.db.get_session = Mock(return_value=mock_session)
    
    # Run P&L attribution by strategy
    result = strategy_engine.attribute_pnl(start=start, end=end, group_by="strategy")
    
    # Verify results
    assert "strategy-1" in result
    assert "strategy-2" in result
    
    # Strategy 1 should have 800 total P&L (500 + 300)
    assert result["strategy-1"]["pnl"] == 800.0
    assert result["strategy-1"]["trades"] == 2
    assert result["strategy-1"]["name"] == "Strategy 1"
    
    # Strategy 2 should have 1200 total P&L
    assert result["strategy-2"]["pnl"] == 1200.0
    assert result["strategy-2"]["trades"] == 1
    assert result["strategy-2"]["name"] == "Strategy 2"
    
    # Total P&L is 2000, so contributions should be 40% and 60%
    assert result["strategy-1"]["contribution_pct"] == pytest.approx(40.0, rel=0.01)
    assert result["strategy-2"]["contribution_pct"] == pytest.approx(60.0, rel=0.01)


def test_attribute_pnl_by_position(strategy_engine):
    """Test P&L attribution by individual position."""
    from src.models.orm import PositionORM
    
    # Create mock strategy
    strategy = Strategy(
        id="strategy-1",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.LIVE,
        rules={},
        symbols=["AAPL", "MSFT"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    
    # Mock database session with positions
    start = datetime.now() - timedelta(days=30)
    end = datetime.now()
    
    mock_session = Mock()
    mock_positions = [
        Mock(
            id="pos-1",
            strategy_id="strategy-1",
            symbol="AAPL",
            opened_at=start + timedelta(days=5),
            closed_at=start + timedelta(days=10),
            realized_pnl=1000.0,
            unrealized_pnl=0.0,
            quantity=10,
            entry_price=150.0,
            current_price=160.0
        ),
        Mock(
            id="pos-2",
            strategy_id="strategy-1",
            symbol="MSFT",
            opened_at=start + timedelta(days=15),
            closed_at=start + timedelta(days=20),
            realized_pnl=-200.0,
            unrealized_pnl=0.0,
            quantity=5,
            entry_price=300.0,
            current_price=296.0
        ),
        Mock(
            id="pos-3",
            strategy_id="strategy-1",
            symbol="AAPL",
            opened_at=start + timedelta(days=20),
            closed_at=None,
            realized_pnl=0.0,
            unrealized_pnl=200.0,
            quantity=10,
            entry_price=155.0,
            current_price=157.0
        )
    ]
    
    mock_query = Mock()
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = mock_positions
    mock_session.query.return_value = mock_query
    
    strategy_engine.db.get_session = Mock(return_value=mock_session)
    
    # Run P&L attribution by position
    result = strategy_engine.attribute_pnl(start=start, end=end, group_by="position")
    
    # Verify results
    assert "pos-1" in result
    assert "pos-2" in result
    assert "pos-3" in result
    
    # Position 1: 1000 P&L
    assert result["pos-1"]["pnl"] == 1000.0
    assert result["pos-1"]["symbol"] == "AAPL"
    assert result["pos-1"]["strategy_name"] == "Test Strategy"
    
    # Position 2: -200 P&L
    assert result["pos-2"]["pnl"] == -200.0
    assert result["pos-2"]["symbol"] == "MSFT"
    
    # Position 3: 200 unrealized P&L
    assert result["pos-3"]["pnl"] == 200.0
    assert result["pos-3"]["symbol"] == "AAPL"
    assert result["pos-3"]["closed_at"] is None  # Still open
    
    # Total P&L is 1000, so contributions should be 100%, -20%, 20%
    assert result["pos-1"]["contribution_pct"] == pytest.approx(100.0, rel=0.01)
    assert result["pos-2"]["contribution_pct"] == pytest.approx(-20.0, rel=0.01)
    assert result["pos-3"]["contribution_pct"] == pytest.approx(20.0, rel=0.01)


def test_attribute_pnl_by_time_period(strategy_engine):
    """Test P&L attribution by time period."""
    from src.models.orm import PositionORM
    
    # Create mock strategy
    strategy = Strategy(
        id="strategy-1",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.LIVE,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    
    # Mock database session with positions across different weeks
    start = datetime.now() - timedelta(days=30)
    end = datetime.now()
    
    mock_session = Mock()
    mock_positions = [
        Mock(
            id="pos-1",
            strategy_id="strategy-1",
            symbol="AAPL",
            opened_at=start + timedelta(days=5),
            closed_at=start + timedelta(days=7),
            realized_pnl=500.0,
            unrealized_pnl=0.0,
            quantity=10,
            entry_price=150.0,
            current_price=155.0
        ),
        Mock(
            id="pos-2",
            strategy_id="strategy-1",
            symbol="AAPL",
            opened_at=start + timedelta(days=15),
            closed_at=start + timedelta(days=17),
            realized_pnl=300.0,
            unrealized_pnl=0.0,
            quantity=10,
            entry_price=155.0,
            current_price=158.0
        ),
        Mock(
            id="pos-3",
            strategy_id="strategy-1",
            symbol="AAPL",
            opened_at=start + timedelta(days=25),
            closed_at=start + timedelta(days=27),
            realized_pnl=-100.0,
            unrealized_pnl=0.0,
            quantity=10,
            entry_price=158.0,
            current_price=157.0
        )
    ]
    
    mock_query = Mock()
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = mock_positions
    mock_session.query.return_value = mock_query
    
    strategy_engine.db.get_session = Mock(return_value=mock_session)
    
    # Run P&L attribution by time period
    result = strategy_engine.attribute_pnl(start=start, end=end, group_by="time_period")
    
    # Verify results - should have weekly groupings
    assert len(result) > 0
    
    # Each period should have P&L, trades, and strategy count
    for period_key, data in result.items():
        assert "pnl" in data
        assert "trades" in data
        assert "strategies" in data
        assert "winning_trades" in data
        assert "losing_trades" in data
    
    # Total P&L across all periods should be 700 (500 + 300 - 100)
    total_pnl = sum(data["pnl"] for data in result.values())
    assert total_pnl == pytest.approx(700.0, rel=0.01)
    
    # Total trades should be 3
    total_trades = sum(data["trades"] for data in result.values())
    assert total_trades == 3


def test_attribute_pnl_invalid_group_by(strategy_engine):
    """Test P&L attribution with invalid group_by parameter."""
    with pytest.raises(ValueError, match="Invalid group_by"):
        strategy_engine.attribute_pnl(group_by="invalid")


def test_compare_to_benchmark_no_positions(strategy_engine, mock_market_data):
    """Test benchmark comparison with no positions."""
    from src.models import MarketData, DataSource
    
    # Create a mock strategy
    strategy = Strategy(
        id="test-strategy-1",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.LIVE,
        rules={},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now() - timedelta(days=60),
        activated_at=datetime.now() - timedelta(days=60),
        performance=PerformanceMetrics()
    )
    
    strategy_engine._load_strategy = Mock(return_value=strategy)
    
    # Mock benchmark data
    start = datetime.now() - timedelta(days=60)
    end = datetime.now()
    
    benchmark_data = []
    current_date = start
    price = 400.0
    
    while current_date <= end:
        benchmark_data.append(MarketData(
            symbol="SPY",
            timestamp=current_date,
            open=price,
            high=price * 1.01,
            low=price * 0.99,
            close=price,
            volume=10000000,
            source=DataSource.YAHOO_FINANCE
        ))
        current_date += timedelta(days=1)
        price *= 1.002
    
    mock_market_data.get_historical_data = Mock(return_value=benchmark_data)
    
    # Mock database session with no positions
    mock_session = Mock()
    mock_query = Mock()
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = []
    mock_session.query.return_value = mock_query
    
    strategy_engine.db.get_session = Mock(return_value=mock_session)
    
    # Run benchmark comparison
    result = strategy_engine.compare_to_benchmark("test-strategy-1", "SPY")
    
    # Verify results
    assert result["strategy_return"] == 0.0
    assert result["benchmark_return"] > 0
    assert result["relative_performance"] < 0  # Underperformed benchmark
    assert result["alpha"] == 0.0
    assert result["beta"] == 0.0
