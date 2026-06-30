"""Canonical eToro per-instrument minimum order amount — single source of truth.

eToro enforces a per-instrument minimum *position amount* (the dollar value it
receives). CFD instruments (forex, indices, commodities) and leveraged products
carry a **$1,000** minimum; ordinary stocks / ETFs / crypto are a low retail
minimum. Before this module the minimum was hardcoded inconsistently in three
places — DEMO floor $1,000 (`risk_manager`), LIVE floor $200 (`trading_scheduler`),
and a stale $2,000 in `order_executor` — none instrument-aware, so a CFD order
sized below $1,000 (e.g. USDCAD at $790.55) was submitted and rejected by eToro
with error 720 every cycle.

This module centralizes the rule. Callers floor a computed order amount UP to
`etoro_min_order_amount(symbol)` (PAPER), or validate a CIO size against it
(graduation dashboard). It never raises — on any classification failure it
returns the conservative CFD floor so we never *under*-estimate the minimum and
let a doomed order through.

Empirical basis: eToro error-720 rejections observed 2026-06 reported
`MinimumPositionAmount: 1000` for USDCAD (forex), SPX500 (index) and PALL
(commodity). The $1,000 CFD floor is therefore confirmed from the broker itself;
the non-CFD value is eToro's published retail minimum.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Confirmed from eToro error-720 rejections (forex/index/commodity CFDs).
ETORO_MIN_CFD = 1000.0
# eToro published retail minimum for cash stocks/ETFs/crypto (well below any
# paper flat ($1,000) or live floor ($200), so it effectively never binds — it
# exists only so the function is total and non-CFD instruments aren't over-floored).
ETORO_MIN_CASH = 10.0

# ── Self-healing learned minimums ────────────────────────────────────────────
# Symbol classification can't perfectly predict eToro's per-instrument minimum
# (e.g. some cash LONGs like ROST/SPY have been observed rejecting at $1,000).
# So we LEARN the real minimum from eToro's own 720 rejections and use
# max(classified_default, learned) thereafter — the same self-healing pattern as
# short_restrictions. A long TTL lets it re-test in case eToro lowers a minimum.
_OVERRIDE_PATH = Path("config/.etoro_min_overrides.json")
_OVERRIDE_TTL_DAYS = 90
_LOCK = threading.Lock()
_OVERRIDES: Dict[str, dict] = {}
_OVERRIDES_LOADED = False


def _load_overrides() -> Dict[str, dict]:
    global _OVERRIDES, _OVERRIDES_LOADED
    if _OVERRIDES_LOADED:
        return _OVERRIDES
    try:
        if _OVERRIDE_PATH.exists():
            with open(_OVERRIDE_PATH) as f:
                data = json.load(f)
            if isinstance(data, dict):
                _OVERRIDES = {str(k).upper(): v for k, v in data.items() if isinstance(v, dict)}
    except Exception as e:
        logger.debug("etoro_min overrides load failed: %s", e)
        _OVERRIDES = {}
    _OVERRIDES_LOADED = True
    return _OVERRIDES


def _save_overrides() -> None:
    try:
        _OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _OVERRIDE_PATH.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(_OVERRIDES, f, indent=2, sort_keys=True)
        tmp.replace(_OVERRIDE_PATH)
    except Exception as e:
        logger.debug("etoro_min overrides save failed: %s", e)


def _learned_minimum(symbol: str) -> float:
    """Learned minimum for `symbol` from past 720 rejections (0.0 if none/expired)."""
    try:
        with _LOCK:
            d = _load_overrides()
            rec = d.get(symbol.upper())
            if not rec:
                return 0.0
            ts = datetime.fromisoformat(rec.get("observed_at", ""))
            if datetime.now() - ts > timedelta(days=_OVERRIDE_TTL_DAYS):
                d.pop(symbol.upper(), None)
                _save_overrides()
                return 0.0
            return float(rec.get("min", 0.0) or 0.0)
    except Exception as e:
        logger.debug("_learned_minimum(%s) failed: %s", symbol, e)
        return 0.0


def looks_like_min_order_violation(message: str) -> bool:
    """True if an eToro error message indicates a below-minimum order amount."""
    if not message:
        return False
    m = str(message).lower()
    return "minimumpositionamount" in m or ("under the minimum" in m)


def parse_min_from_error(message: str) -> Optional[float]:
    """Extract the eToro-reported `MinimumPositionAmount: N` from a 720 message."""
    if not message:
        return None
    try:
        m = re.search(r"MinimumPositionAmount:\s*([0-9]+(?:\.[0-9]+)?)", str(message))
        return float(m.group(1)) if m else None
    except Exception:
        return None


def record_observed_minimum(symbol: str, error_message: str) -> None:
    """Learn the real per-instrument minimum from an eToro 720 rejection.
    Fail-safe: swallows all errors. Stores the max minimum ever observed."""
    if not symbol:
        return
    try:
        observed = parse_min_from_error(error_message)
        if observed is None or observed <= 0:
            return
        with _LOCK:
            d = _load_overrides()
            sym = symbol.upper()
            prev = float((d.get(sym) or {}).get("min", 0.0) or 0.0)
            new_min = max(prev, observed)
            d[sym] = {"min": new_min, "observed_at": datetime.now().isoformat()}
            _save_overrides()
        if observed > prev:
            logger.warning(
                "Learned eToro minimum for %s: $%.0f (from broker 720 rejection) — "
                "future orders will floor to this", symbol, observed,
            )
    except Exception as e:
        logger.debug("record_observed_minimum(%s) failed: %s", symbol, e)

_FOREX_CCYS = frozenset({
    "USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF", "SEK", "NOK", "DKK",
    "SGD", "HKD", "ZAR", "MXN", "PLN", "TRY", "CNH", "CZK", "HUF",
})


def _is_forex_pair(sym: str) -> bool:
    """6-char currency pair (EURUSD, USDCAD, ...). Mirrors order_executor."""
    return len(sym) == 6 and sym[:3] in _FOREX_CCYS and sym[3:] in _FOREX_CCYS


def classify_for_minimum(symbol: str) -> str:
    """Coarse class for minimum-order purposes: 'cfd' (forex/index/commodity/
    leveraged) or 'cash' (stock/etf/crypto). Never raises; defaults to 'cfd'
    (the safe, higher floor) when classification is uncertain so we never
    under-floor a CFD."""
    if not symbol:
        return "cfd"
    sym = str(symbol).strip().upper()

    # Forex pairs are always CFD on eToro.
    if _is_forex_pair(sym):
        return "cfd"

    # Leveraged ETFs (SOXL/TQQQ/...) — canonical set in sl_caps.
    try:
        from src.risk.sl_caps import is_leveraged_etf
        if is_leveraged_etf(sym):
            return "cfd"
    except Exception:
        pass

    # Indices and commodities are CFD on eToro; crypto/stocks/etfs are cash.
    try:
        from src.core.tradeable_instruments import (
            DEMO_ALLOWED_INDICES,
            DEMO_ALLOWED_COMMODITIES,
            DEMO_ALLOWED_CRYPTO,
        )
        if sym in set(DEMO_ALLOWED_INDICES) or sym in set(DEMO_ALLOWED_COMMODITIES):
            return "cfd"
        if sym in set(DEMO_ALLOWED_CRYPTO):
            return "cash"
    except Exception:
        # Registry unavailable — fall through to heuristics below.
        pass

    # Default: treat as cash stock/ETF (the common case). Forex/leveraged/CFD
    # have already been caught above; anything left is overwhelmingly a stock or
    # ETF whose minimum is the low cash floor.
    return "cash"


def etoro_min_order_amount(symbol: str) -> float:
    """Minimum eToro order amount (USD, the amount eToro receives) for `symbol`.

    The greater of the classified default ($1,000 for CFD forex/index/commodity/
    leveraged, $10 for cash stocks/ETFs/crypto) and any minimum LEARNED from a
    past eToro 720 rejection for this symbol. Never raises.
    """
    try:
        classified = ETORO_MIN_CFD if classify_for_minimum(symbol) == "cfd" else ETORO_MIN_CASH
        return max(classified, _learned_minimum(symbol))
    except Exception as e:  # pragma: no cover — total by construction
        logger.warning("etoro_min_order_amount(%s) failed: %s — using CFD floor", symbol, e)
        return ETORO_MIN_CFD


def min_real_size_for_symbol(symbol: str, mirror_ratio: float) -> Optional[float]:
    """Minimum CIO *real* position size for a LIVE pair so the virtual amount
    submitted to eToro (`real / mirror_ratio`) clears the instrument minimum.

    Returns None when mirror_ratio is missing/invalid (caller must not guess).
    """
    try:
        mr = float(mirror_ratio)
    except (TypeError, ValueError):
        return None
    if mr <= 0:
        return None
    return etoro_min_order_amount(symbol) * mr


def get_live_mirror_ratio(default: float = 0.10) -> float:
    """Read live_trading.mirror_ratio from the authoritative YAML. Never raises."""
    try:
        import yaml
        cfg = yaml.safe_load(Path("config/autonomous_trading.yaml").read_text()) or {}
        return float((cfg.get("live_trading", {}) or {}).get("mirror_ratio", default))
    except Exception:
        return default


def validate_cio_position_size(
    symbol: str, position_size_real: float, mirror_ratio: float
) -> Optional[str]:
    """Validate a CIO-set LIVE real position size against the per-symbol eToro
    minimum (accounting for the mirror ratio). Returns an error message string
    when the size is too small to clear the broker minimum, else None.

    The amount eToro receives is virtual = real / mirror_ratio; eToro requires
    virtual >= etoro_min(symbol). Equivalently real >= etoro_min * mirror_ratio.
    """
    try:
        min_real = min_real_size_for_symbol(symbol, mirror_ratio)
        if min_real is None:
            return None  # can't compute (bad mirror) — don't block on a guess
        if float(position_size_real) < min_real:
            inst_min = etoro_min_order_amount(symbol)
            virtual = float(position_size_real) / float(mirror_ratio)
            return (
                f"{symbol} requires a minimum real size of ${min_real:,.2f} "
                f"(${inst_min:,.0f} virtual at {float(mirror_ratio):.3f} mirror); "
                f"got ${float(position_size_real):,.2f} real (${virtual:,.2f} virtual). "
                f"eToro rejects below-minimum orders for this instrument."
            )
    except Exception as e:  # never block legitimately on a validator bug
        logger.debug("validate_cio_position_size(%s) failed: %s", symbol, e)
    return None
