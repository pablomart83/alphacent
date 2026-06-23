#!/usr/bin/env python3
"""Trailing-stop ladder backtest — READ-ONLY (Tier 1).

Reconstructs each closed trade's intra-trade DAILY path from historical_price_cache
and replays the staged trailing ladder (breakeven → profit-lock → ATR trail) under
two configs:

  CURRENT  — the live position_manager params (BREAKEVEN/PROFIT_LOCK/TRAILING +
             ATR_MULTIPLIER_BY_ASSET_CLASS).
  PROPOSED — tighter: earlier breakeven, earlier+smaller profit lock so the +3-5%
             MFE band locks real profit, and a tighter in-profit trail. Leveraged
             ETFs drastically tightened (their +6%/+10%/+12% ladder never engages
             before they reverse).

Both configs replay on the SAME path + same initial SL, so the DELTA isolates the
ladder change. Daily-bar approximation (intraday breach uses the bar low/high);
absolute levels are approximate but the relative comparison is sound.

Run on EC2:
    cd /home/ubuntu/alphacent && set -a && . ./.env.production && set +a \
        && ./venv/bin/python3 scripts/backtest_trailing_stop.py [--days 90]
"""
import argparse
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from sqlalchemy import text
from src.models.database import get_database
from src.risk.sl_caps import is_leveraged_etf

# ── Ladder configs: per class {breakeven, lock_trigger, lock_pct, trail_act, trail_dist, atr_mult} ──
CURRENT = {
    "stock":         dict(be=0.03,  lt=0.05, lk=0.02, ta=0.05, td=0.07, am=2.0),
    "etf":           dict(be=0.025, lt=0.04, lk=0.015,ta=0.04, td=0.05, am=2.0),
    "leveraged_etf": dict(be=0.06,  lt=0.10, lk=0.04, ta=0.10, td=0.12, am=1.5),
    "crypto":        dict(be=0.05,  lt=0.08, lk=0.03, ta=0.08, td=0.10, am=1.5),
    "forex":         dict(be=0.015, lt=0.025,lk=0.01, ta=0.02, td=0.03, am=1.0),
    "commodity":     dict(be=0.03,  lt=0.05, lk=0.02, ta=0.05, td=0.07, am=2.0),
    "index":         dict(be=0.025, lt=0.04, lk=0.015,ta=0.04, td=0.05, am=1.5),
}
# PROPOSED: lock the +3-5% band, tighten the in-profit trail; leveraged hauled in hard.
PROPOSED = {
    "stock":         dict(be=0.02,  lt=0.03, lk=0.012,ta=0.035,td=0.04, am=1.25),
    "etf":           dict(be=0.015, lt=0.025,lk=0.01, ta=0.03, td=0.035,am=1.25),
    "leveraged_etf": dict(be=0.03,  lt=0.05, lk=0.025,ta=0.06, td=0.07, am=1.0),
    "crypto":        dict(be=0.035, lt=0.05, lk=0.02, ta=0.06, td=0.07, am=1.25),
    "forex":         dict(be=0.01,  lt=0.018,lk=0.008,ta=0.018,td=0.022,am=0.9),
    "commodity":     dict(be=0.02,  lt=0.035,lk=0.015,ta=0.04, td=0.05, am=1.5),
    "index":         dict(be=0.015, lt=0.025,lk=0.01, ta=0.03, td=0.035,am=1.25),
}
INIT_SL = {"stock":0.06,"etf":0.06,"leveraged_etf":0.15,"crypto":0.08,
           "forex":0.02,"commodity":0.04,"index":0.05}


def asset_class(symbol, classes):
    sym = (symbol or "").upper()
    if is_leveraged_etf(sym):
        return "leveraged_etf"
    return classes.get(sym, "stock")


def load_classes(session):
    """Map symbol -> class from tradeable_instruments."""
    from src.core.tradeable_instruments import (
        DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX, DEMO_ALLOWED_COMMODITIES,
        DEMO_ALLOWED_INDICES, DEMO_ALLOWED_ETFS,
    )
    m = {}
    for s in DEMO_ALLOWED_CRYPTO: m[s.upper()] = "crypto"
    for s in DEMO_ALLOWED_FOREX: m[s.upper()] = "forex"
    for s in DEMO_ALLOWED_COMMODITIES: m[s.upper()] = "commodity"
    for s in DEMO_ALLOWED_INDICES: m[s.upper()] = "index"
    for s in DEMO_ALLOWED_ETFS: m[s.upper()] = "etf"
    return m


