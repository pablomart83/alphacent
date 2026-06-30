#!/usr/bin/env python3
"""Restore validated, regime-churned RETIRED strategies as DORMANT (2026-06-30).

The 15 currently-RETIRED strategies are all activation-approved with positive
walk-forward Sharpe and 0-1 live trades — i.e. validated edges that were retired
(and are about to be deleted by the next cleanup) WITHOUT decaying on their own
merits. They are regime-mismatched (trend/momentum-heavy in the current ranging
regime), the signature of regime-churn. Under the dormancy model these should be
SLEPT (kept), not deleted.

This flips RETIRED -> BACKTESTED + regime_dormant=true so they are:
  - exempt from cleanup deletion (kept warm),
  - skipped by signal generation (they're regime-mismatched right now),
  - auto-woken when their regime returns ONCE regime_dormancy.enabled=true.

The dormant STATE works regardless of the enabled toggle; we are NOT enabling the
feature here (auto-wake stays off until the regime-authority shadow-watch).

Idempotent: only touches status=RETIRED rows that are activation_approved (the
validated ones); re-running is a no-op. Run with --apply to write; default is a
dry run.

Run on EC2:
    cd /home/ubuntu/alphacent && set -a && . ./.env.production && set +a \
        && ./venv/bin/python3 scripts/restore_regime_retired_as_dormant.py --apply
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm.attributes import flag_modified
from src.models.database import get_database
from src.models.orm import StrategyORM
from src.models.enums import StrategyStatus

REASON = ("Restored from RETIRED as dormant 2026-06-30 — validated edge "
          "(activation_approved, positive WF) with 0-1 live trades: regime-churned, "
          "not decayed. Benched until its regime returns.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args()

    db = get_database()
    session = db.get_session()
    try:
        retired = session.query(StrategyORM).filter(
            StrategyORM.status == StrategyStatus.RETIRED
        ).all()

        candidates = []
        skipped = []
        for s in retired:
            meta = s.strategy_metadata if isinstance(s.strategy_metadata, dict) else {}
            if str(meta.get("activation_approved")).lower() == "true":
                candidates.append((s, meta))
            else:
                skipped.append((s, meta))

        print(f"\nRETIRED total: {len(retired)} | validated (restore): {len(candidates)} | "
              f"not-approved (skip): {len(skipped)}\n")
        for s, meta in candidates:
            wf = meta.get("wf_test_sharpe")
            print(f"  RESTORE  {s.name[:42]:<42} type={meta.get('template_type','?'):<14} "
                  f"wf={wf}")
        for s, meta in skipped:
            print(f"  skip     {s.name[:42]:<42} (not activation_approved)")

        if not args.apply:
            print(f"\n[DRY RUN] would restore {len(candidates)} strategies as dormant. "
                  f"Re-run with --apply to write.")
            return

        now_iso = datetime.now().isoformat()
        n = 0
        for s, meta in candidates:
            s.status = StrategyStatus.BACKTESTED
            s.retired_at = None
            meta["regime_dormant"] = True
            meta["dormant_reason"] = REASON
            meta["dormant_since"] = now_iso
            meta["restored_from_retired"] = True
            meta["restored_at"] = now_iso
            # Clear stale retirement flags; preserve activation_approved.
            meta.pop("regime_retired", None)
            meta.pop("regime_retirement_reason", None)
            meta.pop("pending_retirement", None)
            s.strategy_metadata = meta
            flag_modified(s, "strategy_metadata")
            n += 1
        session.commit()
        print(f"\n[APPLIED] restored {n} strategies: RETIRED -> BACKTESTED + regime_dormant=true.")

        # Verify
        dormant = session.query(StrategyORM).filter(
            StrategyORM.status == StrategyStatus.BACKTESTED
        ).all()
        dcount = sum(1 for x in dormant
                     if isinstance(x.strategy_metadata, dict)
                     and x.strategy_metadata.get("regime_dormant"))
        still_retired = session.query(StrategyORM).filter(
            StrategyORM.status == StrategyStatus.RETIRED).count()
        print(f"[VERIFY] regime_dormant BACKTESTED now: {dcount} | still RETIRED: {still_retired}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
