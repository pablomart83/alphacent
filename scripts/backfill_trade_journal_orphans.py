"""Backfill trade_journal rows whose log_exit was never called.

Background
----------
The trade_journal table uses `trade_id` as a loose link to either:
  - `orders.id` (UUID) when written by order_monitor.log_entry
  - `positions.id` (eToro numeric) when written by order_executor.log_entry

`log_exit` is called with `position.id`. If the entry was logged by
order_monitor with `order.id`, the exit filter `trade_id=position.id` misses
the row → the entry stays with `exit_time IS NULL` forever, even though the
actual position is long closed.

This script:
  1. Identifies orphaned entries (open in trade_journal, but position closed).
  2. Computes exit details from the closed position row.
  3. UPDATEs the trade_journal row with exit_time, exit_price, pnl, etc.
  4. Leaves entries where we can't infer the close cleanly (dupes, missing pos).

Usage
-----
    # Dry run (default): prints planned updates, no DB writes.
    venv/bin/python3 scripts/backfill_trade_journal_orphans.py

    # Apply changes:
    venv/bin/python3 scripts/backfill_trade_journal_orphans.py --apply

Matching strategy (per trade_journal row with exit_time IS NULL):
  1. Try `positions.id = trade_journal.trade_id` (numeric position id path).
  2. If not found, find closed positions by (strategy_id, symbol) entered
     at/after trade_journal.entry_time − 2h and closed. Pick the earliest
     closed position whose entry_time falls within a ±2h window.

Exit fields written:
  - exit_time       = positions.closed_at
  - exit_price      = positions.current_price (at close)
  - exit_reason     = 'backfill_orphan'
  - pnl             = positions.realized_pnl if set, else derived from prices
  - pnl_percent     = (exit_price / entry_price − 1) * 100 signed by side
  - hold_time_hours = (closed_at − entry_time).total_seconds() / 3600
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _detect_side(side_raw: Optional[str]) -> str:
    if not side_raw:
        return 'LONG'
    s = str(side_raw).upper()
    return 'SHORT' if ('SHORT' in s or 'SELL' in s) else 'LONG'


def main(apply: bool) -> int:
    from src.models.database import get_database
    from src.models.orm import PositionORM
    from src.analytics.trade_journal import TradeJournalEntryORM

    db = get_database()
    session = db.get_session()
    try:
        orphans = (
            session.query(TradeJournalEntryORM)
            .filter(TradeJournalEntryORM.exit_time.is_(None))
            .all()
        )
        logger.info(f"Found {len(orphans)} open trade_journal rows")

        matched = 0
        unmatched = 0
        pos_id_matches = 0
        fallback_matches = 0
        duplicate_hits = 0
        skipped_open_pos = 0
        updates = []

        for entry in orphans:
            # Path 1: direct id match (legacy position-id writers)
            pos = session.query(PositionORM).filter(
                PositionORM.id == entry.trade_id
            ).first()

            if pos is not None:
                if pos.closed_at is None:
                    # Position is open — excursion updater will handle it.
                    skipped_open_pos += 1
                    continue
                pos_id_matches += 1
            else:
                # Path 2: symbol + strategy + time window — order-id writers
                if not entry.strategy_id or not entry.symbol or not entry.entry_time:
                    unmatched += 1
                    continue

                window_lo = entry.entry_time - timedelta(hours=2)
                window_hi = entry.entry_time + timedelta(hours=2)

                candidates = (
                    session.query(PositionORM)
                    .filter(
                        PositionORM.strategy_id == entry.strategy_id,
                        PositionORM.symbol == entry.symbol,
                        PositionORM.closed_at.isnot(None),
                        PositionORM.opened_at >= window_lo,
                        PositionORM.opened_at <= window_hi,
                    )
                    .order_by(PositionORM.opened_at.asc())
                    .all()
                )
                if not candidates:
                    unmatched += 1
                    continue
                if len(candidates) > 1:
                    duplicate_hits += 1
                pos = candidates[0]
                fallback_matches += 1

            # Compute exit metrics from the closed position
            exit_time = pos.closed_at
            exit_price = pos.current_price  # current_price is updated at close in order_monitor
            if exit_price is None or exit_price <= 0:
                unmatched += 1
                continue

            entry_price = entry.entry_price or pos.entry_price
            if not entry_price or entry_price <= 0:
                unmatched += 1
                continue

            side = _detect_side(entry.side)
            if side == 'SHORT':
                pnl_percent = (entry_price - exit_price) / entry_price * 100.0
            else:
                pnl_percent = (exit_price - entry_price) / entry_price * 100.0

            realized = pos.realized_pnl
            if realized is None or realized == 0:
                qty = entry.entry_size or pos.quantity or 0
                realized = (exit_price - entry_price) * qty
                if side == 'SHORT':
                    realized = -realized

            hold_time_hours = None
            if exit_time and entry.entry_time:
                hold_time_hours = (exit_time - entry.entry_time).total_seconds() / 3600.0

            updates.append({
                'row': entry,
                'exit_time': exit_time,
                'exit_price': exit_price,
                'pnl': realized,
                'pnl_percent': pnl_percent,
                'hold_time_hours': hold_time_hours,
                'closed_pos_id': pos.id,
            })
            matched += 1

        logger.info(
            "Matching summary: "
            f"matched={matched} (pos_id={pos_id_matches}, fallback={fallback_matches}), "
            f"skipped_open_pos={skipped_open_pos}, unmatched={unmatched}, "
            f"fallback_had_duplicates={duplicate_hits}"
        )

        if not updates:
            logger.info("Nothing to backfill. Exiting.")
            return 0

        # Show a few samples
        for u in updates[:5]:
            r = u['row']
            logger.info(
                f"  SAMPLE trade_id={r.trade_id} sym={r.symbol} side={r.side} "
                f"entry={r.entry_time} → exit={u['exit_time']} "
                f"pnl={u['pnl']:.2f} ({u['pnl_percent']:+.2f}%) "
                f"hold={u['hold_time_hours']:.1f}h closed_pos={u['closed_pos_id']}"
            )

        if not apply:
            logger.info(
                f"DRY-RUN: would update {len(updates)} rows. "
                "Re-run with --apply to write."
            )
            return 0

        # Apply
        logger.info(f"APPLYING updates to {len(updates)} rows...")
        for u in updates:
            r = u['row']
            r.exit_time = u['exit_time']
            r.exit_price = u['exit_price']
            r.exit_reason = getattr(r, 'exit_reason', None) or 'backfill_orphan'
            r.pnl = u['pnl']
            r.pnl_percent = u['pnl_percent']
            r.hold_time_hours = u['hold_time_hours']
        session.commit()
        logger.info(f"Committed {len(updates)} updates.")

        # Re-count to confirm
        remaining_open = (
            session.query(TradeJournalEntryORM)
            .filter(TradeJournalEntryORM.exit_time.is_(None))
            .count()
        )
        logger.info(f"trade_journal rows remaining with exit_time IS NULL: {remaining_open}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
    args = parser.parse_args()
    sys.exit(main(apply=args.apply))
