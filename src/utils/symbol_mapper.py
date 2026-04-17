"""Symbol alias/mapping system for eToro and Yahoo Finance naming conventions.

Maps user-friendly symbols to eToro format and Yahoo Finance tickers.
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# Symbol mapping: user-friendly -> eToro format
SYMBOL_ALIASES: Dict[str, str] = {
    # Cryptocurrencies (removed ARB, OP, RENDER, INJ, SUI, APT - bad Yahoo Finance data)
    "BTC": "BTCUSD",
    "ETH": "ETHUSD",
    "SOL": "SOLUSD",
    "XRP": "XRPUSD",
    "ADA": "ADAUSD",
    "AVAX": "AVAXUSD",
    "DOT": "DOTUSD",
    "LINK": "LINKUSD",
    "NEAR": "NEARUSD",
    "LTC": "LTCUSD",
    "BCH": "BCHUSD",

    # Forex pairs
    "EUR": "EURUSD",
    "GBP": "GBPUSD",
    "JPY": "USDJPY",
}


# Reverse mapping: eToro format -> user-friendly
REVERSE_ALIASES: Dict[str, str] = {v: k for k, v in SYMBOL_ALIASES.items()}


# Yahoo Finance ticker mapping for non-standard symbols
# eToro symbol -> Yahoo Finance ticker
YAHOO_FINANCE_TICKERS: Dict[str, str] = {
    # Crypto (eToro uses BTC/BTCUSD, Yahoo uses BTC-USD)
    # Removed ARB, OP, RENDER, INJ, SUI, APT - terrible Yahoo Finance data quality
    "BTC": "BTC-USD", "BTCUSD": "BTC-USD",
    "ETH": "ETH-USD", "ETHUSD": "ETH-USD",
    "SOL": "SOL-USD", "SOLUSD": "SOL-USD",
    "XRP": "XRP-USD", "XRPUSD": "XRP-USD",
    "ADA": "ADA-USD", "ADAUSD": "ADA-USD",
    "AVAX": "AVAX-USD", "AVAXUSD": "AVAX-USD",
    "DOT": "DOT-USD", "DOTUSD": "DOT-USD",
    "LINK": "LINK-USD", "LINKUSD": "LINK-USD",
    "NEAR": "NEAR-USD", "NEARUSD": "NEAR-USD",
    "LTC": "LTC-USD", "LTCUSD": "LTC-USD",
    "BCH": "BCH-USD", "BCHUSD": "BCH-USD",

    # Indices (eToro names -> Yahoo Finance tickers)
    "SPX500": "^GSPC",
    "NSDQ100": "^NDX",
    "DJ30": "^DJI",
    "UK100": "^FTSE",
    "GER40": "^GDAXI",

    # Commodities (eToro names -> Yahoo Finance tickers)
    "GOLD": "GC=F",
    "SILVER": "SI=F",
    "OIL": "CL=F",
    "COPPER": "HG=F",
    "NATGAS": "NG=F",
    "PLATINUM": "PL=F",
    "ALUMINUM": "ALI=F",
    "ZINC": "ZNC=F",

    # Forex (eToro format -> Yahoo Finance format)
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X",
    "NZDUSD": "NZDUSD=X",
    "EURGBP": "EURGBP=X",
}


# Symbols that only have reliable daily (1d) data on Yahoo Finance.
# Requesting 1h or 4h data for these will fail or return empty results.
# The monitoring service uses this to skip intraday batch downloads for these symbols.
DAILY_ONLY_SYMBOLS = {
    "ZINC",       # ZNC=F — CME zinc futures, no reliable 1h data on Yahoo
    "ALUMINUM",   # ALI=F — CME aluminum futures, thin 1h data
    "PLATINUM",   # PL=F — CME platinum futures, thin 1h data
}


def normalize_symbol(symbol: str) -> str:
    """Normalize symbol to eToro format.
    
    Converts user-friendly symbols to eToro's naming convention.
    If the symbol is already in eToro format or not in the alias map,
    returns it unchanged.
    
    Args:
        symbol: User-provided symbol (e.g., "BTC", "BTCUSD", "AAPL")
        
    Returns:
        eToro-formatted symbol (e.g., "BTCUSD", "BTCUSD", "AAPL")
    """
    symbol_upper = symbol.upper().strip()
    
    if symbol_upper in SYMBOL_ALIASES:
        normalized = SYMBOL_ALIASES[symbol_upper]
        logger.debug(f"Normalized symbol: {symbol} -> {normalized}")
        return normalized
    
    return symbol_upper


def to_yahoo_ticker(symbol: str) -> str:
    """Convert a symbol to its Yahoo Finance ticker format.
    
    Handles crypto (BTC -> BTC-USD), indices (SPX500 -> ^GSPC),
    commodities (GOLD -> GC=F), and forex (EURUSD -> EURUSD=X).
    Stocks and ETFs pass through unchanged.
    
    Args:
        symbol: Symbol in eToro or user-friendly format
        
    Returns:
        Yahoo Finance ticker string
    """
    symbol_upper = symbol.upper().strip()
    
    if symbol_upper in YAHOO_FINANCE_TICKERS:
        yf_ticker = YAHOO_FINANCE_TICKERS[symbol_upper]
        logger.debug(f"Yahoo Finance ticker: {symbol} -> {yf_ticker}")
        return yf_ticker
    
    return symbol_upper


def get_display_symbol(etoro_symbol: str) -> str:
    """Get user-friendly display symbol from eToro format.
    
    Converts eToro symbols back to user-friendly format for display.
    If no alias exists, returns the eToro symbol unchanged.
    
    Args:
        etoro_symbol: eToro-formatted symbol (e.g., "BTCUSD")
        
    Returns:
        User-friendly symbol (e.g., "BTC") or original if no alias
        
    Examples:
        >>> get_display_symbol("BTCUSD")
        "BTC"
        >>> get_display_symbol("AAPL")
        "AAPL"
    """
    etoro_upper = etoro_symbol.upper().strip()
    
    # Check if we have a reverse mapping
    if etoro_upper in REVERSE_ALIASES:
        display = REVERSE_ALIASES[etoro_upper]
        logger.debug(f"Display symbol: {etoro_symbol} -> {display}")
        return display
    
    # Return as-is
    return etoro_upper


def add_alias(user_symbol: str, etoro_symbol: str) -> None:
    """Add a custom symbol alias at runtime.
    
    Allows dynamic addition of symbol mappings.
    
    Args:
        user_symbol: User-friendly symbol
        etoro_symbol: eToro-formatted symbol
    """
    user_upper = user_symbol.upper().strip()
    etoro_upper = etoro_symbol.upper().strip()
    
    SYMBOL_ALIASES[user_upper] = etoro_upper
    REVERSE_ALIASES[etoro_upper] = user_upper
    
    logger.info(f"Added symbol alias: {user_upper} -> {etoro_upper}")


def get_all_aliases() -> Dict[str, str]:
    """Get all symbol aliases.
    
    Returns:
        Dictionary of user-friendly -> eToro format mappings
    """
    return SYMBOL_ALIASES.copy()
