#!/usr/bin/env python3
"""Regime-dormancy validation backtest — READ-ONLY (design §7, 2026-06-30).

The dormancy decision (sleep regime-mismatched validated strategies and wake them
when their regime returns, INSTEAD of retiring + deleting + rebuilding) pays off
only if BOTH hold:

  (A) Regime-matched strategies have a real, persistent edge — already shown by
      scripts/backtest_pullback_gate_value.py (trend LONG profits in uptrends;
      mean-reversion/oversold profits in pullback/severe). Not re-derived here.

  (B) Regimes RECUR on a timescale short enough that keeping a validated strategy
      warm beats deleting it and paying the rebuild cost (re-proposal cadence +
      walk-forward re-validation, which in an up-biased window often REJECTS the
      very short/MR strategies we'd want back — see the SHORT funnel: SHORT WF
      pass 2.9% vs LONG 8.8%). If a regime's typical "away" gap is weeks-to-months,
      dormancy redeploys instantly on return while retire-and-rebuild lags and may
      never re-validate the edge.

This script quantifies (B): it replays the LIVE sub-regime classifier
(market_analyzer.detect_sub_regime thresholds) per trading day over 2021-2026 from
SPY/QQQ/DIA daily OHLC, builds the regime timeline, and reports per-regime episode
count, dwell, and recurrence gap.

Run on EC2:
    cd /home/ubuntu/alphacent && set -a && . ./.env.production && set +a \
        && ./venv/bin/python3 scripts/backtest_regime_dormancy.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from sqlalchemy import text
from src.models.database import get_database

BROAD = ["SPY", "QQQ", "DIA"]


def load_ohlc():
    db = get_database()
    session = db.get_session()
    try:
        rows = session.execute(text("""
            SELECT symbol, date, high, low, close FROM historical_price_cache
            WHERE interval='1d' AND symbol = ANY(:syms) AND close IS NOT NULL
            ORDER BY symbol, date
        """), {"syms": BROAD}).fetchall()
    finally:
        session.close()
    series = {}
    for sym, dt, hi, lo, cl in rows:
        d = dt.replace(tzinfo=None) if getattr(dt, "tzinfo", None) else dt
        series.setdefault((sym or "").upper(), []).append(
            (d, float(hi) if hi else float(cl), float(lo) if lo else float(cl), float(cl))
        )
    return series


def classify(chg20, chg50, atr_ratio):
    """Exact replica of market_analyzer.detect_sub_regime classification."""
    trend_score = chg20 * 0.6 + chg50 * 0.4
    if trend_score > 0.04 and chg20 > 0.03 and chg50 > 0.05:
        return "trending_up_strong"
    if trend_score > 0.015 and chg20 > 0.01:
        return "trending_up_weak"
    if trend_score < -0.04 and chg20 < -0.03 and chg50 < -0.05:
        return "trending_down_strong"
    if trend_score < -0.015 and chg20 < -0.01:
        return "trending_down_weak"
    if atr_ratio < 0.02:
        return "ranging_low_vol"
    if atr_ratio > 0.03:
        return "ranging_high_vol"
    return "ranging"


def main():
    series = load_ohlc()
    if not all(len(series.get(s, [])) > 60 for s in BROAD):
        print("insufficient broad-market OHLC"); return
    spy_dates = [d for d, _, _, _ in series["SPY"]]
    n = len(spy_dates)

    # Per-symbol arrays aligned by index (all three share the SPY calendar length).
    arrs = {s: series[s] for s in BROAD if len(series[s]) == n}

    regime_by_day = []  # (date, regime)
    for i in range(n):
        if i < 50:
            continue
        chg20s, chg50s, atrs = [], [], []
        for s, bars in arrs.items():
            closes = [b[3] for b in bars]
            c = closes[i]
            chg20s.append(c / closes[i - 20] - 1.0)
            chg50s.append(c / closes[i - 50] - 1.0)
            # ATR(14): mean true range over last 14 bars / current price
            trs = []
            for k in range(i - 13, i + 1):
                hi, lo, cl = bars[k][1], bars[k][2], bars[k][3]
                prev_c = bars[k - 1][3]
                trs.append(max(hi - lo, abs(hi - prev_c), abs(lo - prev_c)))
            atrs.append((sum(trs) / len(trs)) / c if c else 0.02)
        if not chg20s:
            continue
        regime = classify(np.mean(chg20s), np.mean(chg50s), np.mean(atrs))
        regime_by_day.append((spy_dates[i], regime))

    print(f"\nRegime-dormancy validation — {len(regime_by_day)} trading days "
          f"({regime_by_day[0][0].date()} → {regime_by_day[-1][0].date()})\n")

    # Episodes: contiguous runs of the same regime.
    episodes = {}  # regime -> list of (start_date, end_date, length_days)
    run_regime = regime_by_day[0][1]
    run_start = regime_by_day[0][0]
    run_len = 1
    prev_date = regime_by_day[0][0]
    for d, r in regime_by_day[1:]:
        if r == run_regime:
            run_len += 1
            prev_date = d
        else:
            episodes.setdefault(run_regime, []).append((run_start, prev_date, run_len))
            run_regime, run_start, run_len, prev_date = r, d, 1, d
    episodes.setdefault(run_regime, []).append((run_start, prev_date, run_len))

    print(f"{'regime':<22} {'days':>5} {'%time':>6} {'episodes':>9} {'med_dwell':>10} {'med_gap_days':>13}")
    total_days = len(regime_by_day)
    for regime in sorted(episodes, key=lambda r: -sum(e[2] for e in episodes[r])):
        eps = episodes[regime]
        days = sum(e[2] for e in eps)
        dwells = [e[2] for e in eps]
        # Recurrence gap: trading days between the end of one episode and the start
        # of the next episode of the SAME regime.
        gaps = []
        for j in range(1, len(eps)):
            prev_end = eps[j - 1][1]
            this_start = eps[j][0]
            gap = sum(1 for d, _ in regime_by_day if prev_end < d < this_start)
            gaps.append(gap)
        med_dwell = int(np.median(dwells)) if dwells else 0
        med_gap = int(np.median(gaps)) if gaps else -1
        print(f"{regime:<22} {days:>5} {100*days/total_days:>5.1f}% {len(eps):>9} "
              f"{med_dwell:>10} {med_gap if med_gap>=0 else 'n/a':>13}")

    # Headline: recurrence frequency for the styles dormancy parks (the
    # non-uptrend regimes that bench the trend book today).
    print("\n=== DORMANCY VERDICT INPUTS ===")
    for regime in ("ranging_low_vol", "ranging", "ranging_high_vol",
                   "trending_down_weak", "trending_down_strong"):
        eps = episodes.get(regime, [])
        if len(eps) < 2:
            print(f"  {regime:<22} episodes={len(eps)} — too few to recur")
            continue
        gaps = []
        for j in range(1, len(eps)):
            gap = sum(1 for d, _ in regime_by_day if eps[j-1][1] < d < eps[j][0])
            gaps.append(gap)
        print(f"  {regime:<22} {len(eps)} episodes, recurs every ~{int(np.median(gaps))} "
              f"trading days (median gap); med dwell {int(np.median([e[2] for e in eps]))}d")
    print("\nINTERPRETATION: a regime that recurs every ~weeks-to-few-months means a "
          "strategy retired on regime-exit must be re-proposed AND re-pass WF before it "
          "redeploys — vs dormancy waking the kept, already-validated edge instantly. "
          "The shorter+more frequent the recurrence, the larger dormancy's edge.")


if __name__ == "__main__":
    main()
