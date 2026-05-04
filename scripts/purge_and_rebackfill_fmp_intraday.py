"""One-shot cleanup of the FMP intraday cache corruption discovered 2026-05-04.

Context — what we're fixing:

  Two separate write paths have been co-polluting `historical_price_cache`
  for 1h (and, to a lesser degree, 4h) bars:

  (1) The FMP sync path in `monitoring_service._sync_price_data` has been
      storing FMP's naive intraday timestamps as-is. FMP returns those
      timestamps in US/Eastern local time but the rest of the codebase
      treats DB timestamps as naive UTC. This means every 1h/4h bar
      sourced from FMP has been stored 4-5 hours in the future (EDT) or
      5 hours (EST). Freshness math under-reported bar age by the same
      offset — which is why the 141 "stuck" symbols looked only 1.5h
      stale to the incremental-gap gate rather than the real 5.5h.

  (2) The `_quick_price_update` path has been writing synthetic single-
      tick bars to the same table — O=H=L=C=price, V=0, tagged FMP (or
      BINANCE / YAHOO depending on asset class). These are sentinel
      bars useful for in-memory live-price access but they destroy the
      OHLC semantics of any quant indicator computed over them.

  The fmp_ohlc and monitoring_service fixes shipped alongside this
  script correct BOTH issues going forward. This script cleans up the
  inconsistent DB state so the system converges to one uniform
  convention: every intraday bar in the cache is real OHLCV, stamped
  in naive UTC, sourced from FMP (non-crypto) or Binance (crypto).

What this script does:

  Phase 1 — delete synthetic placeholder bars. Any row in
    historical_price_cache where open == high == low == close AND
    volume == 0. Covers every interval. Only affects intraday bars
    in practice (EOD bars always have a volume > 0 once markets close).

  Phase 2 — delete all FMP-sourced 1h and 4h rows. They have the wrong
    timezone convention. Trying to shift them in-place is error-prone
    (DST boundaries, winter/summer offsets) and the rebackfill is
    cheap. Crypto bars (Binance) and 1d bars (FMP EOD, date-only) are
    preserved.

  Phase 3 — rebackfill 1h and 4h for every non-crypto symbol via FMP,
    using the fixed fmp_ohlc adapter. New bars land in UTC. 5-year
    depth restored.

Safety:
  - Dry-run first (default).
  - Phase counts printed before any deletion.
  - Rebackfill uses the same fetch_klines adapter as the scheduled
    sync, respects the 300/min rate limit.
  - Safe to re-run. Phase 1/2 are idempotent (nothing to delete on a
    clean DB); Phase 3 skips symbols already at depth.

Usage:
  python3 scripts/purge_and_rebackfill_fmp_intraday.py                 # dry-run
  python3 scripts/purge_and_rebackfill_fmp_intraday.py --execute       # run
  python3 scripts/purge_and_rebackfill_fmp_intraday.py --execute \
      --skip-rebackfill                                                # cleanup only
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import List, Tuple

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)


def _psql(sql: str) -> str:
    res = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "alphacent", "-t", "-A", "-F", ",", "-c", sql],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(f"psql failed: {res.stderr}")
    return res.stdout


def _count(sql_where: str) -> int:
    out = _psql(f"SELECT COUNT(*) FROM historical_price_cache WHERE {sql_where};").strip()
    try:
        return int(out)
    except ValueError:
        return 0


def _delete(sql_where: str, dry_run: bool) -> int:
    if dry_run:
        return _count(sql_where)
    # Run count first so we can report, then DELETE. Postgres's RETURNING
    # on bulk DELETE is expensive on large tables — simpler to count+delete.
    before = _count(sql_where)
    _psql(f"DELETE FROM historical_price_cache WHERE {sql_where};")
    return before


def phase1_purge_synthetic(dry_run: bool) -> int:
    """Remove synthetic single-tick bars (O=H=L=C, V=0)."""
    print()
    print("=" * 78)
    print("Phase 1 — purge synthetic placeholder bars (O=H=L=C, V=0)")
    print("=" * 78)

    # Breakdown by interval + source so we can see the scope
    print()
    print("Breakdown before deletion:")
    rows = _psql(
        "SELECT interval, source, COUNT(*) FROM historical_price_cache "
        "WHERE volume = 0 AND \"open\" = high AND \"open\" = low AND \"open\" = close "
        "GROUP BY interval, source ORDER BY interval, source;"
    ).strip().splitlines()
    for r in rows:
        if r.strip():
            print(f"  {r}")

    where = (
        'volume = 0 AND "open" = high AND "open" = low AND "open" = close'
    )
    count = _delete(where, dry_run)
    verb = "Would delete" if dry_run else "Deleted"
    print(f"\n{verb} {count:,} synthetic bars.")
    return count


def phase2_purge_fmp_intraday(dry_run: bool) -> int:
    """Remove all FMP-sourced 1h/4h rows (ET-timestamped, wrong convention)."""
    print()
    print("=" * 78)
    print("Phase 2 — purge FMP intraday bars (wrong timezone convention)")
    print("=" * 78)

    print()
    print("Breakdown before deletion:")
    rows = _psql(
        "SELECT interval, source, COUNT(*) FROM historical_price_cache "
        "WHERE source = 'FMP' AND interval IN ('1h', '4h') "
        "GROUP BY interval, source ORDER BY interval;"
    ).strip().splitlines()
    for r in rows:
        if r.strip():
            print(f"  {r}")

    where = "source = 'FMP' AND interval IN ('1h', '4h')"
    count = _delete(where, dry_run)
    verb = "Would delete" if dry_run else "Deleted"
    print(f"\n{verb} {count:,} FMP intraday bars.")
    return count


def phase3_rebackfill(dry_run: bool) -> int:
    """Re-fetch 1h and 4h for every non-crypto symbol via (fixed) FMP adapter."""
    print()
    print("=" * 78)
    print("Phase 3 — rebackfill 1h + 4h via (UTC-correct) FMP adapter")
    print("=" * 78)

    from src.core.tradeable_instruments import (
        DEMO_ALL_TRADEABLE, DEMO_ALLOWED_CRYPTO,
    )
    from src.api.fmp_ohlc import (
        is_supported, fetch_klines, FMPAPIError,
    )
    from src.models.database import get_database
    from src.models.orm import HistoricalPriceCacheORM

    crypto = set(DEMO_ALLOWED_CRYPTO)
    all_syms = [s for s in DEMO_ALL_TRADEABLE if s.upper() not in crypto]
    intervals = ["1h", "4h"]

    plan: List[Tuple[str, str]] = []
    skip_unsupported = 0
    for sym in all_syms:
        for itv in intervals:
            if not is_supported(sym, itv):
                skip_unsupported += 1
                continue
            plan.append((sym, itv))

    print(f"\n  PLAN: fetch {len(plan)} (symbol, interval) combos")
    print(f"        {skip_unsupported} not FMP-supported (Yahoo fallback) — skip")

    if dry_run:
        est = len(plan) * 2  # ~2s/combo including throttle
        print(f"\n  Estimated runtime: ~{est // 60}m {est % 60}s")
        print("  Re-run with --execute to kick off the backfill.")
        return 0

    end = datetime.now()
    window = timedelta(days=1825)  # 5y
    db = get_database()

    t0 = time.time()
    ok = 0
    failed = 0
    blocked = 0
    empty = 0
    bars_total = 0
    INTER_SYMBOL_SLEEP_S = 0.5

    for i, (sym, itv) in enumerate(plan):
        fetch_start = end - window
        try:
            bars = fetch_klines(sym, fetch_start, end, itv)
        except FMPAPIError as e:
            if e.reason == "premium_blocked":
                blocked += 1
            else:
                failed += 1
                print(f"    {e.reason}: {sym} {itv}")
            time.sleep(INTER_SYMBOL_SLEEP_S)
            continue
        if not bars:
            empty += 1
            time.sleep(INTER_SYMBOL_SLEEP_S)
            continue
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
                    if ts in existing:
                        continue
                    new_rows.append(HistoricalPriceCacheORM(
                        symbol=sym, date=ts, interval=itv,
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

        if (i + 1) % 25 == 0 or (i + 1) == len(plan):
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            print(f"  {i+1}/{len(plan)}: ok={ok} blocked={blocked} empty={empty} "
                  f"failed={failed} bars={bars_total:,}  ({rate:.1f}/s)")

    elapsed = time.time() - t0
    print(
        f"\n  Phase 3 DONE in {elapsed:.0f}s — "
        f"ok={ok} blocked={blocked} empty={empty} failed={failed}  "
        f"new bars={bars_total:,}"
    )
    return bars_total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--skip-phase1", action="store_true",
                        help="Skip synthetic-bar purge")
    parser.add_argument("--skip-phase2", action="store_true",
                        help="Skip FMP intraday purge")
    parser.add_argument("--skip-rebackfill", action="store_true",
                        help="Skip Phase 3 rebackfill")
    args = parser.parse_args()
    dry_run = not args.execute

    print(f"{'DRY-RUN' if dry_run else 'EXECUTE'} — FMP intraday cache cleanup")
    print(f"Started at {datetime.utcnow().isoformat()}Z")

    total_deleted = 0
    if not args.skip_phase1:
        total_deleted += phase1_purge_synthetic(dry_run)
    if not args.skip_phase2:
        total_deleted += phase2_purge_fmp_intraday(dry_run)

    new_bars = 0
    if not args.skip_rebackfill:
        new_bars = phase3_rebackfill(dry_run)

    print()
    print("=" * 78)
    verb = "Would affect" if dry_run else "Affected"
    print(f"SUMMARY — {verb}: {total_deleted:,} rows deleted, {new_bars:,} new bars fetched")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
