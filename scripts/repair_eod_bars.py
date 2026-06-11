#!/usr/bin/env python3
"""One-time repair of frozen provisional 1d bars (P0, 2026-06-11).

Background
----------
`MarketDataManager._save_historical_to_db` was insert-only: it skipped any
(symbol, date, interval) already present and never updated it. The full sync
writes today's *forming* 1d bar the first time it runs each morning, so that
bar froze at a ~market-open snapshot and was never corrected to the real EOD
close. Verified live: AAPL 1d 2026-06-10 stored close 290.31 while the true
close (from intraday 1h bars) was ~291.66.

Affected rows: 1d bars whose `fetched_at::date = date::date` — written on
their own trading day. ~8,552 such bars, all since 2026-05-03 (FMP-1d
go-live).

This script re-fetches the affected window from the authoritative source via
the (now-upserting) MarketDataManager pipeline and overwrites the frozen bars
with the completed EOD values. The current still-forming day is skipped by
`_bar_is_complete`, so no new provisional bar is written.

Idempotent: safe to re-run. Reads + upserts only; no deletes.

Run ON EC2 (it needs FMP/Yahoo access + the live DB):
    cd /home/ubuntu/alphacent && venv/bin/python3 scripts/repair_eod_bars.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

sys.path.insert(0, ".")

# Repair window: a little before the corruption start (2026-05-03) to now.
REPAIR_START = datetime(2026, 4, 25)


def main() -> int:
    from src.core.config_loader import load_config
    from src.data.market_data_manager import MarketDataManager
    from src.models.database import get_database
    from sqlalchemy import text

    config = load_config()
    md = MarketDataManager(etoro_client=None, config=config)

    db = get_database()
    session = db.get_session()
    try:
        symbols = [
            r[0]
            for r in session.execute(
                text(
                    "SELECT DISTINCT symbol FROM historical_price_cache "
                    "WHERE interval = '1d' ORDER BY symbol"
                )
            ).fetchall()
        ]
    finally:
        session.close()

    end = datetime.utcnow()
    print(f"[repair] {len(symbols)} symbols, window {REPAIR_START.date()} → {end.date()}")

    ok = 0
    failed = 0
    for i, sym in enumerate(symbols, 1):
        try:
            bars = md.get_historical_data(
                sym, REPAIR_START, end, interval="1d", force_fresh=True
            )
            ok += 1
            if i % 25 == 0 or len(bars) == 0:
                print(f"[repair] {i}/{len(symbols)} {sym}: {len(bars)} bars re-fetched/upserted")
        except Exception as e:  # noqa: BLE001 — per-symbol isolation, keep going
            failed += 1
            print(f"[repair] {i}/{len(symbols)} {sym}: FAILED — {e}")

    print(f"[repair] done. ok={ok} failed={failed}")

    # Verification sample — AAPL 2026-06-10 should now match its intraday close.
    session = db.get_session()
    try:
        row = session.execute(
            text(
                "SELECT date::date, close, fetched_at FROM historical_price_cache "
                "WHERE symbol='AAPL' AND interval='1d' AND date='2026-06-10' "
            )
        ).fetchone()
        if row:
            print(f"[repair] verify AAPL 2026-06-10 → close={row[1]} fetched_at={row[2]}")
    finally:
        session.close()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
