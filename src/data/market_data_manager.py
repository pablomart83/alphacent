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
        
        # Auto-load config from YAML if not provided. Uses config_loader so
        # the api_keys.yaml overlay merges in — otherwise we'd read
        # autonomous_trading.yaml's literal "REPLACE_VIA_SECRETS_MANAGER"
        # placeholder for FMP and every non-forex / non-LME FMP fetch
        # would return 401 Unauthorized.
        if config is None:
            try:
                from src.core.config_loader import load_config
                config = load_config()
            except Exception as e:
                logger.warning(f"config_loader failed, falling back to raw yaml: {e}")
                try:
                    import yaml
                    from pathlib import Path
                    config_path = Path("config/autonomous_trading.yaml")
                    if config_path.exists():
                        with open(config_path, 'r') as f:
                            config = yaml.safe_load(f) or {}
                except Exception as e2:
                    logger.warning(f"Could not auto-load config for MarketDataManager: {e2}")
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
        """Compute data age, subtracting weekend gaps when the latest bar is
        from before the weekend.

        Applies to any market that closes over the weekend (equities, ETFs,
        indices, commodities, and forex — all of which have a Fri evening to
        Sun evening hiatus, approximately 48h). Crypto trades 24/7 and does
        NOT get this adjustment.

        2026-05-03: previously only applied for stock_etf_index; commodities
        and forex were measured raw, which tripped the freshness SLA every
        Sunday UTC cycle for GOLD/NATGAS/SILVER 1d and USDCHF/USDCAD 4h. The
        underlying asset was correctly closed — the data was as fresh as it
        can be until Sun 22:00 UTC / Mon 09:30 ET. Now we treat the weekend
        as a legitimate market-closed period for these asset classes too.
        """
        raw_age = now - latest
        # If latest bar is Fri and now is Sat/Sun/Mon, we crossed the
        # weekend — subtract ~48 hours of "market was closed anyway" time.
        if latest.weekday() == 4 and now.weekday() in (5, 6, 0):
            return raw_age - timedelta(hours=48)
        # If latest bar is Thu or earlier and now is Sun/Mon, only one
        # weekend was crossed; still subtract 48h.
        if latest.weekday() <= 4 and now.weekday() in (5, 6, 0) and raw_age > timedelta(hours=48):
            # Only subtract if the weekend actually falls inside the age window
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
        # Weekend-gap adjustment for any market that closes Fri evening
        # through Sun evening (stocks, ETFs, indices, commodities, forex).
        # Crypto is 24/7 and uses raw_age unchanged.
        if family in ("stock_etf_index", "commodity", "forex"):
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
                    # Check if DB data is missing recent bars — if so, do an incremental fetch.
                    # For daily bars, use day-granularity gap. For intraday (1h/4h), use
                    # hour-granularity — otherwise a 4H bar 18 hours stale (0 days)
                    # never triggers a refresh, which caused forex-4H to go 19h stale
                    # on 2026-05-01 (finding F26).
                    latest_db_date = valid_data[-1].timestamp
                    latest_db_naive = latest_db_date.replace(tzinfo=None) if latest_db_date.tzinfo else latest_db_date
                    end_naive = end.replace(tzinfo=None) if end.tzinfo else end

                    if interval == "1d":
                        gap_days = (end_naive - latest_db_naive).days
                        needs_incremental = gap_days > 1
                        gap_hours = gap_days * 24
                    else:
                        # Intraday: use hour-granularity staleness.
                        # 1h bars: refresh if >3h behind (allows some intraday lag)
                        # 4h bars: refresh if >6h behind (one bar gap)
                        gap_hours = (end_naive - latest_db_naive).total_seconds() / 3600
                        threshold_hours = 3 if interval == "1h" else 6
                        needs_incremental = gap_hours > threshold_hours
                        gap_days = int(gap_hours // 24)

                    # 2026-05-03 guard: an incremental fetch only makes sense
                    # when the caller is asking for "up to now" data. For a
                    # backtest window ending in the past (WF test windows,
                    # historical analysis, etc.), the DB already has every
                    # bar that will ever exist for that window — there is
                    # nothing to incrementally fetch. Firing a live data-
                    # source call here hits yfinance's 730d rolling cap on
                    # 1h data and generated thousands of "possibly delisted"
                    # ERROR lines per day for OIL/COPPER/GER40/FR40 1h WF
                    # windows. Skip incremental when `end` is already in
                    # the past; the DB-cache path below returns as-is.
                    _now_naive = datetime.utcnow().replace(tzinfo=None)
                    if needs_incremental and (_now_naive - end_naive).total_seconds() > 86400:
                        logger.debug(
                            f"DB cache for {db_symbol} {interval} covers to "
                            f"{latest_db_naive}; requested end {end_naive} is "
                            f"{(_now_naive - end_naive).days}d in the past "
                            f"— skipping incremental fetch (no live data needed)"
                        )
                        needs_incremental = False

                    if needs_incremental:
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
                                f"DB cache for {db_symbol} {interval} is {gap_hours:.1f}h behind "
                                f"(weekend gap, skipping incremental fetch)"
                            )
                        else:
                            # DB is missing recent bars — fetch only the gap.
                            # For intraday, back up 2 bars to ensure overlap and catch any
                            # newly-closed bar that may have been partial last sync.
                            if interval == "1d":
                                gap_start = latest_db_naive + timedelta(days=1)
                            elif interval == "1h":
                                gap_start = latest_db_naive - timedelta(hours=2)
                            else:  # 4h
                                gap_start = latest_db_naive - timedelta(hours=8)
                            logger.info(
                                f"DB cache for {db_symbol} {interval} is {gap_hours:.1f}h behind, "
                                f"fetching incremental update from {gap_start}"
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
                                    # For daily bars, only count bars newer by calendar date
                                    # (avoids double-counting today's partial bar). For intraday,
                                    # compare by full timestamp so we capture newly-closed hours.
                                    if interval == "1d":
                                        latest_date_only = latest_db_naive.date() if hasattr(latest_db_naive, 'date') and callable(latest_db_naive.date) else latest_db_naive
                                        truly_new = [d for d in gap_valid 
                                                     if (d.timestamp.date() if hasattr(d.timestamp, 'date') and callable(d.timestamp.date) else d.timestamp) > latest_date_only]
                                    else:
                                        truly_new = [d for d in gap_valid if d.timestamp > latest_db_naive]
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
                    # Keyed on db_symbol (display form) to match the lookup above.
                    # S4.0.6 (2026-05-02).
                    self._raw_fetch_cache[f"{db_symbol}:{interval}"] = (valid_data, datetime.now())
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
            # in this session (possibly for a different date range), slice from
            # the cached data instead of making another API call.
            #
            # Key: use db_symbol (display form, e.g. 'BTC') not normalized_symbol
            # (eToro wire form, e.g. 'BTCUSD'). The rest of the pipeline (DB
            # cache, in-memory hist_cache) uses display form; keying raw cache
            # on wire form produced a parallel cache that served stale Yahoo
            # data when the DB already had fresh Binance data for the same
            # symbol. Sprint 4 S4.0.6 (2026-05-02).
            raw_cache_key = f"{db_symbol}:{interval}"
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
                            logger.info(f"Using raw fetch cache for {db_symbol} {interval}: {len(sliced)} bars (from {len(raw_data)} cached)")
                            result = self._validate_and_return_historical_data(sliced, db_symbol)
                            if _cacheable:
                                cache_key = f"{db_symbol}_{interval}_{start.date()}_{end.date()}"
                                self._historical_memory_cache[cache_key] = (result, datetime.now())
                            return result
                        else:
                            logger.info(
                                f"Raw fetch cache for {db_symbol} {interval} doesn't cover "
                                f"requested end {end_naive.date()} (cache ends {latest_cached_ts.date()}), fetching fresh"
                            )

            # The wrapper method _fetch_historical_from_yahoo_finance internally
            # tries Binance first for crypto 1h/4h/1d and falls back to Yahoo.
            # Log accordingly so operators see the real source. S4.0.6.
            logger.info(
                f"Fetching historical data for {db_symbol} {interval} "
                f"(Binance primary for crypto, Yahoo for the rest)"
            )
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
                # Source comes from the MarketData.source of the first bar —
                # _fetch_historical_from_yahoo_finance sets DataSource.BINANCE
                # on Binance fetches and DataSource.YAHOO_FINANCE otherwise.
                _src_name = (
                    str(valid_data[0].source.value)
                    if valid_data and hasattr(valid_data[0].source, 'value')
                    else 'unknown'
                )
                logger.info(
                    f"Retrieved {len(valid_data)} valid historical data points "
                    f"from {_src_name} for {db_symbol} {interval}"
                )
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
                # 2026-05-03: severity should scale with the score, not just
                # the presence of any issue. A 95/100 score with one minor
                # issue (e.g., a weekend gap noted for crypto) is healthy
                # data — surface at INFO. A 50-69 score is notable. Below
                # 50 gets WARNING. Prevents warnings.log flooding for
                # cached reports that are actually fine.
                _score = cached_report.quality_score
                _issues_n = len(cached_report.issues)
                if _score >= 70:
                    logger.info(
                        f"Data quality validation for {symbol}: "
                        f"Score: {_score:.1f}/100, Issues: {_issues_n} (cached)"
                    )
                elif _score >= 50:
                    logger.warning(
                        f"Data quality validation for {symbol}: "
                        f"Score: {_score:.1f}/100, Issues: {_issues_n} (cached)"
                    )
                else:
                    logger.error(
                        f"Data quality validation for {symbol}: "
                        f"POOR - Score: {_score:.1f}/100, Issues: {_issues_n} (cached)"
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

        Sprint 4 S4.0 (2026-05-02): for crypto 1h/4h, try Binance public
        API first. Yahoo caps 1h crypto data at ~7 months, making 4h
        data (resampled from 1h) cap at the same depth. Binance serves
        1h/4h back to 2017 with no auth. The Binance adapter is a no-op
        for non-crypto symbols and falls back to Yahoo on any error
        (network, quota, unsupported pair).

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
        # Sprint 4 S4.0: try Binance first for crypto 1h/4h/1d.
        # Binance is the industry reference for crypto historical
        # candles (deep spot volume since 2018). Only engaged when the
        # (symbol, interval) combo is explicitly supported — unsupported
        # combos silently skip straight to Yahoo.
        #
        # S4.0.1 extension: 1d added too. Rationale is single-source-of-
        # truth across timeframes — Binance 1h/4h/1d candles all roll up
        # consistently, where Yahoo 1d is a cross-venue aggregate with
        # occasional weekend-boundary anomalies. Keeps backtest and live
        # signal-gen agreeing on "what was the close of 2025-10-03".
        #
        # Symbol form: callers pass either display form ("BTC", "SOL") or
        # eToro wire form ("BTCUSD", "SOLUSD"). Our Binance adapter keys
        # on display form, so strip the USD suffix up-front. Without this
        # normalisation, calls from get_historical_data() (which passes
        # normalized_symbol = wire form) silently miss the Binance path
        # and fall straight to Yahoo.
        if interval in ("1h", "4h", "1d"):
            _bn_symbol = symbol.upper().strip()
            # Map eToro wire → canonical display for crypto. Mirrors the
            # table in get_historical_data (kept local to avoid an import
            # cycle for a trivial 6-entry dict).
            _CRYPTO_WIRE_TO_DISPLAY = {
                "BTCUSD": "BTC", "ETHUSD": "ETH", "SOLUSD": "SOL",
                "AVAXUSD": "AVAX", "LINKUSD": "LINK", "DOTUSD": "DOT",
                "XRPUSD": "XRP", "ADAUSD": "ADA", "NEARUSD": "NEAR",
                "LTCUSD": "LTC", "BCHUSD": "BCH",
            }
            if _bn_symbol in _CRYPTO_WIRE_TO_DISPLAY:
                _bn_symbol = _CRYPTO_WIRE_TO_DISPLAY[_bn_symbol]

            try:
                from src.api.binance_ohlc import is_supported as _binance_supported
                from src.api.binance_ohlc import fetch_klines as _binance_fetch
                from src.api.binance_ohlc import BinanceAPIError as _BinanceAPIError

                if _binance_supported(_bn_symbol, interval):
                    try:
                        bars = _binance_fetch(_bn_symbol, start, end, interval)
                        if bars:
                            logger.info(
                                f"Binance (primary): {len(bars)} {interval} bars for {_bn_symbol} "
                                f"({bars[0].timestamp.date()} → {bars[-1].timestamp.date()})"
                            )
                            return bars
                        # Empty result from Binance for a supported pair
                        # is unusual (would mean the whole window has no
                        # trading activity). Fall through to Yahoo as a
                        # safety net rather than returning [].
                        logger.warning(
                            f"Binance returned 0 bars for {_bn_symbol} {interval} "
                            f"{start.date()}→{end.date()}; falling back to Yahoo"
                        )
                    except _BinanceAPIError as be:
                        # Expected fallback path — network hiccup, quota,
                        # temporary outage. Logged at INFO not WARNING
                        # because this is the designed behaviour.
                        logger.info(
                            f"Binance unavailable for {_bn_symbol} {interval} "
                            f"({be}); falling back to Yahoo"
                        )
            except ImportError:
                # Binance adapter absent (e.g. stale deploy). Silently
                # fall through to Yahoo so the primary path keeps working.
                pass

        # FMP primary path for non-crypto 1h/4h (2026-05-03).
        # We pay for FMP Starter; it has 5y+ of intraday history for US
        # stocks, ETFs, forex, and some commodities, which dodges Yahoo's
        # ~7-month 1h rolling cap. Per-(symbol, interval) support matrix
        # lives in src/api/fmp_ohlc.SUPPORT — unsupported combos fall
        # through cleanly (is_supported returns False, no wasted roundtrip).
        # Crypto stays on Binance; we don't need FMP crypto given Binance
        # depth and FMP's 300 req/min budget is better spent on stocks.
        _is_crypto_wire = symbol.upper().strip() in {
            "BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "LINKUSD", "DOTUSD",
            "XRPUSD", "ADAUSD", "NEARUSD", "LTCUSD", "BCHUSD",
            "BTC", "ETH", "SOL", "AVAX", "LINK", "DOT",
            "XRP", "ADA", "NEAR", "LTC", "BCH",
        }
        if interval in ("1h", "4h", "1d") and not _is_crypto_wire:
            try:
                from src.api.fmp_ohlc import is_supported as _fmp_supported
                from src.api.fmp_ohlc import fetch_klines as _fmp_fetch
                from src.api.fmp_ohlc import FMPAPIError as _FMPAPIError

                if _fmp_supported(symbol, interval):
                    try:
                        bars = _fmp_fetch(symbol, start, end, interval)
                        if bars:
                            logger.info(
                                f"FMP (primary non-crypto {interval}): {len(bars)} bars "
                                f"for {symbol} ({bars[0].timestamp.date()} → "
                                f"{bars[-1].timestamp.date()})"
                            )
                            return bars
                        # FMP is the authoritative source for this (symbol,
                        # interval). A 0-bar response almost always means
                        # "no bars in this window" — weekend for forex/equities,
                        # requested range entirely in the future, etc. Falling
                        # back to Yahoo here generates spurious "possibly
                        # delisted" error spam without adding any data. Trust
                        # the FMP response and return empty.
                        #
                        # (If FMP itself is unreachable we get an FMPAPIError,
                        # not an empty list — that case DOES fall through to
                        # Yahoo via the except branch below.)
                        logger.info(
                            f"FMP returned 0 bars for {symbol} {interval} "
                            f"{start.date()}→{end.date()} (likely closed market "
                            f"or future window); returning empty"
                        )
                        return []
                    except _FMPAPIError as fe:
                        if fe.reason == "premium_blocked":
                            # Blocked at the FMP level — silently fall
                            # through to Yahoo without retry. This is a
                            # static property of the Starter plan.
                            logger.debug(
                                f"FMP premium-blocked for {symbol} {interval}; "
                                f"falling back to Yahoo"
                            )
                        else:
                            # Network/quota/parse — log at INFO since the
                            # fallback is designed behaviour.
                            logger.info(
                                f"FMP unavailable for {symbol} {interval} "
                                f"({fe.reason}: {fe}); falling back to Yahoo"
                            )
            except ImportError:
                # FMP adapter absent (e.g. stale deploy). Silently fall
                # through to Yahoo so the primary path keeps working.
                pass

        # Yahoo 1h rolling-cap guard (2026-05-03).
        #
        # Yahoo Finance's /v8 1h endpoint only serves bars where BOTH
        #   start >= now - 730 days  AND  end <= now
        # Any request whose `start` falls outside this rolling window
        # returns empty AND yfinance's own root logger writes an ERROR line:
        #   "$HG=F: possibly delisted; no price data found (1h YYYY-MM-DD
        #    → YYYY-MM-DD) Yahoo error = '1h data not available. The
        #    requested range must be within the last 730 days.'"
        # That ERROR hits our errors.log (yfinance uses the root logger)
        # regardless of what we do with the return value.
        #
        # This fires on every WF backtest for symbols where FMP is premium-
        # blocked at 1h (OIL/COPPER/GER40/FR40) because proposer WF test
        # windows span a year+ of history — the `start` is always outside
        # Yahoo's 730d window. The call was always going to return empty;
        # the ERROR is pure noise that masks real errors.
        #
        # Proper fix: never call Yahoo 1h for a window whose `start` is
        # outside the rolling cap. Return [] so the caller's existing DB-
        # cache fallback path serves from the 5y of bars we already have.
        # Same logic applies to 4h synthesized from 1h (source 1h call
        # would fail identically).
        if interval in ("1h", "4h"):
            _now = datetime.utcnow()
            # Use 720d (not 730d) as a safety margin — Yahoo's cap drifts
            # slightly and empirically starts returning empty a few days
            # before the nominal 730d boundary.
            _yahoo_1h_cap_days = 720
            _start_naive = start.replace(tzinfo=None) if hasattr(start, 'tzinfo') and start.tzinfo else start
            _start_age_days = (_now - _start_naive).total_seconds() / 86400
            if _start_age_days > _yahoo_1h_cap_days:
                logger.info(
                    f"Yahoo 1h cap: skipping fetch for {symbol} {interval} "
                    f"{start.date() if hasattr(start, 'date') else start}→"
                    f"{end.date() if hasattr(end, 'date') else end} — "
                    f"start is {_start_age_days:.0f}d ago, outside Yahoo's "
                    f"{_yahoo_1h_cap_days}d rolling window. Caller's DB cache "
                    f"fallback will serve."
                )
                return []

        yf_symbol = to_yahoo_ticker(symbol)
        ensure_yfinance_cache()
        ticker = yf.Ticker(yf_symbol)
        
        # Map interval format (eToro style to yfinance style).
        # Yahoo Finance doesn't support 4h candles natively, so we fetch
        # 1h and resample below. Note: crypto 4h is now served by Binance
        # via the early-exit branch above; this 1h→4h synthesis only fires
        # for non-crypto 4h (equities, commodities, forex, indices) or as
        # a fallback when Binance is unavailable for crypto 4h.
        interval_map = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "1h": "1h",
            "4h": "1h",  # Fetch 1h, then resample to 4h (fallback path for crypto)
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
        #
        # Sprint 4 S4.0 context (2026-05-02): this path now fires only for
        # non-crypto 4h (equities, commodities, forex, indices) — crypto 4h
        # is served by Binance via the early-exit branch at the top of this
        # function. The F10 invariant below (4h window ≤ 1h source window)
        # remains correct for the Yahoo synthesis path because Yahoo's 1h
        # data is genuinely capped at ~7 months and synthesising 4h beyond
        # that would produce phantom bars that vanish on cache clear.
        #
        # Sprint 2 F10 (2026-05-02): CRITICAL constraint — yfinance's 1h data
        # has a ~7-month hard cap (730 days ≈ 210 days max documented, but
        # empirically ~174-210d depending on symbol and exchange). The 4H
        # resample is a DERIVED view: it can ONLY cover the same calendar
        # window as the source 1h data. If the DB cache contains 4h bars
        # dated before the earliest available 1h bar, those rows are phantom
        # (synthesized from an older 1h snapshot that is no longer
        # reproducible via fresh fetches). This phantom depth disappears on
        # the next cache clear and is invisible to the schema-version
        # invalidator.
        #
        # Enforce the invariant here: the output 4h window cannot be wider
        # than the input 1h window. If a 4h bar's start is before the
        # earliest 1h bar we just fetched, drop it. This keeps the 4h cache
        # HONEST — it mirrors the 1h source window, nothing more.
        if interval == "4h" and yf_interval == "1h":
            if hist.empty:
                logger.warning(f"Yahoo 1H fetch for {symbol} returned empty; cannot synthesize 4H bars")
                return []
            source_first = hist.index.min()
            source_last = hist.index.max()
            logger.info(
                f"Synthesizing 4H bars from {len(hist)} 1H bars for {symbol} "
                f"(source window {source_first} → {source_last})"
            )
            hist_4h = hist.resample('4h').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna(subset=['Open', 'Close'])
            # Trim any resampled 4H bar whose window-start falls outside the
            # source 1h range. resample('4h') creates bins on fixed 4h boundaries
            # starting from the index's base date, which can emit bins
            # technically before the earliest 1h bar (empty after dropna in
            # practice, but the explicit trim is the invariant statement).
            before_trim = len(hist_4h)
            hist_4h = hist_4h[(hist_4h.index >= source_first) & (hist_4h.index <= source_last)]
            trimmed = before_trim - len(hist_4h)
            if trimmed > 0:
                logger.info(
                    f"4H invariant trim: dropped {trimmed} resampled bars outside "
                    f"1H source window for {symbol}"
                )
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

                # Convert to MarketData objects. Read the source column
                # correctly — previously this path defaulted to YAHOO_FINANCE
                # for any row that wasn't explicitly "FMP", silently re-
                # tagging Binance-sourced bars as Yahoo at read-time. That
                # was a hidden correctness bug for consumers that read
                # md.source downstream.
                _source_map = {
                    "BINANCE":       DataSource.BINANCE,
                    "FMP":           DataSource.FMP,
                    "YAHOO_FINANCE": DataSource.YAHOO_FINANCE,
                    "yahoo":         DataSource.YAHOO_FINANCE,  # legacy casing
                    "ETORO":         DataSource.ETORO,
                }
                data_list = []
                for r in records:
                    source = _source_map.get(r.source, DataSource.YAHOO_FINANCE)

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
                rejected_ohlc = 0  # F27: count bars rejected for invalid OHLC
                for md in data_list:
                    if interval == "1d":
                        md_key = md.timestamp.date() if hasattr(md.timestamp, 'date') and callable(md.timestamp.date) else md.timestamp
                    else:
                        md_key = md.timestamp.replace(tzinfo=None) if hasattr(md.timestamp, 'tzinfo') and md.timestamp.tzinfo else md.timestamp
                    
                    if md_key in existing_timestamps:
                        continue

                    # F27 (2026-05-01): validate OHLC at write boundary.
                    # Bars with high < max(open, close) or low > min(open, close)
                    # are mathematically invalid. Historically such bars slipped in
                    # via `monitoring_service._sync_price_data` (batch Yahoo path)
                    # which didn't call `validate_data()` before save. Same rule as
                    # `validate_data` uses at read-time, applied here so downstream
                    # readers don't have to re-filter (and re-log warnings) every
                    # cycle. Epsilon 1e-8 matches validate_data.
                    _eps = 1e-8
                    if md.high is not None and md.open is not None and md.close is not None:
                        if md.high < md.open - _eps or md.high < md.close - _eps:
                            rejected_ohlc += 1
                            continue
                    if md.low is not None and md.open is not None and md.close is not None:
                        if md.low > md.open + _eps or md.low > md.close + _eps:
                            rejected_ohlc += 1
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

                if rejected_ohlc > 0:
                    logger.info(
                        f"F27 save-boundary: rejected {rejected_ohlc} invalid-OHLC "
                        f"{interval} bars for {symbol} (likely partial/forming bars)"
                    )

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
