"""Per-gate observability scoreboard (Tier 1, Path B, read-only).

Answers the question the brief insists on: *which of our existing entry gates
actually help, and which silently destroy edge by blocking winners?*

A gate is only good if the signals it BLOCKS would have lost while the signals
that PASS win. We measure this with a direction-aware **forward-return
counterfactual** computed from price data, so blocked and passed cohorts are on
an identical, honest basis (the blocked signals never became trades, so we can't
use realized P&L — we use "what the trade WOULD have returned over the next N
bars from the decision timestamp").

For every canonical gate, per account (demo / live):
  - blocked_n                  how many entry signals it blocked
  - blocked mean_fwd / win%    forward return of the blocked cohort
  - passed mean_fwd / win%     forward return of the cohort that cleared ALL gates
  - separation = passed_mean - blocked_mean
      separation > 0  → gate blocks worse-than-passed signals  → HELPS
      separation < 0  → gate blocks BETTER-than-passed signals  → HURTS (edge destroyed)

This is read-only analytics. It never gates a trade. It is computed off the hot
path (daily-sync + manual trigger) and the result is cached so the API/Guard
read is instant — never an aggregate on the request path (the slow-Guard
regression came from exactly that).

Source of truth: the existing `signal_decisions` table (we do NOT build a
parallel decision store — we read the funnel and derive an aggregate view).
Account attribution comes from the `account_type` column (populated going
forward) with a best-effort fallback for legacy rows (LIVE-only gates → live,
else demo — the demo cycle is the overwhelming majority of decisions).
"""

from __future__ import annotations

import bisect
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Persisted snapshot so the endpoint is instant and survives restarts.
_SNAPSHOT_PATH = Path("config/.gate_scoreboard.json")
_SNAPSHOT: Optional[Dict[str, Any]] = None
_LOCK = threading.Lock()

# Forward-return horizon (trading days / daily bars). 5 ≈ one trading week — a
# reasonable proxy for "did the setup work" across the mostly-daily/4H book.
DEFAULT_HORIZON_BARS = 5
DEFAULT_LOOKBACK_DAYS = 14  # gate_blocked rows are pruned at 14d (decision_log)

# Separation magnitude (fractional forward return) beyond which we call a gate
# decisively helpful/harmful rather than neutral. 0.4% over a ~1-week horizon.
_VERDICT_THRESHOLD = 0.004
_MIN_COHORT_N = 30  # below this the gate's verdict is "insufficient data"

# LONG-only / LIVE-only gates — used for best-effort account attribution of
# legacy rows that predate the account_type column.
_LIVE_ONLY_GATE_KEYS = {"vix_c1", "btc_trend", "trend_consistency_c3"}


def canonical_gate(reason: Optional[str]) -> Optional[str]:
    """Map a free-text decision `reason` to a canonical gate key, or None when
    the reason is not an ENTRY gate we want on the scoreboard (exits, pure
    execution errors, upstream WF/MC rejections, market-closed deferrals).

    The reason strings are produced across order_executor / strategy_engine /
    trading_scheduler and carry embedded params; we key off stable prefixes.
    """
    if not reason:
        return None
    r = reason.strip().lower()

    # Not entry gates — exclude from the forward-return scoreboard.
    if "exit" in r:                      # "Low-confidence exit ... on losing position"
        return None
    if r.startswith("order execution failed") or "failed to execute" in r:
        return None
    if "market_closed" in r or "market closed" in r:
        return None
    # Upstream proposer rejections (wf/mc) are a different funnel stage; ignore
    # if they ever appear with an entry-ish reason.
    if r.startswith("mc_bootstrap") or r.startswith("tv=") or "overfitted=" in r:
        return None

    # Signal-generation filters (strategy_engine).
    if r.startswith("filter:conviction"):
        return "conviction"
    if r.startswith("filter:frequency"):
        return "frequency"
    if r.startswith("filter:low_confidence"):
        return "low_confidence"
    if r.startswith("filter:fundamental"):
        return "fundamental"
    if r.startswith("filter:ml"):
        return "ml_filter"

    # Pre-flight / coordination gates (trading_scheduler).
    if r.startswith("pullback gate"):
        return "pullback"
    if "choppy market" in r or r.startswith("mqs") or "market quality" in r:
        return "mqs_choppy"
    if r.startswith("same-template duplicate") or "duplicate" in r:
        return "duplicate"
    if r.startswith("symbol limit"):
        return "symbol_limit"
    if "insufficient_balance" in r:
        return "insufficient_balance"
    if "paper_size_below_minimum" in r or "size_below_minimum" in r:
        return "size_below_minimum"
    if "exceed max exposure" in r or "exceed max position" in r or "max exposure" in r:
        return "max_exposure"

    # Signal-time gates (order_executor).
    if r.startswith("vix_gate"):
        return "vix_c1"
    if r.startswith("btc_trend_gate"):
        return "btc_trend"
    if r.startswith("trend_consistency"):
        return "trend_consistency_c3"

    return "other"


