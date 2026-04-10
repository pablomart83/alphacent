"""Tests for MarketHoursManager."""

import pytest
from datetime import datetime, time

from src.data.market_hours_manager import (
    AssetClass,
    Exchange,
    MarketHours,
    MarketHoursManager
)


@pytest.fixture
def market_hours_manager():
    """Create MarketHoursManager instance."""
    return MarketHoursManager()


class TestMarketHoursManager:
    """Tests for MarketHoursManager."""

    def test_cryptocurrency_always_open(self, market_hours_manager):
        """Test cryptocurrency market is always open (24/7)."""
        # Test various times
        times = [
            datetime(2024, 1, 15, 0, 0),   # Monday midnight
            datetime(2024, 1, 15, 12, 0),  # Monday noon
            datetime(2024, 1, 20, 3, 0),   # Saturday 3am
            datetime(2024, 1, 21, 23, 0),  # Sunday 11pm
        ]
        
        for check_time in times:
            assert market_hours_manager.is_market_open(
                AssetClass.CRYPTOCURRENCY,
                check_time
            ) is True

    def test_stock_market_open_weekday(self, market_hours_manager):
        """Test stock market is open during weekday trading hours."""
        # Tuesday at 10:00 AM ET (during trading hours, not a holiday)
        check_time = datetime(2024, 1, 16, 10, 0)
        
        assert market_hours_manager.is_market_open(
            AssetClass.STOCK,
            check_time
        ) is True

    def test_stock_market_closed_before_open(self, market_hours_manager):
        """Test stock market is closed before opening time."""
        # Tuesday at 9:00 AM ET (before 9:30 AM open)
        check_time = datetime(2024, 1, 16, 9, 0)
        
        assert market_hours_manager.is_market_open(
            AssetClass.STOCK,
            check_time
        ) is False

    def test_stock_market_closed_after_close(self, market_hours_manager):
        """Test stock market is closed after closing time."""
        # Tuesday at 5:00 PM ET (after 4:00 PM close)
        check_time = datetime(2024, 1, 16, 17, 0)
        
        assert market_hours_manager.is_market_open(
            AssetClass.STOCK,
            check_time
        ) is False

    def test_stock_market_closed_weekend(self, market_hours_manager):
        """Test stock market is closed on weekends."""
        # Saturday at 10:00 AM ET
        saturday = datetime(2024, 1, 20, 10, 0)
        assert market_hours_manager.is_market_open(
            AssetClass.STOCK,
            saturday
        ) is False
        
        # Sunday at 10:00 AM ET
        sunday = datetime(2024, 1, 21, 10, 0)
        assert market_hours_manager.is_market_open(
            AssetClass.STOCK,
            sunday
        ) is False

    def test_stock_market_closed_holiday(self, market_hours_manager):
        """Test stock market is closed on holidays."""
        # New Year's Day 2024 (Monday) at 10:00 AM ET
        holiday = datetime(2024, 1, 1, 10, 0)
        
        assert market_hours_manager.is_market_open(
            AssetClass.STOCK,
            holiday
        ) is False

    def test_stock_market_early_close(self, market_hours_manager):
        """Test stock market early close days."""
        # Day after Thanksgiving 2024 at 2:00 PM ET (after 1:00 PM early close)
        early_close = datetime(2024, 11, 29, 14, 0)
        
        assert market_hours_manager.is_market_open(
            AssetClass.STOCK,
            early_close
        ) is False

    def test_stock_market_open_early_close_day_before_close(self, market_hours_manager):
        """Test stock market is open on early close day before 1 PM."""
        # Day after Thanksgiving 2024 at 11:00 AM ET (before 1:00 PM early close)
        early_close = datetime(2024, 11, 29, 11, 0)
        
        assert market_hours_manager.is_market_open(
            AssetClass.STOCK,
            early_close
        ) is True

    def test_etf_market_hours_same_as_stock(self, market_hours_manager):
        """Test ETF market hours are same as stock market."""
        # Tuesday at 10:00 AM ET
        check_time = datetime(2024, 1, 16, 10, 0)
        
        stock_open = market_hours_manager.is_market_open(AssetClass.STOCK, check_time)
        etf_open = market_hours_manager.is_market_open(AssetClass.ETF, check_time)
        
        assert stock_open == etf_open

    def test_is_holiday(self, market_hours_manager):
        """Test holiday detection."""
        # New Year's Day 2024
        holiday = datetime(2024, 1, 1)
        assert market_hours_manager.is_holiday(holiday, Exchange.NYSE) is True
        
        # Regular trading day (Tuesday, not a holiday)
        regular_day = datetime(2024, 1, 16)
        assert market_hours_manager.is_holiday(regular_day, Exchange.NYSE) is False

    def test_is_early_close(self, market_hours_manager):
        """Test early close detection."""
        # Day after Thanksgiving 2024
        early_close = datetime(2024, 11, 29)
        assert market_hours_manager.is_early_close(early_close, Exchange.NYSE) is True
        
        # Regular trading day
        regular_day = datetime(2024, 1, 15)
        assert market_hours_manager.is_early_close(regular_day, Exchange.NYSE) is False

    def test_get_market_hours(self, market_hours_manager):
        """Test getting market hours for asset class."""
        hours = market_hours_manager.get_market_hours(AssetClass.STOCK)
        
        assert hours is not None
        assert hours.exchange == Exchange.NYSE
        assert hours.open_time == time(9, 30)
        assert hours.close_time == time(16, 0)

    def test_get_exchange_for_symbol_crypto(self, market_hours_manager):
        """Test exchange detection for cryptocurrency symbols."""
        crypto_symbols = ["BTC-USD", "ETH-USD", "BTCUSD", "ETHEREUM"]
        
        for symbol in crypto_symbols:
            exchange = market_hours_manager.get_exchange_for_symbol(symbol)
            assert exchange == Exchange.CRYPTO

    def test_get_exchange_for_symbol_stock(self, market_hours_manager):
        """Test exchange detection for stock symbols."""
        stock_symbols = ["AAPL", "GOOGL", "MSFT", "TSLA"]
        
        for symbol in stock_symbols:
            exchange = market_hours_manager.get_exchange_for_symbol(symbol)
            assert exchange == Exchange.NYSE

    def test_get_next_open_time_crypto(self, market_hours_manager):
        """Test next open time for crypto (always now)."""
        check_time = datetime(2024, 1, 20, 3, 0)  # Saturday 3am
        
        next_open = market_hours_manager.get_next_open_time(
            AssetClass.CRYPTOCURRENCY,
            check_time
        )
        
        assert next_open == check_time

    def test_get_next_open_time_stock_during_hours(self, market_hours_manager):
        """Test next open time for stock during trading hours."""
        # Tuesday at 10:00 AM ET (market is open)
        check_time = datetime(2024, 1, 16, 10, 0)
        
        next_open = market_hours_manager.get_next_open_time(
            AssetClass.STOCK,
            check_time
        )
        
        # Should return current time since market is open
        assert next_open == check_time

    def test_get_next_open_time_stock_after_close(self, market_hours_manager):
        """Test next open time for stock after market close."""
        # Tuesday at 5:00 PM ET (after close)
        check_time = datetime(2024, 1, 16, 17, 0)
        
        next_open = market_hours_manager.get_next_open_time(
            AssetClass.STOCK,
            check_time
        )
        
        # Should return next day at 9:30 AM
        assert next_open.day == 17  # Wednesday
        assert next_open.hour == 9
        assert next_open.minute == 30

    def test_market_hours_at_exact_open(self, market_hours_manager):
        """Test market is open at exact opening time."""
        # Tuesday at 9:30 AM ET (exact open)
        check_time = datetime(2024, 1, 16, 9, 30)
        
        assert market_hours_manager.is_market_open(
            AssetClass.STOCK,
            check_time
        ) is True

    def test_market_hours_at_exact_close(self, market_hours_manager):
        """Test market is open at exact closing time."""
        # Tuesday at 4:00 PM ET (exact close)
        check_time = datetime(2024, 1, 16, 16, 0)
        
        assert market_hours_manager.is_market_open(
            AssetClass.STOCK,
            check_time
        ) is True


