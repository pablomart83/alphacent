"""Market hours manager — symbol-aware trading-window resolver.

2026-05-04: rewrite for eToro 24/5 reality.

eToro now offers 24/5 trading on all S&P 500 + Nasdaq 100 stocks + a broad
basket of top ETFs (Sun 20:05 ET → Fri 16:00 ET). Our older logic only knew
NYSE regular hours (9:30-16:00 ET), which meant 4H strategies closing at
00:00/04:00/20:00 ET got their signals deferred by the system even though
eToro would happily accept the order.

This module is the single primitive every trading-path caller uses to ask
"is this symbol tradeable right now?". Callers no longer reproduce the
logic inline — the old scattered `now_et.hour >= 4 and now_et.hour < 20`
pattern has been deleted.

Six schedule regimes, selected by `(asset_class, symbol)`:

| Regime              | Window (ET)                                  | Applies to |
|---------------------|----------------------------------------------|------------|
| CRYPTO_24_7         | always open                                  | crypto     |
| ETORO_24_5          | Sun 20:05 → Fri 16:00, holidays closed       | S&P/NDX stocks + top ETFs (default for STOCK/ETF) |
| US_EXTENDED         | Mon-Fri 04:00-20:00, holidays closed         | non-24/5 US stocks/ETFs (explicit opt-out) |
| FOREX_24_5          | Sun 17:00 → Fri 17:00, continuous            | forex      |
| US_INDEX_FUTURES    | Sun 18:00 → Fri 17:00 with 17:00-18:00 break | SPX500, NSDQ100, DJ30 (CME E-mini) |
| NON_US_INDEX        | local exchange hours                         | UK100, GER40, FR40, STOXX50 |
| COMMODITY_FUTURES   | Sun 18:00 → Fri 17:00 with daily 17:00-18:00 | GOLD/SILVER/OIL/COPPER (CME) |

The 24/5 window on eToro is platform policy, not exchange-driven — confirmed
from eToro's 2025-11-17 press release.

Schedule selection precedence:
  1. symbols.yaml `market_schedule:` field (explicit override, e.g. opt a
     specific stock out of 24/5 if eToro excludes it)
  2. asset_class default (STOCK/ETF → ETORO_24_5, FOREX → FOREX_24_5, ...)
  3. fallback: treat as closed (safest)
"""

import logging
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)


class AssetClass(str, Enum):
    """Asset class types with different market hours.

    Extended 2026-05-04 to include FOREX/INDEX/COMMODITY — previously only
    STOCK/ETF/CRYPTOCURRENCY existed on this enum while callers (order_executor
    `_determine_asset_class`) returned FOREX/COMMODITY/INDEX values. Python
    resolved those at runtime via `AttributeError` → swallowed by a try/except
    → silent fallback to STOCK. Now they're first-class.
    """
    STOCK = "STOCK"
    ETF = "ETF"
    FOREX = "FOREX"
    INDEX = "INDEX"
    COMMODITY = "COMMODITY"
    CRYPTOCURRENCY = "CRYPTOCURRENCY"


class MarketSchedule(str, Enum):
    """The six trading-window regimes. See module docstring."""
    CRYPTO_24_7 = "crypto_24_7"
    ETORO_24_5 = "etoro_24_5"
    US_EXTENDED = "us_extended"
    FOREX_24_5 = "forex_24_5"
    US_INDEX_FUTURES = "us_index_futures"
    COMMODITY_FUTURES = "commodity_futures"
    NON_US_INDEX = "non_us_index"


class Exchange(str, Enum):
    """Supported exchanges — retained for backward compatibility with older
    callers that reasoned about exchanges directly. New code uses MarketSchedule."""
    NYSE = "NYSE"
    NASDAQ = "NASDAQ"
    LSE = "LSE"
    CRYPTO = "CRYPTO"