# Human-readable gate names + whether the gate is a real "edge" gate (one whose
# job is to avoid bad trades) vs a capacity/risk gate (blocks for reasons
# unrelated to whether the signal would win — balance, dedup, exposure caps).
GATE_META: Dict[str, Dict[str, Any]] = {
    "conviction":           {"label": "Conviction threshold", "edge_gate": True},
    "frequency":            {"label": "Trade-frequency limiter", "edge_gate": False},
    "low_confidence":       {"label": "Low-confidence floor", "edge_gate": True},
    "fundamental":          {"label": "Fundamental filter", "edge_gate": True},
    "ml_filter":            {"label": "ML meta-label (dormant)", "edge_gate": True},
    "pullback":             {"label": "Pullback gate", "edge_gate": True},
    "mqs_choppy":           {"label": "Market-quality (choppy)", "edge_gate": True},
    "duplicate":            {"label": "Same-template duplicate", "edge_gate": False},
    "symbol_limit":         {"label": "Per-symbol position cap", "edge_gate": False},
    "insufficient_balance": {"label": "Insufficient balance", "edge_gate": False},
    "size_below_minimum":   {"label": "Size below minimum", "edge_gate": False},
    "max_exposure":         {"label": "Max exposure / position size", "edge_gate": False},
    "vix_c1":               {"label": "VIX spike gate (C1)", "edge_gate": True},
    "btc_trend":            {"label": "BTC-trend gate (crypto)", "edge_gate": True},
    "trend_consistency_c3": {"label": "Trend-consistency (C3)", "edge_gate": True},
    "other":                {"label": "Other / uncategorised", "edge_gate": False},
}


def _attribute_account(account_type: Optional[str], gate: str) -> str:
    """Best-effort account bucket for a decision row."""
    if account_type in ("demo", "live"):
        return account_type
    # Legacy rows (no account_type): LIVE-only gates → live, else demo (the
    # demo cycle is ~98% of all decisions).
    return "live" if gate in _LIVE_ONLY_GATE_KEYS else "demo"


def _load_bars_batch(
    symbols: set, start: datetime, end: datetime
) -> Dict[str, List[Tuple[datetime, float]]]:
    """Daily (date, close) series for many symbols in ONE query, read directly
    from the historical_price_cache table (the DB-first cache the system already
    warms hourly). Reading the table directly — rather than via the
    MarketDataManager singleton — makes the scoreboard work both in-service and
    standalone, and never triggers a live Yahoo/eToro fetch from an analytics job.
    Returns {} entries for symbols with no cached daily bars (those decisions
    simply get no forward return)."""
    out: Dict[str, List[Tuple[datetime, float]]] = {s: [] for s in symbols}
    if not symbols:
        return out
    try:
        from sqlalchemy import text
        from src.models.database import get_database
        db = get_database()
        session = db.get_session()
        try:
            rows = session.execute(text("""
                SELECT symbol, date, close
                FROM historical_price_cache
                WHERE interval = '1d'
                  AND symbol = ANY(:syms)
                  AND date >= :start AND date <= :end
                ORDER BY symbol, date
            """), {"syms": list(symbols), "start": start, "end": end}).fetchall()
        finally:
            session.close()
        for sym, dt, close in rows:
            if close is None:
                continue
            d = dt.replace(tzinfo=None) if getattr(dt, "tzinfo", None) else dt
            out.setdefault((sym or "").upper(), []).append((d, float(close)))
        for s in out:
            out[s].sort(key=lambda x: x[0])
    except Exception as e:
        logger.warning("gate_scoreboard: batch bar load failed: %s", e)
    return out


