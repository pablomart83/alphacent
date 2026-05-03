"""Clean up legacy Yahoo-sourced 1h/4h bars from historical_price_cache
for symbols where FMP is the primary data source post-FMP-sprint.

Scope (what's deleted):
  - source = 'YAHOO_FINANCE'
  - interval in ('1h','4h')
  - fmp_ohlc.is_supported(symbol, interval) returns True — i.e. FMP is
    expected to serve this combo. The next sync will populate FMP rows
    if it hasn't already.

Scope (what's preserved):
  - Yahoo 1h/4h rows for symbols FMP Starter does NOT cover (GER40, FR40,
    OIL-1h, COPPER-1h, UK100-4h, STOXX50-4h, US indices at 4h, some
    foreign stocks). These are the legitimate fallback cache rows.
  - All 1d rows (this script only touches 1h/4h).
  - All BINANCE rows (crypto is handled separately).
  - All FMP rows.

Safety:
  - Prints what would be deleted before committing.
  - Runs as a single transaction — either everything in scope is deleted
    or nothing is.
  - No-op if dry_run=True (default).

Usage:
    python3 scripts/cleanup_stale_yahoo_cache.py              # dry-run
    python3 scripts/cleanup_stale_yahoo_cache.py --execute    # commit
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Tuple

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true",
        help="Actually delete (default: dry-run)",
    )
    args = parser.parse_args()
    dry_run = not args.execute

    from sqlalchemy import text
    from src.models.database import get_database
    from src.api.fmp_ohlc import is_supported as _fmp_supported

    db = get_database()
    session = db.get_session()
    try:
        # Distinct (symbol, interval) combos currently in YAHOO_FINANCE 1h/4h
        rows = session.execute(text(
            "SELECT symbol, interval, COUNT(*) AS bars "
            "FROM historical_price_cache "
            "WHERE source = 'YAHOO_FINANCE' AND interval IN ('1h','4h') "
            "GROUP BY symbol, interval "
            "ORDER BY interval, symbol"
        )).fetchall()

        delete_scope: List[Tuple[str, str, int]] = []
        preserve_scope: List[Tuple[str, str, int]] = []

        for sym, itv, cnt in rows:
            if _fmp_supported(sym, itv):
                delete_scope.append((sym, itv, cnt))
            else:
                preserve_scope.append((sym, itv, cnt))

        total_delete_bars = sum(c for _, _, c in delete_scope)
        total_preserve_bars = sum(c for _, _, c in preserve_scope)

        print(f"{'DRY-RUN' if dry_run else 'EXECUTE'} — Yahoo 1h/4h cleanup scope:")
        print("=" * 72)
        print(f"  DELETE: {len(delete_scope)} (symbol, interval) combos, "
              f"{total_delete_bars:,} bars total")
        print(f"  PRESERVE: {len(preserve_scope)} (symbol, interval) combos, "
              f"{total_preserve_bars:,} bars total")
        print()

        # Show a sample of preserved combos — these are the FMP-Starter-blocked
        # symbols that legitimately need Yahoo.
        if preserve_scope:
            print("Sample of PRESERVED (no FMP alternative):")
            for sym, itv, cnt in preserve_scope[:20]:
                print(f"    {sym:<12} {itv:<4} {cnt:>6} bars")
            if len(preserve_scope) > 20:
                print(f"    ... and {len(preserve_scope) - 20} more")
            print()

        if not delete_scope:
            print("Nothing to delete.")
            return 0

        if dry_run:
            print("DRY-RUN: re-run with --execute to commit the delete.")
            return 0

        # Execute — parameterised delete per (symbol, interval)
        print("Executing delete...")
        deleted_total = 0
        for sym, itv, _ in delete_scope:
            result = session.execute(text(
                "DELETE FROM historical_price_cache "
                "WHERE symbol = :s AND interval = :i AND source = 'YAHOO_FINANCE'"
            ), {"s": sym, "i": itv})
            deleted_total += result.rowcount or 0
        session.commit()
        print(f"Deleted {deleted_total:,} stale Yahoo 1h/4h rows.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
