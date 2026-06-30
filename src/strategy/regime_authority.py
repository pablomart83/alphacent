"""Regime authority — the debounced, single source of truth for "the market regime".

`market_analyzer.detect_sub_regime()` is a fine *instantaneous* reading, but it is
extremely noisy: over 2021-2026 it flips every ~1-2 trading days (331 episodes,
median dwell 2d — see scripts/backtest_regime_dormancy.py). Acting on the raw
value makes the system thrash: regime-incompatible strategies get retired on a
flip and the regime flips back days later. It also makes the dormancy stability
gate permanently false (there's almost always a raw change in any 5-day window),
so dormancy would be inert.

This module debounces the raw reading into a CONFIRMED **official regime** via a
state machine: a new raw reading must persist `confirm_days` consecutive trading
days before it is promoted to official. The tuning backtest showed confirm_days=5
yields ~13 confirmed changes/yr with a ~17-trading-day (≈3.4-week) median dwell —
a human-legible regime timeline the whole system can act on.

Consumers read `current_official()` instead of the raw value. The monitoring
recorder advances the machine once per trading day via `step()` and writes the
official regime (with the confirmed-change flag) to regime_history, which makes
`is_regime_stable` meaningful and dormancy functional.

State is a small JSON file (config/.regime_authority.json), matching the codebase's
existing state-file pattern. Fail-safe throughout: any error falls back to the raw
value / "not changed" and never crashes a cycle.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_STATE_PATH = Path("config/.regime_authority.json")
_DEFAULT_CONFIRM_DAYS = 5  # evidence-based (backtest_regime_dormancy.py sweep)
_LOCK = threading.Lock()


def confirm_days() -> int:
    """regime_authority.confirm_days from YAML (default 5). Never raises."""
    try:
        import yaml
        raw = yaml.safe_load(Path("config/autonomous_trading.yaml").read_text()) or {}
        block = raw.get("regime_authority", {}) or {}
        return int(block.get("confirm_days", _DEFAULT_CONFIRM_DAYS))
    except Exception:
        return _DEFAULT_CONFIRM_DAYS


def _load() -> dict:
    try:
        if _STATE_PATH.exists():
            d = json.loads(_STATE_PATH.read_text())
            if isinstance(d, dict):
                return d
    except Exception as e:
        logger.debug("regime_authority state load failed: %s", e)
    return {}


def _save(state: dict) -> None:
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
        tmp.replace(_STATE_PATH)
    except Exception as e:
        logger.debug("regime_authority state save failed: %s", e)


def current_official() -> Optional[str]:
    """The current confirmed/official regime, or None if not yet established.
    This is what consumers (dormancy, sizing, proposer) should read."""
    try:
        with _LOCK:
            return _load().get("official_regime")
    except Exception:
        return None


def get_state() -> dict:
    """Full authority state (for diagnostics/observability)."""
    with _LOCK:
        return _load()


def step(raw_regime: str, today: Optional[date] = None) -> Tuple[Optional[str], bool]:
    """Advance the confirmed-regime state machine with today's raw reading.

    Counts at most once per trading day (weekends skipped; the raw reading does not
    change while markets are closed). A raw value different from the official regime
    must persist `confirm_days` consecutive trading days to be promoted.

    Returns (official_regime, changed_this_step). Fail-safe: on any error returns
    (raw_regime, False) without mutating state.
    """
    if not raw_regime:
        return current_official(), False
    try:
        d = today or date.today()
        today_iso = d.isoformat()
        with _LOCK:
            state = _load()
            official = state.get("official_regime")

            # First observation ever: seed the official regime, no change event.
            if not official:
                state.update({
                    "official_regime": raw_regime,
                    "official_since": today_iso,
                    "candidate_regime": None,
                    "candidate_streak": 0,
                    "last_eval_date": today_iso,
                })
                _save(state)
                logger.info(f"[RegimeAuthority] seeded official regime = {raw_regime}")
                return raw_regime, False

            # Only advance once per trading day; skip weekends (no new market data).
            if state.get("last_eval_date") == today_iso or d.weekday() >= 5:
                return official, False

            cd = confirm_days()
            candidate = state.get("candidate_regime")
            streak = int(state.get("candidate_streak", 0) or 0)
            changed = False

            if raw_regime == official:
                candidate, streak = None, 0
            elif raw_regime == candidate:
                streak += 1
                if streak >= cd:
                    prev = official
                    official = candidate
                    candidate, streak = None, 0
                    changed = True
                    state["official_since"] = today_iso
                    logger.info(
                        f"[RegimeAuthority] CONFIRMED regime change {prev} → {official} "
                        f"(held {cd} trading days)"
                    )
            else:
                candidate, streak = raw_regime, 1

            state.update({
                "official_regime": official,
                "candidate_regime": candidate,
                "candidate_streak": streak,
                "last_eval_date": today_iso,
            })
            _save(state)
            return official, changed
    except Exception as e:
        logger.warning(f"[RegimeAuthority] step failed: {e} — falling back to raw")
        return raw_regime, False
