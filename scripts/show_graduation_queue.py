#!/usr/bin/env python3
"""Read-only: print the current graduation queue (CIO candidate list).

Calls graduation_gate.get_graduation_queue and prints each qualified
(template, symbol) pair with its key stats. Does NOT modify anything — the queue
is a recommendation list; live activation is a separate CIO-approved action.

USAGE (on EC2):
  cd /home/ubuntu/alphacent
  set -a && . ./.env.production && set +a
  venv/bin/python3 scripts/show_graduation_queue.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from src.models.database import get_database
from src.strategy.graduation_gate import get_graduation_queue


def main() -> int:
    db = get_database()
    session = db.get_session()
    try:
        queue = get_graduation_queue(session)
    finally:
        session.close()

    print(f"\nGRADUATION QUEUE — {len(queue)} qualified pair(s)\n")
    for q in queue:
        print(
            f"  {q.get('template_name')} | {q.get('symbol')}: "
            f"trades={q.get('paper_trades')} sharpe={q.get('paper_sharpe')} "
            f"wr={q.get('paper_win_rate')} pnl={q.get('paper_total_pnl')} "
            f"wf={q.get('wf_sharpe')} ratio={q.get('qualification_ratio')}"
        )
    if not queue:
        print("  (empty)")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
