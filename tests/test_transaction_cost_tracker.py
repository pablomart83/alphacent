"""Tests for TransactionCostTracker."""

import pytest
from datetime import datetime, timedelta
from src.strategy.transaction_cost_tracker import (
    TransactionCostTracker,
    TransactionCosts,
    CostComparison
)
from src.models.database import Database


@pytest.fixture
def config():
    """Test configuration."""
    return {
        'backtest': {
            'transaction_costs': {
                'commission_per_share': 0.005,
                'commission_percent': 0.001,
                'slippage_percent': 0.0005,
                'spread_percent': 0.0002
            }
        }
    }


@pytest.fixture
def database():
    """Create in-memory test database."""
    db = Database(":memory:")
    return db


@pytest.fixture
def tracker(config, database):
    """Create transaction cost tracker."""
    return TransactionCostTracker(config=config, database=database)


def test_calculate_trade_cost_basic(tracker):
    """Test basic trade cost calculation."""
    costs = tracker.calculate_trade_cost(
        symbol="AAPL",
        quantity=100,
        price=150.0
    )
    
    assert 'commission' in costs
    assert 'slippage' in costs
    assert 'spread' in costs
    assert 'total' in costs
    assert 'total_percent' in costs
    
    # Verify total is sum of components
    assert costs['total'] == costs['commission'] + costs['slippage'] + costs['spread']
    
    # Verify costs are positive
    assert costs['total'] > 0


def test_calculate_trade_cost_with_filled_price(tracker):
    """Test cost calculation with actual filled price."""
    costs = tracker.calculate_trade_cost(
        symbol="AAPL",
        quantity=100,
        price=150.0,
        filled_price=150.50  # Slippage of $0.50
    )
    
    # Slippage should be calculated from price difference
    expected_slippage = abs(150.50 - 150.0) * 100
    assert costs['slippage'] == expected_slippage


def test_calculate_trade_cost_commission(tracker):
    """Test commission calculation."""
    quantity = 100
    price = 150.0
    trade_value = quantity * price
    
    costs = tracker.calculate_trade_cost(
        symbol="AAPL",
        quantity=quantity,
        price=price
    )
    
    # Commission should be per-share + percentage
    expected_commission = (quantity * 0.005) + (trade_value * 0.001)
    assert costs['commission'] == pytest.approx(expected_commission)


def test_transaction_costs_dataclass():
    """Test TransactionCosts dataclass."""
    costs = TransactionCosts(
        commission=10.0,
        slippage=5.0,
        spread=2.0,
        total=17.0,
        trade_count=5
    )
    
    # Test to_dict
    costs_dict = costs.to_dict()
    assert costs_dict['commission'] == 10.0
    assert costs_dict['slippage'] == 5.0
    assert costs_dict['spread'] == 2.0
    assert costs_dict['total'] == 17.0
    assert costs_dict['trade_count'] == 5
    assert costs_dict['avg_cost_per_trade'] == 17.0 / 5


def test_transaction_costs_zero_trades():
    """Test TransactionCosts with zero trades."""
    costs = TransactionCosts(
        commission=0.0,
        slippage=0.0,
        spread=0.0,
        total=0.0,
        trade_count=0
    )
    
    costs_dict = costs.to_dict()
    assert costs_dict['avg_cost_per_trade'] == 0


def test_cost_comparison_dataclass():
    """Test CostComparison dataclass."""
    before = TransactionCosts(100.0, 50.0, 20.0, 170.0, 10)
    after = TransactionCosts(40.0, 20.0, 8.0, 68.0, 4)
    
    comparison = CostComparison(
        before_costs=before,
        after_costs=after,
        savings=102.0,
        savings_percent=60.0
    )
    
    # Test to_dict
    comp_dict = comparison.to_dict()
    assert 'before' in comp_dict
    assert 'after' in comp_dict
    assert comp_dict['savings'] == 102.0
    assert comp_dict['savings_percent'] == 60.0


def test_get_period_costs_empty(tracker):
    """Test getting costs for period with no trades."""
    costs = tracker.get_period_costs()
    
    assert costs.commission == 0.0
    assert costs.slippage == 0.0
    assert costs.spread == 0.0
    assert costs.total == 0.0
    assert costs.trade_count == 0


def test_calculate_cost_as_percent_of_returns_no_data(tracker):
    """Test cost as % of returns with no data."""
    result = tracker.calculate_cost_as_percent_of_returns()
    
    assert result['total_pnl'] == 0.0
    assert result['cost_as_percent_of_returns'] == 0.0
    assert result['positions_closed'] == 0


def test_compare_periods(tracker):
    """Test comparing costs between periods."""
    now = datetime.now()
    
    # Define periods
    before_start = now - timedelta(days=60)
    before_end = now - timedelta(days=30)
    after_start = now - timedelta(days=29)
    after_end = now
    
    # Compare (will be empty but should work)
    comparison = tracker.compare_periods(
        before_start, before_end,
        after_start, after_end
    )
    
    assert isinstance(comparison, CostComparison)
    assert comparison.before_costs.trade_count == 0
    assert comparison.after_costs.trade_count == 0
    assert comparison.savings == 0.0


def test_get_monthly_report(tracker):
    """Test monthly report generation."""
    report = tracker.get_monthly_report(2024, 1)
    
    assert 'period' in report
    assert report['period'] == "2024-01"
    assert 'start_date' in report
    assert 'end_date' in report
    assert 'costs' in report
    assert 'total_pnl' in report
    assert 'cost_as_percent_of_returns' in report


def test_config_values_used(config, database):
    """Test that config values are properly used."""
    tracker = TransactionCostTracker(config=config, database=database)
    
    assert tracker.commission_per_share == 0.005
    assert tracker.commission_percent == 0.001
    assert tracker.slippage_percent == 0.0005
    assert tracker.spread_percent == 0.0002


def test_large_trade_costs(tracker):
    """Test costs for large trade."""
    costs = tracker.calculate_trade_cost(
        symbol="AAPL",
        quantity=10000,
        price=150.0
    )
    
    # Large trade should have proportionally larger costs
    assert costs['total'] > 100  # Should be significant
    assert costs['total_percent'] > 0


def test_small_trade_costs(tracker):
    """Test costs for small trade."""
    costs = tracker.calculate_trade_cost(
        symbol="AAPL",
        quantity=1,
        price=150.0
    )
    
    # Small trade should have minimal costs
    assert costs['total'] > 0
    assert costs['total'] < 1  # Should be less than $1
