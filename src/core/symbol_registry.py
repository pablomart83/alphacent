"""
Centralized Symbol Registry — single source of truth for all symbol data.

Loads from config/symbols.yaml and provides:
- Symbol lists by asset class
- eToro instrument ID lookups (both directions)
- Sector mappings
- Asset class classification

All other modules should use this registry instead of hardcoded lists.
"""

import logging
import os
from typing import Dict, List, Optional, Set
import yaml

logger = logging.getLogger(__name__)

# Module-level cache — loaded once, reused everywhere
_registry: Optional["SymbolRegistry"] = None


class SymbolRegistry:
    """Loads symbols.yaml and provides fast lookups."""

    ASSET_CLASSES = ("stocks", "etfs", "forex", "indices", "commodities", "crypto")

    def __init__(self, config_path: str = None):
        if config_path is None:
            # Try multiple paths (local dev vs EC2)
            for p in ["config/symbols.yaml", "/home/ubuntu/alphacent/config/symbols.yaml"]:
                if os.path.exists(p):
                    config_path = p
                    break
        if not config_path or not os.path.exists(config_path):
            raise FileNotFoundError(f"symbols.yaml not found")

        with open(config_path, "r") as f:
            raw = yaml.safe_load(f) or {}

        # Build all lookup structures in one pass
        self._by_class: Dict[str, List[str]] = {}
        self._sector_map: Dict[str, str] = {}
        self._etoro_id_to_symbol: Dict[int, str] = {}
        self._symbol_to_etoro_id: Dict[str, int] = {}
        self._asset_class_map: Dict[str, str] = {}
        self._market_schedule_map: Dict[str, str] = {}
        self._all_symbols: List[str] = []

        for asset_class in self.ASSET_CLASSES:
            entries = raw.get(asset_class, [])
            symbols = []
            for entry in entries:
                sym = entry["symbol"]
                # YAML parses bare ON/NO/YES as booleans — force string
                if not isinstance(sym, str):
                    sym = str(sym)
                    logger.warning(f"Symbol '{sym}' in {asset_class} was parsed as {type(entry['symbol']).__name__} — quote it in symbols.yaml")
                etoro_id = entry.get("etoro_id")
                sector = entry.get("sector", "Unknown")
                market_schedule = entry.get("market_schedule")  # optional per-symbol override

                symbols.append(sym)
                self._sector_map[sym] = sector
                self._asset_class_map[sym] = asset_class
                if market_schedule:
                    self._market_schedule_map[sym] = market_schedule
                if etoro_id:
                    self._etoro_id_to_symbol[etoro_id] = sym
                    self._symbol_to_etoro_id[sym] = etoro_id

            self._by_class[asset_class] = symbols
            self._all_symbols.extend(symbols)

        logger.info(
            f"SymbolRegistry loaded: {len(self._all_symbols)} symbols "
            f"({', '.join(f'{k}={len(v)}' for k, v in self._by_class.items())})"
        )

    # --- Symbol lists by asset class ---
    @property
    def stocks(self) -> List[str]:
        return self._by_class.get("stocks", [])

    @property
    def etfs(self) -> List[str]:
        return self._by_class.get("etfs", [])

    @property
    def forex(self) -> List[str]:
        return self._by_class.get("forex", [])

    @property
    def indices(self) -> List[str]:
        return self._by_class.get("indices", [])

    @property
    def commodities(self) -> List[str]:
        return self._by_class.get("commodities", [])

    @property
    def crypto(self) -> List[str]:
        return self._by_class.get("crypto", [])

    @property
    def all_symbols(self) -> List[str]:
        return self._all_symbols.copy()

    def symbols_for_class(self, asset_class: str) -> List[str]:
        return self._by_class.get(asset_class, [])

    # --- Lookups ---
    def get_sector(self, symbol: str) -> str:
        return self._sector_map.get(symbol.upper(), self._sector_map.get(symbol, "Unknown"))

    def get_asset_class(self, symbol: str) -> str:
        return self._asset_class_map.get(symbol.upper(), self._asset_class_map.get(symbol, "unknown"))

    def get_market_schedule(self, symbol: str) -> Optional[str]:
        """Return the per-symbol market_schedule override from symbols.yaml,
        or None if the symbol has no explicit override. The MarketHoursManager
        uses this to opt individual symbols out of the asset-class default
        (e.g., a non-24/5 stock in an otherwise-24/5-default universe)."""
        return self._market_schedule_map.get(
            symbol.upper(), self._market_schedule_map.get(symbol)
        )

    def get_etoro_id(self, symbol: str) -> Optional[int]:
        return self._symbol_to_etoro_id.get(symbol.upper(), self._symbol_to_etoro_id.get(symbol))

    def symbol_from_etoro_id(self, etoro_id: int) -> Optional[str]:
        return self._etoro_id_to_symbol.get(etoro_id)

    def get_sector_map(self) -> Dict[str, str]:
        return self._sector_map.copy()

    def get_etoro_id_to_symbol(self) -> Dict[int, str]:
        return self._etoro_id_to_symbol.copy()

    def get_symbol_to_etoro_id(self) -> Dict[str, int]:
        return self._symbol_to_etoro_id.copy()

    # --- Classification helpers ---
    def is_stock(self, symbol: str) -> bool:
        return self.get_asset_class(symbol) == "stocks"

    def is_etf(self, symbol: str) -> bool:
        return self.get_asset_class(symbol) == "etfs"

    def is_crypto(self, symbol: str) -> bool:
        ac = self.get_asset_class(symbol)
        if ac == "crypto":
            return True
        # Also match USD-suffixed variants (BTCUSD, ETHUSD)
        stripped = symbol.upper().replace("USD", "")
        return self._asset_class_map.get(stripped) == "crypto"

    def is_forex(self, symbol: str) -> bool:
        return self.get_asset_class(symbol) == "forex"

    def is_index(self, symbol: str) -> bool:
        return self.get_asset_class(symbol) == "indices"

    def is_commodity(self, symbol: str) -> bool:
        return self.get_asset_class(symbol) == "commodities"

    def is_tradeable(self, symbol: str) -> bool:
        return symbol.upper() in self._asset_class_map or symbol in self._asset_class_map

    def has_fundamentals(self, symbol: str) -> bool:
        """Returns True only for individual stocks (not ETFs, crypto, forex, etc.)."""
        return self.is_stock(symbol)

    def is_non_equity(self, symbol: str) -> bool:
        """Returns True for anything that's not an individual stock."""
        return not self.is_stock(symbol)


def get_registry() -> SymbolRegistry:
    """Get or create the singleton SymbolRegistry."""
    global _registry
    if _registry is None:
        _registry = SymbolRegistry()
    return _registry


def reset_registry():
    """Force reload of the registry (e.g., after config change)."""
    global _registry
    _registry = None
