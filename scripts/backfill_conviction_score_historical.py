"""One-shot backfill of trade_journal.conviction_score from conviction_score_logs.

For every closed trade where conviction_score IS NULL, find the most recent
conviction_score_logs row within 2h prior to entry_time matching on
(strategy_id, symbol). Writes conviction_score + signal_strength_score +
fundamental_quality_score + regime_alignment_score + passed_threshold to the
trade_journal row.

This recovers historical conviction data so the validation loop can operate
on the full ~900-trade history instead of just post-fix trades.

Dry-run by default. Re-run with --execute to write.

Safety:
- Tagged with trade_metadata.backfill_source = 'conviction_logs_backfill_2026_05_05'
  so rows are auditable and can be undone.
- Only touches rows where conviction_score IS NULL (won't overwrite fresh
  writes from the post-fix order_monitor path).
- Idempotent — re-running finds fewer candidates each time.

Usage:
  set -a; source /home/ubuntu/alphacent/.env.production; set +a
  /home/ubuntu/alphacent/venv/bin/python3 scripts/backfill_conviction_score_historical.py
  /home/ubuntu/alphacent/venv/bin/python3 scripts/backfill_conviction_score_historical.py --execute
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Actually write changes")
    parser.add_argument(
        "--window-hours",
        type=float,
        default=2.0,
        help="How far before entry_time to look for a matching conviction score",
    )
    args = parser.parse_args()
    dry_run = not args.execute

    try:
        import psycopg2
    except ImportError:
        print("psycopg2 not available — run under venv")
        return 1

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL not set — source .env.production first")
        return 1

    conn = psycopg2.connect(url)
    cur = conn.cursor()

    # Find candidate trades: closed, have pnl, conviction_score is NULL
    cur.execute(
        """
        SELECT trade_id, strategy_id, symbol, entry_time
        FROM trade_journal
        WHERE pnl IS NOT NULL
          AND conviction_score IS NULL
          AND strategy_id IS NOT NULL
          AND symbol IS NOT NULL
          AND entry_time IS NOT NULL
        ORDER BY entry_time DESC
        """
    )
    candidates = cur.fetchall()
    print(f"Candidate trades (closed + pnl + NULL conviction): {len(candidates)}")

    if not candidates:
        print("Nothing to backfill.")
        cur.close()
        conn.close()
        return 0

    # For each candidate, find the matching conviction_score_log
    matched = 0
    unmatched = 0
    updates = []  # list of (trade_id, score, sig, fund, regime, passed, metadata_patch)

    WINDOW = args.window_hours

    for trade_id, strategy_id, symbol, entry_time in candidates:
        cur.execute(
            """
            SELECT conviction_score, signal_strength_score,
                   fundamental_quality_score, regime_alignment_score,
                   passed_threshold, threshold, timestamp
            FROM conviction_score_logs
            WHERE strategy_id = %s
              AND symbol = %s
              AND timestamp <= %s
              AND timestamp >= %s - (%s::float * INTERVAL '1 hour')
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (strategy_id, symbol, entry_time, entry_time, WINDOW),
        )
        row = cur.fetchone()
        if row is None:
            unmatched += 1
            continue

        score, sig, fund, regime, passed, threshold, ts = row
        metadata_patch = {
            "backfill_source": "conviction_logs_backfill_2026_05_05",
            "backfill_conviction_timestamp": ts.isoformat() if ts else None,
            "backfill_conviction_threshold": float(threshold) if threshold else None,
        }
        updates.append((trade_id, score, sig, fund, regime, passed, metadata_patch))
        matched += 1

    print(f"  Matched to conviction_score_logs: {matched}")
    print(f"  Unmatched (no score within {WINDOW}h before entry): {unmatched}")
    print()

    if dry_run:
        # Show a sample
        print("Sample of first 10 matches:")
        for u in updates[:10]:
            trade_id, score, sig, fund, regime, passed, _ = u
            print(
                f"  {str(trade_id)[:20]:<20}  conv={score:.1f}  "
                f"sig={sig:.1f}  fund={fund:.1f}  regime={regime:.1f}  "
                f"passed={passed}"
            )
        print()
        print(f"Would update {len(updates)} rows. Re-run with --execute to write.")
        cur.close()
        conn.close()
        return 0

    # Execute: update in batches
    print(f"Writing {len(updates)} rows...")
    written = 0
    failed = 0

    for trade_id, score, sig, fund, regime, passed, metadata_patch in updates:
        try:
            cur.execute(
                """
                UPDATE trade_journal
                SET conviction_score = %s,
                    trade_metadata = COALESCE(trade_metadata::jsonb, '{}'::jsonb)
                                   || %s::jsonb
                WHERE trade_id = %s
                  AND conviction_score IS NULL
                """,
                (score, json.dumps(metadata_patch), trade_id),
            )
            if cur.rowcount == 1:
                written += 1
            else:
                # Either trade already had conviction (rare race) or trade_id not found
                failed += 1
        except Exception as e:
            failed += 1
            print(f"  Failed {trade_id}: {e}")
            conn.rollback()
            continue

    conn.commit()
    cur.close()
    conn.close()

    print()
    print(f"Written: {written}")
    print(f"Skipped/failed: {failed}")
    print()

    # Post-write verification
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          COUNT(*) FILTER (WHERE conviction_score IS NOT NULL) AS with_conv,
          COUNT(*) AS total
        FROM trade_journal
        WHERE pnl IS NOT NULL
        """
    )
    row = cur.fetchone()
    print(f"Post-backfill coverage: {row[0]} / {row[1]} trades have conviction_score "
          f"({100.0 * row[0] / max(row[1], 1):.1f}%)")
    cur.close()
    conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
