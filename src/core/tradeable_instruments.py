"""Tradeable instruments — thin wrapper around SymbolRegistry.

All symbol data lives in config/symbols.yaml.
This module provides backward-compatible list exports for existing code.
"""

from typing import List
from src.models.enums import TradingMode
from src.core.symbol_registry import get_registry

# ============================================================
# Backward-compatible list exports
# These are properties that lazily load from the registry.
# Existing code that does `from tradeable_instruments import DEMO_ALLOWED_STOCKS`
# will get the list from symbols.yaml.
# ============================================================


def _reg():
    return get_registry()


class _LazyList:
    """Descriptor that loads from registry on first access."""
    def __init__(self, attr):
        self._attr = attr
        self._cache = None

    def __iter__(self):
        return iter(self._get())

    def __contains__(self, item):
        return item in self._get()

    def __len__(self):
        return len(self._get())

    def __getitem__(self, idx):
        return self._get()[idx]

    def __add__(self, other):
        return self._get() + list(other)

    def __radd__(self, other):
        return list(other) + self._get()

    def copy(self):
        return self._get().copy()

    def _get(self):
        if self._cache is None:
            self._cache = getattr(_reg(), self._attr)
        return self._cache


DEMO_ALLOWED_STOCKS = _LazyList("stocks")
DEMO_ALLOWED_ETFS = _LazyList("etfs")
DEMO_ALLOWED_FOREX = _LazyList("forex")
DEMO_ALLOWED_INDICES = _LazyList("indices")
DEMO_ALLOWED_COMMODITIES = _LazyList("commodities")
DEMO_ALLOWED_CRYPTO = _LazyList("crypto")


class _AllSymbols(_LazyList):
    def __init__(self):
        super().__init__("all_symbols")


DEMO_ALL_TRADEABLE = _AllSymbols()
LIVE_ALLOWED_STOCKS = DEMO_ALL_TRADEABLE

# Symbols confirmed not available on eToro
SYMBOLS_NOT_ON_ETORO = [
    "NATURALGAS", "WHEAT", "COCOA", "CORN", "SUGAR", "COTTON",
    "PALLADIUM", "ALUMINIUM", "BAE.L", "HACK", "PPA", "SQ",
]


def get_tradeable_symbols(mode: TradingMode) -> List[str]:
    return _reg().all_symbols


def is_tradeable(symbol: str, mode: TradingMode) -> bool:
    return _reg().is_tradeable(symbol)


def get_blocked_reason(symbol: str, mode: TradingMode) -> str:
    symbol = symbol.upper()
    if symbol in SYMBOLS_NOT_ON_ETORO:
        return f"{symbol} is not available on eToro"
    if not is_tradeable(symbol, mode):
        return f"{symbol} is not in the list of verified tradeable instruments"
    return ""


def get_all_tradeable_symbols() -> List[str]:
    return _reg().all_symbols


def get_default_watchlist(mode: TradingMode) -> List[str]:
    return [
        "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META",
        "SPY", "QQQ", "BTC", "ETH", "SOL",
    ]
