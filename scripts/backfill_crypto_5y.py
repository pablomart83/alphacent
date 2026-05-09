#!/usr/bin/env python3
"""One-shot script: backfill 5 years of Binance OHLC data for all crypto symbols.

Run once after deploying the rolling WF changes. Extends the cache from
~2.4 years to 5 years, giving the rolling WF validator enough history to
place 3 evenly-spaced windows across multiple regime periods.

Usage:
    python3 scripts/backfill_crypto_5y.py [--dry-run] [--symbol BTC]

Flags:
    --dry-run   Print what would be fetched without writing to DB.
    --symbol X  Only backfill a single symbol (for testing).

Expected runtime: ~5-10 minutes (Binance rate limit is generous at 1200
weight/min; each klines request is weight 1-10 depending on limit param).
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SYMBOLS = ["BTC", "ETH", "SOL", "AVAX", "LINK", "DOT"]
INTERVALS = ["1d", "4h", "1h"]
WINDOW_DAYS = 1825  # 5 years


def main():
    parser = argparse.ArgumentParser(description="Backfill 5y Binance crypto data")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing")
    parser.add_argument("--symbol", help="Only backfill this symbol")
    args = parser.parse_args()

    symbols = [args.symbol.upper()] if args.symbol else SYMBOLS

    from src.api.binance_ohlc import fetch_klines, is_supported, BinanceAPIError

    # DB setup
    if not args.dry_run:
        from src.models.database import get_database
        from src.data.market_data_manager import MarketDataManager
        db = get_database()

    end = datetime.now(timezone.utc).replace(tzinfo=None)
    start_5y = end - timedelta(days=WINDOW_DAYS)

    total_bars = 0
    total_written = 0

    for symbol in symbols:
        for interval in INTERVALS:
            if not is_supported(symbol, interval):
                logger.info(f"  {symbol} {interval}: not supported by Binance adapter, skip")
                continue

            # Check existing cache depth
            earliest_in_db = None
            if not args.dry_run:
                try:
                    from sqlalchemy import text as _sa_text
                    sess = db.get_session()
                    try:
                        row = sess.execute(_sa_text(
                            "SELECT MIN(date), MAX(date), COUNT(*) FROM historical_price_cache "
                            "WHERE symbol = :sym AND interval = :iv"
                        ), {"sym": symbol, "iv": interval}).fetchone()
                        if row and row[0]:
                            earliest_in_db = row[0]
                            if hasattr(earliest_in_db, 'tzinfo') and earliest_in_db.tzinfo:
                                earliest_in_db = earliest_in_db.replace(tzinfo=None)
                            logger.info(
                                f"  {symbol} {interval}: DB has {row[2]} bars "
                                f"({row[0].date() if row[0] else '?'} → {row[1].date() if row[1] else '?'})"
                            )
                    finally:
                        sess.close()
                except Exception as e:
                    logger.warning(f"  {symbol} {interval}: DB check failed: {e}")

            # Determine fetch window
            if earliest_in_db is not None and earliest_in_db <= start_5y + timedelta(days=30):
                logger.info(
                    f"  {symbol} {interval}: already has 5y depth "
                    f"(earliest={earliest_in_db.date()}), skip"
                )
                continue

            fetch_start = start_5y
            if earliest_in_db is not None and earliest_in_db > start_5y:
                # Only need to backfill the gap before the existing data
                fetch_end = earliest_in_db + timedelta(days=2)  # 2-day overlap
                logger.info(
                    f"  {symbol} {interval}: fetching gap "
                    f"{fetch_start.date()} → {fetch_end.date()}"
                )
            else:
                fetch_end = end
                logger.info(
                    f"  {symbol} {interval}: full backfill "
                    f"{fetch_start.date()} → {fetch_end.date()}"
                )

            if args.dry_run:
                logger.info(f"  [DRY RUN] Would fetch {symbol} {interval} "
                            f"{fetch_start.date()} → {fetch_end.date()}")
                continue

            try:
                bars = fetch_klines(symbol, fetch_start, fetch_end, interval)
                if not bars:
                    logger.warning(f"  {symbol} {interval}: Binance returned 0 bars")
                    continue

                logger.info(
                    f"  {symbol} {interval}: fetched {len(bars)} bars "
                    f"({bars[0].timestamp.date()} → {bars[-1].timestamp.date()})"
                )
                total_bars += len(bars)

                # Write to DB using the market_data_manager save path
                # which deduplicates against existing rows
                from src.data.market_data_manager import MarketDataManager as _MDM
                _mdm = _MDM.__new__(_MDM)
                _mdm.db = db
                _mdm._save_historical_to_db(symbol, bars, interval)
                total_written += len(bars)
                logger.info(f"  {symbol} {interval}: written to DB ✓")

            except BinanceAPIError as e:
                logger.error(f"  {symbol} {interval}: Binance error: {e}")
            except Exception as e:
                logger.error(f"  {symbol} {interval}: unexpected error: {e}", exc_info=True)

    if args.dry_run:
        logger.info("Dry run complete — no data written")
    else:
        logger.info(
            f"\nBackfill complete: {total_bars} bars fetched, "
            f"{total_written} written to DB"
        )

        # Verify final cache depth
        logger.info("\nFinal cache depth:")
        try:
            from sqlalchemy import text as _sa_text
            sess = db.get_session()
            try:
                rows = sess.execute(_sa_text(
                    "SELECT symbol, interval, COUNT(*) as bars, "
                    "MIN(date)::date as earliest, MAX(date)::date as latest "
                    "FROM historical_price_cache "
                    "WHERE symbol = ANY(:syms) "
                    "GROUP BY symbol, interval ORDER BY symbol, interval"
                ), {"syms": symbols}).fetchall()
                for row in rows:
                    years = (row[4] - row[3]).days / 365 if row[3] and row[4] else 0
                    logger.info(
                        f"  {row[0]:6s} {row[1]:3s}: {row[2]:6d} bars  "
                        f"{row[3]} → {row[4]}  ({years:.1f}y)"
                    )
            finally:
                sess.close()
        except Exception as e:
            logger.warning(f"Verification query failed: {e}")


if __name__ == "__main__":
    main()
