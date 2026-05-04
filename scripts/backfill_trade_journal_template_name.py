"""Backfill trade_journal.trade_metadata['template_name'] from strategies table.

Context: the loser-pair sizing penalty in risk_manager.calculate_position_size
(Step 10b) queries trade_journal.trade_metadata->>'template_name' to identify
(template, symbol) pairs with net-losing history. Before this session (2026-05-05)
the write path never populated template_name, so zero of 892 closed trades had
the key and the penalty never fired. The write path is fixed; this script
recovers what can be recovered for historical rows.

Backfill sources, in order:
  1. strategies.strategy_metadata->>'template_name' — 216 of 892 rows. Strategies
     still in the library with intact metadata.
  2. strategy_proposals.template_name — marginal additional coverage for strategies
     that were proposed but have since been deleted. In practice only ~2 matches
     (proposals table is newer than most closed trades).

Rows with no recoverable template are left as-is; the loser-pair lookup
already defaults to a safe no-op when template_name is absent. Every
backfilled row is tagged with trade_metadata['backfill_source'] =
'legacy_backfill_2026_05_05' for auditability.

Dry-run by default. Run with --apply to commit.

Usage on EC2:
    python3 scripts/backfill_trade_journal_template_name.py
    python3 scripts/backfill_trade_journal_template_name.py --apply
"""

import argparse
import json
import logging
import sys
from typing import Dict, Optional, Tuple

from sqlalchemy import text

from src.models.database import get_database

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("backfill_template_name")

BACKFILL_MARKER = "legacy_backfill_2026_05_05"


def _resolve_template_from_strategy(strategy_metadata, strategy_name) -> Optional[str]:
    """Extract template_name from a strategy's metadata, falling back to name."""
    if isinstance(strategy_metadata, dict):
        tname = strategy_metadata.get("template_name")
        if tname:
            return tname
    # Fallback: strategies.name — stable identifier even without metadata
    if strategy_name:
        return strategy_name
    return None


def _resolve_template_from_proposals(session, strategy_id: str) -> Optional[str]:
    """Best-effort recovery for retired strategies via strategy_proposals."""
    row = session.execute(
        text(
            "SELECT template_name FROM strategy_proposals "
            "WHERE strategy_id = :sid AND template_name IS NOT NULL "
            "ORDER BY proposed_at DESC LIMIT 1"
        ),
        {"sid": strategy_id},
    ).fetchone()
    return row[0] if row else None


def run(apply: bool = False) -> Tuple[int, int, int]:
    """Backfill template_name. Returns (scanned, updated, skipped)."""
    db = get_database()
    session = db.get_session()
    try:
        # Pull every closed trade_journal row lacking template_name, plus its
        # originating strategy (if still alive).
        rows = session.execute(
            text(
                """
                SELECT t.id, t.trade_id, t.strategy_id, t.symbol, t.trade_metadata,
                       s.name AS strategy_name, s.strategy_metadata AS smeta
                FROM trade_journal t
                LEFT JOIN strategies s ON s.id = t.strategy_id
                WHERE t.pnl IS NOT NULL
                  AND (
                    t.trade_metadata IS NULL
                    OR NOT ((t.trade_metadata::jsonb) ? 'template_name')
                  )
                """
            )
        ).fetchall()
    finally:
        session.close()

    logger.info("Scanned %d closed trades without template_name", len(rows))

    scanned = len(rows)
    updated = 0
    skipped = 0
    per_source: Dict[str, int] = {"strategies": 0, "strategy_proposals": 0}

    session = db.get_session()
    try:
        for row in rows:
            tid = row.id
            strategy_id = row.strategy_id
            existing_meta = row.trade_metadata or {}
            if not isinstance(existing_meta, dict):
                # Corrupt row — log and skip
                logger.warning("Row id=%s has non-dict trade_metadata, skipping", tid)
                skipped += 1
                continue

            # Source 1: strategies table
            tname = _resolve_template_from_strategy(row.smeta, row.strategy_name)
            source = "strategies" if tname else None

            # Source 2: strategy_proposals fallback
            if not tname and strategy_id and strategy_id != "etoro_position":
                tname = _resolve_template_from_proposals(session, strategy_id)
                if tname:
                    source = "strategy_proposals"

            if not tname:
                skipped += 1
                continue

            new_meta = dict(existing_meta)
            new_meta["template_name"] = tname
            new_meta["backfill_source"] = BACKFILL_MARKER
            new_meta["backfill_template_source"] = source

            if apply:
                session.execute(
                    text(
                        "UPDATE trade_journal SET trade_metadata = CAST(:meta AS JSON) WHERE id = :id"
                    ),
                    {"meta": json.dumps(new_meta), "id": tid},
                )

            per_source[source] = per_source.get(source, 0) + 1
            updated += 1

            if updated % 100 == 0:
                logger.info("Progress: %d / %d updated", updated, scanned)

        if apply:
            session.commit()
            logger.info("Committed backfill changes")
        else:
            logger.info("Dry-run — no changes written. Re-run with --apply to commit.")
    finally:
        session.close()

    logger.info(
        "Result: scanned=%d updated=%d skipped=%d (source breakdown: %s)",
        scanned,
        updated,
        skipped,
        per_source,
    )
    return scanned, updated, skipped


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit changes")
    args = parser.parse_args()
    scanned, updated, skipped = run(apply=args.apply)
    sys.exit(0)
