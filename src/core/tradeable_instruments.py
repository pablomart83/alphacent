"""Tradeable instruments configuration for eToro demo accounts.

Verified against eToro DEMO API on 2026-04-10 by querying instrument IDs.
All instrument IDs confirmed via eToro search API.
Total: ~300 symbols across all asset classes.
"""

from typing import List, Set
from src.models.enums import TradingMode

# ============================================================
# STOCKS (198 total)
# ============================================================
DEMO_ALLOWED_STOCKS = [
    # --- Tech Giants ---
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "NFLX",
    "AMD", "INTC", "CSCO", "ADBE", "ORCL", "CRM",
    # --- Mega-cap tech/growth ---
    "AVGO", "QCOM", "TXN", "MU", "AMAT", "NOW", "PANW", "SHOP",
    # --- AI / Data Center Infrastructure ---
    "APP", "VRT", "DELL", "HPE", "EQIX", "DLR", "GEV", "CEG", "VST",
    # --- Semiconductors ---
    "TSM", "ASML", "ARM", "KLAC", "LRCX", "ON", "NXPI", "MPWR", "ADI", "MCHP",
    # --- AI Infrastructure ---
    "SMCI", "MRVL",
    # --- Software / Cloud ---
    "INTU", "CDNS", "SNPS", "DDOG", "ZS", "NET", "MDB", "TEAM",
    "WDAY", "VEEV", "OKTA", "PATH",
    # --- Cybersecurity ---
    "CRWD", "FTNT",
    # --- Finance ---
    "JPM", "V", "MA", "PYPL", "COIN", "GS", "MS", "BLK", "SCHW", "AXP",
    "C", "BAC", "WFC", "USB", "PNC", "TFC",
    "SPGI", "MCO", "ICE", "CME", "FICO", "GPN",
    # --- Fintech / Payments ---
    "AFRM", "SOFI", "HOOD", "NU", "GRAB",
    # --- Consumer / Retail ---
    "WMT", "DIS", "PG", "KO", "PEP", "MCD", "NKE", "COST", "HD", "LOW",
    "TGT", "SBUX", "LULU", "CMG",
    "TJX", "ROST", "ORLY", "AZO", "MNST", "EL", "CL", "KMB", "CAVA",
    # --- Healthcare / Pharma / Biotech ---
    "JNJ", "UNH", "LLY", "ABBV", "MRK", "PFE", "TMO", "ISRG", "DXCM",
    "MRNA", "AMGN", "NVO", "GILD", "REGN", "VRTX",
    "BMY", "ZTS", "SYK", "BSX", "MDT", "EW", "A", "DHR", "IQV",
    # --- Energy ---
    "XOM", "CVX", "COP", "SLB",
    "LNG", "OKE", "WMB", "KMI", "ET",
    "FANG", "DVN", "EOG", "MPC", "VLO",
    # --- Nuclear / Clean Energy ---
    "CCJ", "UEC", "LEU", "FSLR", "ENPH",
    # --- Defense ---
    "BA", "RTX", "LMT", "NOC", "GD",
    "HII", "LHX", "TDG", "HWM", "LDOS", "BAH",
    # --- Industrials ---
    "CAT", "HON", "GE", "FDX",
    "DE", "EMR", "ETN", "ITW", "PH", "ROK", "GWW", "FAST", "URI",
    # --- Materials / Mining ---
    "NEM", "FCX", "VALE", "BHP", "RIO", "SCCO", "ALB", "MP",
    # --- Utilities ---
    "NEE",
    # --- Telecom / Media ---
    "T", "VZ", "TMUS", "CHTR", "CMCSA",
    # --- REITs ---
    "AMT", "PLD", "CCI", "PSA", "O",
    # --- Autos / EV ---
    "F", "GM", "STLA", "RIVN", "LCID",
    # --- International ---
    "BABA", "SONY", "TM", "SPOT", "SE", "SAP", "GLOB",
    # --- European Defense ---
    "RHM.DE", "RR.L",
    # --- Crypto-Adjacent ---
    "MSTR", "MARA", "RIOT", "HUT",
    # --- Space / Frontier Tech ---
    "RKLB", "ASTS", "LUNR",
    # --- AI Software ---
    "AI", "SOUN", "IONQ", "BBAI",
    # --- High-Momentum Growth ---
    "UBER", "ABNB", "SNAP", "PLTR", "SNOW", "MELI",
    "CPNG", "DASH", "RBLX", "DUOL", "HIMS", "CELH", "ONON",
    # --- Shipping ---
    "ZIM",
]

# ============================================================
# ETFs (42 total)
# ============================================================
DEMO_ALLOWED_ETFS = [
    # Broad market
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO",
    # Precious metals
    "GLD", "SLV",
    # Sector rotation (SPDR)
    "XLE", "XLF", "XLK", "XLU", "XLV", "XLI", "XLP", "XLY",
    # Bonds
    "TLT", "HYG",
    # Thematic
    "XHB", "XBI", "ARKK", "ITA", "FXI",
    # Commodity
    "USO", "UNG", "DBA", "WEAT", "PALL", "URA", "COPX",
    # International
    "EEM", "EWZ", "KWEB",
    # Semiconductor
    "SOXX", "SMH",
    # Cybersecurity
    "CIBR",
    # Leveraged
    "SOXL", "TQQQ", "SQQQ", "SPXU", "UPRO", "DFEN",
]

# ============================================================
# FOREX (8 pairs)
# ============================================================
DEMO_ALLOWED_FOREX = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF",
    "NZDUSD", "EURGBP",
]

# ============================================================
# INDICES (5)
# ============================================================
DEMO_ALLOWED_INDICES = [
    "SPX500", "NSDQ100", "DJ30", "UK100", "GER40",
]

# ============================================================
# COMMODITIES (8)
# ============================================================
DEMO_ALLOWED_COMMODITIES = [
    "GOLD", "SILVER", "OIL", "COPPER",
    "NATGAS", "PLATINUM", "ALUMINUM", "ZINC",
]

# ============================================================
# CRYPTO (11)
# ============================================================
DEMO_ALLOWED_CRYPTO = [
    "BTC", "ETH", "SOL", "XRP", "ADA", "AVAX", "DOT", "LINK",
    "NEAR", "LTC", "BCH",
]

# Symbols confirmed not available on eToro
SYMBOLS_NOT_ON_ETORO = [
    "NATURALGAS", "WHEAT", "COCOA", "CORN", "SUGAR", "COTTON",
    "PALLADIUM", "ALUMINIUM", "BAE.L", "HACK", "PPA", "SQ",
]

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
    return symbol.upper() in get_tradeable_symbols(mode)


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
    return (
        DEMO_ALLOWED_STOCKS + DEMO_ALLOWED_ETFS + DEMO_ALLOWED_FOREX +
        DEMO_ALLOWED_INDICES + DEMO_ALLOWED_COMMODITIES + DEMO_ALLOWED_CRYPTO
    )


def get_default_watchlist(mode: TradingMode) -> List[str]:
    """Get default watchlist for market data dashboard."""
    return [
        "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META",
        "SPY", "QQQ", "BTC", "ETH", "SOL",
    ]
