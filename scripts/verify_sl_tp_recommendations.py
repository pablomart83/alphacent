#!/usr/bin/env python3
"""MAE/MFE → SL/TP recommendations — READ-ONLY proof (Tier 1).

Computes (and optionally persists) the evidence-backed SL/TP recommendations
and prints them. Validates the SOXL case end-to-end (the leveraged-ETF stop
logic the manual diagnostic surfaced).

Run on EC2:
    cd /home/ubuntu/alphacent && set -a && . ./.env.production && set +a \
        && ./venv/bin/python3 scripts/verify_sl_tp_recommendations.py [--persist] [--min-trades 12]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analytics.sl_tp_recommender import (
    compute_recommendations,
    persist_recommendations,
)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--persist", action="store_true", help="write pending rows to improvement_recommendations")
    ap.add_argument("--min-trades", type=int, default=12)
    ap.add_argument("--lookback", type=int, default=120)
    args = ap.parse_args()

    recs = compute_recommendations(min_trades=args.min_trades, lookback_days=args.lookback)
    print(f"\n{len(recs)} SL/TP recommendation(s) (min_trades={args.min_trades}, lookback={args.lookback}d)\n")
    print("=" * 96)

    for r in sorted(recs, key=lambda x: (x["scope_type"], -x["n_trades"])):
        ev = r["evidence"]
        print(f"\n[{r['scope_type']}] {r['scope_key']}  (n={r['n_trades']}, {r.get('asset_class')}, "
              f"src={r.get('current_source')})")
        print(f"  SL {r['current_sl']:.1%} → {r['proposed_sl']:.1%}   "
              f"TP {r['current_tp']:.1%} → {r['proposed_tp']:.1%}   cap={ev['sl_cap']:.1%}")
        print(f"  {r['summary']}")
        print(f"  evidence: MAE p50/p80/p90={ev['mae_p50']:.1%}/{ev['mae_p80']:.1%}/{ev['mae_p90']:.1%}  "
              f"MFE p50/p75={ev['mfe_p50']:.1%}/{ev['mfe_p75']:.1%}  "
              f"realized_med={ev['realized_median']:.1%}  capture={ev['capture_ratio']:.0%}  "
              f"win={ev['win_rate']:.0%}  exp_capture_gain={ev['expected_capture_gain']:.1%}")

    # SOXL validation
    soxl = [r for r in recs if r["scope_key"] == "SOXL"]
    print("\n" + "=" * 96)
    if soxl:
        print(f"SOXL validation: recommendation present — {soxl[0]['summary']}")
    else:
        print("SOXL validation: no recommendation (current SL/TP already within MAE/MFE envelope, "
              "or insufficient tracked trades).")

    if args.persist:
        n = persist_recommendations(recs)
        print(f"\nPersisted {n} pending recommendation(s) to improvement_recommendations.")
    else:
        print("\n(dry run — pass --persist to write rows)")


if __name__ == "__main__":
    main()
