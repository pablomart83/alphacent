"""Realized-volatility classifier — single source of truth for "is this a
high-volatility, churn-prone symbol?".

Companion to src.risk.sl_caps.is_leveraged_etf. The 2026-06-21 SOXL analysis
showed that the "sub-day churn loses, multi-day holds win" pattern is NOT
leverage-specific — it recurs across the high-volatility cohort (semis, miners,
high-beta growth). `diagnose_symbol_edge.py --scan` surfaced 19 such names
(SOXL/MU/AMD/AVGO/SOXX/ARM/SMH/TQQQ/ADI/TXN/…), together bleeding ~$11k on
sub-day trades while earning strongly on ≥3-day holds.

So anti-churn (daily-only), wider stops, and the paper size-haircut are gated on
LEVERAGE *or* HIGH REALIZED VOLATILITY, not just the leveraged-ETF label.

Threshold calibration (annualized realized vol, daily-bar, 120d):
  cohort:  SOXL 135% · HUT 106% · MU 82% · ARM 81% · AMD 70% · TQQQ 59% ·
           AVGO 50% · TXN/SOXX 45% · SMH 40%
  normal:  GLD 33% · MSFT 32% · AAPL 23% · KO 18% · SPY 14%
A clean separator sits ~40% annualized ≈ 0.025 daily stdev of returns. We read
the daily stdev (`volatility` / `std_dev_returns`) the proposer already computes
each cycle and persists to config/.market_stats_cache.json — no extra DB work.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Optional

# 0.025 daily stdev of returns ≈ 40% annualized (sqrt(252)). Tunable.
HIGH_VOL_DAILY_STD = 0.025

_CACHE_PATH = Path("config/.market_stats_cache.json")
_TTL_SECONDS = 600  # re-read the on-disk stats cache at most every 10 min
_mem: Dict[str, object] = {"ts": 0.0, "vols": {}}


def _load_vols() -> Dict[str, float]:
    """Symbol -> daily stdev of returns, from the market-stats cache. In-process
    cached with a short TTL. Fail-safe: returns the last good map (or empty)."""
    now = time.time()
    if (now - float(_mem["ts"])) < _TTL_SECONDS and _mem["vols"]:
        return _mem["vols"]  # type: ignore[return-value]
    try:
        data = json.loads(_CACHE_PATH.read_text())
        ms = data.get("market_statistics", {}) or {}
        vols: Dict[str, float] = {}
        for sym, entry in ms.items():
            vm = ((entry or {}).get("volatility_metrics", {}) or {})
            v = vm.get("volatility")
            if v is None:
                v = vm.get("std_dev_returns")
            if v is not None:
                try:
                    vols[sym.upper()] = float(v)
                except (TypeError, ValueError):
                    pass
        if vols:
            _mem["vols"] = vols
            _mem["ts"] = now
    except Exception:
        pass  # keep last good map; never raise into a hot path
    return _mem["vols"]  # type: ignore[return-value]


def realized_daily_vol(symbol: str) -> Optional[float]:
    """Daily stdev of returns for `symbol` from the stats cache, or None."""
    if not symbol:
        return None
    return _load_vols().get(symbol.split(":")[0].upper())


def is_high_vol(symbol: str) -> bool:
    """True if the symbol's realized daily volatility is at/above the churn-prone
    threshold (~40% annualized). Fail-safe False when vol is unknown — so a missing
    stats cache never changes behaviour (the leveraged-ETF check still applies)."""
    v = realized_daily_vol(symbol)
    return v is not None and v >= HIGH_VOL_DAILY_STD
