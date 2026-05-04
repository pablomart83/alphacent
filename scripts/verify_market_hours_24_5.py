"""Sanity-check the market_hours_manager 24/5 rewrite against a
hand-crafted truth table. Run locally (no DB access needed):

    python3 scripts/verify_market_hours_24_5.py

Exits 0 on all-green, 1 on any mismatch.
"""

import sys
from datetime import datetime

import pytz

from src.data.market_hours_manager import (
    AssetClass,
    MarketHoursManager,
    MarketSchedule,
)

ET = pytz.timezone("US/Eastern")


def _et(y: int, m: int, d: int, hh: int, mm: int = 0) -> datetime:
    return ET.localize(datetime(y, m, d, hh, mm))


# Each case: (label, asset_class, symbol, et_time, expected)
# Week of 2026-05-04 (Mon) through 2026-05-10 (Sun). Not a holiday week.
CASES = [
    # --- 24/5 stocks (S&P/NDX) — ETORO_24_5 ---
    ("Mon 10:00 AAPL 24/5",      AssetClass.STOCK, "AAPL",   _et(2026, 5, 4, 10, 0),  True),
    ("Mon 02:00 AAPL 24/5 (pre)",AssetClass.STOCK, "AAPL",   _et(2026, 5, 4, 2, 0),   True),
    ("Fri 15:30 AAPL 24/5",      AssetClass.STOCK, "AAPL",   _et(2026, 5, 8, 15, 30), True),
    ("Fri 16:00 AAPL 24/5 close",AssetClass.STOCK, "AAPL",   _et(2026, 5, 8, 16, 0),  False),
    ("Fri 16:01 AAPL closed",    AssetClass.STOCK, "AAPL",   _et(2026, 5, 8, 16, 1),  False),
    ("Sat 12:00 AAPL closed",    AssetClass.STOCK, "AAPL",   _et(2026, 5, 9, 12, 0),  False),
    ("Sun 20:00 AAPL still closed", AssetClass.STOCK, "AAPL",_et(2026, 5, 10, 20, 0), False),
    ("Sun 20:05 AAPL reopen",    AssetClass.STOCK, "AAPL",   _et(2026, 5, 10, 20, 5), True),
    # --- ETF default is also ETORO_24_5 ---
    ("Tue 03:00 SPY 24/5",       AssetClass.ETF,   "SPY",    _et(2026, 5, 5, 3, 0),   True),
    # --- Crypto: always ---
    ("Sat 14:00 BTC 24/7",       AssetClass.CRYPTOCURRENCY, "BTC", _et(2026, 5, 9, 14, 0), True),
    # --- Forex: Sun 17 → Fri 17 ---
    ("Mon 23:00 EURUSD open",    AssetClass.FOREX, "EURUSD", _et(2026, 5, 4, 23, 0),  True),
    ("Sat 08:00 EURUSD closed",  AssetClass.FOREX, "EURUSD", _et(2026, 5, 9, 8, 0),   False),
    ("Sun 16:59 EURUSD closed",  AssetClass.FOREX, "EURUSD", _et(2026, 5, 10, 16, 59),False),
    ("Sun 17:00 EURUSD reopen",  AssetClass.FOREX, "EURUSD", _et(2026, 5, 10, 17, 0), True),
    ("Fri 16:59 EURUSD open",    AssetClass.FOREX, "EURUSD", _et(2026, 5, 8, 16, 59), True),
    ("Fri 17:00 EURUSD closed",  AssetClass.FOREX, "EURUSD", _et(2026, 5, 8, 17, 0),  False),
    # --- US indices (SPX500/NSDQ100/DJ30) — CME E-mini ---
    ("Mon 10:00 SPX500 open",    AssetClass.INDEX, "SPX500", _et(2026, 5, 4, 10, 0),  True),
    ("Mon 17:30 SPX500 break",   AssetClass.INDEX, "SPX500", _et(2026, 5, 4, 17, 30), False),
    ("Mon 18:00 SPX500 reopen",  AssetClass.INDEX, "SPX500", _et(2026, 5, 4, 18, 0),  True),
    ("Sun 17:59 SPX500 closed",  AssetClass.INDEX, "SPX500", _et(2026, 5, 10, 17, 59),False),
    ("Sun 18:00 SPX500 reopen",  AssetClass.INDEX, "SPX500", _et(2026, 5, 10, 18, 0), True),
    # --- Non-US index ---
    ("Mon 05:00 UK100 open",     AssetClass.INDEX, "UK100",  _et(2026, 5, 4, 5, 0),   True),
    ("Mon 12:00 UK100 closed",   AssetClass.INDEX, "UK100",  _et(2026, 5, 4, 12, 0),  False),
    ("Sun 05:00 UK100 closed",   AssetClass.INDEX, "UK100",  _et(2026, 5, 10, 5, 0),  False),
    # --- Commodities (CME) ---
    ("Mon 10:00 GOLD open",      AssetClass.COMMODITY, "GOLD", _et(2026, 5, 4, 10, 0), True),
    ("Mon 17:30 GOLD break",     AssetClass.COMMODITY, "GOLD", _et(2026, 5, 4, 17, 30), False),
    # --- US holiday closure: 2026-05-25 is Memorial Day (Monday) ---
    ("Memorial Day Mon AAPL",    AssetClass.STOCK, "AAPL",   _et(2026, 5, 25, 10, 0), False),
    ("Memorial Day Mon SPY",     AssetClass.ETF,   "SPY",    _et(2026, 5, 25, 10, 0), False),
    # --- Early close: Fri 2026-11-27 (Black Friday half-day) ---
    ("BlackFri 12:00 AAPL open", AssetClass.STOCK, "AAPL",   _et(2026, 11, 27, 12, 0), True),
    ("BlackFri 13:00 AAPL closed",AssetClass.STOCK, "AAPL",  _et(2026, 11, 27, 13, 0), False),
]


def main() -> int:
    mhm = MarketHoursManager()
    failures = []
    for label, ac, sym, t, expected in CASES:
        got = mhm.is_market_open(ac, check_time=t, symbol=sym)
        status = "PASS" if got == expected else "FAIL"
        line = f"{status}  {label:<36} expected={expected} got={got}"
        print(line)
        if got != expected:
            failures.append(line)

    print()
    print(f"{len(CASES) - len(failures)}/{len(CASES)} passed")
    if failures:
        print("\nFailed cases:")
        for f in failures:
            print("  " + f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
