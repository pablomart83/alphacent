#!/usr/bin/env python3
"""
CLI wrapper to seed the durable WF-validation ledger from current state.

Core logic lives in src/strategy/wf_ledger.py. The proposer upserts the ledger
on every walk-forward pass going forward; this script seeds it from the
currently-surviving `strategies` rows so already-established (template, symbol)
pairs are covered immediately, without waiting for a re-validation cycle.

WHY: the graduation gate divides paper Sharpe by the WF test Sharpe. That Sharpe
lives in strategies.strategy_metadata JSON, which dies with the row when the
BACKTESTED TTL deletes a stale version. When every surviving version of a
template loses its WF Sharpe at once (deleted + not-yet-re-validated), the gate
fail-closes a pair whose WF edge WAS established. The ledger (no TTL, keyed by
(template, symbol)) persists that edge so recovery survives version deletion.

Idempotent — safe to re-run. Creating the table is automatic on backend start
(Base.metadata.create_all); this only populates rows.

USAGE (on EC2):
  cd /home/ubuntu/alphacent
  venv/bin/python3 scripts/backfill_wf_ledger.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from src.models.database import get_database  # noqa: E402  (ensures table exists)
from src.strategy.wf_ledger import backfill_from_current_state  # noqa: E402


def main() -> int:
    # Touch the DB so Base.metadata.create_all has created wf_validation_ledger.
    get_database()

    print("Seeding wf_validation_ledger from surviving strategies ...")
    stats = backfill_from_current_state()

    print("\n=== SUMMARY ===")
    for k, v in stats.items():
        print(f"  {k:22s} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