def _forward_return(
    bars: List[Tuple[datetime, float]],
    decision_ts: datetime,
    is_long: bool,
    horizon: int,
) -> Optional[float]:
    """Direction-aware forward return from the first bar at/after `decision_ts`
    to `horizon` bars later. None when there isn't enough forward data."""
    if not bars:
        return None
    dts = decision_ts.replace(tzinfo=None) if getattr(decision_ts, "tzinfo", None) else decision_ts
    times = [b[0] for b in bars]
    i = bisect.bisect_left(times, dts)
    if i >= len(bars):
        return None
    j = i + horizon
    if j >= len(bars):
        return None
    entry = bars[i][1]
    exit_ = bars[j][1]
    if entry <= 0:
        return None
    raw = (exit_ / entry) - 1.0
    return raw if is_long else -raw


def _stats(returns: List[float]) -> Dict[str, Any]:
    if not returns:
        return {"n": 0, "mean_fwd": None, "win_rate": None, "median_fwd": None}
    import numpy as np
    arr = np.array(returns, dtype=float)
    return {
        "n": int(len(arr)),
        "mean_fwd": round(float(arr.mean()), 5),
        "median_fwd": round(float(np.median(arr)), 5),
        "win_rate": round(float((arr > 0).mean()), 4),
    }


def compute_gate_scoreboard(
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    horizon_bars: int = DEFAULT_HORIZON_BARS,
) -> Dict[str, Any]:
    """Compute the full per-gate, per-account scoreboard. Heavy (price fetches
    for every symbol seen) — call OFF the request path. Returns the snapshot
    dict (also persisted via set_snapshot by the caller)."""
    from sqlalchemy import text
    from src.models.database import get_database

    t0 = time.time()
    cutoff = datetime.now() - timedelta(days=lookback_days)

    db = get_database()
    session = db.get_session()
    try:
        rows = session.execute(text("""
            SELECT symbol, direction, reason, stage, decision, account_type, timestamp
            FROM signal_decisions
            WHERE timestamp >= :cutoff
              AND direction IN ('long', 'short')
              AND (
                    stage = 'gate_blocked'
                 OR (stage = 'signal_emitted' AND decision IN ('emitted', 'rejected'))
              )
        """), {"cutoff": cutoff}).mappings().all()
        rows = [dict(r) for r in rows]
    finally:
        session.close()

    # Partition into blocked (with canonical gate) and passed (emitted) cohorts,
    # keyed by (symbol, is_long, account) → list of decision timestamps.
    # blocked[account][gate] = [(symbol, is_long, ts), ...]
    blocked: Dict[str, Dict[str, List[Tuple[str, bool, datetime]]]] = {"demo": {}, "live": {}}
    passed: Dict[str, List[Tuple[str, bool, datetime]]] = {"demo": [], "live": []}
    symbols_needed: set = set()

    for r in rows:
        sym = (r.get("symbol") or "").upper()
        if not sym:
            continue
        is_long = (r.get("direction") == "long")
        ts = r.get("timestamp")
        if not isinstance(ts, datetime):
            continue
        stage = r.get("stage")
        decision = r.get("decision")
        if stage == "signal_emitted" and decision == "emitted":
            acct = _attribute_account(r.get("account_type"), "passed")
            passed.setdefault(acct, []).append((sym, is_long, ts))
            symbols_needed.add(sym)
            continue
        # blocked path
        gate = canonical_gate(r.get("reason"))
        if gate is None:
            continue
        acct = _attribute_account(r.get("account_type"), gate)
        blocked.setdefault(acct, {}).setdefault(gate, []).append((sym, is_long, ts))
        symbols_needed.add(sym)

    # Fetch daily bars once per symbol (covers the lookback window + horizon).
    bar_start = cutoff - timedelta(days=10)
    bar_end = datetime.now()
    bars_by_symbol = _load_bars_batch(symbols_needed, bar_start, bar_end)

    def fwd_returns(items: List[Tuple[str, bool, datetime]]) -> List[float]:
        out: List[float] = []
        for sym, is_long, ts in items:
            fr = _forward_return(bars_by_symbol.get(sym, []), ts, is_long, horizon_bars)
            if fr is not None:
                out.append(fr)
        return out

    accounts_out: Dict[str, Any] = {}
    total_decisions = 0
    total_with_fr = 0

    # Build per-account views plus a combined "all" view.
    account_keys = ["demo", "live"]
    for acct in account_keys:
        passed_items = passed.get(acct, [])
        passed_fr = fwd_returns(passed_items)
        passed_stats = _stats(passed_fr)
        passed_mean = passed_stats["mean_fwd"]

        gates_out: List[Dict[str, Any]] = []
        for gate, items in sorted(blocked.get(acct, {}).items(), key=lambda kv: -len(kv[1])):
            br = fwd_returns(items)
            bstats = _stats(br)
            total_decisions += len(items)
            total_with_fr += bstats["n"]
            meta = GATE_META.get(gate, {"label": gate, "edge_gate": False})
            sep = None
            verdict = "insufficient_data"
            if bstats["n"] >= _MIN_COHORT_N and passed_mean is not None:
                sep = round(passed_mean - bstats["mean_fwd"], 5)
                if not meta["edge_gate"]:
                    # Capacity/risk gates (balance, dedup, exposure caps) don't
                    # try to predict signal quality — they block for reasons
                    # unrelated to whether the signal would win. Reporting
                    # helps/hurts for them misleads (a per-symbol cap "blocks
                    # winners" precisely because we already hold the winner).
                    verdict = "capacity"
                elif abs(sep) < _VERDICT_THRESHOLD:
                    verdict = "neutral"
                elif sep > 0:
                    verdict = "helps"      # blocks worse-than-passed signals
                else:
                    verdict = "hurts"      # blocks better-than-passed signals (edge destroyed)
            elif not meta["edge_gate"]:
                verdict = "capacity"
            gates_out.append({
                "gate": gate,
                "label": meta["label"],
                "edge_gate": meta["edge_gate"],
                "blocked_n": len(items),
                "blocked_with_fwd": bstats["n"],
                "blocked_mean_fwd": bstats["mean_fwd"],
                "blocked_win_rate": bstats["win_rate"],
                "passed_mean_fwd": passed_mean,
                "passed_win_rate": passed_stats["win_rate"],
                "separation": sep,
                "verdict": verdict,
            })
        total_decisions += len(passed_items)
        total_with_fr += passed_stats["n"]
        accounts_out[acct] = {
            "passed": passed_stats,
            "gates": gates_out,
        }

    snapshot = {
        "computed_at": datetime.now().isoformat(),
        "lookback_days": lookback_days,
        "horizon_bars": horizon_bars,
        "compute_seconds": round(time.time() - t0, 1),
        "coverage": {
            "decisions": total_decisions,
            "with_forward_return": total_with_fr,
            "symbols": len(symbols_needed),
        },
        "accounts": accounts_out,
        "notes": (
            "Forward return is gross, direction-aware, over horizon_bars daily "
            "bars from the decision timestamp. separation>0 ⇒ gate blocks "
            "worse-than-passed signals (helps); separation<0 ⇒ gate blocks "
            "better-than-passed (hurts). edge_gate=false gates (balance/dedup/"
            "caps) block for capacity reasons, not signal quality."
        ),
    }
    return snapshot


