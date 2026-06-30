"""Regime dormancy — separate VALIDITY (proven edge) from ACTIVITY (regime is now).

Design: REGIME_DORMANCY_DESIGN_2026-06-30.md (CIO-approved 2026-06-30).

Today the system *retires* (and then deletes) a validated strategy when its
regime no longer matches the market — so every regime change throws away
validated edges and rebuilds them from scratch when the regime returns. This
module replaces regime-mismatch RETIREMENT with regime DORMANCY: a
regime-mismatched-but-validated strategy is put to sleep (excluded from signal
generation, exempt from cleanup deletion) and woken when its regime returns.
Edge-decay retirement is unaffected — dormancy only parks regime-mismatched
edges, it never protects a dead one.

**Default OFF.** `regime_dormancy.enabled` defaults to False, in which case the
caller keeps its current retire behavior and this module changes nothing.
Enabling requires the regime-flip backtest in the design §7. Self-contained,
fail-safe (any error → treat as "not dormant / don't act", never crash a cycle).

State lives in `strategy_metadata`:
  - `regime_dormant: bool`           — True ⇒ asleep (skipped by signal gen)
  - `dormant_reason: str`
  - `dormant_since: ISO str`
  - `dormant_from_regime: str`       — regime active when it was put to sleep
  - `last_active_regime: str`
  - `dormant_revalidate: bool`       — woken past max-warm-age; flag for scrutiny
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "enabled": False,
    "sleep_confirm_days": 5,     # regime stable ≥ this before sleeping a mismatch
    "wake_confirm_days": 3,      # regime stable ≥ this before waking a match
    "min_dwell_days": 2,         # min time in a state before toggling again
    "max_warm_age_days": 60,     # older validation ⇒ flag for re-validation on wake
}

_CFG_CACHE: Optional[Dict[str, Any]] = None
_CFG_TS: float = 0.0


def _cfg() -> Dict[str, Any]:
    """Read the `regime_dormancy` block from the authoritative YAML (cached ~60s).
    Missing block/keys fall back to _DEFAULTS. Never raises."""
    global _CFG_CACHE, _CFG_TS
    import time
    now = time.time()
    if _CFG_CACHE is not None and (now - _CFG_TS) < 60:
        return _CFG_CACHE
    cfg = dict(_DEFAULTS)
    try:
        import yaml
        from pathlib import Path
        raw = yaml.safe_load(Path("config/autonomous_trading.yaml").read_text()) or {}
        block = raw.get("regime_dormancy", {}) or {}
        for k in _DEFAULTS:
            if k in block:
                cfg[k] = block[k]
    except Exception as e:
        logger.debug("regime_dormancy config read failed: %s — using defaults (disabled)", e)
    _CFG_CACHE = cfg
    _CFG_TS = now
    return cfg


def is_enabled() -> bool:
    try:
        return bool(_cfg().get("enabled", False))
    except Exception:
        return False


def _int(key: str) -> int:
    try:
        return int(_cfg().get(key, _DEFAULTS[key]))
    except Exception:
        return int(_DEFAULTS[key])


# ── State helpers (operate on a metadata dict; caller persists) ───────────────

def is_dormant(meta: Optional[dict]) -> bool:
    """True if the strategy's metadata flags it regime-dormant. Fail-safe False."""
    try:
        return bool((meta or {}).get("regime_dormant"))
    except Exception:
        return False


def mark_dormant(meta: dict, current_regime: str, reason: str) -> dict:
    """Stamp dormancy flags on `meta` (in place) and return it. Caller persists
    with flag_modified + commit."""
    meta["regime_dormant"] = True
    meta["dormant_reason"] = reason
    meta["dormant_since"] = datetime.now().isoformat()
    meta["dormant_from_regime"] = current_regime
    return meta


def mark_awake(meta: dict, current_regime: str, needs_revalidation: bool) -> dict:
    """Clear dormancy flags on `meta` (in place) and return it."""
    meta["regime_dormant"] = False
    meta["last_active_regime"] = current_regime
    meta["dormant_revalidate"] = bool(needs_revalidation)
    meta.pop("dormant_reason", None)
    meta.pop("dormant_since", None)
    meta.pop("dormant_from_regime", None)
    return meta


def _days_in_state(meta: Optional[dict], key: str) -> Optional[float]:
    try:
        ts = (meta or {}).get(key)
        if not ts:
            return None
        return (datetime.now() - datetime.fromisoformat(ts)).total_seconds() / 86400.0
    except Exception:
        return None


def dwell_satisfied(meta: Optional[dict]) -> bool:
    """True if enough time has passed since the last sleep toggle (anti-flap).
    Applies to a currently-dormant strategy considering waking; for a
    not-yet-dormant strategy there is no dwell constraint."""
    days = _days_in_state(meta, "dormant_since")
    if days is None:
        return True
    return days >= _int("min_dwell_days")


def needs_revalidation_on_wake(meta: Optional[dict]) -> bool:
    """True if the strategy's last validation is older than max_warm_age_days,
    so it should be flagged for scrutiny when woken (edge may have drifted).
    Best-effort: reads common validation-timestamp keys; if none, returns False
    (do not block a wake on a missing timestamp)."""
    try:
        m = meta or {}
        for k in ("last_validated_at", "wf_validated_at", "activation_approved_at", "created_at"):
            ts = m.get(k)
            if ts:
                age = (datetime.now() - datetime.fromisoformat(str(ts))).total_seconds() / 86400.0
                return age > _int("max_warm_age_days")
    except Exception:
        pass
    return False


# ── Regime stability (mirrors monitoring_service fundamental-exit guard) ──────

def is_regime_stable(session, days: int) -> bool:
    """True if there has been NO regime change in the last `days` days.
    Mirrors the existing pattern: count RegimeHistoryORM rows with
    regime_changed == 1 (NOT == True — Postgres int!=bool). Fail-closed to
    False (when uncertain, don't toggle)."""
    try:
        from src.models.orm import RegimeHistoryORM
        window = datetime.utcnow() - timedelta(days=int(days))
        changes = session.query(RegimeHistoryORM).filter(
            RegimeHistoryORM.detected_at >= window,
            RegimeHistoryORM.regime_changed == 1,
        ).count()
        return changes == 0
    except Exception as e:
        logger.debug("is_regime_stable failed: %s — treating as NOT stable", e)
        return False
