"""Integration tests for symbol mapping in market data manager."""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from src.data.market_data_manager import MarketDataManager
from src.models import MarketData, DataSource


class TestMarketDataSymbolMapping:
    """Test symbol mapping integration with market data manager."""
    
    @pytest.fixture
    def mock_etoro_client(self):
        """Create a mock eToro client."""
        client = Mock()
        return client
    
    @pytest.fixture
    def manager(self, mock_etoro_client):
        """Create a market data manager with mock client."""
        return MarketDataManager(mock_etoro_client, cache_ttl=60)
    
    def test_get_quote_with_friendly_symbol(self, manager, mock_etoro_client):
        """Test getting quote with user-friendly symbol like 'BTC'."""
        # Setup mock to return data for BTCUSD
        mock_data = MarketData(
            symbol="BTCUSD",
            timestamp=datetime.now(),
            open=50000.0,
            high=51000.0,
            low=49000.0,
            close=50500.0,
            volume=1000000.0,
            source=DataSource.ETORO
        )
        mock_etoro_client.get_market_data.return_value = mock_data
        
        # Request with friendly symbol "BTC"
        result = manager.get_quote("BTC", use_cache=False)
        
        # Should call eToro API with normalized symbol "BTCUSD"
        mock_etoro_client.get_market_data.assert_called_once_with("BTCUSD", timeframe="1m")
        
        # Should return the data
        assert result.symbol == "BTCUSD"
        assert result.close == 50500.0
    
    def test_get_quote_with_etoro_format(self, manager, mock_etoro_client):
        """Test getting quote with eToro format still works."""
        # Setup mock
        mock_data = MarketData(
            symbol="BTCUSD",
            timestamp=datetime.now(),
            open=50000.0,
            high=51000.0,
            low=49000.0,
            close=50500.0,
            volume=1000000.0,
            source=DataSource.ETORO
        )
        mock_etoro_client.get_market_data.return_value = mock_data
        
        # Request with eToro format "BTCUSD"
        result = manager.get_quote("BTCUSD", use_cache=False)
        
        # Should call eToro API with same symbol
        mock_etoro_client.get_market_data.assert_called_once_with("BTCUSD", timeframe="1m")
        
        # Should return the data
        assert result.symbol == "BTCUSD"
        assert result.close == 50500.0
    
    def test_get_quote_case_insensitive(self, manager, mock_etoro_client):
        """Test symbol mapping is case-insensitive."""
        # Setup mock
        mock_data = MarketData(
            symbol="ETHUSD",
            timestamp=datetime.now(),
            open=3000.0,
            high=3100.0,
            low=2900.0,
            close=3050.0,
            volume=500000.0,
            source=DataSource.ETORO
        )
        mock_etoro_client.get_market_data.return_value = mock_data
        
        # Request with lowercase
        result = manager.get_quote("eth", use_cache=False)
        
        # Should normalize to ETHUSD
        mock_etoro_client.get_market_data.assert_called_once_with("ETHUSD", timeframe="1m")
        assert result.symbol == "ETHUSD"
    
    def test_get_quote_stock_symbol_unchanged(self, manager, mock_etoro_client):
        """Test stock symbols pass through unchanged."""
        # Setup mock
        mock_data = MarketData(
            symbol="AAPL",
            timestamp=datetime.now(),
            open=150.0,
            high=152.0,
            low=149.0,
            close=151.0,
            volume=1000000.0,
            source=DataSource.ETORO
        )
        mock_etoro_client.get_market_data.return_value = mock_data
        
        # Request with stock symbol
        result = manager.get_quote("AAPL", use_cache=False)
        
        # Should pass through unchanged
        mock_etoro_client.get_market_data.assert_called_once_with("AAPL", timeframe="1m")
        assert result.symbol == "AAPL"
    
    def test_cache_uses_normalized_symbol(self, manager, mock_etoro_client):
        """Test cache uses normalized symbol as key."""
        # Setup mock
        mock_data = MarketData(
            symbol="BTCUSD",
            timestamp=datetime.now(),
            open=50000.0,
            high=51000.0,
            low=49000.0,
            close=50500.0,
            volume=1000000.0,
            source=DataSource.ETORO
        )
        mock_etoro_client.get_market_data.return_value = mock_data
        
        # First request with "BTC"
        result1 = manager.get_quote("BTC", use_cache=True)
        assert mock_etoro_client.get_market_data.call_count == 1
        
        # Second request with "BTCUSD" should hit cache
        result2 = manager.get_quote("BTCUSD", use_cache=True)
        assert mock_etoro_client.get_market_data.call_count == 1  # Still 1, used cache
        
        # Both should return same data
        assert result1.close == result2.close
    
    def test_get_historical_data_with_friendly_symbol(self, manager, mock_etoro_client):
        """Test getting historical data with friendly symbol."""
        # Setup mock
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 2)
        mock_data = [
            MarketData(
                symbol="BTCUSD",
                timestamp=datetime(2024, 1, 1, 12, 0),
                open=50000.0,
                high=51000.0,
                low=49000.0,
                close=50500.0,
                volume=1000000.0,
                source=DataSource.ETORO
            )
        ]
        mock_etoro_client.get_historical_data.return_value = mock_data
        
        # Request with friendly symbol
        result = manager.get_historical_data("BTC", start, end, "1d")
        
        # Should call with normalized symbol
        mock_etoro_client.get_historical_data.assert_called_once_with("BTCUSD", start, end, "1d")
        
        # Should return the data
        assert len(result) == 1
        assert result[0].symbol == "BTCUSD"