class TestMarketHours:
    """Tests for MarketHours class."""

    def test_market_hours_creation(self):
        """Test creating MarketHours instance."""
        hours = MarketHours(
            exchange=Exchange.NYSE,
            open_time=time(9, 30),
            close_time=time(16, 0),
            timezone="America/New_York"
        )
        
        assert hours.exchange == Exchange.NYSE
        assert hours.open_time == time(9, 30)
        assert hours.close_time == time(16, 0)
        assert hours.timezone == "America/New_York"
        assert 0 in hours.days_open  # Monday
        assert 4 in hours.days_open  # Friday
        assert 5 not in hours.days_open  # Saturday
        assert 6 not in hours.days_open  # Sunday

    def test_market_hours_custom_days(self):
        """Test MarketHours with custom trading days."""
        # Market open only on Monday, Wednesday, Friday
        hours = MarketHours(
            exchange=Exchange.NYSE,
            open_time=time(9, 30),
            close_time=time(16, 0),
            timezone="America/New_York",
            days_open={0, 2, 4}
        )
        
        assert 0 in hours.days_open  # Monday
        assert 1 not in hours.days_open  # Tuesday
        assert 2 in hours.days_open  # Wednesday
        assert 3 not in hours.days_open  # Thursday
        assert 4 in hours.days_open  # Friday
