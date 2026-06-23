#!/usr/bin/env python3
"""Gate scoreboard — READ-ONLY (Tier 1 observability).

Computes and prints the per-gate, per-account blocked-vs-passed forward-return
counterfactual from signal_decisions. Also persists the snapshot so the
/analytics/observability/gate-scoreboard endpoint serves it.

A gate "helps" when the cohort it blocks would have done WORSE (forward) than
the cohort that cleared all gates; it "hurts" when it blocks BETTER signals.

Run on EC2:
    cd /home/ubuntu/alphacent && set -a && . ./.env.production && set +a \
        && ./venv/bin/python3 scripts/verify_gate_scoreboard.py [--lookback 14] [--horizon 5]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analytics.gate_scoreboard import compute_and_store


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lookback", type=int, default=14)
    ap.add_argument("--horizon", type=int, default=5)
    args = ap.parse_args()

    snap = compute_and_store(lookback_days=args.lookback, horizon_bars=args.horizon)

    print(f"\ncomputed_at={snap['computed_at']}  compute={snap['compute_seconds']}s")
    print(f"coverage: {snap['coverage']}")
    print(f"horizon={snap['horizon_bars']} bars, lookback={snap['lookback_days']}d\n")
    print("=" * 96)

    for acct in ("demo", "live"):
        a = snap["accounts"].get(acct, {})
        p = a.get("passed", {})
        gates = a.get("gates", [])
        if not gates and not p.get("n"):
            continue
        print(f"\nACCOUNT: {acct.upper()}   passed cohort: n={p.get('n')} "
              f"mean_fwd={p.get('mean_fwd')} win_rate={p.get('win_rate')}")
        print(f"  {'gate':24} {'blk_n':>6} {'fwd_blk':>9} {'win_blk':>8} "
              f"{'fwd_pass':>9} {'sep':>9}  verdict")
        for g in gates:
            tag = "EDGE" if g["edge_gate"] else "cap "
            print(f"  {g['label'][:24]:24} {g['blocked_n']:>6} "
                  f"{str(g['blocked_mean_fwd']):>9} {str(g['blocked_win_rate']):>8} "
                  f"{str(g['passed_mean_fwd']):>9} {str(g['separation']):>9}  "
                  f"{g['verdict']:<18} [{tag}]")
    print("\n" + "=" * 96)
    print("sep>0 ⇒ gate blocks worse-than-passed (HELPS); sep<0 ⇒ blocks "
          "better-than-passed (HURTS — destroying edge). [EDGE]=quality gate, "
          "[cap]=capacity/risk gate (balance/dedup/exposure).")


if __name__ == "__main__":
    main()
