#!/usr/bin/env python3
"""Pullback-gate regime-scope backtest — READ-ONLY (Tier 1).

The gate scoreboard shows the pullback gate blocks winners in the current
uptrend. This quantifies the proposed fix: exempt DAILY trend-following LONGs
from the MODERATE pullback block WHEN the broad market is in a confirmed 50d
uptrend (keep blocking intraday/momentum, keep the gate in ranging/down regimes).

For every moderate pullback-block decision it reconstructs:
  - the symbol's forward N-bar return (the counterfactual "would it have won"),
  - the broad-market (SPY) 50-day trend AS OF the block (confirmed uptrend?),
  - whether the blocked strategy is an exemptable daily trend-follower.
Then compares the would-exempt cohort's forward edge to the passed cohort.

If the would-exempt cohort's forward edge is materially positive (≈ passed or
better), exempting it recovers edge — the change is validated. The 50d gate
ensures we ONLY exempt in uptrends (in a downtrend the cohort would be empty).

Run on EC2:
    cd /home/ubuntu/alphacent && set -a && . ./.env.production && set +a \
        && ./venv/bin/python3 scripts/backtest_pullback_regime_scope.py [--days 90]
"""
import argparse
import bisect
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from sqlalchemy import text
from src.models.database import get_database
from src.analytics.gate_scoreboard import _load_bars_batch, _forward_return

HORIZON = 5
UPTREND_50D_MIN = 0.03   # broad-market 50d change > +3% ⇒ "confirmed uptrend"
BROAD_TREND_KW = ("ema ribbon", "adx", "trend following", "trend_following")
INTRADAY_KW = ("breakout", "momentum", "vwap trend", "atr dynamic", "opening range")


def is_exemptable_daily_trend(template_name: str) -> bool:
    """Matches the gate's moderate-exemption target: a DAILY broad-trend
    template that is not intraday-aggressive and not momentum."""
    t = (template_name or "").lower()
    if not t:
        return False
    is_daily = not (t.startswith("4h") or "4h " in t or " 4h" in t or "1h" in t)
    is_broad = any(k in t for k in BROAD_TREND_KW)
    is_intraday = any(k in t for k in INTRADAY_KW)
    is_momentum = "momentum" in t
    return is_daily and is_broad and not is_intraday and not is_momentum


def spy_50d_asof(spy_bars, ts):
    """Broad-market 50-trading-day change as of a timestamp."""
    if len(spy_bars) < 51:
        return None
    times = [b[0] for b in spy_bars]
    i = bisect.bisect_right(times, ts.replace(tzinfo=None) if getattr(ts, "tzinfo", None) else ts) - 1
    if i < 50:
        return None
    c_now, c_then = spy_bars[i][1], spy_bars[i - 50][1]
    return (c_now / c_then - 1.0) if c_then > 0 else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=90)
    args = ap.parse_args()

    db = get_database()
    session = db.get_session()
    try:
        cutoff = datetime.now() - timedelta(days=args.days)
        blocks = session.execute(text("""
            SELECT symbol, timestamp, template_name FROM signal_decisions
            WHERE timestamp >= :cut AND reason LIKE 'Pullback gate (moderate)%'
              AND symbol IS NOT NULL
        """), {"cut": cutoff}).fetchall()
        passed = session.execute(text("""
            SELECT symbol, timestamp FROM signal_decisions
            WHERE timestamp >= :cut AND stage='signal_emitted' AND decision='emitted'
              AND direction='long' AND symbol IS NOT NULL
        """), {"cut": cutoff}).fetchall()
    finally:
        session.close()

    symbols = {(r[0] or "").upper() for r in blocks} | {(r[0] or "").upper() for r in passed} | {"SPY"}
    bar_start = cutoff - timedelta(days=120)  # 50d trend + ATR headroom
    bars = _load_bars_batch(symbols, bar_start, datetime.now())
    spy = bars.get("SPY", [])

    def fwd(sym, ts):
        return _forward_return(bars.get(sym.upper(), []), ts, True, HORIZON)

    passed_fr = [v for v in (fwd(s, t) for s, t in passed) if v is not None]
    passed_mean = float(np.mean(passed_fr)) if passed_fr else None

    all_fr, uptrend_fr, exempt_fr, still_blocked_fr = [], [], [], []
    n_uptrend = 0
    for sym, ts, tmpl in blocks:
        fr = fwd(sym, ts)
        if fr is None:
            continue
        all_fr.append(fr)
        s50 = spy_50d_asof(spy, ts)
        in_uptrend = (s50 is not None and s50 >= UPTREND_50D_MIN)
        if in_uptrend:
            n_uptrend += 1
            uptrend_fr.append(fr)
            if is_exemptable_daily_trend(tmpl):
                exempt_fr.append(fr)
            else:
                still_blocked_fr.append(fr)

    def line(label, arr):
        if not arr:
            print(f"  {label:42} n={0}")
            return
        a = np.array(arr)
        sep = (a.mean() - passed_mean) if passed_mean is not None else float("nan")
        print(f"  {label:42} n={len(a):>5}  fwd={a.mean()*100:>6.2f}%  win={ (a>0).mean()*100:>4.0f}%  "
              f"sep_vs_passed={sep*100:>+6.2f}%")

    print(f"\nPullback-gate regime-scope backtest — {args.days}d, horizon={HORIZON} bars")
    print(f"confirmed-uptrend = SPY 50d change ≥ {UPTREND_50D_MIN:.0%}\n")
    print(f"  passed (emitted LONG) cohort: n={len(passed_fr)}  fwd={passed_mean*100 if passed_mean else float('nan'):.2f}%\n")
    line("ALL moderate pullback blocks", all_fr)
    line("  └ during confirmed uptrend", uptrend_fr)
    line("     ├ WOULD-EXEMPT (daily trend)", exempt_fr)
    line("     └ still blocked (intraday/momentum)", still_blocked_fr)
    print(f"\n  blocks during confirmed uptrend: {n_uptrend}/{len([1 for s,t,_ in blocks if fwd(s,t) is not None])} scored")
    print("\nVERDICT: if WOULD-EXEMPT fwd edge ≈ passed or better (sep ≥ ~0), exempting daily-trend "
          "LONGs in confirmed uptrends recovers edge. 'still blocked' staying weak ⇒ keep blocking those.")


if __name__ == "__main__":
    main()
