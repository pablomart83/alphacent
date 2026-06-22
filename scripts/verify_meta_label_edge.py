#!/usr/bin/env python3
"""Meta-label edge proof — READ-ONLY, prove-first (Tier 1).

Trains the per-asset-class meta-label model on ALL realized trades
(trade_journal, exit_time IS NOT NULL) and reports HONEST out-of-sample edge
using PURGED + EMBARGOED walk-forward CV:

  - per asset class: n, base win-rate, OOS precision/recall/F1/AUC
  - calibration (reliability) bins
  - feature importance (which features predict winners)
  - a held-out ECONOMIC backtest of "filter/size by P(win)" vs "trade
    everything", with OUR per-asset-class costs already netted into returns

Honest by construction: if a class's model does not beat its base rate / does
not improve cost-net return over trade-everything, the report says so and the
class is left UNTRAINED (no model file written) unless --persist is passed.

Run on EC2 via venv (read-only DB):
    ./venv/bin/python3 scripts/verify_meta_label_edge.py
    ./venv/bin/python3 scripts/verify_meta_label_edge.py --persist   # write .pkl
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from src.models.database import get_database
from src.ml.meta_label_trainer import (
    MetaLabelTrainer,
    build_samples,
)

TRADE_QUERY = """
    SELECT id, symbol, side, entry_time, exit_time, entry_price, entry_size,
           pnl, pnl_percent, hold_time_hours, market_regime, sector,
           conviction_score, account_type, trade_metadata
    FROM trade_journal
    WHERE exit_time IS NOT NULL
    ORDER BY entry_time ASC
"""


def load_rows(session):
    rows = session.execute(text(TRADE_QUERY)).mappings().all()
    return [dict(r) for r in rows]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--persist", action="store_true",
                    help="write per-asset-class .pkl models (default: report only)")
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()

    db = get_database()
    session = db.get_session()
    try:
        rows = load_rows(session)
    finally:
        session.close()

    print(f"\nLoaded {len(rows)} closed trades from trade_journal")
    samples = build_samples(rows)
    print(f"Built {len(samples)} labeled samples (cost-net, our costs)\n")

    by_class = defaultdict(list)
    for s in samples:
        by_class[s.asset_class].append(s)

    print("Sample distribution by asset class:")
    for ac in sorted(by_class, key=lambda k: -len(by_class[k])):
        grp = by_class[ac]
        wins = sum(s.label for s in grp)
        print(f"  {ac:12} n={len(grp):5}  cost-net win-rate={wins/len(grp):.3f}")
    print()

    trainer = MetaLabelTrainer(n_folds=args.folds)
    print("=" * 78)
    for ac in sorted(by_class, key=lambda k: -len(by_class[k])):
        grp = by_class[ac]
        res = trainer.fit_and_persist_class(grp) if args.persist else trainer.cross_validate_class(grp)
        print(f"\nASSET CLASS: {ac}   (n={res.n_samples}, base win-rate={res.base_rate})")
        if res.skip_reason:
            print(f"  SKIP — {res.skip_reason}")
            continue
        lift = res.oos_precision - res.base_rate
        print(f"  OOS precision={res.oos_precision}  recall={res.oos_recall}  "
              f"F1={res.oos_f1}  AUC={res.oos_auc}  ({res.n_folds} folds)")
        print(f"  precision LIFT over base rate: {lift:+.4f}  "
              f"({'EDGE' if lift > 0.02 and res.oos_auc and res.oos_auc > 0.53 else 'NO CLEAR EDGE'})")
        econ = res.economic or {}
        if econ:
            print(f"  economic (cost-net avg return/trade, OUR costs):")
            print(f"    A trade-everything : {econ.get('policy_A_trade_all_avg_net')}")
            print(f"    B enforce(P>=.5)   : {econ.get('policy_B_enforce_avg_net')}  "
                  f"coverage={econ.get('policy_B_coverage')}")
            print(f"    C prob-sized       : {econ.get('policy_C_prob_sized_avg_net')}")
            print(f"    blocked cohort avg : {econ.get('blocked_cohort_avg_net')}")
            print(f"    passed  cohort avg : {econ.get('passed_cohort_avg_net')}")
            print(f"    separation (pass-blocked): {econ.get('separation')}")
        if res.feature_importance:
            top = list(res.feature_importance.items())[:8]
            print("  top features: " + ", ".join(f"{k}={v}" for k, v in top))
        if res.calibration:
            print("  calibration (pred->realized, n):")
            for b in res.calibration:
                print(f"    [{b['bin_low']:.1f}-{b['bin_high']:.1f}] "
                      f"pred={b['predicted']:.3f} real={b['realized']:.3f} n={b['count']}")
    print("\n" + "=" * 78)
    print("Honest verdict: a class shows EDGE only if OOS precision beats its base "
          "rate AND AUC>0.53 AND the enforce/prob-sized policy's cost-net return "
          "beats trade-everything. Otherwise leave it disabled.")


if __name__ == "__main__":
    main()
