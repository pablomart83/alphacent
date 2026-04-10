"""Tradeable instruments configuration for eToro demo accounts.

Verified against eToro DEMO API on 2026-02-19/20 by placing $10 market orders.
All instrument IDs confirmed via eToro instrumentsmetadata API.
"""

from typing import List, Set
from src.models.enums import TradingMode

# Verified tradeable stocks on eToro DEMO (all confirmed with real orders)
DEMO_ALLOWED_STOCKS = [
    # Tech Giants
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "NFLX",
    "AMD", "INTC", "CSCO", "ADBE", "ORCL", "CRM",
    # Mega-cap tech/growth (expanded)
    "AVGO", "QCOM", "TXN", "MU", "AMAT",
    "NOW", "PANW", "SHOP",
    # Finance
    "JPM", "V", "MA", "PYPL", "COIN",
    # Financial services (expanded)
    "GS", "MS", "BLK", "SCHW", "AXP",
    # Consumer / Industrial
    "WMT", "DIS", "BA", "JNJ", "PG", "UNH", "KO", "PEP", "MCD",
    "NKE", "COST", "HD", "LOW", "TGT", "SBUX", "GE",
    # Healthcare/Pharma (expanded)
    "LLY", "ABBV", "MRK", "PFE", "TMO",
    "ISRG", "DXCM", "MRNA", "AMGN",
    # Energy (expanded)
    "XOM", "CVX", "COP", "SLB",
    # Industrials/Materials (expanded)
    "CAT", "HON", "RTX", "LMT",
    "FDX",  # UPS removed — instrument 1275 flagged untradable on eToro DEMO
    # Consumer/Retail (expanded)
    "LULU", "CMG",
    # Tech / Growth
    "UBER", "ABNB", "SNAP", "PLTR",
    # International
    "BABA",
    # Semiconductors (expanded)
    "TSM", "ASML", "ARM",
    # Defense (expanded)
    "NOC", "GD",
    # Healthcare/Pharma (expanded)
    "NVO", "GILD",
    # High-momentum growth
    "CRWD", "SNOW", "MELI",
    # Mining / Materials
    "NEM", "FCX", "VALE",
    # Utilities (defensive rotation)
    "NEE",
    # Shipping (Hormuz disruption)
    "ZIM",
    # AI infrastructure
    "SMCI", "MRVL",
    # Cybersecurity
    "FTNT",
    # Biotech
    "REGN", "VRTX",
]

# ETFs verified tradeable on eToro DEMO
DEMO_ALLOWED_ETFS = [
    # Broad market / commodity ETFs
    "SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "VTI", "VOO",
    # Sector rotation ETFs (all 8 SPDR sectors available on eToro)
    "XLE", "XLF", "XLK", "XLU", "XLV", "XLI", "XLP", "XLY",
    # Bond ETFs
    "TLT", "HYG",
    # Thematic ETFs (expanded)
    "XHB", "XBI", "ARKK", "ITA", "FXI",
    # Commodity ETFs
    "USO", "UNG", "DBA", "WEAT", "PALL", "URA", "COPX",
]

# Forex pairs verified tradeable on eToro DEMO
DEMO_ALLOWED_FOREX = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF",
    "NZDUSD", "EURGBP",
]

# Indices verified tradeable on eToro DEMO
DEMO_ALLOWED_INDICES = [
    "SPX500", "NSDQ100", "DJ30", "UK100", "GER40",
]

# Commodities verified tradeable on eToro DEMO
DEMO_ALLOWED_COMMODITIES = [
    "GOLD", "SILVER", "OIL", "COPPER",
    "NATGAS", "PLATINUM",
    "ALUMINUM", "ZINC",
]

# Cryptocurrencies verified tradeable on eToro DEMO (2026-02-20)
# Removed ARB, OP, RENDER, INJ, SUI, APT - terrible Yahoo Finance data quality (0/100 scores)
# Removed DOGE - 0/100 data quality score from Yahoo Finance (27 issues)
DEMO_ALLOWED_CRYPTO = [
    "BTC", "ETH", "SOL", "XRP", "ADA", "AVAX", "DOT", "LINK",
    "NEAR", "LTC", "BCH",
]

# Symbols confirmed not available on eToro
SYMBOLS_NOT_ON_ETORO = ["NATURALGAS", "WHEAT", "COCOA", "CORN", "SUGAR", "COTTON", "PALLADIUM", "ALUMINIUM"]

# Combined list of all tradeable symbols
DEMO_ALL_TRADEABLE = (
    DEMO_ALLOWED_STOCKS + DEMO_ALLOWED_ETFS + DEMO_ALLOWED_FOREX +
    DEMO_ALLOWED_INDICES + DEMO_ALLOWED_COMMODITIES + DEMO_ALLOWED_CRYPTO
)

# Live mode - assume all verified symbols are available
LIVE_ALLOWED_STOCKS = DEMO_ALL_TRADEABLE.copy()


def get_tradeable_symbols(mode: TradingMode) -> List[str]:
    """Get list of tradeable symbols for the given trading mode."""
    if mode == TradingMode.DEMO:
        return DEMO_ALL_TRADEABLE.copy()
    else:
        return LIVE_ALLOWED_STOCKS.copy()


def is_tradeable(symbol: str, mode: TradingMode) -> bool:
    """Check if a symbol is tradeable in the given mode."""
    symbol = symbol.upper()
    allowed = get_tradeable_symbols(mode)
    return symbol in allowed


def get_blocked_reason(symbol: str, mode: TradingMode) -> str:
    """Get reason why a symbol is blocked."""
    symbol = symbol.upper()

    if symbol in SYMBOLS_NOT_ON_ETORO:
        return f"{symbol} is not available on eToro"

    if not is_tradeable(symbol, mode):
        return f"{symbol} is not in the list of verified tradeable instruments"

    return ""


def get_all_tradeable_symbols() -> List[str]:
    """Get all tradeable symbols across all asset classes."""
    all_symbols = []
    all_symbols.extend(DEMO_ALLOWED_STOCKS)
    all_symbols.extend(DEMO_ALLOWED_ETFS)
    all_symbols.extend(DEMO_ALLOWED_FOREX)
    all_symbols.extend(DEMO_ALLOWED_INDICES)
    all_symbols.extend(DEMO_ALLOWED_COMMODITIES)
    all_symbols.extend(DEMO_ALLOWED_CRYPTO)
    return all_symbols


def get_default_watchlist(mode: TradingMode) -> List[str]:
    """Get default watchlist for market data dashboard."""
    return [
        "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META",
        "SPY", "QQQ", "BTC", "ETH", "SOL",
    ]
