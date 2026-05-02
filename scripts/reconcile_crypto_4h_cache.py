"""Sprint 2 F10 — reconcile stale 4H crypto cache against 1H source window.

Problem
-------
yfinance caps 1h crypto history at ~7 months (210d for BTC/ETH; ~174d for
SOL/AVAX/LINK/DOT). The 4H cache was previously synthesised from an older
1h snapshot — for BTC/ETH 4H bars go back to 2025-02-02 (15 months) while
current 1h only extends to 2025-10-03 (7 months). That phantom 4H depth is
unreproducible: any cache clear / schema-version invalidation truncates 4h
to the current 1h reach, silently dropping ~8 months of bars.

The 4H depth must equal the 1H depth — no more, no less. This script:
  1. For each of BTC/ETH/SOL/AVAX/LINK/DOT, find the earliest 1H bar in
     historical_price_cache.
  2. Delete 4H rows dated before (earliest_1h - 1 day) for that symbol.
     (-1d margin: resample can create a legal 4H bar just before the first
      full 1H bar if the partial leading hours are present.)
  3. Report bars-before / bars-after for each symbol.

After this runs, the 4H cache HONESTLY reflects the 1H source range.
Going forward, the guard in
  market_data_manager._fetch_historical_from_yahoo_finance
prevents phantom 4H bars from being re-inserted.

Usage: python3 scripts/reconcile_crypto_4h_cache.py
"""
from __future__ import annotations

import logging
import sys
from datetime import timedelta
from pathlib import Path

# Make src importable when run from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from src.models.database import get_database  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("reconcile_crypto_4h_cache")

CRYPTO_SYMBOLS = ["BTC", "ETH", "SOL", "AVAX", "LINK", "DOT"]


def reconcile() -> int:
    db = get_database()
    session = db.get_session()
    total_deleted = 0
    try:
        for sym in CRYPTO_SYMBOLS:
            # Earliest 1H bar for this symbol
            row_1h = session.execute(
                text(
                    "SELECT MIN(date) AS first_1h, MAX(date) AS last_1h, "
                    "COUNT(*) AS bars_1h "
                    "FROM historical_price_cache "
                    "WHERE symbol = :sym AND interval = '1h'"
                ),
                {"sym": sym},
            ).fetchone()
            if not row_1h or row_1h[0] is None:
                log.warning(
                    f"{sym}: no 1H data in cache — skipping (nothing to reconcile against)"
                )
                continue
            first_1h, last_1h, bars_1h = row_1h[0], row_1h[1], int(row_1h[2])

            # State before
            row_4h_before = session.execute(
                text(
                    "SELECT MIN(date) AS first_4h, MAX(date) AS last_4h, "
                    "COUNT(*) AS bars_4h "
                    "FROM historical_price_cache "
                    "WHERE symbol = :sym AND interval = '4h'"
                ),
                {"sym": sym},
            ).fetchone()
            if not row_4h_before or row_4h_before[0] is None:
                log.info(f"{sym}: no 4H data — nothing to delete")
                continue
            first_4h_before, last_4h_before, bars_4h_before = (
                row_4h_before[0], row_4h_before[1], int(row_4h_before[2])
            )

            cutoff = first_1h - timedelta(days=1)
            # Delete phantom 4H bars older than (first_1h - 1 day).
            result = session.execute(
                text(
                    "DELETE FROM historical_price_cache "
                    "WHERE symbol = :sym AND interval = '4h' AND date < :cutoff"
                ),
                {"sym": sym, "cutoff": cutoff},
            )
            deleted = int(result.rowcount or 0)

            # State after
            row_4h_after = session.execute(
                text(
                    "SELECT MIN(date) AS first_4h, MAX(date) AS last_4h, "
                    "COUNT(*) AS bars_4h "
                    "FROM historical_price_cache "
                    "WHERE symbol = :sym AND interval = '4h'"
                ),
                {"sym": sym},
            ).fetchone()
            bars_4h_after = (
                int(row_4h_after[2]) if row_4h_after and row_4h_after[2] else 0
            )
            first_4h_after = row_4h_after[0] if row_4h_after else None

            log.info(
                f"{sym}: 1H range {first_1h.date()} → {last_1h.date()} "
                f"({bars_1h} bars) | "
                f"4H before {first_4h_before.date()} → "
                f"{last_4h_before.date()} ({bars_4h_before} bars) | "
                f"deleted {deleted} | "
                f"4H after "
                f"{first_4h_after.date() if first_4h_after else 'N/A'} "
                f"({bars_4h_after} bars)"
            )
            total_deleted += deleted
        session.commit()
    except Exception as e:
        session.rollback()
        log.error(f"Reconciliation failed, rolled back: {e}", exc_info=True)
        return 1
    finally:
        session.close()

    log.info(
        f"Done. Total 4H bars deleted across {len(CRYPTO_SYMBOLS)} symbols: "
        f"{total_deleted}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(reconcile())
