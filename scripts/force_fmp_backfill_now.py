"""One-shot FMP backfill for the full non-crypto universe.

Bypasses the _sync_price_data weekend-skip so stocks/ETFs/indices/
commodities get their full 5y backfill at 1d+1h+4h immediately, rather
than waiting for Monday's market-hours sync.

Scope:
  - All non-crypto symbols in DEMO_ALL_TRADEABLE
  - 1d, 1h, 4h
  - Only FMP-supported (symbol, interval) combos
  - Per-combo depth check: if cache already has ≥ 4y (for 1d) or
    ≥ 1.5y (for 1h/4h), skip to avoid wasted API calls. Otherwise
    full 5y backfill.

Safety:
  - Dry-run first (default). Shows how many symbols will be fetched.
  - Uses the existing fmp_ohlc.fetch_klines client — same routing and
    dedup semantics as the scheduled sync.
  - Rate-limit-aware: 300 req/min budget honoured by fetch_klines'
    ThreadPoolExecutor(max_workers=4).
  - Skips symbols already at or above target depth.

Usage:
    python3 scripts/force_fmp_backfill_now.py              # dry-run
    python3 scripts/force_fmp_backfill_now.py --execute    # run
    python3 scripts/force_fmp_backfill_now.py --execute --only 1d
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)


def _psql(sql: str) -> str:
    """Run SQL via sudo -u postgres psql."""
    res = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "alphacent", "-t", "-A", "-F", ",", "-c", sql],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(f"psql failed: {res.stderr}")
    return res.stdout


def _get_depth_days(symbol: str, interval: str, end: datetime) -> int:
    """Return how many calendar days back the current cache reaches for
    (symbol, interval). 0 if no rows."""
    out = _psql(
        f"SELECT MIN(date) FROM historical_price_cache "
        f"WHERE symbol = '{symbol}' AND interval = '{interval}';"
    ).strip()
    if not out:
        return 0
    try:
        min_dt = datetime.fromisoformat(out.split(".")[0])
        return (end - min_dt).days
    except Exception:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--only", choices=["1d", "1h", "4h"], default=None,
        help="Limit to a single interval (default: all three)",
    )
    parser.add_argument(
        "--target-days-1d", type=int, default=1460,
        help="Depth target for 1d (default 4y, skip if cache deeper)",
    )
    parser.add_argument(
        "--target-days-intraday", type=int, default=540,
        help="Depth target for 1h/4h (default 1.5y, skip if cache deeper)",
    )
    args = parser.parse_args()
    dry_run = not args.execute

    from src.core.tradeable_instruments import (
        DEMO_ALL_TRADEABLE, DEMO_ALLOWED_CRYPTO,
    )
    from src.api.fmp_ohlc import (
        is_supported, fetch_klines, FMPAPIError,
    )
    # Import market_data_manager only for DB save; we don't need full
    # config/etoro_client instantiation
    from src.models.database import get_database
    from src.models.orm import HistoricalPriceCacheORM

    crypto = set(DEMO_ALLOWED_CRYPTO)
    all_syms = [s for s in DEMO_ALL_TRADEABLE if s.upper() not in crypto]

    intervals = [args.only] if args.only else ["1d", "1h", "4h"]
    windows_days = {"1d": 1825, "1h": 1825, "4h": 1825}  # 5 years each
    target_days = {
        "1d": args.target_days_1d,
        "1h": args.target_days_intraday,
        "4h": args.target_days_intraday,
    }

    end = datetime.now()
    print(f"{'DRY-RUN' if dry_run else 'EXECUTE'} — Force FMP backfill across {len(all_syms)} non-crypto symbols")
    print(f"Intervals: {intervals}")
    print(f"Targets: {target_days}")
    print("=" * 78)

    plan: List[Tuple[str, str]] = []
    skip_shallow_supported: int = 0
    skip_deep: int = 0
    skip_unsupported: int = 0

    for sym in all_syms:
        for itv in intervals:
            if not is_supported(sym, itv):
                skip_unsupported += 1
                continue
            depth = _get_depth_days(sym, itv, end)
            if depth >= target_days[itv]:
                skip_deep += 1
                continue
            plan.append((sym, itv))
            skip_shallow_supported += 1

    print(f"  PLAN: fetch {len(plan)} (symbol, interval) combos")
    print(f"        {skip_deep} already at target depth — skip")
    print(f"        {skip_unsupported} not FMP-supported (Yahoo fallback) — skip")
    print()

    if not plan:
        print("Nothing to do — all combos already at or above target depth.")
        return 0

    if dry_run:
        # Show the first 20 combos as a sanity sample
        print("Sample (first 20):")
        for sym, itv in plan[:20]:
            d = _get_depth_days(sym, itv, end)
            print(f"    {sym:<14} {itv:<4}  current={d}d  target={target_days[itv]}d")
        if len(plan) > 20:
            print(f"    ... and {len(plan) - 20} more")
        print()
        est_seconds = len(plan) * 2  # ~2s/combo at FMP's rate limit
        print(f"Estimated runtime: ~{est_seconds // 60}m {est_seconds % 60}s "
              f"(at 300 req/min with 4 parallel workers)")
        print()
        print("Re-run with --execute to kick off the backfill.")
        return 0

    # Execute — serial per-combo, fetch_klines already parallelises pages
    print(f"Backfilling {len(plan)} combos...")
    db = get_database()
    t0 = time.time()
    ok = 0
    failed = 0
    blocked = 0
    empty = 0
    bars_total = 0
    # Inter-symbol throttle — FMP Starter is 300 req/min. Each symbol at
    # 1h with 5y needs ~22 pages × 2 parallel workers = ~11 seconds of
    # request flight. Sleep 0.5s between symbols to keep avg well below
    # 5 req/sec and leave headroom for the scheduled service sync that
    # also hits FMP.
    INTER_SYMBOL_SLEEP_S = 0.5

    for i, (sym, itv) in enumerate(plan):
        fetch_start = end - timedelta(days=windows_days[itv])
        try:
            bars = fetch_klines(sym, fetch_start, end, itv)
        except FMPAPIError as e:
            if e.reason == "premium_blocked":
                blocked += 1
            elif e.reason == "rate_limited":
                # The adapter already retried MAX_RETRIES. Log and move on.
                failed += 1
                print(f"    rate-limited after retries: {sym} {itv}")
            else:
                failed += 1
            time.sleep(INTER_SYMBOL_SLEEP_S)
            continue
        if not bars:
            empty += 1
            time.sleep(INTER_SYMBOL_SLEEP_S)
            continue
        # Save via direct ORM bulk insert (avoid instantiating full
        # MarketDataManager which needs etoro_client)
        try:
            session = db.get_session()
            try:
                existing = {
                    r[0] for r in session.query(HistoricalPriceCacheORM.date).filter(
                        HistoricalPriceCacheORM.symbol == sym,
                        HistoricalPriceCacheORM.interval == itv,
                        HistoricalPriceCacheORM.date >= bars[0].timestamp,
                        HistoricalPriceCacheORM.date <= bars[-1].timestamp,
                    ).all()
                }
                new_rows: list = []
                now_dt = datetime.now()
                for b in bars:
                    ts = b.timestamp
                    if hasattr(ts, 'tzinfo') and ts.tzinfo:
                        ts = ts.replace(tzinfo=None)
                    if itv == "1d":
                        ts = ts.replace(hour=0, minute=0, second=0, microsecond=0)
                    if ts in existing:
                        continue
                    new_rows.append(HistoricalPriceCacheORM(
                        symbol=sym,
                        date=ts,
                        interval=itv,
                        open=b.open, high=b.high, low=b.low, close=b.close,
                        volume=b.volume,
                        source=b.source.value if hasattr(b.source, 'value') else str(b.source),
                        fetched_at=now_dt,
                    ))
                if new_rows:
                    session.bulk_save_objects(new_rows)
                    session.commit()
                    bars_total += len(new_rows)
            finally:
                session.close()
            ok += 1
        except Exception as e:
            failed += 1
            print(f"    DB save failed for {sym} {itv}: {e}")
            time.sleep(INTER_SYMBOL_SLEEP_S)
            continue
        time.sleep(INTER_SYMBOL_SLEEP_S)
        # Progress
        if (i + 1) % 25 == 0 or (i + 1) == len(plan):
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"  {i+1}/{len(plan)}: ok={ok} blocked={blocked} empty={empty} "
                  f"failed={failed} bars={bars_total:,}  ({rate:.1f}/s)")

    elapsed = time.time() - t0
    print()
    print(f"DONE in {elapsed:.0f}s — ok={ok} blocked={blocked} empty={empty} "
          f"failed={failed}  total new bars={bars_total:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
