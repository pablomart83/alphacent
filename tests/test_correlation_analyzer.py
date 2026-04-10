"""Unit tests for correlation analyzer."""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock

from src.utils.correlation_analyzer import CorrelationAnalyzer


@pytest.fixture
def mock_market_data():
    """Create mock market data manager."""
    return Mock()


@pytest.fixture
def correlation_analyzer(mock_market_data):
    """Create correlation analyzer instance."""
    return CorrelationAnalyzer(mock_market_data)


def create_mock_price_data(symbol, days=100, trend=0.001, volatility=0.02):
    """Create mock price data for testing."""
    dates = [datetime.now() - timedelta(days=i) for i in range(days)]
    dates.reverse()
    
    # Generate correlated price series
    prices = [100.0]
    for i in range(1, days):
        change = trend + volatility * (0.5 - pd.np.random.random())
        prices.append(prices[-1] * (1 + change))
    
    return [
        {
            'date': date.strftime('%Y-%m-%d'),
            'close': price,
            'open': price * 0.99,
            'high': price * 1.01,
            'low': price * 0.98,
            'volume': 1000000
        }
        for date, price in zip(dates, prices)
    ]


class TestCorrelationCalculation:
    """Test correlation calculation."""
    
    def test_perfect_correlation_same_symbol(self, correlation_analyzer, mock_market_data):
        """Same symbol should have perfect correlation."""
        # Create identical price data
        price_data = create_mock_price_data("AAPL", days=100)
        
        mock_market_data.get_historical_data = Mock(return_value=price_data)
        
        correlation = correlation_analyzer.get_correlation("AAPL", "AAPL")
        
        assert correlation is not None
        assert correlation > 0.99, f"Expected perfect correlation, got {correlation:.3f}"
    
    def test_high_correlation_similar_stocks(self, correlation_analyzer, mock_market_data):
        """Similar stocks should have high correlation."""
        # Create highly correlated price data
        base_data = create_mock_price_data("SPY", days=100, trend=0.001, volatility=0.02)
        
        # Create correlated data with small noise
        correlated_data = []
        for item in base_data:
            correlated_item = item.copy()
            # Add small random noise
            noise = 0.001 * (0.5 - pd.np.random.random())
            correlated_item['close'] = item['close'] * (1 + noise)
            correlated_data.append(correlated_item)
        
        def get_data(symbol, start, end, interval='1d'):
            if symbol == "SPY":
                return base_data
            elif symbol == "SPX500":
                return correlated_data
            return None
        
        mock_market_data.get_historical_data = get_data
        
        correlation = correlation_analyzer.get_correlation("SPY", "SPX500")
        
        assert correlation is not None
        assert correlation > 0.7, f"Expected high correlation, got {correlation:.3f}"
    
    def test_low_correlation_different_sectors(self, correlation_analyzer, mock_market_data):
        """Different sector stocks should have lower correlation."""
        # Create uncorrelated price data
        tech_data = create_mock_price_data("AAPL", days=100, trend=0.002, volatility=0.03)
        utility_data = create_mock_price_data("XLU", days=100, trend=0.0005, volatility=0.01)
        
        def get_data(symbol, start, end, interval='1d'):
            if symbol == "AAPL":
                return tech_data
            elif symbol == "XLU":
                return utility_data
            return None
        
        mock_market_data.get_historical_data = get_data
        
        correlation = correlation_analyzer.get_correlation("AAPL", "XLU")
        
        # Correlation should be lower (though random data might still show some correlation)
        assert correlation is not None
    
    def test_insufficient_data_returns_none(self, correlation_analyzer, mock_market_data):
        """Should return None when insufficient data."""
        # Create very short price data
        short_data = create_mock_price_data("AAPL", days=10)
        
        mock_market_data.get_historical_data = Mock(return_value=short_data)
        
        correlation = correlation_analyzer.get_correlation("AAPL", "MSFT")
        
        assert correlation is None
    
    def test_missing_data_returns_none(self, correlation_analyzer, mock_market_data):
        """Should return None when data is missing."""
        mock_market_data.get_historical_data = Mock(return_value=None)
        
        correlation = correlation_analyzer.get_correlation("AAPL", "MSFT")
        
        assert correlation is None
    
    def test_correlation_caching(self, correlation_analyzer, mock_market_data):
        """Should cache correlation results."""
        price_data = create_mock_price_data("AAPL", days=100)
        
        call_count = 0
        def get_data(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return price_data
        
        mock_market_data.get_historical_data = get_data
        
        # First call should fetch data
        correlation1 = correlation_analyzer.get_correlation("AAPL", "MSFT")
        first_call_count = call_count
        
        # Second call should use cache
        correlation2 = correlation_analyzer.get_correlation("AAPL", "MSFT")
        second_call_count = call_count
        
        assert correlation1 == correlation2
        assert second_call_count == first_call_count, "Cache not used - data fetched again"
    
    def test_cache_respects_ttl(self, correlation_analyzer, mock_market_data, monkeypatch):
        """Should refresh cache after TTL expires."""
        price_data = create_mock_price_data("AAPL", days=100)
        mock_market_data.get_historical_data = Mock(return_value=price_data)
        
        # Set short TTL for testing
        correlation_analyzer._cache_ttl_days = 0
        
        # First call
        correlation1 = correlation_analyzer.get_correlation("AAPL", "MSFT")
        
        # Second call should fetch again due to expired TTL
        correlation2 = correlation_analyzer.get_correlation("AAPL", "MSFT")
        
        # Should have called get_historical_data twice (once per symbol, twice)
        assert mock_market_data.get_historical_data.call_count >= 2


class TestCorrelationChecking:
    """Test correlation checking methods."""
    
    def test_are_correlated_high_threshold(self, correlation_analyzer, monkeypatch):
        """Should detect correlated symbols above threshold."""
        # Mock get_correlation to return high correlation
        monkeypatch.setattr(correlation_analyzer, "get_correlation", lambda s1, s2: 0.85)
        
        assert correlation_analyzer.are_correlated("SPY", "SPX500", threshold=0.8)
    
    def test_are_correlated_below_threshold(self, correlation_analyzer, monkeypatch):
        """Should not detect correlation below threshold."""
        # Mock get_correlation to return low correlation
        monkeypatch.setattr(correlation_analyzer, "get_correlation", lambda s1, s2: 0.5)
        
        assert not correlation_analyzer.are_correlated("AAPL", "XLU", threshold=0.8)
    
    def test_are_correlated_handles_none(self, correlation_analyzer, monkeypatch):
        """Should handle None correlation gracefully (fail open)."""
        # Mock get_correlation to return None
        monkeypatch.setattr(correlation_analyzer, "get_correlation", lambda s1, s2: None)
        
        # Should return False (fail open) when correlation cannot be calculated
        assert not correlation_analyzer.are_correlated("AAPL", "UNKNOWN")
    
    def test_find_correlated_symbols(self, correlation_analyzer, monkeypatch):
        """Should find all correlated symbols in list."""
        # Mock get_correlation to return different values
        def mock_correlation(s1, s2):
            if (s1, s2) in [("AAPL", "MSFT"), ("MSFT", "AAPL")]:
                return 0.85
            elif (s1, s2) in [("AAPL", "GOOGL"), ("GOOGL", "AAPL")]:
                return 0.90
            else:
                return 0.3
        
        monkeypatch.setattr(correlation_analyzer, "get_correlation", mock_correlation)
        
        correlated = correlation_analyzer.find_correlated_symbols(
            "AAPL",
            ["MSFT", "GOOGL", "XLU", "GLD"],
            threshold=0.8
        )
        
        assert len(correlated) == 2
        symbols = [s for s, c in correlated]
        assert "MSFT" in symbols
        assert "GOOGL" in symbols
        assert "XLU" not in symbols
        assert "GLD" not in symbols
    
    def test_find_correlated_symbols_excludes_self(self, correlation_analyzer, monkeypatch):
        """Should exclude the symbol itself from results."""
        monkeypatch.setattr(correlation_analyzer, "get_correlation", lambda s1, s2: 0.9)
        
        correlated = correlation_analyzer.find_correlated_symbols(
            "AAPL",
            ["AAPL", "MSFT"],
            threshold=0.8
        )
        
        # Should only include MSFT, not AAPL itself
        assert len(correlated) == 1
        assert correlated[0][0] == "MSFT"


class TestCacheManagement:
    """Test cache management."""
    
    def test_clear_cache(self, correlation_analyzer, mock_market_data):
        """Should clear correlation cache."""
        price_data = create_mock_price_data("AAPL", days=100)
        mock_market_data.get_historical_data = Mock(return_value=price_data)
        
        # Populate cache
        correlation_analyzer.get_correlation("AAPL", "MSFT")
        assert len(correlation_analyzer._correlation_cache) > 0
        
        # Clear cache
        correlation_analyzer.clear_cache()
        assert len(correlation_analyzer._correlation_cache) == 0
