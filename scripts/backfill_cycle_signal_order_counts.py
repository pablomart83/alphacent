#!/usr/bin/env python3
"""Backfill signals/orders counts on autonomous_cycle_runs from cycle_history.log.

The cycle row's signals_generated / signals_passed / orders_submitted / orders_filled
were never written by _update_cycle_run (fixed forward 2026-06-30), so historical
rows show 0 even when Stage 7b produced signals/orders. The cycle history log
(logs/cycles/cycle_history.log) DID record the true per-cycle counts:

    CYCLE cycle_1782826970 | 2026-06-30 13:56:53
      [SIGNALS] 1 generated -> 1 coordinated -> 0 rejected
      [ORDERS] 1 submitted this cycle, 0 confirmed filled since last cycle

This parses those blocks and updates the matching autonomous_cycle_runs row (joined
by cycle_id, which matches). Source of truth = the log. Idempotent. Default dry-run;
pass --apply to write.

Run on EC2:
    cd /home/ubuntu/alphacent && set -a && . ./.env.production && set +a \
        && ./venv/bin/python3 scripts/backfill_cycle_signal_order_counts.py --apply
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models.database import get_database
from src.models.orm import AutonomousCycleRunORM

LOG_PATH = Path("logs/cycles/cycle_history.log")
_CYCLE_RE = re.compile(r"^CYCLE\s+(\S+)\s*\|", re.M)
_SIGNALS_RE = re.compile(r"\[SIGNALS\]\s+(\d+)\s+generated\s*->\s*(\d+)\s+coordinated\s*->\s*(\d+)\s+rejected")
_ORDERS_RE = re.compile(r"\[ORDERS\]\s+(\d+)\s+submitted this cycle,\s+(\d+)\s+confirmed filled")


def parse_log():
    """Return {cycle_id: {signals_generated, signals_passed, orders_submitted, orders_filled}}."""
    if not LOG_PATH.exists():
        print(f"log not found: {LOG_PATH}")
        return {}
    text = LOG_PATH.read_text(errors="replace")
    # Split into per-cycle blocks on the CYCLE marker.
    matches = list(_CYCLE_RE.finditer(text))
    out = {}
    for i, m in enumerate(matches):
        cid = m.group(1)
        block = text[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        sig = _SIGNALS_RE.search(block)
        om = _ORDERS_RE.search(block)
        rec = {}
        if sig:
            rec["signals_generated"] = int(sig.group(1))
            rec["signals_passed"] = int(sig.group(2))  # coordinated
        if om:
            rec["orders_submitted"] = int(om.group(1))
            rec["orders_filled"] = int(om.group(2))
        if rec:
            # last block for a cycle_id wins (cycles are unique anyway)
            out[cid] = rec
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args()

    parsed = parse_log()
    print(f"parsed {len(parsed)} cycle blocks from {LOG_PATH}")
    nonzero = {c: r for c, r in parsed.items()
               if any(r.get(k, 0) for k in ("signals_generated", "orders_submitted", "orders_filled"))}
    print(f"  of which {len(nonzero)} have non-zero signals/orders")

    db = get_database()
    session = db.get_session()
    try:
        matched = updated = corrected_nonzero = 0
        for cid, rec in parsed.items():
            run = session.query(AutonomousCycleRunORM).filter_by(cycle_id=cid).first()
            if not run:
                continue
            matched += 1
            changes = {}
            for k, v in rec.items():
                if getattr(run, k, None) != v:
                    changes[k] = (getattr(run, k, None), v)
            if not changes:
                continue
            if any(rec.get(k, 0) for k in ("signals_generated", "orders_submitted", "orders_filled")):
                corrected_nonzero += 1
            if args.apply:
                for k, v in rec.items():
                    setattr(run, k, v)
            updated += 1
        if args.apply:
            session.commit()
        print(f"matched {matched} cycle rows; "
              f"{'updated' if args.apply else 'WOULD update'} {updated} "
              f"({corrected_nonzero} with non-zero corrections)")
        if not args.apply:
            print("dry run — re-run with --apply to write")
        # Show the non-zero ones for sanity
        for c, r in sorted(nonzero.items()):
            print(f"  {c}: {r}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