# ---------------------------------------------------------------------------
# Holiday calendar — US markets. Holidays close ETORO_24_5, US_EXTENDED, and
# (per CME rules) US_INDEX_FUTURES and COMMODITY_FUTURES too.
# ---------------------------------------------------------------------------
US_HOLIDAYS: Set[datetime] = {
    # 2024
    datetime(2024, 1, 1), datetime(2024, 1, 15), datetime(2024, 2, 19),
    datetime(2024, 3, 29), datetime(2024, 5, 27), datetime(2024, 6, 19),
    datetime(2024, 7, 4), datetime(2024, 9, 2), datetime(2024, 11, 28),
    datetime(2024, 12, 25),
    # 2025
    datetime(2025, 1, 1), datetime(2025, 1, 20), datetime(2025, 2, 17),
    datetime(2025, 4, 18), datetime(2025, 5, 26), datetime(2025, 6, 19),
    datetime(2025, 7, 4), datetime(2025, 9, 1), datetime(2025, 11, 27),
    datetime(2025, 12, 25),
    # 2026
    datetime(2026, 1, 1), datetime(2026, 1, 19), datetime(2026, 2, 16),
    datetime(2026, 4, 3), datetime(2026, 5, 25), datetime(2026, 6, 19),
    datetime(2026, 7, 3), datetime(2026, 9, 7), datetime(2026, 11, 26),
    datetime(2026, 12, 25),
}

# Early close days — 1:00 PM ET close for US stock markets.
US_EARLY_CLOSE: Set[datetime] = {
    datetime(2024, 7, 3), datetime(2024, 11, 29), datetime(2024, 12, 24),
    datetime(2025, 7, 3), datetime(2025, 11, 28), datetime(2025, 12, 24),
    datetime(2026, 11, 27), datetime(2026, 12, 24),
}


def _is_us_holiday(check_time: datetime) -> bool:
    d = check_time.date()
    return datetime(d.year, d.month, d.day) in US_HOLIDAYS


def _is_us_early_close(check_time: datetime) -> bool:
    d = check_time.date()
    return datetime(d.year, d.month, d.day) in US_EARLY_CLOSE


# ---------------------------------------------------------------------------
# Schedule check implementations. Each takes an ET-localized datetime and
# returns True if eToro will accept an order for a symbol on this schedule.
# ---------------------------------------------------------------------------

def _check_crypto_24_7(now_et: datetime) -> bool:
    return True


def _check_etoro_24_5(now_et: datetime) -> bool:
    """eToro 24/5: Sun 20:05 ET → Fri 16:00 ET. Closed on US holidays.
    Respects early-close days (1:00 PM ET).
    """
    weekday = now_et.weekday()  # Mon=0, Sun=6
    hhmm = now_et.time()

    # US holiday → closed
    if _is_us_holiday(now_et):
        return False

    # Early close day → closed from 13:00 ET
    if _is_us_early_close(now_et) and hhmm >= time(13, 0):
        return False

    # Saturday: closed all day
    if weekday == 5:
        return False

    # Sunday: open from 20:05 ET only
    if weekday == 6:
        return hhmm >= time(20, 5)

    # Friday: closed from 16:00 ET
    if weekday == 4:
        return hhmm < time(16, 0)

    # Mon/Tue/Wed/Thu: always open during these days (24h)
    return True


def _check_us_extended(now_et: datetime) -> bool:
    """Pre + regular + post US market hours: Mon-Fri 04:00-20:00 ET.
    Closed on holidays. Respects early-close days (1:00 PM ET).
    """
    weekday = now_et.weekday()
    hhmm = now_et.time()

    if weekday >= 5:  # Sat/Sun
        return False

    if _is_us_holiday(now_et):
        return False

    if _is_us_early_close(now_et) and hhmm >= time(13, 0):
        return False

    return time(4, 0) <= hhmm < time(20, 0)


