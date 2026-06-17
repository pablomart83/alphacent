#!/usr/bin/env python3
"""
CLI wrapper for the LIVE execution-cost (slippage) backfill.

Core logic lives in src/analytics/execution_cost_backfill.py (shared with
MonitoringService._run_daily_sync, which runs it once per day). This script is
for manual / ad-hoc runs and verification.

WHY: production close paths journal exits with the close-DECISION price and never
capture eToro's actual executed close rate, so trade_journal.exit_slippage was
100% NULL. This pulls eToro's real executed rates (get_trade_history, LIVE) and
reconciles each closed trade to broker ground truth, computing true execution
slippage (decision price vs actual close) with the same drift guard as entries.

USAGE (on EC2):
  set -a && . ./.env.production && set +a
  venv/bin/python3 scripts/backfill_execution_costs.py --min-date 2026-05-01           # dry-run
  venv/bin/python3 scripts/backfill_execution_costs.py --min-date 2026-05-01 --apply   # write
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta

sys.path.insert(0, ".")

from src.analytics.execution_cost_backfill import backfill_live_execution_costs


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill LIVE exit slippage from eToro trade history")
    ap.add_argument("--min-date", default=(datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d"),
                    help="Earliest close date to reconcile (YYYY-MM-DD). Default: 90 days ago.")
    ap.add_argument("--apply", action="store_true", help="Write changes. Omit for a dry run.")
    args = ap.parse_args()

    print(f"{'APPLY' if args.apply else 'DRY RUN'}: backfilling LIVE execution costs since {args.min_date} ...")
    stats = backfill_live_execution_costs(min_date=args.min_date, apply=args.apply)

    print("\n=== SUMMARY ===")
    for k, v in stats.items():
        print(f"  {k:22s} {v}")
    if not args.apply:
        print("\nDRY RUN — no changes written. Re-run with --apply to persist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
