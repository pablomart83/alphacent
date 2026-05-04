"""Print the current schedule + open/closed state for one representative
symbol per asset class. Use to confirm live behaviour post-deploy.

    python3 scripts/check_market_hours_live.py
"""

from datetime import datetime

import pytz

from src.data.market_hours_manager import AssetClass, MarketHoursManager


def main() -> int:
    mhm = MarketHoursManager()
    et = datetime.now(pytz.timezone("US/Eastern"))
    print(f"Current ET: {et.strftime('%a %Y-%m-%d %H:%M:%S %Z')}\n")

    cases = [
        (AssetClass.STOCK, "AAPL"),
        (AssetClass.STOCK, "TSLA"),
        (AssetClass.ETF, "SPY"),
        (AssetClass.ETF, "QQQ"),
        (AssetClass.FOREX, "EURUSD"),
        (AssetClass.FOREX, "USDJPY"),
        (AssetClass.CRYPTOCURRENCY, "BTC"),
        (AssetClass.INDEX, "SPX500"),
        (AssetClass.INDEX, "NSDQ100"),
        (AssetClass.INDEX, "UK100"),
        (AssetClass.INDEX, "GER40"),
        (AssetClass.COMMODITY, "GOLD"),
        (AssetClass.COMMODITY, "OIL"),
    ]

    for ac, sym in cases:
        sched = mhm.get_schedule(ac, sym)
        open_now = mhm.is_market_open(ac, symbol=sym)
        print(f"  {sym:<10} {ac.value:<18} -> schedule={sched.value:<22} open_now={open_now}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
