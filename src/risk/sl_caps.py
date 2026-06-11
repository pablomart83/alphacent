"""
Asset-class-aware stop-loss / take-profit caps.

Single source of truth for the SL distance the system will allow on any
position — automated (order_executor at signal time) or manual (position
modification via the UI). Extracted from the inline clamp block in
`order_executor` so both paths use the exact same policy.

Caps are expressed as the max allowed distance from entry price, as a
positive fraction (0.09 = 9%). They mirror the steering file's
"Max SL clamps" documentation and the risk envelope the monitoring
service is designed to enforce.
"""

from __future__ import annotations

from src.core.symbol_registry import get_registry


# Canonical leveraged-ETF set — single source of truth for the whole system.
# order_executor (SL cap + FIX-03 sizing), position_manager (TSL class), and
# market_data_manager all import `is_leveraged_etf` from here. Previously this
# membership list was duplicated in 4 places with drift (position_manager had
# ROM/UWM/USD; the others didn't), so a leveraged ETF could get the wide TSL
# but not the FIX-03 sizing. One list, one truth.
_LEVERAGED_ETF_SET = frozenset({
    # 3x / 2x Long
    "SOXL", "TQQQ", "UPRO", "SPXL", "UDOW", "LABU", "TECL", "FAS", "TNA",
    "NAIL", "CURE", "DFEN", "WANT", "HIBL",
    "SSO", "QLD", "DDM", "ROM", "UWM", "USD",
    # 3x / 2x Inverse
    "SQQQ", "SPXU", "SDOW", "SOXS", "LABD", "TECS", "FAZ", "TZA", "HIBS",
})


def is_leveraged_etf(symbol: str) -> bool:
    """True if `symbol` is a known leveraged (2x/3x) ETF. Canonical check."""
    return symbol.upper() in _LEVERAGED_ETF_SET

# SL cap fractions (max distance from entry). These are *cap* values — the
# signal path may pick a lower value based on ATR. Manual writes may go up
# to but not exceed these.
_SL_CAP_STOCKS = 0.09
_SL_CAP_ETFS = 0.09
_SL_CAP_LEVERAGED_ETF = 0.20
_SL_CAP_CRYPTO = 0.15
_SL_CAP_FOREX = 0.04
_SL_CAP_INDICES = 0.09
_SL_CAP_COMMODITIES = 0.10
_SL_CAP_DEFAULT = 0.10

# TP caps — looser, we don't put a hard ceiling on profit targets but we do
# reject values so far from entry they could never realistically be hit.
_TP_CAP_DEFAULT = 2.00  # 200%: keeps sanity check without constraining strategy.


def _is_forex_like(symbol: str) -> bool:
    """Return True for a 6-letter FX ticker (AAABBB)."""
    sym = symbol.upper()
    return len(sym) == 6 and sym[:3].isalpha() and sym[3:].isalpha()


def _is_crypto_like(symbol: str) -> bool:
    sym = symbol.upper()
    # Exact asset-class from registry takes precedence in `sl_cap_pct`; this
    # is the fallback when the registry returns "unknown".
    return any(c in sym for c in ("BTC", "ETH", "XRP", "ADA", "SOL"))


def sl_cap_pct(symbol: str) -> float:
    """
    Max allowed SL distance (fraction) for `symbol`, asset-class aware.

    Resolution order:
      1. Symbol registry asset class (authoritative when known).
      2. Leveraged-ETF set membership (wider cap for known 3x products).
      3. Heuristic fallbacks — forex pattern, crypto substrings.
      4. Default stocks cap.
    """
    sym_upper = symbol.upper()

    # Leveraged ETFs get a wider cap regardless of registry class.
    if sym_upper in _LEVERAGED_ETF_SET:
        return _SL_CAP_LEVERAGED_ETF

    asset_class = ""
    try:
        asset_class = (get_registry().get_asset_class(sym_upper) or "").lower()
    except Exception:
        asset_class = ""

    if asset_class == "crypto":
        return _SL_CAP_CRYPTO
    if asset_class == "forex":
        return _SL_CAP_FOREX
    if asset_class == "indices":
        return _SL_CAP_INDICES
    if asset_class == "commodities":
        return _SL_CAP_COMMODITIES
    if asset_class == "etfs":
        return _SL_CAP_ETFS
    if asset_class == "stocks":
        return _SL_CAP_STOCKS

    # Registry miss — fall through to heuristics so unknown symbols aren't
    # treated as stocks by default (FX/crypto caps are tighter).
    if _is_forex_like(sym_upper):
        return _SL_CAP_FOREX
    if _is_crypto_like(sym_upper):
        return _SL_CAP_CRYPTO
    return _SL_CAP_DEFAULT


def tp_cap_pct(symbol: str) -> float:  # noqa: ARG001 — symbol kept for future use
    """Max allowed TP distance (fraction). Uniform cap; symbol reserved."""
    return _TP_CAP_DEFAULT
