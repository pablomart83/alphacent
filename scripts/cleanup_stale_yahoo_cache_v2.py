"""Cleanup stale Yahoo 1h/4h rows for symbols where FMP is the declared
primary source. This version uses sudo psql (matches how our other
diagnostic scripts talk to the DB on EC2), so it avoids the psycopg2
auth issue when run as the ubuntu user.

Scope (delete): source = 'YAHOO_FINANCE', interval in ('1h','4h'),
fmp_ohlc.is_supported(symbol, interval) == True.

Scope (preserve): Yahoo rows for FMP-Starter-blocked combos
(GER40, FR40, OIL-1h, COPPER-1h, US indices at 4h, etc.) — those
legitimately rely on the Yahoo fallback path.

Usage:
    python3 scripts/cleanup_stale_yahoo_cache_v2.py              # dry-run
    python3 scripts/cleanup_stale_yahoo_cache_v2.py --execute    # commit
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)


def _psql(sql: str, tuples_only: bool = True) -> str:
    """Run SQL via sudo -u postgres psql."""
    args = ["sudo", "-u", "postgres", "psql", "alphacent"]
    if tuples_only:
        args.extend(["-t", "-A", "-F", ","])
    args.extend(["-c", sql])
    res = subprocess.run(args, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"psql failed: {res.stderr}")
    return res.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="commit the delete")
    args = parser.parse_args()
    dry_run = not args.execute

    from src.api.fmp_ohlc import is_supported

    # Step 1: enumerate distinct (sym, interval) in Yahoo 1h/4h/1d
    out = _psql(
        "SELECT symbol, interval FROM historical_price_cache "
        "WHERE source = 'YAHOO_FINANCE' AND interval IN ('1h','4h','1d') "
        "GROUP BY symbol, interval ORDER BY interval, symbol;"
    )
    rows = [line.split(",") for line in out.strip().split("\n") if line.strip()]

    delete_combos = []
    preserve_combos = []
    for sym, itv in rows:
        if is_supported(sym, itv):
            delete_combos.append((sym, itv))
        else:
            preserve_combos.append((sym, itv))

    print(f"{'DRY-RUN' if dry_run else 'EXECUTE'} — Yahoo 1h/4h/1d cleanup scope:")
    print("=" * 72)
    print(f"  DELETE:   {len(delete_combos)} (symbol, interval) combos")
    print(f"  PRESERVE: {len(preserve_combos)} (symbol, interval) combos")
    if preserve_combos:
        print("\nPreserved combos (no FMP alternative — keep Yahoo fallback):")
        for sym, itv in preserve_combos:
            print(f"    {sym:<14} {itv}")

    if not delete_combos:
        print("\nNothing to delete.")
        return 0

    if dry_run:
        # Count how many rows would be deleted
        count_out = _psql(
            "SELECT COUNT(*) FROM historical_price_cache "
            "WHERE source = 'YAHOO_FINANCE' AND interval IN ('1h','4h','1d') "
            "AND (symbol, interval) IN (VALUES "
            + ",".join(f"('{s}','{i}')" for s, i in delete_combos)
            + ");"
        )
        print(f"\nDRY-RUN: would delete {count_out.strip()} rows.")
        print("Re-run with --execute to commit.")
        return 0

    # Execute — batched delete in one statement
    print("\nExecuting delete...")
    delete_out = _psql(
        "DELETE FROM historical_price_cache "
        "WHERE source = 'YAHOO_FINANCE' AND interval IN ('1h','4h','1d') "
        "AND (symbol, interval) IN (VALUES "
        + ",".join(f"('{s}','{i}')" for s, i in delete_combos)
        + ") RETURNING 1;",
        tuples_only=True,
    )
    deleted = len([x for x in delete_out.strip().split("\n") if x.strip()])
    print(f"Deleted {deleted:,} stale Yahoo 1h/4h/1d rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
