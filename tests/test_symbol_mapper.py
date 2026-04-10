"""Tests for symbol mapper utility."""

import pytest
from src.utils.symbol_mapper import (
    normalize_symbol,
    get_display_symbol,
    add_alias,
    get_all_aliases,
    to_yahoo_ticker,
    SYMBOL_ALIASES
)


class TestSymbolMapper:
    """Test symbol mapping functionality."""
    
    def test_normalize_crypto_symbols(self):
        """Test normalization of cryptocurrency symbols."""
        assert normalize_symbol("BTC") == "BTCUSD"
        assert normalize_symbol("btc") == "BTCUSD"
        assert normalize_symbol("ETH") == "ETHUSD"
        assert normalize_symbol("eth") == "ETHUSD"
        assert normalize_symbol("DOGE") == "DOGEUSD"
    
    def test_normalize_already_normalized(self):
        """Test that already normalized symbols pass through."""
        assert normalize_symbol("BTCUSD") == "BTCUSD"
        assert normalize_symbol("ETHUSD") == "ETHUSD"
    
    def test_normalize_stock_symbols(self):
        """Test that stock symbols pass through unchanged."""
        assert normalize_symbol("AAPL") == "AAPL"
        assert normalize_symbol("MSFT") == "MSFT"
        assert normalize_symbol("GOOGL") == "GOOGL"
    
    def test_normalize_case_insensitive(self):
        """Test case-insensitive normalization."""
        assert normalize_symbol("btc") == "BTCUSD"
        assert normalize_symbol("BTC") == "BTCUSD"
        assert normalize_symbol("Btc") == "BTCUSD"
    
    def test_normalize_with_whitespace(self):
        """Test normalization handles whitespace."""
        assert normalize_symbol(" BTC ") == "BTCUSD"
        assert normalize_symbol("  eth  ") == "ETHUSD"
    
    def test_get_display_symbol(self):
        """Test getting user-friendly display symbols."""
        assert get_display_symbol("BTCUSD") == "BTC"
        assert get_display_symbol("ETHUSD") == "ETH"
        assert get_display_symbol("DOGEUSD") == "DOGE"
    
    def test_get_display_symbol_no_alias(self):
        """Test display symbol for symbols without aliases."""
        assert get_display_symbol("AAPL") == "AAPL"
        assert get_display_symbol("MSFT") == "MSFT"
    
    def test_add_custom_alias(self):
        """Test adding custom aliases at runtime."""
        # Add a custom alias
        add_alias("TEST", "TESTUSD")
        
        # Verify it works
        assert normalize_symbol("TEST") == "TESTUSD"
        assert get_display_symbol("TESTUSD") == "TEST"
    
    def test_get_all_aliases(self):
        """Test getting all aliases."""
        aliases = get_all_aliases()
        
        # Should be a dictionary
        assert isinstance(aliases, dict)
        
        # Should contain known aliases
        assert "BTC" in aliases
        assert aliases["BTC"] == "BTCUSD"
        assert "ETH" in aliases
        assert aliases["ETH"] == "ETHUSD"
    
    def test_forex_aliases(self):
        """Test forex symbol aliases."""
        assert normalize_symbol("EUR") == "EURUSD"
        assert normalize_symbol("GBP") == "GBPUSD"
        assert normalize_symbol("JPY") == "USDJPY"
    
    def test_commodity_aliases(self):
        """Test commodity symbols pass through unchanged (they're eToro native names)."""
        # GOLD, SILVER, OIL are eToro's native names — no alias needed
        assert normalize_symbol("GOLD") == "GOLD"
        assert normalize_symbol("SILVER") == "SILVER"
        assert normalize_symbol("OIL") == "OIL"

    def test_to_yahoo_ticker_crypto(self):
        """Test Yahoo Finance ticker mapping for crypto."""
        assert to_yahoo_ticker("BTC") == "BTC-USD"
        assert to_yahoo_ticker("ETH") == "ETH-USD"
        assert to_yahoo_ticker("SOL") == "SOL-USD"
        assert to_yahoo_ticker("BTCUSD") == "BTC-USD"

    def test_to_yahoo_ticker_indices(self):
        """Test Yahoo Finance ticker mapping for indices."""
        assert to_yahoo_ticker("SPX500") == "^GSPC"
        assert to_yahoo_ticker("NSDQ100") == "^NDX"
        assert to_yahoo_ticker("DJ30") == "^DJI"

    def test_to_yahoo_ticker_commodities(self):
        """Test Yahoo Finance ticker mapping for commodities."""
        assert to_yahoo_ticker("GOLD") == "GC=F"
        assert to_yahoo_ticker("OIL") == "CL=F"

    def test_to_yahoo_ticker_forex(self):
        """Test Yahoo Finance ticker mapping for forex."""
        assert to_yahoo_ticker("EURUSD") == "EURUSD=X"

    def test_to_yahoo_ticker_stocks_passthrough(self):
        """Test that stock symbols pass through unchanged."""
        assert to_yahoo_ticker("AAPL") == "AAPL"
        assert to_yahoo_ticker("MSFT") == "MSFT"
