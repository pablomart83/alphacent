"""Tests for MarketDataManager."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.api.etoro_client import EToroAPIClient, EToroAPIError
from src.data.market_data_manager import MarketDataManager, MarketDataCache
from src.models import DataSource, MarketData, TradingMode


@pytest.fixture
def mock_etoro_client():
    """Create mock eToro client."""
    client = Mock(spec=EToroAPIClient)
    client.mode = TradingMode.DEMO
    return client


@pytest.fixture
def market_data_manager(mock_etoro_client):
    """Create MarketDataManager with mock client."""
    return MarketDataManager(mock_etoro_client, cache_ttl=60)


@pytest.fixture
def sample_market_data():
    """Create sample market data."""
    return MarketData(
        symbol="AAPL",
        timestamp=datetime.now(),
        open=150.0,
        high=152.0,
        low=149.0,
        close=151.0,
        volume=1000000.0,
        source=DataSource.ETORO
    )


class TestMarketDataCache:
    """Tests for MarketDataCache."""

    def test_cache_miss(self):
        """Test cache returns None for missing key."""
        cache = MarketDataCache(ttl_seconds=60)
        assert cache.get("AAPL") is None

    def test_cache_hit(self, sample_market_data):
        """Test cache returns data for valid key."""
        cache = MarketDataCache(ttl_seconds=60)
        cache.set("AAPL", sample_market_data)
        
        cached = cache.get("AAPL")
        assert cached is not None
        assert cached.symbol == "AAPL"
        assert cached.close == 151.0

    def test_cache_expiration(self, sample_market_data):
        """Test cache expires after TTL."""
        cache = MarketDataCache(ttl_seconds=0)  # Immediate expiration
        cache.set("AAPL", sample_market_data)
        
        # Should be expired immediately
        cached = cache.get("AAPL")
        assert cached is None

    def test_cache_clear(self, sample_market_data):
        """Test cache clear removes all data."""
        cache = MarketDataCache(ttl_seconds=60)
        cache.set("AAPL", sample_market_data)
        cache.set("GOOGL", sample_market_data)
        
        cache.clear()
        
        assert cache.get("AAPL") is None
        assert cache.get("GOOGL") is None

    def test_cache_remove(self, sample_market_data):
        """Test cache remove removes specific key."""
        cache = MarketDataCache(ttl_seconds=60)
        cache.set("AAPL", sample_market_data)
        cache.set("GOOGL", sample_market_data)
        
        cache.remove("AAPL")
        
        assert cache.get("AAPL") is None
        assert cache.get("GOOGL") is not None


class TestMarketDataManager:
    """Tests for MarketDataManager."""

    def test_get_quote_from_etoro(self, market_data_manager, mock_etoro_client, sample_market_data):
        """Test fetching quote from eToro API."""
        mock_etoro_client.get_market_data.return_value = sample_market_data
        
        data = market_data_manager.get_quote("AAPL", use_cache=False)
        
        assert data.symbol == "AAPL"
        assert data.close == 151.0
        assert data.source == DataSource.ETORO
        mock_etoro_client.get_market_data.assert_called_once()

    def test_get_quote_uses_cache(self, market_data_manager, mock_etoro_client, sample_market_data):
        """Test get_quote uses cache on second call."""
        mock_etoro_client.get_market_data.return_value = sample_market_data
        
        # First call - should hit API
        data1 = market_data_manager.get_quote("AAPL")
        assert mock_etoro_client.get_market_data.call_count == 1
        
        # Second call - should use cache
        data2 = market_data_manager.get_quote("AAPL")
        assert mock_etoro_client.get_market_data.call_count == 1  # No additional call
        
        assert data1.symbol == data2.symbol
        assert data1.close == data2.close

    @patch('src.data.market_data_manager.yf.Ticker')
    def test_get_quote_fallback_to_yahoo(self, mock_yf_ticker, market_data_manager, mock_etoro_client):
        """Test fallback to Yahoo Finance when eToro fails."""
        # Make eToro fail
        mock_etoro_client.get_market_data.side_effect = EToroAPIError("API unavailable")
        
        # Mock Yahoo Finance response
        mock_ticker = Mock()
        mock_hist = Mock()
        mock_hist.empty = False
        mock_hist.iloc = [Mock()]
        mock_hist.iloc[-1] = {
            'Open': 150.0,
            'High': 152.0,
            'Low': 149.0,
            'Close': 151.0,
            'Volume': 1000000.0
        }
        mock_ticker.history.return_value = mock_hist
        mock_yf_ticker.return_value = mock_ticker
        
        data = market_data_manager.get_quote("AAPL", use_cache=False)
        
        assert data.symbol == "AAPL"
        assert data.close == 151.0
        assert data.source == DataSource.YAHOO_FINANCE

    def test_get_quote_fails_all_sources(self, market_data_manager, mock_etoro_client):
        """Test error when all sources fail."""
        mock_etoro_client.get_market_data.side_effect = EToroAPIError("API unavailable")
        
        with patch('src.data.market_data_manager.yf.Ticker') as mock_yf:
            mock_yf.side_effect = Exception("Yahoo Finance unavailable")
            
            with pytest.raises(ValueError, match="Failed to fetch market data"):
                market_data_manager.get_quote("AAPL", use_cache=False)

    def test_validate_data_valid(self, market_data_manager, sample_market_data):
        """Test validation passes for valid data."""
        assert market_data_manager.validate_data(sample_market_data) is True

    def test_validate_data_invalid_prices(self, market_data_manager):
        """Test validation fails for invalid prices."""
        invalid_data = MarketData(
            symbol="AAPL",
            timestamp=datetime.now(),
            open=150.0,
            high=140.0,  # High < Low - invalid
            low=149.0,
            close=151.0,
            volume=1000000.0,
            source=DataSource.ETORO
        )
        
        assert market_data_manager.validate_data(invalid_data) is False

    def test_validate_data_negative_price(self, market_data_manager):
        """Test validation fails for negative prices."""
        invalid_data = MarketData(
            symbol="AAPL",
            timestamp=datetime.now(),
            open=-150.0,  # Negative - invalid
            high=152.0,
            low=149.0,
            close=151.0,
            volume=1000000.0,
            source=DataSource.ETORO
        )
        
        assert market_data_manager.validate_data(invalid_data) is False

    def test_validate_data_negative_volume(self, market_data_manager):
        """Test validation fails for negative volume."""
        invalid_data = MarketData(
            symbol="AAPL",
            timestamp=datetime.now(),
            open=150.0,
            high=152.0,
            low=149.0,
            close=151.0,
            volume=-1000000.0,  # Negative - invalid
            source=DataSource.ETORO
        )
        
        assert market_data_manager.validate_data(invalid_data) is False

    def test_get_historical_data_from_etoro(self, market_data_manager, mock_etoro_client, sample_market_data):
        """Test fetching historical data from eToro."""
        mock_etoro_client.get_historical_data.return_value = [sample_market_data]
        
        start = datetime.now() - timedelta(days=30)
        end = datetime.now()
        
        data_list = market_data_manager.get_historical_data("AAPL", start, end)
        
        assert len(data_list) == 1
        assert data_list[0].symbol == "AAPL"
        mock_etoro_client.get_historical_data.assert_called_once()

    @patch('src.data.market_data_manager.yf.Ticker')
    def test_get_historical_data_fallback(self, mock_yf_ticker, market_data_manager, mock_etoro_client):
        """Test historical data fallback to Yahoo Finance."""
        # Make eToro fail
        mock_etoro_client.get_historical_data.side_effect = EToroAPIError("API unavailable")
        
        # Mock Yahoo Finance response
        mock_ticker = Mock()
        mock_hist = Mock()
        mock_hist.empty = False
        
        # Create a mock timestamp with to_pydatetime method
        mock_timestamp = Mock()
        mock_timestamp.to_pydatetime.return_value = datetime.now()
        
        mock_hist.iterrows.return_value = [
            (mock_timestamp, {
                'Open': 150.0,
                'High': 152.0,
                'Low': 149.0,
                'Close': 151.0,
                'Volume': 1000000.0
            })
        ]
        mock_ticker.history.return_value = mock_hist
        mock_yf_ticker.return_value = mock_ticker
        
        start = datetime.now() - timedelta(days=30)
        end = datetime.now()
        
        data_list = market_data_manager.get_historical_data("AAPL", start, end)
        
        assert len(data_list) == 1
        assert data_list[0].source == DataSource.YAHOO_FINANCE

    def test_clear_cache(self, market_data_manager, mock_etoro_client, sample_market_data):
        """Test clearing cache."""
        mock_etoro_client.get_market_data.return_value = sample_market_data
        
        # Populate cache
        market_data_manager.get_quote("AAPL")
        
        # Clear cache
        market_data_manager.clear_cache()
        
        # Next call should hit API again
        mock_etoro_client.get_market_data.reset_mock()
        market_data_manager.get_quote("AAPL")
        assert mock_etoro_client.get_market_data.call_count == 1

    def test_invalidate_symbol(self, market_data_manager, mock_etoro_client, sample_market_data):
        """Test invalidating specific symbol."""
        mock_etoro_client.get_market_data.return_value = sample_market_data
        
        # Populate cache for two symbols
        market_data_manager.get_quote("AAPL")
        market_data_manager.get_quote("GOOGL")
        
        # Invalidate one symbol
        market_data_manager.invalidate_symbol("AAPL")
        
        # AAPL should hit API, GOOGL should use cache
        mock_etoro_client.get_market_data.reset_mock()
        market_data_manager.get_quote("AAPL")
        assert mock_etoro_client.get_market_data.call_count == 1
        
        market_data_manager.get_quote("GOOGL")
        assert mock_etoro_client.get_market_data.call_count == 1  # No additional call
