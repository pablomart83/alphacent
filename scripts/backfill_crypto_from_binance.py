#!/usr/bin/env python3
"""Backfill 1h/4h crypto historical cache from Binance public API.

Sprint 4 S4.0 (2026-05-02): after wiring Binance as the primary source
for crypto 1h/4h data (lifts the ~7-month Yahoo cap), this script does a
one-shot backfill of the historical_price_cache table for all 6 tradeable
crypto symbols so the DB cache reflects the true Binance depth.

Runs through `MarketDataManager.get_historical_data` which internally
routes crypto 1h/4h to Binance via `_fetch_historical_from_yahoo_finance`'s
new Sprint 4 early-exit branch. Idempotent — the unique (symbol, date,
interval) constraint on historical_price_cache skips existing rows.

Request window: 730 days for 4h (covers 2 regime cycles), 365 days for
1h (Binance can go further but 1h bar count explodes past 1 year).

Sanity check before and after: logs the earliest cached bar per symbol
so you can see the Binance-backed depth materialise.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml

from src.data.market_data_manager import MarketDataManager
from src.models.database import get_database
from src.models.orm import HistoricalPriceCacheORM


CRYPTO_SYMBOLS = ["BTC", "ETH", "SOL", "AVAX", "LINK", "DOT"]

# (interval, days_back) — matches the new WF windows.
# 730d for 4h → ~4380 bars/symbol (2y covers 2 regime cycles)
# 730d for 1h → ~17500 bars/symbol (2y; Binance pagination handles it in ~18 requests)
# 730d for 1d → 730 bars/symbol (weekly/monthly strategies need 2y to fit train+test)
INTERVAL_WINDOWS = [
    ("4h", 730),
    ("1h", 730),
    ("1d", 730),
]


def _cache_stats(session, symbol: str, interval: str):
    earliest_row = (
        session.query(HistoricalPriceCacheORM)
        .filter(HistoricalPriceCacheORM.symbol == symbol, HistoricalPriceCacheORM.interval == interval)
        .order_by(HistoricalPriceCacheORM.date.asc())
        .first()
    )
    count = (
        session.query(HistoricalPriceCacheORM)
        .filter(HistoricalPriceCacheORM.symbol == symbol, HistoricalPriceCacheORM.interval == interval)
        .count()
    )
    earliest = earliest_row.date.isoformat() if earliest_row else None
    return count, earliest


def main():
    config_path = ROOT / "config" / "autonomous_trading.yaml"
    config = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}

    db = get_database()
    mdm = MarketDataManager(config)

    end = datetime.utcnow()

    print("=" * 78)
    print("Binance crypto cache backfill")
    print("=" * 78)

    for interval, days_back in INTERVAL_WINDOWS:
        start = end - timedelta(days=days_back)
        print(f"\n--- Interval {interval} ({days_back}d) ---")
        for sym in CRYPTO_SYMBOLS:
            session = db.get_session()
            try:
                before_count, before_first = _cache_stats(session, sym, interval)
            finally:
                session.close()

            print(f"{sym} {interval}: before → {before_count} bars, first={before_first}")

            try:
                bars = mdm.get_historical_data(
                    symbol=sym, start=start, end=end, interval=interval, prefer_yahoo=True
                )
                fetched = len(bars) if bars else 0
            except Exception as e:
                print(f"  ERROR fetching {sym} {interval}: {e}")
                continue

            session = db.get_session()
            try:
                after_count, after_first = _cache_stats(session, sym, interval)
            finally:
                session.close()

            gained = after_count - before_count
            print(
                f"  fetched {fetched}, cache now {after_count} bars "
                f"(+{gained}), first={after_first}"
            )

    print()
    print("Done. Next WF cycle will run on the extended windows.")


if __name__ == "__main__":
    main()
