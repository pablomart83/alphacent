"""Market data manager with caching and fallback to Yahoo Finance."""

import logging
import time as _time_lbts
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests
import yfinance as yf

# Redirect yfinance's internal SQLite cache to /tmp to avoid conflicts with alphacent.db.
# Don't force-initialize the DB at import time — that can interfere with SQLAlchemy's
# connection pool during startup. Instead, set the path and let yfinance init lazily.
try:
    import tempfile, os
    _yf_cache_dir = os.path.join(tempfile.gettempdir(), 'yfinance_tz_cache')
    os.makedirs(_yf_cache_dir, exist_ok=True)
    os.environ['YF_CACHE_DIR'] = _yf_cache_dir
    os.environ['YFINANCE_CACHE_DIR'] = _yf_cache_dir
    yf.set_tz_cache_location(_yf_cache_dir)
except (AttributeError, TypeError, OSError):
    pass

# Thread lock for lazy yfinance DB initialization (prevents race on first use)
import threading as _yf_threading
_yf_init_lock = _yf_threading.Lock()
_yf_initialized = False

def ensure_yfinance_cache():
    """Initialize yfinance cache DB once, thread-safe. Call before batch downloads."""
    global _yf_initialized
    if _yf_initialized:
        return
    with _yf_init_lock:
        if _yf_initialized:
            return
        try:
            from yfinance.cache import _TzDBManager
            _TzDBManager.get_database()
            _yf_initialized = True
        except Exception:
            pass

from src.api.etoro_client import EToroAPIClient, EToroAPIError
from src.data.data_quality_validator import DataQualityValidator, DataQualityReport
from src.models import DataSource, MarketData
from src.utils.symbol_mapper import to_etoro_wire_format as normalize_symbol, to_yahoo_ticker

logger = logging.getLogger(__name__)

# ── Module-level singleton ────────────────────────────────────────────────────
# MarketDataManager is expensive to construct (reads config, creates HTTP session,
# initialises DataQualityValidator). Instantiating it per-symbol inside loops
# (trailing stops, risk checks, order executor) creates hundreds of objects per
# minute and floods the log with "Initialized MarketDataManager" lines.
#
# get_market_data_manager() returns a shared instance, creating it on first call.
# Callers that need a fresh instance (e.g. after config reload) can pass
# force_new=True.
_shared_mdm: "Optional[MarketDataManager]" = None
_shared_mdm_lock = _yf_threading.Lock()

def get_market_data_manager(config: dict = None, force_new: bool = False) -> "Optional[MarketDataManager]":
    """Return the shared MarketDataManager singleton, creating it if needed.
    
    Returns None if not yet initialized and config is not available.
    The monitoring_service registers the authoritative instance via
    set_market_data_manager() once it has the etoro_client available.
    """
    global _shared_mdm
    if _shared_mdm is not None and not force_new:
        return _shared_mdm
    with _shared_mdm_lock:
        if _shared_mdm is not None and not force_new:
            return _shared_mdm
        if config is None:
            try:
                import yaml
                from pathlib import Path
                _p = Path("config/autonomous_trading.yaml")
                config = yaml.safe_load(_p.read_text()) if _p.exists() else {}
            except Exception:
                config = {}
        _shared_mdm = MarketDataManager(config)
        return _shared_mdm


def set_market_data_manager(instance: "MarketDataManager") -> None:
    """Register an externally-created MarketDataManager as the shared singleton.
    
    Called by MonitoringService after it creates an instance with etoro_client.
    This ensures the singleton has live price access, not just DB/Yahoo.
    """
    global _shared_mdm
    with _shared_mdm_lock:
        _shared_mdm = instance


class MarketDataCache:
    """Simple in-memory cache with TTL for market data."""

    def __init__(self, ttl_seconds: int = 60):
        """Initialize cache with TTL.
        
        Args:
            ttl_seconds: Time-to-live for cached data in seconds
        """
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, tuple[MarketData, datetime]] = {}
        self._quality_cache: Dict[str, DataQualityReport] = {}

    def get(self, key: str) -> Optional[MarketData]:
        """Get cached data if not expired.
        
        Args:
            key: Cache key (typically symbol)
            
        Returns:
            Cached market data or None if expired/missing
        """
        if key not in self._cache:
            return None

        data, cached_at = self._cache[key]
        age = (datetime.now() - cached_at).total_seconds()

        if age > self.ttl_seconds:
            # Expired, remove from cache
            del self._cache[key]
            logger.debug(f"Cache expired for {key} (age: {age}s)")
            return None

        logger.debug(f"Cache hit for {key} (age: {age}s)")
        return data

    def set(self, key: str, data: MarketData) -> None:
        """Store data in cache with current timestamp.
        
        Args:
            key: Cache key
            data: Market data to cache
        """
        self._cache[key] = (data, datetime.now())
        logger.debug(f"Cached data for {key}")

    def clear(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        self._quality_cache.clear()
        logger.debug("Cache cleared")

    def remove(self, key: str) -> None:
        """Remove specific key from cache.
        
        Args:
            key: Cache key to remove
        """
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"Removed {key} from cache")
        if key in self._quality_cache:
            del self._quality_cache[key]
    
    def get_quality_report(self, key: str) -> Optional[DataQualityReport]:
        """Get cached quality report for symbol."""
        return self._quality_cache.get(key)
    
    def set_quality_report(self, key: str, report: DataQualityReport) -> None:
        """Store quality report in cache."""
        self._quality_cache[key] = report


class HistoricalDataCache:
    """Cache for historical OHLCV data with configurable TTL.
    
    Designed for signal generation: caches Yahoo Finance data so multiple
    strategies trading the same symbol share a single data fetch.
    """

    def __init__(self, ttl_seconds: int = 3600):
        """Initialize cache with TTL (default 1 hour).
        
        Args:
            ttl_seconds: Time-to-live for cached data in seconds
        """
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, tuple[List, datetime]] = {}

    def get(self, key: str) -> Optional[List]:
        """Get cached historical data if not expired.
        
        Args:
            key: Cache key (symbol:interval:days)
            
        Returns:
            Cached list of MarketData or None if expired/missing
        """
        if key not in self._cache:
            return None

        data, cached_at = self._cache[key]
        age = (datetime.now() - cached_at).total_seconds()

        if age > self.ttl_seconds:
            del self._cache[key]
            logger.debug(f"Historical cache expired for {key} (age: {age:.0f}s)")
            return None

        logger.debug(f"Historical cache hit for {key} (age: {age:.0f}s, {len(data)} points)")
        return data

    def set(self, key: str, data: List) -> None:
        """Store historical data in cache.
        
        Args:
            key: Cache key
            data: List of MarketData points
        """
        self._cache[key] = (data, datetime.now())
        logger.debug(f"Cached {len(data)} historical points for {key}")

    def clear(self) -> None:
        """Clear all cached historical data."""
        self._cache.clear()

    def clear_intraday(self) -> int:
        """Clear intraday (1h, 4h) cached entries that are older than 50 minutes.
        
        Called before each hourly signal run to ensure fresh candle data.
        Keeps daily data and very recent intraday data (e.g., from a manual
        cycle that just ran moments ago).
        
        Returns:
            Number of entries cleared
        """
        now = datetime.now()
        stale_keys = []
        for k, (data, cached_at) in self._cache.items():
            if ':1h:' in k or ':4h:' in k:
                age_seconds = (now - cached_at).total_seconds()
                if age_seconds > 3000:  # 50 minutes — older than the previous hourly run
                    stale_keys.append(k)
        
        for k in stale_keys:
            del self._cache[k]
        
        if stale_keys:
            logger.info(f"Cleared {len(stale_keys)} stale intraday cache entries (kept {len(self._cache)} fresh/daily)")
        return len(stale_keys)

    @property
    def size(self) -> int:
        """Number of cached entries."""
        return len(self._cache)


# Global historical data cache instance (shared across signal generation cycles)
_historical_cache: Optional['HistoricalDataCache'] = None