def _check_forex_24_5(now_et: datetime) -> bool:
    """Forex: Sun 17:00 ET → Fri 17:00 ET, continuous. eToro follows this
    standard FX-market window. US holidays have reduced liquidity but don't
    close FX; we keep it open.
    """
    weekday = now_et.weekday()
    hhmm = now_et.time()

    # Saturday closed all day
    if weekday == 5:
        return False

    # Sunday: open from 17:00 ET
    if weekday == 6:
        return hhmm >= time(17, 0)

    # Friday: closed from 17:00 ET
    if weekday == 4:
        return hhmm < time(17, 0)

    # Mon-Thu: 24h
    return True


def _check_us_index_futures(now_et: datetime) -> bool:
    """CME E-mini index futures (SPX500/NSDQ100/DJ30 CFDs on eToro):
    Sun 18:00 ET → Fri 17:00 ET, with a daily maintenance break 17:00-18:00 ET
    Mon-Thu. Closed on US holidays.
    """
    weekday = now_et.weekday()
    hhmm = now_et.time()

    if _is_us_holiday(now_et):
        return False

    # Saturday: closed
    if weekday == 5:
        return False

    # Sunday: open from 18:00 ET
    if weekday == 6:
        return hhmm >= time(18, 0)

    # Friday: closed from 17:00 ET (no reopen Sunday in this check)
    if weekday == 4:
        return hhmm < time(17, 0)

    # Mon-Thu: open except for 17:00-18:00 ET daily break
    return not (time(17, 0) <= hhmm < time(18, 0))


def _check_commodity_futures(now_et: datetime) -> bool:
    """CME commodity futures schedule (gold/silver/oil/copper CFDs on eToro):
    Sun 18:00 ET → Fri 17:00 ET, with 17:00-18:00 ET daily break Mon-Thu.
    Matches US_INDEX_FUTURES structurally. Closed on US holidays.
    """
    return _check_us_index_futures(now_et)


def _check_non_us_index(now_et: datetime) -> bool:
    """Non-US indices (UK100/GER40/FR40/STOXX50): local exchange hours
    approximated as 02:00-11:30 ET (≈ 07:00-16:30 London, 08:00-17:30 CET).
    Closed weekends. Holidays follow local calendar — we don't encode those;
    a holiday-closed venue will return empty data from eToro, which surfaces
    separately via the FAILED-order path.
    """
    weekday = now_et.weekday()
    hhmm = now_et.time()

    if weekday >= 5:
        return False

    return time(2, 0) <= hhmm < time(11, 30)


_SCHEDULE_CHECKS = {
    MarketSchedule.CRYPTO_24_7: _check_crypto_24_7,
    MarketSchedule.ETORO_24_5: _check_etoro_24_5,
    MarketSchedule.US_EXTENDED: _check_us_extended,
    MarketSchedule.FOREX_24_5: _check_forex_24_5,
    MarketSchedule.US_INDEX_FUTURES: _check_us_index_futures,
    MarketSchedule.COMMODITY_FUTURES: _check_commodity_futures,
    MarketSchedule.NON_US_INDEX: _check_non_us_index,
}


# ---------------------------------------------------------------------------
# Asset-class → default schedule. Every stock/ETF in our DEMO universe is a
# curated US large-cap (S&P 500 or Nasdaq 100 constituent, or top-tier ETF)
# that eToro trades 24/5. So the default for STOCK and ETF is ETORO_24_5.
# Exceptions are declared per-symbol in config/symbols.yaml via the
# `market_schedule:` key (e.g. `market_schedule: us_extended` for a non-24/5
# name). Non-US indices are opt-in via explicit annotation because our
# indices list mixes US index-CFDs (SPX500/NSDQ100/DJ30) with EU indices
# (UK100/GER40/FR40/STOXX50).
# ---------------------------------------------------------------------------
_DEFAULT_SCHEDULE_BY_ASSET_CLASS: Dict[AssetClass, MarketSchedule] = {
    AssetClass.STOCK: MarketSchedule.ETORO_24_5,
    AssetClass.ETF: MarketSchedule.ETORO_24_5,
    AssetClass.FOREX: MarketSchedule.FOREX_24_5,
    AssetClass.CRYPTOCURRENCY: MarketSchedule.CRYPTO_24_7,
    AssetClass.COMMODITY: MarketSchedule.COMMODITY_FUTURES,
    AssetClass.INDEX: MarketSchedule.US_INDEX_FUTURES,  # default; overridden per-symbol for non-US indices
}


