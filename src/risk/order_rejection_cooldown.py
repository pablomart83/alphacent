"""Self-healing cooldown for entries that keep getting the SAME broker rejection.

Some entry orders are rejected by eToro for a condition that will NOT change
cycle-to-cycle — most notably a below-minimum amount (error 720) on a pair whose
configured size is too small (e.g. the live USDCAD pair sized at $100.4 real,
which is below the $1,000 forex-CFD minimum → $790 virtual). The signal re-fires
every cycle, the order is resubmitted, eToro rejects it again — ~45×/day of pure
error-log noise with no chance of success until the *size* changes.

This cooldown (mirrors short_restrictions) suppresses re-submission of the same
(symbol, account) ENTRY for a short window after such a rejection:
  - `record_rejection(symbol, account)` stamps {key: ISO-now} on a below-min 720.
  - `is_on_cooldown(symbol, account)` is True while within TTL_HOURS, so the
    entry is skipped before submission.
  - `clear(symbol, account)` removes the stamp — called when the CIO updates the
    pair's position_size (the condition that caused the rejection has changed),
    so the fix takes effect immediately instead of waiting out the TTL.

TTL is short (hours) so the system SELF-HEALS: if nothing else changes it
re-tests a few times a day rather than locking the pair out. Fail-open
everywhere: any error → not on cooldown (never suppress a legitimate order).
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

_PATH = Path("config/.order_rejection_cooldown.json")
TTL_HOURS = 4  # re-test the pair every few hours in case the size was fixed

_LOCK = threading.Lock()
_CACHE: Dict[str, str] = {}
_CACHE_LOADED = False


def _key(symbol: str, account: str) -> str:
    return f"{(symbol or '').upper()}|{(account or 'demo').lower()}"


def _load() -> Dict[str, str]:
    global _CACHE, _CACHE_LOADED
    if _CACHE_LOADED:
        return _CACHE
    try:
        if _PATH.exists():
            with open(_PATH) as f:
                data = json.load(f)
            if isinstance(data, dict):
                _CACHE = {str(k): str(v) for k, v in data.items()}
    except Exception as e:
        logger.debug("order_rejection_cooldown load failed: %s", e)
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
        logger.debug("order_rejection_cooldown save failed: %s", e)


def is_on_cooldown(symbol: str, account: str) -> bool:
    """True if this (symbol, account) entry was recently rejected for an
    unchanged condition and is still within TTL. Fail-open: False on any error."""
    if not symbol:
        return False
    try:
        with _LOCK:
            d = _load()
            k = _key(symbol, account)
            stamp = d.get(k)
            if not stamp:
                return False
            ts = datetime.fromisoformat(stamp)
            if datetime.now() - ts > timedelta(hours=TTL_HOURS):
                d.pop(k, None)
                _save()
                return False
            return True
    except Exception as e:
        logger.debug("is_on_cooldown(%s,%s) failed: %s", symbol, account, e)
        return False


def record_rejection(symbol: str, account: str) -> None:
    """Stamp this (symbol, account) entry on cooldown (called on a repeatable
    broker rejection, e.g. below-minimum 720). Fail-safe."""
    if not symbol:
        return
    try:
        with _LOCK:
            d = _load()
            k = _key(symbol, account)
            first = k not in d
            d[k] = datetime.now().isoformat()
            _save()
        if first:
            logger.warning(
                "Order-rejection cooldown set for %s (%s) — eToro rejected the entry "
                "for an unchanged condition (e.g. below minimum); suppressing "
                "re-submission for %dh (self-heals; cleared on size update)",
                symbol, account, TTL_HOURS,
            )
    except Exception as e:
        logger.debug("record_rejection(%s,%s) failed: %s", symbol, account, e)


def clear(symbol: str, account: str = None) -> None:
    """Clear the cooldown for a symbol (all accounts if `account` is None).
    Called when the underlying condition changes (e.g. CIO updates the size)."""
    if not symbol:
        return
    try:
        with _LOCK:
            d = _load()
            sym = symbol.upper()
            removed = False
            for k in list(d.keys()):
                if k.split("|", 1)[0] == sym and (account is None or k.endswith(f"|{account.lower()}")):
                    d.pop(k, None)
                    removed = True
            if removed:
                _save()
                logger.info("Order-rejection cooldown cleared for %s (%s)", symbol, account or "all")
    except Exception as e:
        logger.debug("clear(%s) failed: %s", symbol, e)
