"""
eToro Instrument ID to Symbol mappings — reads from SymbolRegistry.

All data lives in config/symbols.yaml.
This module provides backward-compatible dict exports.
"""

from src.core.symbol_registry import get_registry


class _LazyDict:
    """Dict-like that loads from registry on first access."""
    def __init__(self, attr):
        self._attr = attr
        self._cache = None

    def _get(self):
        if self._cache is None:
            self._cache = getattr(get_registry(), self._attr)()
        return self._cache

    def __getitem__(self, key):
        return self._get()[key]

    def __contains__(self, key):
        return key in self._get()

    def __iter__(self):
        return iter(self._get())

    def __len__(self):
        return len(self._get())

    def get(self, key, default=None):
        return self._get().get(key, default)

    def items(self):
        return self._get().items()

    def keys(self):
        return self._get().keys()

    def values(self):
        return self._get().values()


INSTRUMENT_ID_TO_SYMBOL = _LazyDict("get_etoro_id_to_symbol")
SYMBOL_TO_INSTRUMENT_ID = _LazyDict("get_symbol_to_etoro_id")
