"""Verify 24/5 eligibility for every BACKTESTED + DEMO strategy in the library.

Takes the live strategies.status IN ('BACKTESTED', 'DEMO') list, looks up each
primary symbol's asset class, and calls MarketHoursManager.is_market_open at
6 representative ET times:

  1. US regular hours (Mon 10:00 ET)               — every schedule open
  2. US post-market       (Mon 18:00 ET)           — 24/5 stocks open, regular-session closed
  3. US overnight         (Tue 02:00 ET)           — 24/5 stocks open, US_EXTENDED closed
  4. US pre-market        (Tue 07:00 ET)           — 24/5 stocks open + US_EXTENDED
  5. Saturday             (Sat 12:00 ET)           — everything closed except crypto
  6. Sunday reopen        (Sun 21:00 ET)           — 24/5 stocks just reopened

For each strategy we print: primary symbol, asset class, schedule, and a 6-col
open/closed grid. The summary answers the real question: for each BACKTESTED
strategy, is the system capable of submitting its order during 24/5 hours?
"""

import sys
from collections import Counter
from datetime import datetime
from typing import Tuple

import pytz

from src.core.symbol_registry import get_registry
from src.data.market_hours_manager import (
    AssetClass,
    MarketHoursManager,
    MarketSchedule,
)
from src.models.database import get_database
from src.models.orm import StrategyORM

ET = pytz.timezone("US/Eastern")


# Six test times, anchored to the coming week
REF = datetime(2026, 5, 4)  # This Monday
TEST_TIMES = [
    ("regular",      ET.localize(REF.replace(hour=10, minute=0))),             # Mon 10:00 ET
    ("post_market",  ET.localize(REF.replace(hour=18, minute=0))),             # Mon 18:00 ET
    ("overnight",    ET.localize(REF.replace(day=5, hour=2, minute=0))),       # Tue 02:00 ET
    ("pre_market",   ET.localize(REF.replace(day=5, hour=7, minute=0))),       # Tue 07:00 ET
    ("saturday",     ET.localize(REF.replace(day=9, hour=12, minute=0))),      # Sat 12:00 ET
    ("sun_reopen",   ET.localize(REF.replace(day=10, hour=21, minute=0))),     # Sun 21:00 ET
]


def classify(symbol: str, reg) -> Tuple[AssetClass, str]:
    """Map symbol → AssetClass (using live SymbolRegistry)."""
    ac_str = (reg.get_asset_class(symbol) or "unknown").lower()
    if ac_str == "stocks":
        return AssetClass.STOCK, "stocks"
    if ac_str == "etfs":
        return AssetClass.ETF, "etfs"
    if ac_str == "forex":
        return AssetClass.FOREX, "forex"
    if ac_str == "crypto":
        return AssetClass.CRYPTOCURRENCY, "crypto"
    if ac_str == "commodities":
        return AssetClass.COMMODITY, "commodities"
    if ac_str == "indices":
        return AssetClass.INDEX, "indices"
    return AssetClass.STOCK, "unknown"  # safest default


def main() -> int:
    reg = get_registry()
    mhm = MarketHoursManager()  # singleton OK for a one-off script

    db = get_database()
    session = db.get_session()
    try:
        rows = (
            session.query(StrategyORM)
            .filter(StrategyORM.status.in_(["BACKTESTED", "DEMO"]))
            .all()
        )
        rows_data = [
            (r.name, r.status.value if hasattr(r.status, "value") else str(r.status),
             (r.symbols or []), (r.strategy_metadata or {}))
            for r in rows
        ]
    finally:
        session.close()

    print(f"Evaluating {len(rows_data)} BACKTESTED + DEMO strategies\n")
    print(f"Test times (ET):")
    for label, dt in TEST_TIMES:
        print(f"  {label:<12} {dt.strftime('%a %Y-%m-%d %H:%M %Z')}")
    print()

    # Counters for the summary
    status_counter: Counter = Counter()  # status_counter[(status, test_label)] = open_count
    total_by_status: Counter = Counter()
    schedule_breakdown: Counter = Counter()  # (status, schedule) -> count

    # Detail grid
    header = f"{'status':<11} {'symbol':<10} {'asset_class':<14} {'schedule':<20} | " + " ".join(f"{l:<11}" for l, _ in TEST_TIMES)
    print(header)
    print("-" * len(header))

    for name, status, symbols, meta in rows_data:
        primary = (symbols[0] if symbols else "").upper() if symbols else ""
        if not primary:
            continue
        ac, ac_lbl = classify(primary, reg)
        schedule = mhm.get_schedule(ac, primary)
        schedule_breakdown[(status, schedule.value)] += 1
        total_by_status[status] += 1

        cells = []
        for label, t in TEST_TIMES:
            is_open = mhm.is_market_open(ac, check_time=t, symbol=primary)
            cells.append("OPEN" if is_open else "closed")
            if is_open:
                status_counter[(status, label)] += 1

        # Only print first 30 rows in detail to keep output scannable
        # (full coverage is in the summary). Flip this constant to see all.
        if total_by_status[status] <= 15:
            print(
                f"{status:<11} {primary:<10} {ac_lbl:<14} "
                f"{schedule.value:<20} | "
                + " ".join(f"{c:<11}" for c in cells)
            )

    print("-" * len(header))
    print()
    print("SUMMARY — open strategies at each test time, by status:")
    for status in ("BACKTESTED", "DEMO"):
        total = total_by_status[status]
        if total == 0:
            continue
        print(f"\n  {status} (n={total}):")
        for label, _ in TEST_TIMES:
            opened = status_counter[(status, label)]
            pct = (100.0 * opened / total) if total else 0.0
            print(f"    {label:<12}  {opened:>4} / {total}  ({pct:5.1f}%)")

    print()
    print("SCHEDULE DISTRIBUTION:")
    for (status, sched), count in sorted(schedule_breakdown.items()):
        print(f"  {status:<11}  {sched:<22}  {count}")

    print()
    # The 24/5 verdict — what % of US-equity BACKTESTED strategies are
    # eligible for order submission during the 24/5 window?
    print("24/5 VERDICT (using Tue 02:00 ET overnight as the canonical 24/5-only window):")
    for status in ("BACKTESTED", "DEMO"):
        total = total_by_status[status]
        if total == 0:
            continue
        overnight_open = status_counter[(status, "overnight")]
        sat_open = status_counter[(status, "saturday")]
        print(f"  {status:<11}  overnight open = {overnight_open}/{total}, saturday open = {sat_open}/{total}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