# Hardcoded non-US index symbols — override the INDEX default.
_NON_US_INDEX_SYMBOLS: Set[str] = {"UK100", "GER40", "FR40", "STOXX50", "DAX", "CAC"}


class MarketHoursManager:
    """Resolves (asset_class, symbol, time) → is market open for orders.

    Thread-safe (all state is immutable or per-call). Exchange and
    market_hours dicts are retained for backward-compatibility callers that
    still reason about exchanges rather than schedules.
    """

    US_HOLIDAYS = US_HOLIDAYS  # back-compat alias
    US_EARLY_CLOSE = US_EARLY_CLOSE  # back-compat alias

    def __init__(self):
        # Kept for older callers that still inspect these attributes. New
        # code should use MarketSchedule / get_schedule().
        self.market_hours = {
            Exchange.NYSE: {"open": time(9, 30), "close": time(16, 0)},
            Exchange.NASDAQ: {"open": time(9, 30), "close": time(16, 0)},
            Exchange.LSE: {"open": time(8, 0), "close": time(16, 30)},
            Exchange.CRYPTO: {"open": time(0, 0), "close": time(23, 59)},
        }
        self.asset_class_exchange = {
            AssetClass.STOCK: Exchange.NYSE,
            AssetClass.ETF: Exchange.NYSE,
            AssetClass.INDEX: Exchange.NYSE,
            AssetClass.COMMODITY: Exchange.NYSE,
            AssetClass.FOREX: Exchange.NYSE,
            AssetClass.CRYPTOCURRENCY: Exchange.CRYPTO,
        }
        logger.debug("Initialized MarketHoursManager (symbol-aware, 24/5 capable)")

    # --- Schedule resolution ----------------------------------------------

    def get_schedule(
        self,
        asset_class: AssetClass,
        symbol: Optional[str] = None,
    ) -> MarketSchedule:
        """Pick the right MarketSchedule for (asset_class, symbol).

        Precedence:
          1. SymbolRegistry market_schedule override (from symbols.yaml)
          2. Non-US index symbols override INDEX default
          3. Asset-class default
          4. Safest fallback: ETORO_24_5 (matches most US equities)
        """
        # 1. Per-symbol override from symbols.yaml
        if symbol:
            override = _get_registry_market_schedule(symbol)
            if override:
                try:
                    return MarketSchedule(override)
                except ValueError:
                    logger.warning(
                        f"Invalid market_schedule '{override}' for {symbol} "
                        f"in symbols.yaml — falling through to defaults"
                    )

            # 2. Non-US index heuristic — only applies when no explicit override
            if asset_class == AssetClass.INDEX:
                if symbol.upper() in _NON_US_INDEX_SYMBOLS:
                    return MarketSchedule.NON_US_INDEX

        # 3. Asset-class default
        return _DEFAULT_SCHEDULE_BY_ASSET_CLASS.get(
            asset_class, MarketSchedule.ETORO_24_5
        )

    # --- Primary API ------------------------------------------------------

    def is_market_open(
        self,
        asset_class: AssetClass,
        check_time: Optional[datetime] = None,
        symbol: Optional[str] = None,
    ) -> bool:
        """True if eToro will accept an order for `symbol` (of `asset_class`) now.

        Args:
            asset_class: STOCK / ETF / FOREX / INDEX / COMMODITY / CRYPTOCURRENCY
            check_time: UTC-aware or ET-aware datetime (defaults to now)
            symbol: optional symbol for per-symbol schedule resolution

        Returns:
            True if within the trading window.

        Fail-open behavior: any internal exception → True. A market-hours
        primitive that throws would block every order in the system; we'd
        rather submit during a known-edge-case window and let eToro refuse.
        """
        try:
            now = self._to_et(check_time)
            schedule = self.get_schedule(asset_class, symbol)
            check_fn = _SCHEDULE_CHECKS.get(schedule)
            if check_fn is None:
                logger.warning(
                    f"Unknown schedule {schedule} for {asset_class.value}/{symbol} — "
                    f"defaulting to open"
                )
                return True
            result = check_fn(now)
            logger.debug(
                f"is_market_open({asset_class.value}, {symbol}) → "
                f"{result} (schedule={schedule.value}, ET={now.strftime('%a %H:%M')})"
            )
            return result
        except Exception as e:
            logger.warning(
                f"is_market_open failed for {asset_class}/{symbol}: {e} — defaulting to True"
            )
            return True

    # --- Helpers ----------------------------------------------------------

    @staticmethod
    def _to_et(check_time: Optional[datetime]) -> datetime:
        import pytz
        et_tz = pytz.timezone('US/Eastern')
        if check_time is None:
            return datetime.now(et_tz)
        if check_time.tzinfo is None:
            # Naive datetime — assume UTC (that's how most of the codebase stores it).
            check_time = pytz.UTC.localize(check_time)
        return check_time.astimezone(et_tz)

    def get_next_open_time(
        self,
        asset_class: AssetClass,
        from_time: Optional[datetime] = None,
        symbol: Optional[str] = None,
    ) -> datetime:
        """Approximate next market-open time. Walks forward in 15-min steps
        up to 10 days to find the first open moment. Used for diagnostic /
        "next open in Nh" displays, not for scheduling correctness.
        """
        import pytz
        et_tz = pytz.timezone('US/Eastern')
        now = self._to_et(from_time)

        if self.is_market_open(asset_class, check_time=now, symbol=symbol):
            return now

        # Walk forward 15 min at a time — coarse enough to be fast, fine enough
        # to land within a few minutes of the true open.
        check = now
        max_steps = 10 * 24 * 4  # 10 days × 96 fifteen-minute steps
        for _ in range(max_steps):
            check = check + timedelta(minutes=15)
            if self.is_market_open(asset_class, check_time=check, symbol=symbol):
                return check

        logger.warning(
            f"get_next_open_time: could not find open window within 10 days "
            f"for {asset_class.value}/{symbol}"
        )
        return now + timedelta(days=1)


