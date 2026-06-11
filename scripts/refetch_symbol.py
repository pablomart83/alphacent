#!/usr/bin/env python3
"""Purge + re-fetch all cached bars for one symbol (P1 wrong-instrument repair).

Use when a symbol's cached history was written under the wrong underlying
(e.g. NSDQ100 was routed to FMP ^IXIC / Nasdaq Composite instead of the
Nasdaq-100 ^NDX). Deletes the contaminated rows for the symbol across all
intervals, then re-fetches from the now-correct source via the
MarketDataManager pipeline (which upserts).

Targeted single-symbol purge of provably-wrong data — NOT a retention prune.

Run ON EC2:
    cd /home/ubuntu/alphacent && set -a && . ./.env.production && set +a && \
        venv/bin/python3 scripts/refetch_symbol.py NSDQ100
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

sys.path.insert(0, ".")

# Per-interval re-fetch lookback. 1d gets the full WF horizon + margin; intraday
# is bounded by Yahoo's ~720d rolling cap anyway.
WINDOWS_DAYS = {"1d": 1100, "4h": 700, "1h": 700}


def main(symbol: str) -> int:
    from src.core.config_loader import load_config
    from src.data.market_data_manager import MarketDataManager
    from src.models.database import get_database
    from sqlalchemy import text

    symbol = symbol.upper().strip()
    config = load_config()
    md = MarketDataManager(etoro_client=None, config=config)
    db = get_database()

    # 1. Purge contaminated rows for this symbol (all intervals).
    session = db.get_session()
    try:
        before = session.execute(
            text("SELECT count(*) FROM historical_price_cache WHERE symbol=:s"),
            {"s": symbol},
        ).scalar()
        session.execute(
            text("DELETE FROM historical_price_cache WHERE symbol=:s"), {"s": symbol}
        )
        session.commit()
        print(f"[refetch] {symbol}: purged {before} contaminated rows")
    finally:
        session.close()

    # 2. Re-fetch each interval from the corrected source.
    end = datetime.utcnow()
    for interval, days in WINDOWS_DAYS.items():
        start = end - timedelta(days=days)
        try:
            bars = md.get_historical_data(symbol, start, end, interval=interval, force_fresh=True)
            print(f"[refetch] {symbol} {interval}: {len(bars)} bars re-fetched/upserted")
        except Exception as e:  # noqa: BLE001
            print(f"[refetch] {symbol} {interval}: FAILED — {e}")

    # 3. Verify.
    session = db.get_session()
    try:
        for row in session.execute(
            text(
                "SELECT interval, source, count(*), min(date)::date, max(date)::date, "
                "min(close), max(close) FROM historical_price_cache "
                "WHERE symbol=:s GROUP BY interval, source ORDER BY interval, source"
            ),
            {"s": symbol},
        ).fetchall():
            print(f"[refetch] verify {symbol} {row[0]}/{row[1]}: {row[2]} bars "
                  f"{row[3]}→{row[4]} close[{row[5]:.1f},{row[6]:.1f}]")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: refetch_symbol.py SYMBOL")
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
