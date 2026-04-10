"""Tests for eToro API client."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from src.api import (
    AuthenticationError,
    EToroAPIClient,
    EToroAPIError,
)
from src.models import (
    OrderSide,
    OrderType,
    TradingMode,
)


class TestEToroAPIClient:
    """Tests for EToroAPIClient class."""

    def test_client_initialization(self):
        """Test client initializes correctly."""
        client = EToroAPIClient(
            public_key="test_public",
            user_key="test_user",
            mode=TradingMode.DEMO
        )
        assert client.public_key == "test_public"
        assert client.user_key == "test_user"
        assert client.mode == TradingMode.DEMO
        assert client.BASE_URL == "https://public-api.etoro.com"
        assert client.is_authenticated()  # Header-based auth - always authenticated if keys present

    def test_client_live_mode(self):
        """Test client works in live mode."""
        client = EToroAPIClient(
            public_key="test_public",
            user_key="test_user",
            mode=TradingMode.LIVE
        )
        assert client.mode == TradingMode.LIVE
        assert client.is_authenticated()

    def test_get_headers(self):
        """Test headers include API keys."""
        client = EToroAPIClient("public_key", "user_key", TradingMode.DEMO)
        headers = client._get_headers()
        
        assert "x-api-key" in headers
        assert "x-user-key" in headers
        assert "x-request-id" in headers
        assert headers["x-api-key"] == "public_key"
        assert headers["x-user-key"] == "user_key"
        assert headers["Content-Type"] == "application/json"

    def test_rate_limiting(self):
        """Test rate limiting enforces minimum interval."""
        import time
        client = EToroAPIClient("public", "user", TradingMode.DEMO)
        
        # First call should not sleep
        start = time.time()
        client._enforce_rate_limit()
        first_duration = time.time() - start
        assert first_duration < 0.1  # Should be instant
        
        # Second call immediately after should sleep
        start = time.time()
        client._enforce_rate_limit()
        second_duration = time.time() - start
        assert second_duration >= 0.9  # Should sleep ~1 second

    def test_order_validation_limit_requires_price(self):
        """Test that LIMIT orders require price parameter."""
        client = EToroAPIClient("public", "user", TradingMode.DEMO)
        
        with pytest.raises(ValueError) as exc_info:
            client.place_order(
                symbol="AAPL",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=10.0
                # Missing price parameter
            )
        
        assert "Price required for LIMIT orders" in str(exc_info.value)

    def test_order_validation_stop_loss_requires_stop_price(self):
        """Test that STOP_LOSS orders require stop_price parameter."""
        client = EToroAPIClient("public", "user", TradingMode.DEMO)
        
        with pytest.raises(ValueError) as exc_info:
            client.place_order(
                symbol="AAPL",
                side=OrderSide.SELL,
                order_type=OrderType.STOP_LOSS,
                quantity=10.0
                # Missing stop_price parameter
            )
        
        assert "Stop price required for STOP_LOSS orders" in str(exc_info.value)

    def test_market_data_validation_missing_fields(self):
        """Test market data validation rejects missing fields."""
        client = EToroAPIClient("public", "user", TradingMode.DEMO)
        
        invalid_data = {
            "timestamp": "2024-01-01T00:00:00",
            "open": 100.0,
            "high": 105.0
            # Missing low, close, volume
        }
        
        assert not client._validate_market_data(invalid_data)

    def test_market_data_validation_null_values(self):
        """Test market data validation rejects null values."""
        client = EToroAPIClient("public", "user", TradingMode.DEMO)
        
        invalid_data = {
            "timestamp": "2024-01-01T00:00:00",
            "open": 100.0,
            "high": None,  # Null value
            "low": 95.0,
            "close": 102.0,
            "volume": 1000.0
        }
        
        assert not client._validate_market_data(invalid_data)

    def test_market_data_validation_negative_prices(self):
        """Test market data validation rejects negative prices."""
        client = EToroAPIClient("public", "user", TradingMode.DEMO)
        
        invalid_data = {
            "timestamp": "2024-01-01T00:00:00",
            "open": -100.0,  # Negative price
            "high": 105.0,
            "low": 95.0,
            "close": 102.0,
            "volume": 1000.0
        }
        
        assert not client._validate_market_data(invalid_data)

    def test_market_data_validation_high_less_than_low(self):
        """Test market data validation rejects high < low."""
        client = EToroAPIClient("public", "user", TradingMode.DEMO)
        
        invalid_data = {
            "timestamp": "2024-01-01T00:00:00",
            "open": 100.0,
            "high": 95.0,  # High < low
            "low": 105.0,
            "close": 102.0,
            "volume": 1000.0
        }
        
        assert not client._validate_market_data(invalid_data)

    def test_market_data_validation_valid_data(self):
        """Test market data validation accepts valid data."""
        client = EToroAPIClient("public", "user", TradingMode.DEMO)
        
        valid_data = {
            "timestamp": "2024-01-01T00:00:00",
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 102.0,
            "volume": 1000.0
        }
        
        assert client._validate_market_data(valid_data)

    def test_disconnect(self):
        """Test client disconnect closes session."""
        client = EToroAPIClient("public", "user", TradingMode.DEMO)
        
        # Mock the session
        client._session = Mock()
        
        client.disconnect()
        
        # Verify session was closed
        client._session.close.assert_called_once()
