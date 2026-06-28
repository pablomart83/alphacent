"""Self-maintaining denylist of eToro short-restricted instruments.

Some eToro instruments reject SELL/short entries with
"opening position is disallowed for Sell positions of this instrument".
Before this, the system kept re-emitting ENTER_SHORT signals on those names
every cycle — the order was submitted, rejected by eToro, and the signal
re-fired next cycle (wasted cycles + error-log noise + a short that never
fills, which quietly skews the short book).

Design (mirrors the rejection-blacklist cooldown pattern):
  - When eToro rejects a short with the "disallowed for Sell" message,
    `record_short_restriction(symbol)` stamps {symbol: ISO-now} in
    config/.short_restricted.json.
  - `is_short_restricted(symbol)` returns True while the stamp is within
    TTL_DAYS. The TTL means the denylist SELF-HEALS — if eToro later allows
    shorting the instrument, the entry expires and we re-test rather than
    locking it out forever.
  - `execute_signal` consults this before submitting an ENTER_SHORT and skips
    (gates) the order if restricted, so we stop wasting submissions.

Fail-open everywhere: any error → treat as NOT restricted (never block a
legitimate order because of a denylist read/write problem).
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

_PATH = Path("config/.short_restricted.json")
TTL_DAYS = 30  # re-test an instrument after a month in case eToro re-enables shorting

_LOCK = threading.Lock()
_CACHE: Dict[str, str] = {}
_CACHE_LOADED = False


def _load() -> Dict[str, str]:
    global _CACHE, _CACHE_LOADED
    if _CACHE_LOADED:
        return _CACHE
    try:
        if _PATH.exists():
            with open(_PATH) as f:
                data = json.load(f)
            if isinstance(data, dict):
                _CACHE = {str(k).upper(): str(v) for k, v in data.items()}
    except Exception as e:
        logger.debug(f"short_restrictions load failed: {e}")
        _CACHE = {}
    _CACHE_LOADED = True
    return _CACHE


def _save() -> None:
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _PATH.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(_CACHE, f, indent=2, sort_keys=True)
        tmp.replace(_PATH)
    except Exception as e:
        logger.debug(f"short_restrictions save failed: {e}")


def is_short_restricted(symbol: str) -> bool:
    """True if `symbol` is on the short denylist and the stamp is within TTL.
    Fail-open: returns False on any error."""
    if not symbol:
        return False
    try:
        with _LOCK:
            d = _load()
            stamp = d.get(symbol.upper())
            if not stamp:
                return False
            ts = datetime.fromisoformat(stamp)
            if datetime.now() - ts > timedelta(days=TTL_DAYS):
                # Expired — drop it so we re-test on the next short signal.
                d.pop(symbol.upper(), None)
                _save()
                return False
            return True
    except Exception as e:
        logger.debug(f"is_short_restricted({symbol}) failed: {e}")
        return False


def record_short_restriction(symbol: str) -> None:
    """Stamp `symbol` as short-restricted (called when eToro rejects a short).
    Fail-safe: swallows all errors."""
    if not symbol:
        return
    try:
        with _LOCK:
            d = _load()
            sym = symbol.upper()
            first_time = sym not in d
            d[sym] = datetime.now().isoformat()
            _save()
        if first_time:
            logger.warning(
                f"Short-restricted instrument recorded: {symbol} — eToro disallows "
                f"opening Sell positions; future ENTER_SHORT will be skipped for "
                f"{TTL_DAYS}d (self-heals on expiry)"
            )
    except Exception as e:
        logger.debug(f"record_short_restriction({symbol}) failed: {e}")


def looks_like_short_disallowed(message: str) -> bool:
    """True if an eToro error message indicates short-selling is disallowed."""
    if not message:
        return False
    m = str(message).lower()
    return "disallowed" in m and "sell" in m