# --- snapshot persistence / access ---------------------------------------

def set_snapshot(snapshot: Dict[str, Any]) -> None:
    global _SNAPSHOT
    with _LOCK:
        _SNAPSHOT = snapshot
        try:
            _SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_SNAPSHOT_PATH, "w") as f:
                json.dump(snapshot, f)
        except Exception as e:
            logger.debug("gate_scoreboard: persist failed: %s", e)


def get_snapshot() -> Optional[Dict[str, Any]]:
    global _SNAPSHOT
    with _LOCK:
        if _SNAPSHOT is not None:
            return _SNAPSHOT
        try:
            if _SNAPSHOT_PATH.exists():
                with open(_SNAPSHOT_PATH) as f:
                    _SNAPSHOT = json.load(f)
                    return _SNAPSHOT
        except Exception as e:
            logger.debug("gate_scoreboard: load failed: %s", e)
    return None


def compute_and_store(
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    horizon_bars: int = DEFAULT_HORIZON_BARS,
) -> Dict[str, Any]:
    """Compute the scoreboard and persist it. Safe to call from a worker
    thread (daily sync) or a manual trigger endpoint."""
    snap = compute_gate_scoreboard(lookback_days=lookback_days, horizon_bars=horizon_bars)
    set_snapshot(snap)
    logger.info(
        "Gate scoreboard computed: %d decisions, %d with forward-return, %d symbols, %.1fs",
        snap["coverage"]["decisions"], snap["coverage"]["with_forward_return"],
        snap["coverage"]["symbols"], snap["compute_seconds"],
    )
    return snap