def get_bars(session, symbol, start, end):
    rows = session.execute(text("""
        SELECT date, open, high, low, close FROM historical_price_cache
        WHERE interval='1d' AND UPPER(symbol)=:s AND date >= :a AND date <= :b
        ORDER BY date
    """), {"s": symbol.upper(), "a": start, "b": end}).fetchall()
    return [(r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in rows
            if all(v is not None for v in r[1:])]


def atr_pct(bars_before, ref_price):
    if len(bars_before) < 5 or ref_price <= 0:
        return None
    trs = []
    for i in range(1, len(bars_before)):
        h, l, pc = bars_before[i][2], bars_before[i][3], bars_before[i-1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return None
    return (sum(trs[-14:]) / min(14, len(trs[-14:]))) / ref_price


def simulate(entry, path_bars, is_long, cfg, atrp, init_sl):
    """Replay the ladder over the intra-trade daily path. Returns realized
    fractional return."""
    if entry <= 0 or not path_bars:
        return None
    trail_dist = max(cfg["td"], (atrp or 0) * cfg["am"])
    if is_long:
        stop = entry * (1 - init_sl)
        hwm = entry
        for (_, o, h, l, c) in path_bars:
            if l <= stop:
                return stop / entry - 1.0
            hwm = max(hwm, h)
            prof = hwm / entry - 1.0
            if prof >= cfg["ta"]:
                stop = max(stop, hwm * (1 - trail_dist))
            elif prof >= cfg["lt"]:
                stop = max(stop, entry * (1 + cfg["lk"]))
            elif prof >= cfg["be"]:
                stop = max(stop, entry)
        return path_bars[-1][4] / entry - 1.0
    else:
        stop = entry * (1 + init_sl)
        lwm = entry
        for (_, o, h, l, c) in path_bars:
            if h >= stop:
                return 1.0 - stop / entry
            lwm = min(lwm, l)
            prof = 1.0 - lwm / entry
            if prof >= cfg["ta"]:
                stop = min(stop, lwm * (1 + trail_dist))
            elif prof >= cfg["lt"]:
                stop = min(stop, entry * (1 - cfg["lk"]))
            elif prof >= cfg["be"]:
                stop = min(stop, entry)
        return 1.0 - path_bars[-1][4] / entry


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=90)
    args = ap.parse_args()

    db = get_database()
    session = db.get_session()
    try:
        classes = load_classes(session)
        cutoff = datetime.now() - timedelta(days=args.days)
        trades = session.execute(text("""
            SELECT symbol, entry_price, entry_time, exit_time, side, pnl_percent
            FROM trade_journal
            WHERE exit_time >= :cut AND entry_time IS NOT NULL AND entry_price > 0
              AND exit_reason LIKE 'Trailing stop%'
        """), {"cut": cutoff}).fetchall()

        agg = defaultdict(lambda: {"n":0,"cur":[],"prop":[],"actual":[],"mfe_cap_cur":[],"mfe_cap_prop":[]})
        skipped = 0
        for sym, entry, et, xt, side, actual_pct in trades:
            cls = asset_class(sym, classes)
            is_long = (side or "BUY").upper() in ("BUY", "LONG")
            pre = get_bars(session, sym, et - timedelta(days=30), et)
            path = get_bars(session, sym, et, xt + timedelta(days=1))
            if len(path) < 2:
                skipped += 1
                continue
            atrp = atr_pct(pre, float(entry))
            init = INIT_SL.get(cls, 0.06)
            r_cur = simulate(float(entry), path, is_long, CURRENT[cls], atrp, init)
            r_prop = simulate(float(entry), path, is_long, PROPOSED[cls], atrp, init)
            if r_cur is None or r_prop is None:
                skipped += 1
                continue
            a = agg[cls]
            a["n"] += 1
            a["cur"].append(r_cur)
            a["prop"].append(r_prop)
            if actual_pct is not None:
                a["actual"].append(float(actual_pct) / 100.0)

        print(f"\nTrailing-stop ladder backtest — {args.days}d, TSL-exit trades, daily-path replay")
        print(f"(skipped {skipped} trades with insufficient cached bars)\n")
        print(f"{'class':14} {'n':>4} {'actual%':>8} {'CURRENT%':>9} {'PROPOSED%':>10} {'delta':>8} {'cur_win':>8} {'prop_win':>9}")
        tot = {"n":0,"cur":0.0,"prop":0.0,"actual":0.0}
        for cls, a in sorted(agg.items(), key=lambda kv: -kv[1]["n"]):
            if a["n"] == 0:
                continue
            cur = np.array(a["cur"]); prop = np.array(a["prop"])
            actual = np.array(a["actual"]) if a["actual"] else np.array([np.nan])
            cur_win = float((cur > 0).mean()); prop_win = float((prop > 0).mean())
            print(f"{cls:14} {a['n']:>4} {np.nanmean(actual)*100:>7.2f}% {cur.mean()*100:>8.2f}% "
                  f"{prop.mean()*100:>9.2f}% {(prop.mean()-cur.mean())*100:>+7.2f}% "
                  f"{cur_win*100:>7.0f}% {prop_win*100:>8.0f}%")
            tot["n"] += a["n"]; tot["cur"] += cur.sum(); tot["prop"] += prop.sum()
            tot["actual"] += (actual[~np.isnan(actual)].sum() if a["actual"] else 0.0)
        if tot["n"]:
            print("-"*78)
            print(f"{'ALL':14} {tot['n']:>4} {tot['actual']/tot['n']*100:>7.2f}% "
                  f"{tot['cur']/tot['n']*100:>8.2f}% {tot['prop']/tot['n']*100:>9.2f}% "
                  f"{(tot['prop']-tot['cur'])/tot['n']*100:>+7.2f}%")
            print(f"\nPer-trade avg return delta (PROPOSED − CURRENT): "
                  f"{(tot['prop']-tot['cur'])/tot['n']*100:+.2f} pts over {tot['n']} trades")
            print("NOTE: 'actual%' = realized P&L of these trades; 'CURRENT%' = our replay of the "
                  "live ladder (sanity check it tracks actual); 'PROPOSED%' = tighter ladder. "
                  "Daily-bar approximation — relative delta is the signal.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