def get_historical_cache(ttl_seconds: int = 3500) -> HistoricalDataCache:
    """Get or create the global historical data cache.
    
    Args:
        ttl_seconds: TTL for cache entries (default 3500s — just under 1 hour
                     so hourly signal loop always gets fresh data)
        
    Returns:
        HistoricalDataCache instance
    """
    global _historical_cache
    if _historical_cache is None:
        _historical_cache = HistoricalDataCache(ttl_seconds=ttl_seconds)
    return _historical_cache


class MarketDataManager:
    """Manages market data from eToro API with Yahoo Finance fallback and caching."""

    def __init__(self, etoro_client: EToroAPIClient, cache_ttl: int = 60, config: Dict = None):
        """Initialize market data manager.
        
        Args:
            etoro_client: eToro API client for primary data source
            cache_ttl: Cache time-to-live in seconds (default 60)
            config: Optional config dict with data source API keys
        """
        self.etoro_client = etoro_client
        self.cache = MarketDataCache(ttl_seconds=cache_ttl)
        self.quality_validator = DataQualityValidator()
        
        # Auto-load config from YAML if not provided
        if config is None:
            try:
                import yaml
                from pathlib import Path
                config_path = Path("config/autonomous_trading.yaml")
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Could not auto-load config for MarketDataManager: {e}")
                config = {}
        
        self._config = config
        self._fmp_api_key = self._config.get('data_sources', {}).get('financial_modeling_prep', {}).get('api_key', '')
        self._historical_memory_cache: Dict[str, tuple] = {}  # cache_key -> (data, timestamp)
        self._purged_symbols: set = set()  # Track symbols already purged this session to avoid re-purging
        self._raw_fetch_cache: Dict[str, tuple] = {}  # "{symbol}:{interval}" -> (full_data_list, timestamp) — avoids redundant Yahoo fetches
        # F02 Part C: cache of latest bar timestamps per (symbol, interval).
        # Populated by get_latest_bar_timestamp; TTL 30s to avoid hammering DB
        # on every freshness check during signal generation (100+ checks per cycle).
        self._latest_ts_cache: Dict[tuple, tuple] = {}  # (symbol, interval) -> (timestamp_or_None, monotonic_at)
        if self._fmp_api_key:
            logger.info(f"Initialized MarketDataManager with cache TTL={cache_ttl}s, FMP API key configured")
        else:
            logger.info(f"Initialized MarketDataManager with cache TTL={cache_ttl}s")

    def get_quote(self, symbol: str, use_cache: bool = True) -> MarketData:
        """Get real-time quote (price, bid, ask, volume).
        
        Attempts to fetch from eToro API first, falls back to Yahoo Finance if unavailable.
        Uses cache if enabled and data is fresh.
        
        Args:
            symbol: Instrument symbol (e.g., "AAPL", "BTC", "BTCUSD")
            use_cache: Whether to use cached data if available
            
        Returns:
            Market data with current quote
            
        Raises:
            ValueError: If data cannot be fetched from any source
        """
        # Normalize symbol to eToro format (e.g., BTC -> BTCUSD)
        normalized_symbol = normalize_symbol(symbol)
        logger.debug(f"Symbol normalized: {symbol} -> {normalized_symbol}")
        
        # Check cache first (use normalized symbol for cache key)
        if use_cache:
            cached_data = self.cache.get(normalized_symbol)
            if cached_data is not None:
                return cached_data

        # Try eToro API first
        try:
            logger.debug(f"Fetching quote for {normalized_symbol} from eToro API")
            data = self.etoro_client.get_market_data(normalized_symbol, timeframe="1m")
            
            # Validate data
            if self.validate_data(data):
                self.cache.set(normalized_symbol, data)
                return data
            else:
                logger.warning(f"eToro data validation failed for {normalized_symbol}, trying fallback")
        
        except EToroAPIError as e:
            logger.warning(f"eToro API unavailable for {normalized_symbol}: {e}, trying Yahoo Finance fallback")
        except Exception as e:
            logger.error(f"Unexpected error fetching from eToro for {normalized_symbol}: {e}, trying fallback")

        # Fallback to Yahoo Finance
        try:
            logger.info(f"Fetching quote for {normalized_symbol} from Yahoo Finance (fallback)")
            data = self._fetch_from_yahoo_finance(normalized_symbol)
            
            if self.validate_data(data):
                self.cache.set(normalized_symbol, data)
                return data
            else:
                logger.error(f"Yahoo Finance data validation failed for {normalized_symbol}")
                raise ValueError(f"Invalid data from Yahoo Finance for {normalized_symbol}")
        
        except Exception as e:
            logger.error(f"Yahoo Finance fallback failed for {normalized_symbol}: {e}")
            raise ValueError(f"Failed to fetch market data for {normalized_symbol} from all sources: {e}")

    # ------------------------------------------------------------------
    # Freshness SLA — F02 Part C
    # ------------------------------------------------------------------
    # Max age thresholds for signal-generation. If the latest bar for a
    # (symbol, interval) is older than the threshold (adjusted for weekend
    # gaps for stock/etf/index), `is_data_fresh_for_signal()` returns
    # (False, reason) and callers must skip the signal rather than compute
    # indicators on stale data.
    #
    # Tighter than _get_historical_from_db's staleness check: that one
    # decides whether to hit Yahoo; this one decides whether to emit
    # signals at all.
    _FRESHNESS_MAX_AGE_HOURS = {
        # (interval, asset_class_family) -> max age in hours
        ("1d", "stock_etf_index"): 48,    # allows 2 closed weekdays
        ("1d", "forex"):           48,
        ("1d", "commodity"):       48,
        ("1d", "crypto"):          30,    # 24/7 — shouldn't lag
        ("4h", "stock_etf_index"): 30,    # 4H bar during RTH
        ("4h", "forex"):           12,
        ("4h", "commodity"):       30,
        ("4h", "crypto"):          8,
        ("1h", "stock_etf_index"): 24,    # allows overnight close
        ("1h", "forex"):           6,
        ("1h", "commodity"):       12,
        ("1h", "crypto"):          6,
    }

    def _get_asset_class_family(self, symbol: str) -> str:
        """Coarse asset-class family for freshness SLA lookup.

        Returns one of: 'crypto', 'forex', 'commodity', 'stock_etf_index'.
        """
        sym = symbol.upper()
        try:
            from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX
            # Normalise crypto (BTCUSD -> BTC, BTC -> BTC)
            crypto_base = {s.replace("USD", "") for s in DEMO_ALLOWED_CRYPTO}
            if sym.replace("USD", "") in crypto_base:
                return "crypto"
            if sym in set(DEMO_ALLOWED_FOREX):
                return "forex"
        except ImportError:
            pass
        # Commodity check via existing symbol_mapper DAILY_ONLY_SYMBOLS heuristic
        try:
            from src.utils.symbol_mapper import DAILY_ONLY_SYMBOLS
            commodity_syms = {"GOLD", "SILVER", "OIL", "COPPER", "NATGAS", "PLATINUM",
                              "ALUMINUM", "ZINC"} | set(DAILY_ONLY_SYMBOLS)
            if sym in commodity_syms:
                return "commodity"
        except ImportError:
            pass
        # Default bucket covers stocks, ETFs, indices (all share market-hours profile)
        return "stock_etf_index"

    def get_latest_bar_timestamp(self, symbol: str, interval: str) -> Optional[datetime]:
        """Return the timestamp of the latest cached bar for (symbol, interval).

        Returns None if no cached data exists. Used by freshness SLA check.
        Cached in-process for 30 seconds — this is called many times per
        signal-generation cycle for the same (symbol, interval) pair, and
        hitting the DB each time is wasteful.

        Raises:
            RuntimeError: If the underlying DB query fails. Callers should
                decide whether to fail-open (treat as fresh) or fail-closed
                (treat as stale) based on their risk tolerance.
        """
        # 30s in-memory cache keyed by (symbol, interval) — shared across threads
        # within this MarketDataManager instance. The underlying data only changes
        # every hour (price sync) so a short TTL is fine.
        cache_key = (symbol, interval)
        now_mono = _time_lbts.monotonic()
        entry = self._latest_ts_cache.get(cache_key)
        if entry is not None and (now_mono - entry[1]) < 30.0:
            return entry[0]

        try:
            from src.models.database import get_database
            from src.models.orm import HistoricalPriceCacheORM

            db = get_database()
            session = db.get_session()
            try:
                latest = (
                    session.query(HistoricalPriceCacheORM.date)
                    .filter(
                        HistoricalPriceCacheORM.symbol == symbol,
                        HistoricalPriceCacheORM.interval == interval,
                    )
                    .order_by(HistoricalPriceCacheORM.date.desc())
                    .first()
                )
            finally:
                session.close()
        except Exception as e:
            # Bubble up — caller's fail-open/fail-closed decision belongs there.
            # Previous behaviour (swallow + return None) caused the 2026-05-01 10:02
            # post-deploy flood where an AttributeError on `db.session_scope()` (typo
            # in initial implementation) was silently swallowed and every call
            # returned None → every symbol reported "no cached data" → trailing
            # stops disabled across the book.
            raise RuntimeError(
                f"get_latest_bar_timestamp DB query failed for {symbol} {interval}: {e}"
            ) from e

        ts = None
        if latest is not None:
            ts = latest[0]
            if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
                ts = ts.replace(tzinfo=None)

        self._latest_ts_cache[cache_key] = (ts, now_mono)
        return ts

    def _subtract_weekend_hours(self, latest: datetime, now: datetime) -> timedelta:
        """Compute data age, subtracting weekend gaps when the latest bar is Friday close.

        Only relevant for stock/etf/index intervals. Crypto and forex aren't adjusted.
        Conservative: if the latest bar is from Friday and `now` is Saturday/Sunday/Monday,
        subtract the weekend (approx. 64 hours) from the raw age.
        """
        raw_age = now - latest
        # If both dates are in the same week, no weekend to subtract
        if latest.weekday() == 4 and now.weekday() >= 5:
            # Friday bar, now Sat or Sun — subtract remaining Friday evening + weekend
            return raw_age - timedelta(hours=48)
        if latest.weekday() == 4 and now.weekday() == 0:
            # Friday bar, now Monday — subtract full weekend
            return raw_age - timedelta(hours=48)
        return raw_age

    def is_data_fresh_for_signal(
        self,
        symbol: str,
        interval: str,
        as_of: Optional[datetime] = None,
    ) -> tuple:
        """Check if cached data is fresh enough to generate signals.

        Returns (is_fresh, reason). If not fresh, callers MUST skip the symbol
        in signal generation and in ATR-based stop-loss recalculation. Silently
        computing indicators on stale bars poisons signals — the F02 root-cause
        incident (166-symbol DST crash) is exactly this failure mode left
        unguarded.

        Args:
            symbol: DB-canonical symbol (e.g. 'AAPL', 'BTC', 'EURUSD').
            interval: '1d', '4h', or '1h'.
            as_of: Reference 'now' (UTC-naive). Defaults to datetime.utcnow().

        Returns:
            (True, '') if fresh; (False, human-readable reason) if stale or missing.
        """
        if as_of is None:
            as_of = datetime.utcnow()
        elif as_of.tzinfo is not None:
            as_of = as_of.astimezone(timezone.utc).replace(tzinfo=None)

        # Fail-open on DB query errors — an exception in the freshness helper
        # is an operational issue, not a market-data issue. Blocking every
        # signal because of a bug in our own checker is worse than not having
        # the check. The warning gets logged so it gets fixed.
        try:
            latest = self.get_latest_bar_timestamp(symbol, interval)
        except RuntimeError as e:
            logger.warning(
                f"[freshness-sla] Check failed for {symbol} {interval}: {e} — "
                f"failing open (treating as fresh) to avoid blocking trading"
            )
            return (True, "")

        if latest is None:
            return (False, f"no cached data for {symbol} {interval}")

        family = self._get_asset_class_family(symbol)
        max_age_hours = self._FRESHNESS_MAX_AGE_HOURS.get((interval, family))
        if max_age_hours is None:
            # Unknown interval — be permissive, log and return fresh
            logger.debug(f"is_data_fresh_for_signal: no SLA for ({interval}, {family}); passing")
            return (True, "")

        raw_age = as_of - latest
        # Weekend-gap adjustment for stock/etf/index
        if family == "stock_etf_index":
            effective_age = self._subtract_weekend_hours(latest, as_of)
            # Floor at 0 — don't report negative age if math overshoots
            if effective_age < timedelta(0):
                effective_age = timedelta(0)
        else:
            effective_age = raw_age

        max_age = timedelta(hours=max_age_hours)
        if effective_age > max_age:
            return (
                False,
                f"{symbol} {interval} age={effective_age} (raw={raw_age}) "
                f"> limit={max_age} for {family}"
            )
        return (True, "")

    def get_historical_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
        prefer_yahoo: bool = False,
        force_fresh: bool = False
    ) -> List[MarketData]:
        """Get historical OHLCV data for backtesting.

        Database-first strategy for daily data:
        1. Check DB cache first (fastest, persists across restarts)
        2. If DB has sufficient fresh data, return it directly
        3. Otherwise fetch from API sources and save to DB

        Args:
            symbol: Instrument symbol (e.g., "AAPL", "BTC", "BTCUSD")
            start: Start date/time
            end: End date/time
            interval: Data interval (1m, 5m, 15m, 1h, 1d)
            prefer_yahoo: If True, try Yahoo Finance first for better historical data coverage
            force_fresh: If True, bypass DB cache and fetch fresh data (e.g., for real-time signal generation)

        Returns:
            List of market data points in chronological order

        Raises:
            ValueError: If data cannot be fetched from any source
        """
        # Two separate symbol forms are needed:
        #   db_symbol   — the canonical display form used everywhere in the DB
        #                 (positions, orders, trade_journal, historical_price_cache).
        #                 For crypto: "BTC", "ETH". For stocks: "AAPL". Never "BTCUSD".
        #   yahoo_symbol — the Yahoo Finance ticker used only for API calls.
        #                 For crypto: "BTC-USD". For indices: "^GSPC". Stocks pass through.
        #
        # normalize_symbol (symbol_mapper) converts "BTC" → "BTCUSD" — this is the eToro
        # wire format, NOT the canonical DB key. Using it for DB operations caused all
        # historical_price_cache rows to be stored as "BTCUSD" while every other table
        # uses "BTC", making 8,675 rows of BTC price history unreachable.
        #
        # The fix: use the input symbol (already canonical) for all DB operations.
        # Only convert to Yahoo ticker format for the actual API fetch.
        db_symbol = symbol.upper().strip()  # canonical form — used for all DB reads/writes
        # Legacy: if caller passed "BTCUSD" or "ETHUSD" (eToro wire format), strip the USD suffix
        # so we always store/retrieve under the display form ("BTC", "ETH").
        _CRYPTO_WIRE_TO_DISPLAY = {
            "BTCUSD": "BTC", "ETHUSD": "ETH", "SOLUSD": "SOL",
            "XRPUSD": "XRP", "ADAUSD": "ADA", "AVAXUSD": "AVAX",
            "DOTUSD": "DOT", "LINKUSD": "LINK", "NEARUSD": "NEAR",
            "LTCUSD": "LTC", "BCHUSD": "BCH",
        }
        if db_symbol in _CRYPTO_WIRE_TO_DISPLAY:
            db_symbol = _CRYPTO_WIRE_TO_DISPLAY[db_symbol]

        # normalized_symbol kept for backward compat with the rest of this function
        # (LME check, forex check, Yahoo fetch). It's the eToro wire format.
        normalized_symbol = normalize_symbol(symbol)
        logger.debug(f"Symbol: db_key={db_symbol}, etoro_wire={normalized_symbol}")

        # LME metals (ZINC, ALUMINUM, NICKEL) only have daily data on Yahoo Finance.
        # Return empty immediately for any intraday request — no point going through
        # DB → Yahoo → FMP chain only to get nothing and crash in the strategy engine.
        is_lme_metal = db_symbol.upper() in ("NICKEL", "ALUMINUM", "ZINC", "RUBBER")
        if is_lme_metal and interval != '1d':
            logger.warning(f"LME metal {db_symbol} only has daily data (requested {interval}). Skipping.")
            return []

        # Cacheable intervals that get persisted to DB
        _cacheable = interval in ("1d", "1h", "4h")
        
        # In-memory cache check (fastest, avoids DB query)
        if _cacheable and not force_fresh:
            cache_key = f"{db_symbol}_{interval}_{start.date()}_{end.date()}"
            if cache_key in self._historical_memory_cache:
                cached_data, cached_at = self._historical_memory_cache[cache_key]
                cache_age = (datetime.now() - cached_at).total_seconds()
                if cache_age < 3600:  # 1 hour TTL for in-memory cache
                    logger.debug(f"Using in-memory cached data for {normalized_symbol} (age: {cache_age:.0f}s)")
                    return cached_data

        # DB-first: check database cache (unless force_fresh)
        if _cacheable and not force_fresh:
            db_data = self._get_historical_from_db(db_symbol, start, end, interval)
            if db_data:
                valid_data = [d for d in db_data if self.validate_data(d)]
                if valid_data:
                    # Check if DB data is missing recent days — if so, do an incremental fetch
                    latest_db_date = valid_data[-1].timestamp
                    latest_db_naive = latest_db_date.replace(tzinfo=None) if latest_db_date.tzinfo else latest_db_date
                    end_naive = end.replace(tzinfo=None) if end.tzinfo else end
                    gap_days = (end_naive - latest_db_naive).days
                    
                    if gap_days > 1:
                        # Skip incremental fetch if the gap is just a weekend/holiday
                        # For stocks/ETFs: no data on Sat/Sun. A gap of 2-3 days ending on
                        # a weekend is normal and doesn't need an API call.
                        latest_weekday = latest_db_naive.weekday()  # 0=Mon, 4=Fri
                        today_weekday = end_naive.weekday()
                        
                        # If latest data is Friday and today is Sat/Sun/Mon, gap is expected
                        is_weekend_gap = (
                            latest_weekday == 4 and today_weekday in (5, 6, 0) and gap_days <= 3
                        ) or (
                            today_weekday in (5, 6) and gap_days <= 2
                        )
                        
                        # Forex and crypto trade on weekends, so skip this optimization for them
                        from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX
                        is_always_trading = db_symbol in set(DEMO_ALLOWED_CRYPTO + DEMO_ALLOWED_FOREX)
                        
                        if is_weekend_gap and not is_always_trading:
                            logger.debug(
                                f"DB cache for {db_symbol} is {gap_days} days behind "
                                f"(weekend gap, skipping incremental fetch)"
                            )
                        else:
                            # DB is missing recent trading days — fetch only the gap
                            gap_start = latest_db_naive + timedelta(days=1)
                            logger.info(
                                f"DB cache for {db_symbol} is {gap_days} days behind, "
                                f"fetching incremental update from {gap_start.date()} to {end_naive.date()}"
                            )
                            try:
                                gap_data = self._fetch_historical_from_yahoo_finance(normalized_symbol, gap_start, end, interval)
                                gap_valid = [d for d in gap_data if self.validate_data(d)]
                                
                                # Yahoo failed for gap fill — try FMP as emergency fallback
                                if not gap_valid and self._fmp_api_key and interval == '1d':
                                    logger.info(f"Yahoo gap fill empty for {db_symbol}, trying FMP")
                                    gap_data = self._fetch_historical_from_fmp(normalized_symbol, gap_start, end, interval)
                                    gap_valid = [d for d in gap_data if self.validate_data(d)]
                                if gap_valid:
                                    # Only count bars that are actually newer than what's in DB
                                    latest_date_only = latest_db_naive.date() if hasattr(latest_db_naive, 'date') and callable(latest_db_naive.date) else latest_db_naive
                                    truly_new = [d for d in gap_valid 
                                                 if (d.timestamp.date() if hasattr(d.timestamp, 'date') and callable(d.timestamp.date) else d.timestamp) > latest_date_only]
                                    if truly_new:
                                        self._save_historical_to_db(db_symbol, truly_new, interval)
                                        valid_data.extend(truly_new)
                                        valid_data.sort(key=lambda d: d.timestamp)
                                        logger.info(f"Incremental update: added {len(truly_new)} new bars for {db_symbol}")
                            except Exception as e:
                                logger.debug(f"Incremental update failed for {db_symbol}: {e} — using DB data as-is")
                    
                    result = self._validate_and_return_historical_data(valid_data, db_symbol, from_db_cache=True)
                    # Cache in memory for fast subsequent access
                    cache_key = f"{db_symbol}_{interval}_{start.date()}_{end.date()}"
                    self._historical_memory_cache[cache_key] = (result, datetime.now())
                    return result

        # Data source priority for historical prices:
        #   Daily:    DB cache → Yahoo Finance → FMP (emergency fallback) → eToro
        #   Intraday: DB cache → Yahoo Finance → eToro
        #   Forex:    DB cache → FMP (primary, Yahoo inverts high/low) → Yahoo (fallback)
        # Yahoo is primary for prices (free, unlimited, 20+ years history).
        # FMP API calls are reserved for fundamentals (earnings, ratios, calendars)
        # which Yahoo doesn't provide. Only use FMP for prices as emergency fallback.
        # EXCEPTION: Forex pairs use FMP first because Yahoo Finance returns inverted
        # high/low values and "possibly delisted" errors for some date ranges.

        # Forex: try FMP first (Yahoo has known issues with forex data)
        is_forex = self._is_forex_symbol(normalized_symbol)
        if (is_forex or is_lme_metal) and self._fmp_api_key and interval == '1d':
            try:
                logger.info(f"Fetching historical data for {normalized_symbol} from FMP (forex primary)")
                data_list = self._fetch_historical_from_fmp(normalized_symbol, start, end, interval)
                valid_data = [d for d in data_list if self.validate_data(d)]
                if len(valid_data) > 0:
                    valid_data.sort(key=lambda d: d.timestamp)
                    if _cacheable:
                        self._save_historical_to_db(db_symbol, valid_data, interval)
                    self._raw_fetch_cache[f"{normalized_symbol}:{interval}"] = (valid_data, datetime.now())
                    logger.info(f"Retrieved {len(valid_data)} valid historical data points from FMP (forex)")
                    result = self._validate_and_return_historical_data(valid_data, db_symbol)
                    if _cacheable:
                        cache_key = f"{db_symbol}_{interval}_{start.date()}_{end.date()}"
                        self._historical_memory_cache[cache_key] = (result, datetime.now())
                    return result
                else:
                    logger.warning(f"FMP returned no data for forex {normalized_symbol}, falling back to Yahoo")
            except Exception as e:
                logger.warning(f"FMP failed for forex {normalized_symbol}: {e}, falling back to Yahoo")

        # Yahoo Finance: primary for all price data
        try:
            # Check raw fetch cache first — if we already fetched this symbol+interval
            # from Yahoo in this session (possibly for a different date range), slice from
            # the cached data instead of making another API call.
            raw_cache_key = f"{normalized_symbol}:{interval}"
            if raw_cache_key in self._raw_fetch_cache:
                raw_data, raw_ts = self._raw_fetch_cache[raw_cache_key]
                cache_age = (datetime.now() - raw_ts).total_seconds()
                if cache_age < 3600 and raw_data:  # 1h TTL
                    start_naive = start.replace(tzinfo=None) if hasattr(start, 'tzinfo') and start.tzinfo else start
                    end_naive = end.replace(tzinfo=None) if hasattr(end, 'tzinfo') and end.tzinfo else end
                    sliced = [d for d in raw_data 
                              if start_naive <= (d.timestamp.replace(tzinfo=None) if hasattr(d.timestamp, 'tzinfo') and d.timestamp.tzinfo else d.timestamp) <= end_naive]
                    # Only use cache if we got enough bars AND the cached data actually
                    # extends to (or near) the requested end date. Without this check,
                    # a cache populated by the train period (e.g., Mar-Dec) will return
                    # a thin slice for the test period (e.g., Dec-Apr) instead of fetching
                    # fresh data that covers the full range. This was causing 4H strategies
                    # to get only 49 bars in the test period instead of 150+.
                    if len(sliced) >= 10:
                        # Check if the latest cached bar is within 7 days of the requested end
                        latest_cached_ts = max(
                            (d.timestamp.replace(tzinfo=None) if hasattr(d.timestamp, 'tzinfo') and d.timestamp.tzinfo else d.timestamp)
                            for d in raw_data
                        )
                        cache_covers_end = (end_naive - latest_cached_ts).days <= 7
                        if cache_covers_end:
                            logger.info(f"Using raw fetch cache for {normalized_symbol} {interval}: {len(sliced)} bars (from {len(raw_data)} cached)")
                            result = self._validate_and_return_historical_data(sliced, normalized_symbol)
                            if _cacheable:
                                cache_key = f"{normalized_symbol}_{interval}_{start.date()}_{end.date()}"
                                self._historical_memory_cache[cache_key] = (result, datetime.now())
                            return result
                        else:
                            logger.info(
                                f"Raw fetch cache for {normalized_symbol} {interval} doesn't cover "
                                f"requested end {end_naive.date()} (cache ends {latest_cached_ts.date()}), fetching fresh"
                            )

            logger.info(f"Fetching historical data for {normalized_symbol} from Yahoo Finance (primary)")
            data_list = self._fetch_historical_from_yahoo_finance(normalized_symbol, start, end, interval)
            valid_data = [d for d in data_list if self.validate_data(d)]
            if len(valid_data) > 0:
                valid_data.sort(key=lambda d: d.timestamp)
                if _cacheable:
                    self._save_historical_to_db(db_symbol, valid_data, interval)
                # Cache the full raw dataset for this symbol+interval so subsequent
                # requests with different date ranges can slice from it.
                # Merge with existing cache to accumulate the widest date range —
                # train period fetch covers Mar-Dec, test period fetch covers Oct-Apr,
                # merged cache covers Mar-Apr (full walk-forward window).
                if raw_cache_key in self._raw_fetch_cache:
                    existing_data, _ = self._raw_fetch_cache[raw_cache_key]
                    # Merge: deduplicate by timestamp, keep the freshest data
                    existing_by_ts = {
                        (d.timestamp.replace(tzinfo=None) if hasattr(d.timestamp, 'tzinfo') and d.timestamp.tzinfo else d.timestamp): d
                        for d in existing_data
                    }
                    for d in valid_data:
                        ts = d.timestamp.replace(tzinfo=None) if hasattr(d.timestamp, 'tzinfo') and d.timestamp.tzinfo else d.timestamp
                        existing_by_ts[ts] = d  # New data overwrites old for same timestamp
                    merged = sorted(existing_by_ts.values(), key=lambda d: d.timestamp)
                    self._raw_fetch_cache[raw_cache_key] = (merged, datetime.now())
                    if len(merged) > len(valid_data):
                        logger.info(f"Merged raw fetch cache for {db_symbol} {interval}: {len(valid_data)} new + {len(existing_data)} existing = {len(merged)} total")
                else:
                    self._raw_fetch_cache[raw_cache_key] = (valid_data, datetime.now())
                logger.info(f"Retrieved {len(valid_data)} valid historical data points from Yahoo Finance")
                result = self._validate_and_return_historical_data(valid_data, db_symbol)
                if _cacheable:
                    cache_key = f"{db_symbol}_{interval}_{start.date()}_{end.date()}"
                    self._historical_memory_cache[cache_key] = (result, datetime.now())
                return result
            else:
                logger.warning(f"No valid data from Yahoo Finance for {db_symbol}, trying FMP")
        except Exception as e:
            logger.warning(f"Yahoo Finance failed for {db_symbol}: {e}, trying FMP fallback")

        # FMP: emergency fallback for daily data only (preserve API calls for fundamentals)
        if self._fmp_api_key and interval == '1d':
            try:
                logger.info(f"Fetching historical data for {db_symbol} from FMP (fallback)")
                data_list = self._fetch_historical_from_fmp(normalized_symbol, start, end, interval)
                valid_data = [d for d in data_list if self.validate_data(d)]
                if len(valid_data) > 0:
                    valid_data.sort(key=lambda d: d.timestamp)
                    if _cacheable:
                        self._save_historical_to_db(db_symbol, valid_data, interval)
                    logger.info(f"Retrieved {len(valid_data)} valid historical data points from FMP")
                    result = self._validate_and_return_historical_data(valid_data, db_symbol)
                    if _cacheable:
                        cache_key = f"{db_symbol}_{interval}_{start.date()}_{end.date()}"
                        self._historical_memory_cache[cache_key] = (result, datetime.now())
                    return result
                else:
                    logger.warning(f"No valid data from FMP for {db_symbol}")
            except Exception as e:
                logger.warning(f"FMP failed for {db_symbol}: {e}, trying eToro fallback")

        # eToro API: last resort fallback
        try:
            logger.info(f"Fetching historical data for {normalized_symbol} from eToro API ({start} to {end})")
            data_list = self.etoro_client.get_historical_data(normalized_symbol, start, end, interval)

            # Validate all data points
            valid_data = [d for d in data_list if self.validate_data(d)]

            if len(valid_data) > 0:
                # Sort by timestamp to ensure chronological order
                valid_data.sort(key=lambda d: d.timestamp)
                # Save to DB cache
                if _cacheable:
                    self._save_historical_to_db(db_symbol, valid_data, interval)
                logger.info(f"Retrieved {len(valid_data)} valid historical data points from eToro")
                result = self._validate_and_return_historical_data(valid_data, db_symbol)
                # Cache in memory for fast subsequent access
                if _cacheable:
                    cache_key = f"{db_symbol}_{interval}_{start.date()}_{end.date()}"
                    self._historical_memory_cache[cache_key] = (result, datetime.now())
                return result
            else:
                logger.error(f"No valid data from eToro for {db_symbol}")

        except EToroAPIError as e:
            logger.error(f"eToro API failed for {db_symbol}: {e}")
        except Exception as e:
            logger.error(f"eToro API error for {db_symbol}: {e}")

        raise ValueError(f"Failed to fetch historical data for {db_symbol} from all sources")
    
    def _validate_and_return_historical_data(
        self,
        valid_data: List[MarketData],
        symbol: str,
        from_db_cache: bool = False
    ) -> List[MarketData]:
        """Validate data quality and return historical data.
        
        Args:
            valid_data: List of validated market data points
            symbol: Symbol being validated
            from_db_cache: If True, skip validation (data was validated when first stored)
            
        Returns:
            List of market data points
        """
        # Skip validation for DB-cached data — it was validated when first stored
        if from_db_cache:
            return valid_data

        # Check for cached data quality report (skip re-validation if fresh)
        cached_report = self.quality_validator.get_cached_report(symbol, max_age_hours=24.0)
        if cached_report:
            # Use cached report — log the score but skip full validation
            if cached_report.has_critical_issues():
                logger.error(
                    f"Data quality validation for {symbol}: "
                    f"CRITICAL - Score: {cached_report.quality_score:.1f}/100 (cached)"
                )
            elif cached_report.has_warnings():
                logger.warning(
                    f"Data quality validation for {symbol}: "
                    f"Score: {cached_report.quality_score:.1f}/100, "
                    f"Issues: {len(cached_report.issues)} (cached)"
                )
            else:
                logger.info(
                    f"Data quality validation for {symbol}: "
                    f"PASSED - Score: {cached_report.quality_score:.1f}/100 (cached)"
                )
            return valid_data  # Return data without re-validating

        # Run quality validation
        quality_report = self.quality_validator.validate_data_quality(valid_data, symbol)
        self.cache.set_quality_report(symbol, quality_report)
        
        # Log quality issues but don't block trading
        if quality_report.has_critical_issues():
            logger.warning(
                f"Data quality issues for {symbol}: "
                f"{len(quality_report.issues)} issues found, "
                f"score: {quality_report.quality_score:.1f}/100"
            )
            for issue in quality_report.issues:
                if issue.severity == "error":
                    logger.error(f"  - {issue.message}")
        elif quality_report.has_warnings():
            logger.info(
                f"Data quality warnings for {symbol}: "
                f"{len(quality_report.issues)} warnings, "
                f"score: {quality_report.quality_score:.1f}/100"
            )
        
        return valid_data

    def validate_data(self, data: MarketData) -> bool:
        """Validate data integrity (no nulls, reasonable values, chronological).
        
        Args:
            data: Market data to validate
            
        Returns:
            True if data is valid
        """
        try:
            # Check for None values
            if data.symbol is None or data.timestamp is None:
                logger.warning("Market data has None symbol or timestamp")
                return False

            # Check prices are positive
            if any(p is None or p <= 0 for p in [data.open, data.high, data.low, data.close]):
                logger.warning(f"Market data for {data.symbol} has invalid prices")
                return False

            # Check volume is non-negative
            if data.volume is None or data.volume < 0:
                logger.warning(f"Market data for {data.symbol} has invalid volume")
                return False

            # Check OHLC relationships
            if data.high < data.low:
                logger.warning(f"Market data for {data.symbol} has high < low")
                return False

            # Use a small epsilon for float comparison — open=high or close=high
            # are valid bars (e.g., a down-day where open was the high).
            # Strict < avoids false positives from floating-point rounding.
            _eps = 1e-8
            if data.high < data.open - _eps or data.high < data.close - _eps:
                logger.warning(f"Market data for {data.symbol} has high < open or close")
                return False

            if data.low > data.open + _eps or data.low > data.close + _eps:
                logger.warning(f"Market data for {data.symbol} has low > open or close")
                return False

            # Check timestamp is reasonable (not in future, not too old)
            # Make timezone-aware comparison to handle both naive and aware timestamps
            now = datetime.now()
            data_ts = data.timestamp
            
            # If data timestamp is timezone-aware, make now timezone-aware too
            if data_ts.tzinfo is not None and data_ts.tzinfo.utcoffset(data_ts) is not None:
                from datetime import timezone
                now = datetime.now(timezone.utc)
                # Convert to same timezone as data
                if data_ts.tzinfo != timezone.utc:
                    now = now.astimezone(data_ts.tzinfo)
            
            if data_ts > now + timedelta(minutes=5):
                logger.warning(f"Market data for {data.symbol} has future timestamp")
                return False

            # Data is valid
            return True

        except Exception as e:
            logger.error(f"Error validating market data: {e}")
            return False

    def _fetch_from_yahoo_finance(self, symbol: str) -> MarketData:
        """Fetch current quote from Yahoo Finance.
        
        Args:
            symbol: Instrument symbol (will be converted to Yahoo Finance ticker format)
            
        Returns:
            Market data from Yahoo Finance
            
        Raises:
            Exception: If fetch fails
        """
        yf_symbol = to_yahoo_ticker(symbol)
        ensure_yfinance_cache()
        ticker = yf.Ticker(yf_symbol)
        
        # Get current data.
        # period="1d" is pre-computed by yfinance (no user-supplied datetime), so
        # DST ambiguous-hour risk is low here. Still, normalise the returned index
        # before iteration for safety — see src/utils/yfinance_compat.py.
        from src.utils.yfinance_compat import normalize_yf_index_to_utc_naive
        hist = ticker.history(period="1d", interval="1m")
        hist = normalize_yf_index_to_utc_naive(hist)
        
        if hist.empty:
            raise ValueError(f"No data available from Yahoo Finance for {symbol} (ticker: {yf_symbol})")

        # Get most recent data point
        latest = hist.iloc[-1]
        
        market_data = MarketData(
            symbol=symbol,
            timestamp=datetime.now(),
            open=float(latest['Open']),
            high=float(latest['High']),
            low=float(latest['Low']),
            close=float(latest['Close']),
            volume=float(latest['Volume']),
            source=DataSource.YAHOO_FINANCE
        )

        logger.debug(f"Fetched quote from Yahoo Finance for {symbol} (ticker: {yf_symbol}): close={market_data.close}")
        return market_data

    def _fetch_historical_from_yahoo_finance(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d"
    ) -> List[MarketData]:
        """Fetch historical data from Yahoo Finance.
        
        Args:
            symbol: Instrument symbol (will be converted to Yahoo Finance ticker format)
            start: Start date/time
            end: End date/time
            interval: Data interval (1m, 5m, 15m, 1h, 1d)
            
        Returns:
            List of market data points
            
        Raises:
            Exception: If fetch fails
        """
        yf_symbol = to_yahoo_ticker(symbol)
        ensure_yfinance_cache()
        ticker = yf.Ticker(yf_symbol)
        
        # Map interval format (eToro style to yfinance style)
        # Yahoo Finance doesn't support 4h — we synthesize from 1h bars below.
        interval_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "1h": "1h",
            "4h": "1h",  # Fetch 1h, then resample to 4h
            "1d": "1d"
        }
        yf_interval = interval_map.get(interval, "1d")
        
        # Pass tz-aware UTC bounds to yfinance to avoid DST ambiguous-hour crashes.
        # See src/utils/yfinance_compat.py for the full rationale.
        from src.utils.yfinance_compat import to_tz_aware_utc, normalize_yf_index_to_utc_naive
        start_utc = to_tz_aware_utc(start)
        end_utc = to_tz_aware_utc(end)

        # Fetch historical data
        hist = ticker.history(start=start_utc, end=end_utc, interval=yf_interval)
        
        if hist.empty:
            raise ValueError(f"No historical data available from Yahoo Finance for {symbol} (ticker: {yf_symbol})")

        # Normalise index to UTC-naive FIRST — before any resampling or iteration.
        # Belt-and-braces: tz-aware UTC input above doesn't prevent the output
        # from being tz-aware. Stripping tz here makes every downstream
        # to_pydatetime() and .resample() call unambiguous.
        hist = normalize_yf_index_to_utc_naive(hist)

        # Synthesize 4H bars from 1H data using proper OHLCV resampling.
        # This is how real trading platforms build higher-timeframe candles:
        # Open = first bar's open, High = max of all highs, Low = min of all lows,
        # Close = last bar's close, Volume = sum of all volumes.
        if interval == "4h" and yf_interval == "1h":
            logger.info(f"Synthesizing 4H bars from {len(hist)} 1H bars for {symbol}")
            hist_4h = hist.resample('4h').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna(subset=['Open', 'Close'])
            logger.info(f"Synthesized {len(hist_4h)} 4H bars from {len(hist)} 1H bars for {symbol}")
            hist = hist_4h

        # Convert to MarketData objects (keep original symbol, not Yahoo ticker)
        data_list = []
        for timestamp, row in hist.iterrows():
            market_data = MarketData(
                symbol=symbol,
                timestamp=timestamp.to_pydatetime().replace(tzinfo=None),
                open=float(row['Open']),
                high=float(row['High']),
                low=float(row['Low']),
                close=float(row['Close']),
                volume=float(row['Volume']),
                source=DataSource.YAHOO_FINANCE
            )
            data_list.append(market_data)

        logger.debug(f"Fetched {len(data_list)} historical data points from Yahoo Finance for {symbol} (ticker: {yf_symbol}, interval={interval})")
        return data_list

    def _is_forex_symbol(self, symbol: str) -> bool:
        """Check if a symbol is a forex pair.
        
        Args:
            symbol: Symbol to check
            
        Returns:
            True if the symbol is a forex pair
        """
        from src.core.tradeable_instruments import DEMO_ALLOWED_FOREX
        return symbol.upper() in DEMO_ALLOWED_FOREX

    def _fetch_historical_from_fmp(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d"
    ) -> List[MarketData]:
        """Fetch historical data from FMP (Financial Modeling Prep).
        
        Primarily used for forex pairs where Yahoo Finance returns inverted high/low values.
        
        Args:
            symbol: Instrument symbol (e.g., "EURUSD")
            start: Start date/time
            end: End date/time
            interval: Data interval (only 1d supported by FMP historical endpoint)
            
        Returns:
            List of market data points
            
        Raises:
            ValueError: If FMP API key is not configured or fetch fails
        """
        if not self._fmp_api_key:
            raise ValueError("FMP API key not configured")
        
        url = f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}"
        params = {
            "apikey": self._fmp_api_key,
            "from": start.strftime("%Y-%m-%d"),
            "to": end.strftime("%Y-%m-%d"),
        }
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            raise ValueError(f"FMP API request failed for {symbol}: {e}")
        
        historical = data.get("historical", [])
        if not historical:
            raise ValueError(f"No historical data from FMP for {symbol}")
        
        data_list = []
        for bar in historical:
            try:
                bar_date = datetime.strptime(bar["date"], "%Y-%m-%d")
                market_data = MarketData(
                    symbol=symbol,
                    timestamp=bar_date,
                    open=float(bar["open"]),
                    high=float(bar["high"]),
                    low=float(bar["low"]),
                    close=float(bar["close"]),
                    volume=float(bar.get("volume", 0)),
                    source=DataSource.FMP
                )
                data_list.append(market_data)
            except (KeyError, ValueError) as e:
                logger.debug(f"Skipping malformed FMP bar for {symbol}: {e}")
                continue
        
        # FMP returns newest first, reverse to chronological order
        data_list.sort(key=lambda d: d.timestamp)
        
        logger.info(f"Fetched {len(data_list)} historical data points from FMP for {symbol}")
        return data_list

    def clear_cache(self) -> None:
        """Clear all cached market data."""
        self.cache.clear()
        logger.info("Market data cache cleared")
    def _get_historical_from_db(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d"
    ) -> Optional[List[MarketData]]:
        """Get historical OHLCV data from the database cache.

        Args:
            symbol: Instrument symbol
            start: Start date
            end: End date
            interval: Data interval ("1d", "1h", "4h")

        Returns:
            List of MarketData if sufficient data exists, None otherwise
        """
        try:
            from src.models.database import get_database
            from src.models.orm import HistoricalPriceCacheORM

            db = get_database()
            session = db.get_session()
            try:
                records = session.query(HistoricalPriceCacheORM).filter(
                    HistoricalPriceCacheORM.symbol == symbol,
                    HistoricalPriceCacheORM.interval == interval,
                    HistoricalPriceCacheORM.date >= start,
                    HistoricalPriceCacheORM.date <= end
                ).order_by(HistoricalPriceCacheORM.date.asc()).all()

                if not records:
                    return None

                # Detect poisoned cache: daily bars stored under intraday interval key.
                # If interval is 1h or 4h but the bars are spaced ~24h apart, the cache
                # was populated with daily data (from a previous bug where Yahoo fell back
                # to 1d when 4h wasn't in the interval_map). Reject and force a fresh fetch.
                purge_key = f"{symbol}:{interval}"
                if interval in ("1h", "4h") and len(records) >= 5 and purge_key not in self._purged_symbols:
                    # Use median gap from a mid-dataset sample (not mean of first 3 bars)
                    # because a single weekend gap inflates the mean for legitimate data.
                    mid = len(records) // 2
                    sample_size = min(20, len(records))
                    half = sample_size // 2
                    sample_records = records[max(0, mid - half):mid + half]
                    if len(sample_records) >= 3:
                        gaps = sorted([
                            (sample_records[i+1].date - sample_records[i].date).total_seconds() / 3600
                            for i in range(len(sample_records) - 1)
                        ])
                        median_gap_hours = gaps[len(gaps) // 2]
                        max_expected_gap = 8 if interval == "1h" else 28  # 1h: 8h (overnight), 4h: 28h
                        if median_gap_hours > max_expected_gap:
                            logger.warning(
                                f"DB cache for {symbol} {interval} contains daily-resolution data "
                                f"(median gap {median_gap_hours:.0f}h between bars). Purging poisoned cache."
                            )
                            # Delete the poisoned records so they don't keep getting returned
                            session.query(HistoricalPriceCacheORM).filter(
                                HistoricalPriceCacheORM.symbol == symbol,
                                HistoricalPriceCacheORM.interval == interval,
                            ).delete()
                            session.commit()
                            self._purged_symbols.add(purge_key)
                            return None

                # Check coverage
                if interval == "1d":
                    expected_days = (end - start).days
                    expected_bars = max(1, int(expected_days * 252 / 365))
                else:
                    # For 1h: ~7 bars/day stocks, ~24 bars/day crypto
                    hours_per_bar = 1 if interval == "1h" else 4
                    expected_bars = max(1, int((end - start).total_seconds() / (hours_per_bar * 3600) * 0.5))
                
                coverage = len(records) / expected_bars if expected_bars > 0 else 0

                if coverage < 0.3:
                    logger.debug(
                        f"DB cache for {symbol} {interval} has insufficient coverage: "
                        f"{len(records)} bars vs ~{expected_bars} expected ({coverage:.0%})"
                    )
                    return None

                # Staleness check for intraday data.
                # Only reject if the market was actually open and we're missing bars.
                # Overnight/weekend gaps are expected — don't force a Yahoo fetch for those.
                latest_bar = records[-1]
                latest_date = latest_bar.date.replace(tzinfo=None) if hasattr(latest_bar.date, 'tzinfo') and latest_bar.date.tzinfo else latest_bar.date
                end_naive = end.replace(tzinfo=None) if hasattr(end, 'tzinfo') and end.tzinfo else end
                end_gap = (end_naive - latest_date).total_seconds()
                
                if interval == "1d" and end_gap > 7 * 86400:
                    logger.debug(
                        f"DB cache for {symbol} 1d doesn't cover requested end date: "
                        f"latest bar is {end_gap / 86400:.1f} days before {end.date()}"
                    )
                    return None
                elif interval != "1d" and end_gap > 2 * 3600:
                    # Only force a fresh fetch if the market was open during the gap.
                    # Overnight (16h gap) and weekend (66h gap) are normal — don't
                    # trigger 208 Yahoo calls on every restart just because it's morning.
                    import pytz
                    now_utc = datetime.utcnow()
                    now_et = now_utc  # approximate — just need weekday + hour
                    try:
                        et_tz = pytz.timezone('US/Eastern')
                        now_et = datetime.now(et_tz).replace(tzinfo=None)
                    except Exception:
                        pass
                    
                    is_weekend = now_et.weekday() >= 5  # Sat=5, Sun=6
                    is_premarket = now_et.hour < 9 or (now_et.hour == 9 and now_et.minute < 30)
                    is_afterhours = now_et.hour >= 16
                    
                    from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO
                    is_crypto = symbol.upper().replace("USD", "") in {s.replace("USD", "") for s in DEMO_ALLOWED_CRYPTO}
                    
                    # Crypto trades 24/7 — always stale after 2h
                    # Stocks/ETFs/Forex: only stale if market was open during the gap
                    market_was_closed = not is_crypto and (is_weekend or is_premarket or is_afterhours)
                    
                    if not market_was_closed:
                        logger.debug(
                            f"DB cache for {symbol} {interval} is stale: "
                            f"latest bar is {end_gap / 3600:.1f}h before now (market open)"
                        )
                        return None
                    # else: market was closed, gap is expected — use DB data as-is

                # Convert to MarketData objects
                data_list = []
                for r in records:
                    source = DataSource.YAHOO_FINANCE
                    if r.source == "FMP":
                        source = DataSource.FMP if hasattr(DataSource, 'FMP') else DataSource.YAHOO_FINANCE

                    md = MarketData(
                        symbol=symbol,
                        timestamp=r.date.replace(tzinfo=None) if hasattr(r.date, 'tzinfo') and r.date.tzinfo else r.date,
                        open=r.open,
                        high=r.high,
                        low=r.low,
                        close=r.close,
                        volume=r.volume,
                        source=source
                    )
                    data_list.append(md)

                logger.info(
                    f"Retrieved {len(data_list)} {interval} bars for {symbol} from DB cache "
                    f"(coverage: {coverage:.0%})"
                )
                return data_list

            finally:
                session.close()

        except Exception as e:
            logger.debug(f"Error reading historical data from DB for {symbol}: {e}")
            return None

    def _save_historical_to_db(
        self,
        symbol: str,
        data_list: List[MarketData],
        interval: str = "1d"
    ) -> None:
        """Save historical OHLCV data to the database cache.

        Uses bulk insert with conflict ignore for efficiency.
        The unique index on (symbol, date, interval) prevents duplicates.

        Args:
            symbol: Instrument symbol
            data_list: List of MarketData points to cache
            interval: Data interval ("1d", "1h", "4h")
        """
        if not data_list:
            return

        # Prevent cache poisoning: validate bar spacing matches the declared interval.
        # If we're saving "1h" data but the bars are spaced ~24h apart, the data is
        # actually daily and would corrupt the intraday cache.
        # Use MEDIAN gap from a mid-dataset sample (not mean of first 10 bars) because
        # a single weekend gap (66h) in a small sample inflates the mean above the
        # threshold even for legitimate 1h stock data.
        if interval in ("1h", "4h") and len(data_list) >= 10:
            # Sample from the middle of the dataset to avoid start/end boundary effects
            mid = len(data_list) // 2
            sample_size = min(30, len(data_list))
            half = sample_size // 2
            sample = data_list[max(0, mid - half):mid + half]
            gaps = sorted([
                (sample[i+1].timestamp - sample[i].timestamp).total_seconds() / 3600
                for i in range(len(sample) - 1)
            ])
            median_gap_hours = gaps[len(gaps) // 2] if gaps else 0
            max_expected = 8 if interval == "1h" else 28  # 1h: 8h max (overnight), 4h: 28h
            if median_gap_hours > max_expected:
                logger.warning(
                    f"Refusing to save {len(data_list)} bars as {interval} for {symbol} — "
                    f"median gap {median_gap_hours:.0f}h indicates daily data, not {interval}"
                )
                return

        try:
            from src.models.database import get_database
            from src.models.orm import HistoricalPriceCacheORM
            from sqlalchemy import text

            db = get_database()
            session = db.get_session()
            try:
                # Normalize 1d bar timestamps to midnight UTC for consistent storage.
                # yfinance returns 1d bars with different tz conventions depending on API:
                #   - ticker.history() often returns midnight UTC (00:00)
                #   - yf.download() batch returns midnight market-local, which becomes
                #     04:00 UTC (EDT) or 05:00 UTC (EST) after tz_convert
                # Without normalization, the same trading day ends up with two DB rows
                # (one per source), defeating the UniqueConstraint on (symbol, date, interval).
                # Storing all 1d bars at midnight UTC makes the constraint effective and
                # matches the convention of the ~190K existing 1d rows in the cache.
                if interval == "1d":
                    for md in data_list:
                        if md.timestamp:
                            md.timestamp = md.timestamp.replace(hour=0, minute=0, second=0, microsecond=0)

                # Get existing timestamps in one query to avoid per-bar lookups
                existing_timestamps = set()
                existing = session.query(HistoricalPriceCacheORM.date).filter(
                    HistoricalPriceCacheORM.symbol == symbol,
                    HistoricalPriceCacheORM.interval == interval,
                    HistoricalPriceCacheORM.date >= data_list[0].timestamp,
                    HistoricalPriceCacheORM.date <= data_list[-1].timestamp
                ).all()
                
                if interval == "1d":
                    # For daily bars, normalize to date-only for comparison
                    for r in existing:
                        d = r.date
                        if hasattr(d, 'date') and callable(d.date):
                            existing_timestamps.add(d.date())
                        else:
                            existing_timestamps.add(d)
                else:
                    # For intraday bars, use full timestamp
                    for r in existing:
                        d = r.date
                        if hasattr(d, 'replace'):
                            existing_timestamps.add(d.replace(tzinfo=None) if hasattr(d, 'tzinfo') and d.tzinfo else d)
                        else:
                            existing_timestamps.add(d)

                # Bulk insert only new bars
                new_records = []
                now = datetime.now()
                for md in data_list:
                    if interval == "1d":
                        md_key = md.timestamp.date() if hasattr(md.timestamp, 'date') and callable(md.timestamp.date) else md.timestamp
                    else:
                        md_key = md.timestamp.replace(tzinfo=None) if hasattr(md.timestamp, 'tzinfo') and md.timestamp.tzinfo else md.timestamp
                    
                    if md_key in existing_timestamps:
                        continue
                    new_records.append(HistoricalPriceCacheORM(
                        symbol=symbol,
                        date=md.timestamp,
                        interval=interval,
                        open=md.open,
                        high=md.high,
                        low=md.low,
                        close=md.close,
                        volume=md.volume,
                        source=md.source.value if hasattr(md.source, 'value') else str(md.source),
                        fetched_at=now
                    ))

                if new_records:
                    session.bulk_save_objects(new_records)
                    session.commit()
                    logger.debug(f"Bulk saved {len(new_records)} new {interval} bars for {symbol} to DB cache")

            except Exception as e:
                logger.warning(f"Error saving historical data to DB for {symbol}: {e}")
                session.rollback()
            finally:
                session.close()

        except Exception as e:
            logger.debug(f"Error accessing DB for historical data save: {e}")



    def invalidate_symbol(self, symbol: str) -> None:
        """Invalidate cached data for specific symbol.
        
        Args:
            symbol: Symbol to invalidate
        """
        self.cache.remove(symbol)
        logger.info(f"Invalidated cache for {symbol}")
    
    def get_quality_report(self, symbol: str) -> Optional[DataQualityReport]:
        """Get latest data quality report for symbol.
        
        Args:
            symbol: Symbol to get report for
            
        Returns:
            DataQualityReport or None if no report available
        """
        # Check cache first
        cached_report = self.cache.get_quality_report(symbol)
        if cached_report:
            return cached_report
        
        # Check validator history
        return self.quality_validator.get_latest_report(symbol)
    
    def get_all_quality_reports(self) -> Dict[str, DataQualityReport]:
        """Get latest quality reports for all symbols.
        
        Returns:
            Dictionary mapping symbol to DataQualityReport
        """
        return self.quality_validator.get_all_reports()


# ---------------------------------------------------------------------------
# Module-level singleton — ONE shared MarketDataManager across the process.
#
# Why this matters:
# - _raw_fetch_cache: avoids redundant Yahoo calls for the same symbol/interval
#   within a session. Multiple instances each have empty caches.
# - _historical_memory_cache: 1h in-memory cache for DB query results.
#   Multiple instances re-query DB on every call.
# - _purged_symbols: tracks poisoned cache purges — multiple instances re-purge.
#
# The singleton is set by the monitoring service on startup (it has the etoro_client).
# All other code that needs a MarketDataManager should call get_market_data_manager().
# ---------------------------------------------------------------------------

_mdm_singleton: Optional['MarketDataManager'] = None
_mdm_lock = __import__('threading').Lock()


def get_market_data_manager() -> Optional['MarketDataManager']:
    """Return the shared MarketDataManager singleton, or None if not yet initialized."""
    return _mdm_singleton


def set_market_data_manager(instance: 'MarketDataManager') -> None:
    """Register the shared singleton. Called once by the monitoring service on startup."""
    global _mdm_singleton
    with _mdm_lock:
        _mdm_singleton = instance