# ---------------------------------------------------------------------------
# Lazy symbol-registry lookup for per-symbol market_schedule override.
# We don't import SymbolRegistry at module load because it's heavy and this
# module is imported by low-level code (order_executor) that shouldn't pay
# the cost until it actually needs a schedule decision.
# ---------------------------------------------------------------------------
def _get_registry_market_schedule(symbol: str) -> Optional[str]:
    """Look up `market_schedule:` from symbols.yaml for `symbol`. Returns
    None if the symbol isn't in the registry or has no override set."""
    try:
        from src.core.symbol_registry import get_registry
        reg = get_registry()
        getter = getattr(reg, "get_market_schedule", None)
        if getter is None:
            return None
        return getter(symbol)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Module-level singleton. Every caller used to do `MarketHoursManager()`
# inline which (a) spammed the init log — one entry per TSL iteration over 75
# positions — and (b) wasted a tiny bit of work per call. Routes through
# get_market_hours_manager() to share one instance.
# ---------------------------------------------------------------------------
_singleton: Optional[MarketHoursManager] = None


def get_market_hours_manager() -> MarketHoursManager:
    """Lazy-initialized module-level MarketHoursManager. Logs once."""
    global _singleton
    if _singleton is None:
        _singleton = MarketHoursManager()
        logger.info("MarketHoursManager singleton created (symbol-aware, 24/5 capable)")
    return _singleton
