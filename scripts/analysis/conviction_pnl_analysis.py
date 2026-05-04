"""Conviction-vs-P&L analysis — validate whether the conviction score is
actually predictive of trade outcomes.

Reads trade_journal, groups by conviction bucket, reports win rate, avg P&L,
and total P&L per bucket. Uses a direct psycopg2 connection via DATABASE_URL.

Usage (on EC2):
  set -a; source /home/ubuntu/alphacent/.env.production; set +a
  /home/ubuntu/alphacent/venv/bin/python3 scripts/analysis/conviction_pnl_analysis.py
"""
from __future__ import annotations

import os
import sys
import json
from collections import defaultdict


def main() -> int:
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

    cur.execute("""
        SELECT trade_metadata, pnl, conviction_score
        FROM trade_journal
        WHERE pnl IS NOT NULL
          AND exit_time > NOW() - INTERVAL '10 days'
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # Bucket by conviction score
    buckets = defaultdict(list)  # bucket -> list of pnl
    total_with_conv = 0

    for trade_metadata, pnl, conv_col in rows:
        # Prefer the direct column, fall back to metadata
        conv = conv_col
        if conv is None and trade_metadata:
            try:
                md = trade_metadata if isinstance(trade_metadata, dict) else json.loads(trade_metadata)
                conv = md.get("conviction_score")
            except Exception:
                conv = None
        if conv is None:
            continue
        try:
            conv = float(conv)
        except (TypeError, ValueError):
            continue
        total_with_conv += 1

        if conv < 60:
            b = "1:<60"
        elif conv < 65:
            b = "2:60-65"
        elif conv < 70:
            b = "3:65-70"
        elif conv < 75:
            b = "4:70-75"
        else:
            b = "5:>=75"
        buckets[b].append(float(pnl))

    print(f"Total closed trades (last 10d): {len(rows)}")
    print(f"Trades with conviction_score (column or metadata): {total_with_conv}")
    print()
    print(f"{'bucket':<10} {'n':>5} {'avg_pnl':>10} {'wr%':>6} {'total':>12}")
    print("-" * 50)
    for b in sorted(buckets.keys()):
        pnls = buckets[b]
        n = len(pnls)
        avg = sum(pnls) / n if n else 0.0
        wr = 100.0 * sum(1 for p in pnls if p > 0) / n if n else 0.0
        total = sum(pnls)
        print(f"{b:<10} {n:>5} {avg:>10.2f} {wr:>6.1f} {total:>12.2f}")

    # Also: by component score
    print()
    print("=" * 50)
    print("By signal direction:")
    print()
    # Pull again with direction
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute("""
        SELECT trade_metadata, side, pnl, conviction_score
        FROM trade_journal
        WHERE pnl IS NOT NULL
          AND exit_time > NOW() - INTERVAL '10 days'
    """)
    rows2 = cur.fetchall()
    cur.close()
    conn.close()

    dir_buckets = defaultdict(list)
    for trade_metadata, side, pnl, conv_col in rows2:
        conv = conv_col
        if conv is None and trade_metadata:
            try:
                md = trade_metadata if isinstance(trade_metadata, dict) else json.loads(trade_metadata)
                conv = md.get("conviction_score")
            except Exception:
                conv = None
        if conv is None:
            continue
        try:
            conv = float(conv)
        except (TypeError, ValueError):
            continue
        if conv < 60:
            b = "1:<60"
        elif conv < 65:
            b = "2:60-65"
        elif conv < 70:
            b = "3:65-70"
        elif conv < 75:
            b = "4:70-75"
        else:
            b = "5:>=75"
        dir_buckets[(side, b)].append(float(pnl))

    print(f"{'side':<7} {'bucket':<10} {'n':>5} {'avg_pnl':>10} {'wr%':>6} {'total':>12}")
    print("-" * 60)
    for (side, b) in sorted(dir_buckets.keys()):
        pnls = dir_buckets[(side, b)]
        n = len(pnls)
        avg = sum(pnls) / n if n else 0.0
        wr = 100.0 * sum(1 for p in pnls if p > 0) / n if n else 0.0
        total = sum(pnls)
        print(f"{str(side):<7} {b:<10} {n:>5} {avg:>10.2f} {wr:>6.1f} {total:>12.2f}")

    # Retroactive: join conviction_score_logs -> trade_journal by strategy+time
    print()
    print("=" * 70)
    print("Retroactive join — LAST 10 DAYS ONLY (post ETF tier + signal-time gates)")
    print("conviction_score_logs × trade_journal by strategy+symbol+time")
    print("(Attributes P&L to the conviction score computed closest before entry)")
    print()
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute("""
        SELECT csl.conviction_score, tj.pnl, tj.side
        FROM conviction_score_logs csl
        JOIN trade_journal tj
          ON tj.strategy_id = csl.strategy_id
         AND tj.symbol = csl.symbol
         AND tj.entry_time BETWEEN csl.timestamp AND csl.timestamp + INTERVAL '2 hours'
        WHERE tj.pnl IS NOT NULL
          AND csl.timestamp > NOW() - INTERVAL '10 days'
    """)
    rows3 = cur.fetchall()
    cur.close()
    conn.close()

    join_buckets = defaultdict(list)
    for conv, pnl, side in rows3:
        if conv is None:
            continue
        if conv < 60:
            b = "1:<60"
        elif conv < 65:
            b = "2:60-65"
        elif conv < 70:
            b = "3:65-70"
        elif conv < 75:
            b = "4:70-75"
        else:
            b = "5:>=75"
        join_buckets[b].append(float(pnl))

    print(f"Matched trades via join: {len(rows3)}")
    print()
    print(f"{'bucket':<10} {'n':>5} {'avg_pnl':>10} {'wr%':>6} {'total':>12}")
    print("-" * 50)
    for b in sorted(join_buckets.keys()):
        pnls = join_buckets[b]
        n = len(pnls)
        avg = sum(pnls) / n if n else 0.0
        wr = 100.0 * sum(1 for p in pnls if p > 0) / n if n else 0.0
        total = sum(pnls)
        print(f"{b:<10} {n:>5} {avg:>10.2f} {wr:>6.1f} {total:>12.2f}")

    # Split by side
    print()
    print("Per-side breakdown (LONG vs SHORT):")
    print(f"{'side':<7} {'bucket':<10} {'n':>5} {'avg_pnl':>10} {'wr%':>6} {'total':>12}")
    print("-" * 60)
    side_buckets = defaultdict(list)
    for conv, pnl, side in rows3:
        if conv is None:
            continue
        if conv < 60:
            b = "1:<60"
        elif conv < 65:
            b = "2:60-65"
        elif conv < 70:
            b = "3:65-70"
        elif conv < 75:
            b = "4:70-75"
        else:
            b = "5:>=75"
        side_buckets[(str(side), b)].append(float(pnl))
    for (side, b) in sorted(side_buckets.keys()):
        pnls = side_buckets[(side, b)]
        n = len(pnls)
        avg = sum(pnls) / n if n else 0.0
        wr = 100.0 * sum(1 for p in pnls if p > 0) / n if n else 0.0
        total = sum(pnls)
        print(f"{side:<7} {b:<10} {n:>5} {avg:>10.2f} {wr:>6.1f} {total:>12.2f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
