#!/usr/bin/env python3
"""Backfill 1h crypto historical cache to 730 days.

yfinance caps 1h lookback at 730 days. We currently have ~180 days cached.
This script fetches the full 730-day window for each crypto symbol and
inserts missing bars into historical_price_cache.

Idempotent — uses the unique (symbol, date, interval) constraint; will skip
existing rows.
"""
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Setup path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Import the factory (at line 63) not the getter (at line 1648)
from src.data.market_data_manager import MarketDataManager, get_market_data_manager
from src.models.database import get_database
from src.models.orm import HistoricalPriceCacheORM
import yaml

CRYPTO_SYMBOLS = ["BTC", "ETH", "SOL", "AVAX", "LINK", "DOT"]
INTERVALS = ["1h"]


def main():
    # Load full config
    config_path = ROOT / "config" / "autonomous_trading.yaml"
    config = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}

    db = get_database()
    # Construct MarketDataManager directly — the exported get_market_data_manager
    # returns the runtime singleton (None outside of a running service).
    mdm = MarketDataManager(config)
    if not mdm:
        print("ERROR: could not instantiate MarketDataManager")
        sys.exit(1)

    end = datetime.now()
    start = end - timedelta(days=729)  # just under the 730d yfinance cap

    for sym in CRYPTO_SYMBOLS:
        for interval in INTERVALS:
            # Check current coverage
            session = db.get_session()
            try:
                current_earliest = session.query(HistoricalPriceCacheORM).filter(
                    HistoricalPriceCacheORM.symbol == sym,
                    HistoricalPriceCacheORM.interval == interval,
                ).order_by(HistoricalPriceCacheORM.date.asc()).first()
                current_count = session.query(HistoricalPriceCacheORM).filter(
                    HistoricalPriceCacheORM.symbol == sym,
                    HistoricalPriceCacheORM.interval == interval,
                ).count()
            finally:
                session.close()

            earliest_str = current_earliest.date.isoformat() if current_earliest else "none"
            print(f"{sym} {interval}: {current_count} bars, earliest={earliest_str}")

            # Fetch the full 730d window; the manager handles dedup/insert
            try:
                print(f"  → fetching {sym} {interval} for 730 days...")
                bars = mdm.get_historical_data(
                    symbol=sym,
                    start=start,
                    end=end,
                    interval=interval,
                    prefer_yahoo=True,
                )
                print(f"  → got {len(bars) if bars else 0} bars")
            except Exception as e:
                print(f"  ERROR fetching {sym} {interval}: {e}")
                continue

            # Re-check coverage after fetch
            session = db.get_session()
            try:
                new_earliest = session.query(HistoricalPriceCacheORM).filter(
                    HistoricalPriceCacheORM.symbol == sym,
                    HistoricalPriceCacheORM.interval == interval,
                ).order_by(HistoricalPriceCacheORM.date.asc()).first()
                new_count = session.query(HistoricalPriceCacheORM).filter(
                    HistoricalPriceCacheORM.symbol == sym,
                    HistoricalPriceCacheORM.interval == interval,
                ).count()
            finally:
                session.close()

            new_earliest_str = new_earliest.date.isoformat() if new_earliest else "none"
            gained = new_count - current_count
            print(f"  ← {sym} {interval}: {new_count} bars (+{gained}), earliest={new_earliest_str}")
    print()
    print("NOTE: yfinance 1h history for crypto is capped at ~7 months regardless")
    print("of the 730d request window. No amount of re-fetching will extend history")
    print("further back. WF windows for 1h crypto are sized 90d/90d to fit this.")
    print("Done.")


if __name__ == "__main__":
    main()
