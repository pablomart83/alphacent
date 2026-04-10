"""Tests for TradeFrequencyLimiter."""

import pytest
from datetime import datetime, timedelta
from src.strategy.trade_frequency_limiter import TradeFrequencyLimiter, TradeFrequencyCheck
from src.models.strategy import Strategy, TradingSignal
from src.models.enums import StrategyStatus, StrategyType, SignalAction
from src.models.database import Database


@pytest.fixture
def config():
    """Test configuration."""
    return {
        'alpha_edge': {
            'min_holding_period_days': 7,
            'max_trades_per_strategy_per_month': 4
        }
    }


@pytest.fixture
def database():
    """Create in-memory test database."""
    db = Database(":memory:")
    return db


@pytest.fixture
def limiter(config, database):
    """Create trade frequency limiter."""
    return TradeFrequencyLimiter(config=config, database=database)


@pytest.fixture
def sample_strategy():
    """Create sample strategy."""
    return Strategy(
        id="test-strategy",
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.ACTIVE,
        strategy_type=StrategyType.MEAN_REVERSION,
        entry_conditions=["RSI < 30"],
        exit_conditions=["RSI > 70"],
        symbols=["AAPL"],
        created_at=datetime.now()
    )


@pytest.fixture
def sample_signal():
    """Create sample signal."""
    return TradingSignal(
        strategy_id="test-strategy",
        symbol="AAPL",
        signal_type=SignalAction.BUY,
        confidence=0.8,
        reason="RSI oversold",
        generated_at=datetime.now()
    )


def test_first_signal_allowed(limiter, sample_signal, sample_strategy):
    """Test that first signal is always allowed."""
    check = limiter.check_signal_allowed(sample_signal, sample_strategy)
    
    assert isinstance(check, TradeFrequencyCheck)
    assert check.allowed is True
    assert check.trades_this_month == 0
    assert check.days_since_last_trade is None


def test_monthly_limit_enforcement(limiter, sample_signal, sample_strategy):
    """Test monthly trade limit enforcement."""
    # Record 4 trades (the limit)
    for i in range(4):
        limiter.record_trade(sample_strategy.id, f"SYMBOL{i}")
    
    # 5th signal should be rejected
    check = limiter.check_signal_allowed(sample_signal, sample_strategy)
    
    assert check.allowed is False
    assert "Monthly trade limit reached" in check.reason
    assert check.trades_this_month == 4


def test_minimum_holding_period_enforcement(limiter, sample_signal, sample_strategy):
    """Test minimum holding period enforcement."""
    # Record a trade 3 days ago
    three_days_ago = datetime.now() - timedelta(days=3)
    limiter.record_trade(sample_strategy.id, "AAPL", three_days_ago)
    
    # New signal should be rejected (need 7 days)
    check = limiter.check_signal_allowed(sample_signal, sample_strategy)
    
    assert check.allowed is False
    assert "Minimum holding period not met" in check.reason
    assert check.days_since_last_trade is not None
    assert check.days_since_last_trade < 7


def test_signal_allowed_after_holding_period(limiter, sample_signal, sample_strategy):
    """Test signal allowed after holding period."""
    # Record a trade 8 days ago
    eight_days_ago = datetime.now() - timedelta(days=8)
    limiter.record_trade(sample_strategy.id, "AAPL", eight_days_ago)
    
    # New signal should be allowed
    check = limiter.check_signal_allowed(sample_signal, sample_strategy)
    
    assert check.allowed is True
    assert check.days_since_last_trade >= 7


def test_record_trade_updates_cache(limiter, sample_strategy):
    """Test that recording trades updates cache."""
    # Record 2 trades
    limiter.record_trade(sample_strategy.id, "AAPL")
    limiter.record_trade(sample_strategy.id, "MSFT")
    
    # Check cache
    month_key = datetime.now().strftime('%Y-%m')
    assert sample_strategy.id in limiter._trade_count_cache
    assert month_key in limiter._trade_count_cache[sample_strategy.id]
    assert limiter._trade_count_cache[sample_strategy.id][month_key] == 2


def test_get_strategy_stats(limiter, sample_strategy):
    """Test getting strategy statistics."""
    # Record 2 trades
    limiter.record_trade(sample_strategy.id, "AAPL")
    limiter.record_trade(sample_strategy.id, "MSFT")
    
    stats = limiter.get_strategy_stats(sample_strategy.id)
    
    assert stats['trades_this_month'] == 2
    assert stats['max_trades_per_month'] == 4
    assert stats['trades_remaining'] == 2
    assert stats['can_trade_now'] is True


def test_clear_cache(limiter, sample_strategy):
    """Test cache clearing."""
    # Record a trade
    limiter.record_trade(sample_strategy.id, "AAPL")
    
    # Verify cache has data
    assert len(limiter._trade_count_cache) > 0
    
    # Clear cache
    limiter.clear_cache()
    
    # Verify cache is empty
    assert len(limiter._trade_count_cache) == 0
    assert len(limiter._last_trade_cache) == 0


def test_multiple_strategies_independent(limiter):
    """Test that different strategies are tracked independently."""
    strategy1_id = "strategy-1"
    strategy2_id = "strategy-2"
    
    # Record 4 trades for strategy 1
    for i in range(4):
        limiter.record_trade(strategy1_id, f"SYMBOL{i}")
    
    # Record 1 trade for strategy 2
    limiter.record_trade(strategy2_id, "AAPL")
    
    # Strategy 1 should be at limit
    stats1 = limiter.get_strategy_stats(strategy1_id)
    assert stats1['trades_this_month'] == 4
    assert stats1['trades_remaining'] == 0
    
    # Strategy 2 should have room
    stats2 = limiter.get_strategy_stats(strategy2_id)
    assert stats2['trades_this_month'] == 1
    assert stats2['trades_remaining'] == 3


def test_config_values_used(config, database):
    """Test that config values are properly used."""
    limiter = TradeFrequencyLimiter(config=config, database=database)
    
    assert limiter.min_holding_period_days == 7
    assert limiter.max_trades_per_strategy_per_month == 4
    
    # Test with different config
    config2 = {
        'alpha_edge': {
            'min_holding_period_days': 14,
            'max_trades_per_strategy_per_month': 2
        }
    }
    limiter2 = TradeFrequencyLimiter(config=config2, database=database)
    
    assert limiter2.min_holding_period_days == 14
    assert limiter2.max_trades_per_strategy_per_month == 2
