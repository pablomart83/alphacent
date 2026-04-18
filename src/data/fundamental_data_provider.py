"""
Fundamental Data Provider - Fetches and caches fundamental company data.

Integrates with Financial Modeling Prep API (primary) and Alpha Vantage (fallback).
Implements rate limiting and 24-hour caching to minimize API calls.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
import requests
from threading import Lock

logger = logging.getLogger(__name__)

# Import API usage monitor
try:
    from src.monitoring.api_usage_monitor import get_api_usage_monitor, ApiPriority
    API_MONITORING_ENABLED = True
except ImportError:
    API_MONITORING_ENABLED = False
    logger.warning("API usage monitoring not available")


@dataclass
class FundamentalData:
    """Container for fundamental company data."""
    symbol: str
    timestamp: datetime
    
    # Income statement
    eps: Optional[float] = None
    revenue: Optional[float] = None
    revenue_growth: Optional[float] = None
    
    # Balance sheet
    total_debt: Optional[float] = None
    total_equity: Optional[float] = None
    debt_to_equity: Optional[float] = None
    
    # Key metrics
    roe: Optional[float] = None  # Return on Equity
    pe_ratio: Optional[float] = None
    market_cap: Optional[float] = None
    
    # Insider trading
    insider_net_buying: Optional[float] = None
    
    # Share dilution
    shares_outstanding: Optional[float] = None
    shares_change_percent: Optional[float] = None
    
    # Dividend data
    dividend_yield: Optional[float] = None  # Annual dividend yield (e.g., 0.025 for 2.5%)
    
    # Earnings data
    earnings_surprise: Optional[float] = None  # Latest earnings surprise % (e.g., 0.05 for 5% beat)
    
    # Data source
    source: str = "unknown"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class RateLimiter:
    """
    Two-layer rate limiter for FMP API calls.

    Layer 1 — Rolling window: enforces max_calls per period_seconds (e.g. 300/min).
    Layer 2 — Token bucket: enforces a per-second burst cap so concurrent workers
               can't fire all their calls in the first second of a window.

    With 300/min and 8 workers each making 5 sequential calls:
    - Without throttle: 40 calls fire in the first ~0.1s → 429 errors
    - With token bucket at 5/s: calls spread evenly, 300/min fully utilized
    """

    def __init__(self, max_calls: int, period_seconds: int = 86400):
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self.calls = []
        self.lock = Lock()
        self.circuit_breaker_active = False
        self.circuit_breaker_reset_time = None

        # Token bucket: refill at max_calls/period_seconds per second
        # e.g. 300/60 = 5 tokens/sec
        self._tokens_per_sec = max_calls / max(period_seconds, 1)
        self._bucket_tokens = float(max_calls)  # Start full
        self._bucket_last_refill = time.time()
        self._bucket_max = float(max_calls)

    def _refill_bucket(self) -> None:
        """Refill token bucket based on elapsed time. Must be called under lock."""
        now = time.time()
        elapsed = now - self._bucket_last_refill
        self._bucket_tokens = min(
            self._bucket_max,
            self._bucket_tokens + elapsed * self._tokens_per_sec
        )
        self._bucket_last_refill = now

    def _get_next_midnight_utc(self) -> float:
        from datetime import timezone
        now_utc = datetime.now(timezone.utc)
        next_midnight = now_utc.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return next_midnight.timestamp()

    def _check_circuit_breaker_reset(self) -> None:
        if self.circuit_breaker_active and self.circuit_breaker_reset_time:
            if time.time() >= self.circuit_breaker_reset_time:
                logger.info(f"Circuit breaker reset after {self.period_seconds}s cooldown")
                self.calls = []
                self._bucket_tokens = self._bucket_max
                self.circuit_breaker_active = False
                self.circuit_breaker_reset_time = None

    def activate_circuit_breaker(self) -> None:
        with self.lock:
            self.circuit_breaker_active = True
            self.circuit_breaker_reset_time = time.time() + self.period_seconds
            current_time = time.time()
            self.calls = [current_time] * self.max_calls
            self._bucket_tokens = 0.0
            reset_dt = datetime.fromtimestamp(self.circuit_breaker_reset_time)
            logger.warning(f"Circuit breaker activated — resets at {reset_dt}")

    def can_make_call(self) -> bool:
        """Check if a call can be made (rolling window + token bucket)."""
        with self.lock:
            self._check_circuit_breaker_reset()
            self._refill_bucket()
            now = time.time()
            # Rolling window check
            self.calls = [t for t in self.calls if now - t < self.period_seconds]
            if len(self.calls) >= self.max_calls:
                return False
            # Token bucket check — must have at least 1 token
            if self._bucket_tokens < 1.0:
                return False
            return True

    def wait_for_token(self, timeout: float = 30.0) -> bool:
        """
        Block until a token is available or timeout expires.
        Use this instead of can_make_call() in the cache warmer for smooth throttling.

        Returns True if a token was acquired, False if timed out.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                self._check_circuit_breaker_reset()
                self._refill_bucket()
                now = time.time()
                self.calls = [t for t in self.calls if now - t < self.period_seconds]
                if len(self.calls) < self.max_calls and self._bucket_tokens >= 1.0:
                    # Consume token and record call atomically
                    self._bucket_tokens -= 1.0
                    self.calls.append(now)
                    return True
            # Sleep for the time it takes to generate one token
            sleep_time = max(0.01, 1.0 / max(self._tokens_per_sec, 0.1))
            time.sleep(sleep_time)
        return False

    def record_call(self) -> None:
        """Record a call (use only when NOT using wait_for_token)."""
        with self.lock:
            self._bucket_tokens = max(0.0, self._bucket_tokens - 1.0)
            self.calls.append(time.time())

    def get_usage(self) -> Dict[str, Any]:
        with self.lock:
            self._check_circuit_breaker_reset()
            self._refill_bucket()
            now = time.time()
            self.calls = [t for t in self.calls if now - t < self.period_seconds]
            return {
                'calls_made': len(self.calls),
                'max_calls': self.max_calls,
                'usage_percent': (len(self.calls) / self.max_calls) * 100,
                'calls_remaining': self.max_calls - len(self.calls),
                'tokens_available': round(self._bucket_tokens, 1),
                'tokens_per_sec': round(self._tokens_per_sec, 2),
                'circuit_breaker_active': self.circuit_breaker_active,
                **(
                    {'circuit_breaker_reset_time': datetime.fromtimestamp(self.circuit_breaker_reset_time).isoformat()}
                    if self.circuit_breaker_reset_time else {}
                ),
            }



class FundamentalDataCache:
    """Cache for fundamental data with TTL."""
    
    def __init__(self, ttl_seconds: int = 86400):
        """
        Initialize cache.
        
        Args:
            ttl_seconds: Time-to-live in seconds (default: 24 hours)
        """
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, FundamentalData] = {}
        self.lock = Lock()
    
    def get(self, symbol: str) -> Optional[FundamentalData]:
        """Get cached data if not expired."""
        with self.lock:
            if symbol not in self.cache:
                return None
            
            data = self.cache[symbol]
            age = datetime.now() - data.timestamp
            
            if age.total_seconds() > self.ttl_seconds:
                del self.cache[symbol]
                return None
            
            return data
    
    def set(self, symbol: str, data: FundamentalData) -> None:
        """Store data in cache."""
        with self.lock:
            self.cache[symbol] = data
    
    def clear(self) -> None:
        """Clear all cached data."""
        with self.lock:
            self.cache.clear()


# ---------------------------------------------------------------------------
# Module-level singleton — ONE shared instance across the entire process.
#
# Why this matters:
# - Rate limiter: one shared token bucket enforces 300/min globally.
#   Multiple instances each think they have 300 calls — combined they blow the limit.
# - Memory cache: earnings_calendar_cache, FundamentalDataCache live on the instance.
#   Multiple instances each have empty caches → every call hits FMP.
# - DB cache: _get_from_database() is stateless (reads DB), so multiple instances
#   don't cause DB duplication, but they do cause redundant DB reads.
#
# Usage:
#   from src.data.fundamental_data_provider import get_fundamental_data_provider
#   provider = get_fundamental_data_provider()
# ---------------------------------------------------------------------------

_singleton_instance: Optional['FundamentalDataProvider'] = None
_singleton_lock = Lock()


class FundamentalDataProvider:
    """
    Provides fundamental company data from multiple sources.

    Primary source: Financial Modeling Prep (FMP)
    Fallback source: Alpha Vantage

    Use get_fundamental_data_provider() to get the shared singleton instance.
    Never instantiate directly — multiple instances means multiple rate limiters
    and multiple memory caches, which causes redundant API calls.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize provider.

        Do NOT call this directly — use get_fundamental_data_provider() to get
        the shared singleton. Direct instantiation bypasses the singleton and
        creates a separate rate limiter + memory cache, causing redundant API calls.

        Args:
            config: Configuration dictionary with data_sources section
        """

        if config is None:
            try:
                from src.core.config_loader import load_config
                config = load_config()
            except Exception:
                try:
                    import yaml
                    from pathlib import Path
                    config_path = Path("config/autonomous_trading.yaml")
                    config = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}
                except Exception:
                    config = {}

        self.config = config
        
        # FMP configuration - using new stable API
        fmp_config = config.get('data_sources', {}).get('financial_modeling_prep', {})
        self.fmp_enabled = fmp_config.get('enabled', False)
        self.fmp_api_key = fmp_config.get('api_key', '')
        self.fmp_base_url = "https://financialmodelingprep.com/stable"  # Updated to stable API
        
        # Alpha Vantage configuration (fallback)
        av_config = config.get('data_sources', {}).get('alpha_vantage', {})
        self.av_enabled = av_config.get('enabled', False)
        self.av_api_key = av_config.get('api_key', '')
        
        # Rate limiting - supports per-minute or per-day limits
        fmp_rate_limit = fmp_config.get('rate_limit', 300)
        fmp_rate_period = fmp_config.get('rate_limit_period', 60)  # Default: 60 seconds (per-minute)
        self.fmp_rate_limiter = RateLimiter(max_calls=fmp_rate_limit, period_seconds=fmp_rate_period)
        
        # In-memory caching (fast, but not persistent)
        cache_duration = fmp_config.get('cache_duration', 86400)
        self.cache = FundamentalDataCache(ttl_seconds=cache_duration)
        
        # Database caching (persistent across restarts)
        from src.models.database import get_database
        self.database = get_database()
        
        # Smart caching configuration
        self.cache_strategy = fmp_config.get('cache_strategy', 'earnings_aware')
        
        if self.cache_strategy == 'earnings_aware':
            earnings_config = fmp_config.get('earnings_aware_cache', {})
            self.default_cache_ttl = earnings_config.get('default_ttl', 30 * 24 * 3600)  # 30 days
            self.earnings_period_ttl = earnings_config.get('earnings_period_ttl', 24 * 3600)  # 24 hours
            self.earnings_calendar_ttl = earnings_config.get('earnings_calendar_ttl', 7 * 24 * 3600)  # 7 days
            logger.info(f"Using earnings-aware caching: default={self.default_cache_ttl}s, earnings={self.earnings_period_ttl}s")
        else:
            self.default_cache_ttl = cache_duration
            self.earnings_period_ttl = cache_duration
            self.earnings_calendar_ttl = cache_duration
            logger.info(f"Using fixed caching: {cache_duration}s")
        
        self.db_cache_ttl = self.default_cache_ttl  # Use default for database cache
        
        # Earnings calendar cache (in-memory, 7-day TTL)
        self.earnings_calendar_cache: Dict[str, Dict[str, Any]] = {}
        self.earnings_calendar_timestamps: Dict[str, datetime] = {}
        
        # Insider trading cache (in-memory, 24h TTL)
        self._insider_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._insider_cache_timestamps: Dict[str, datetime] = {}
        
        # Sector performance cache (in-memory, 24h TTL)
        self._sector_perf_cache: Optional[Dict[str, Dict[str, float]]] = None
        self._sector_perf_cache_ts: Optional[datetime] = None
        
        period_label = "min" if fmp_rate_period <= 60 else f"{fmp_rate_period}s"
        logger.info(f"FundamentalDataProvider initialized - FMP: {self.fmp_enabled}, "
                   f"AV: {self.av_enabled}, Rate limit: {fmp_rate_limit}/{period_label}, "
                   f"Cache strategy: {self.cache_strategy}")
    
    def get_fundamental_data(self, symbol: str, use_cache: bool = True) -> Optional[FundamentalData]:
        """
        Get fundamental data for a symbol.
        
        Caching strategy (in order):
        1. Skip non-fundamental symbols (crypto, forex, indices, commodities, ETFs)
        2. Memory cache (fastest, but lost on restart)
        3. Database cache (persistent, 24-hour TTL)
        4. FMP API (slowest, rate limited)
        5. Alpha Vantage fallback (immediate if FMP data is incomplete)
        6. Stale database data (better than nothing)
        
        Args:
            symbol: Stock symbol
            use_cache: Whether to use cached data
            
        Returns:
            FundamentalData object or None if unavailable
        """
        # Skip symbols that don't have traditional fundamental data
        # Instead of a hardcoded list, dynamically check against asset class lists.
        # Commodities, forex, indices, crypto, and ETFs don't have earnings/P&E/revenue.
        try:
            from src.core.tradeable_instruments import (
                DEMO_ALLOWED_COMMODITIES, DEMO_ALLOWED_FOREX,
                DEMO_ALLOWED_INDICES, DEMO_ALLOWED_CRYPTO,
                DEMO_ALLOWED_ETFS,
            )
            _non_fundamental = (
                set(DEMO_ALLOWED_COMMODITIES) | set(DEMO_ALLOWED_FOREX) |
                set(DEMO_ALLOWED_INDICES) | set(DEMO_ALLOWED_CRYPTO) |
                set(DEMO_ALLOWED_ETFS)
            )
        except ImportError:
            _non_fundamental = set()
        
        if symbol.upper() in _non_fundamental:
            logger.debug(f"Skipping fundamental data fetch for {symbol} (non-fundamental asset)")
            return None
        
        # FMP starter plan only covers US-listed securities.
        # Skip non-US exchange symbols (contain '.') to avoid 402 errors.
        if '.' in symbol.upper():
            logger.debug(f"Skipping fundamental data for non-US symbol {symbol}")
            return None
        
        # Check memory cache first (fastest)
        if use_cache:
            cached = self.cache.get(symbol)
            if cached:
                logger.debug(f"Using memory-cached fundamental data for {symbol}")
                return cached
        
        # Check database cache (persistent)
        if use_cache:
            db_data = self._get_from_database(symbol)
            if db_data:
                # Also store in memory cache for faster subsequent access
                self.cache.set(symbol, db_data)
                logger.debug(f"Using database-cached fundamental data for {symbol}")
                return db_data
        
        # Try FMP API (using stable API)
        fmp_data = None
        if self.fmp_enabled:
            fmp_data = self._fetch_from_fmp(symbol)
            if fmp_data:
                # Check if data is complete enough
                if self._is_data_complete(fmp_data):
                    # Store in both caches
                    self.cache.set(symbol, fmp_data)
                    self._save_to_database(fmp_data)
                    return fmp_data
                else:
                    logger.debug(f"FMP data for {symbol} is incomplete (eps={fmp_data.eps}, pe={fmp_data.pe_ratio}) — using as-is")
                    # Still save what we have — partial data is better than nothing
                    self.cache.set(symbol, fmp_data)
                    self._save_to_database(fmp_data)
                    return fmp_data
        
        # Alpha Vantage fallback disabled — free tier is 25 req/day, exhausted immediately
        # during cache warming. Returns rate-limit message for every call after the first 25.
        # FMP alone is sufficient with the relaxed _is_data_complete check (eps OR pe_ratio).

        # Last resort: Check for stale data in database (better than nothing)
        stale_data = self._get_from_database(symbol, allow_stale=True)
        if stale_data:
            logger.warning(f"Using stale fundamental data for {symbol} (age: {(datetime.now() - stale_data.timestamp).days} days)")
            # Don't cache stale data in memory
            return stale_data
        
        logger.error(f"Failed to fetch fundamental data for {symbol} from all sources")
        return None
    
    def _is_data_complete(self, data: FundamentalData) -> bool:
        """
        Check if fundamental data is complete enough to use.
        
        revenue_growth is structurally unavailable from a single-period FMP fetch
        (requires 2 periods to compute), so we only require eps OR pe_ratio.
        
        Args:
            data: FundamentalData object to check
            
        Returns:
            True if data is complete enough, False otherwise
        """
        # At least one of eps or pe_ratio must be present
        is_complete = data.eps is not None or data.pe_ratio is not None
        
        if not is_complete:
            logger.debug(f"Data incomplete for {data.symbol}: EPS={data.eps}, "
                        f"revenue_growth={data.revenue_growth}, pe_ratio={data.pe_ratio}")
        
        return is_complete
    
    def _merge_fundamental_data(self, primary: FundamentalData, fallback: FundamentalData) -> FundamentalData:
        """
        Merge two FundamentalData objects, preferring non-None values from primary.
        
        Args:
            primary: Primary data source (e.g., FMP)
            fallback: Fallback data source (e.g., Alpha Vantage)
            
        Returns:
            Merged FundamentalData object
        """
        merged = FundamentalData(
            symbol=primary.symbol,
            timestamp=primary.timestamp,
            eps=primary.eps if primary.eps is not None else fallback.eps,
            revenue=primary.revenue if primary.revenue is not None else fallback.revenue,
            revenue_growth=primary.revenue_growth if primary.revenue_growth is not None else fallback.revenue_growth,
            total_debt=primary.total_debt if primary.total_debt is not None else fallback.total_debt,
            total_equity=primary.total_equity if primary.total_equity is not None else fallback.total_equity,
            debt_to_equity=primary.debt_to_equity if primary.debt_to_equity is not None else fallback.debt_to_equity,
            roe=primary.roe if primary.roe is not None else fallback.roe,
            pe_ratio=primary.pe_ratio if primary.pe_ratio is not None else fallback.pe_ratio,
            market_cap=primary.market_cap if primary.market_cap is not None else fallback.market_cap,
            insider_net_buying=primary.insider_net_buying if primary.insider_net_buying is not None else fallback.insider_net_buying,
            shares_outstanding=primary.shares_outstanding if primary.shares_outstanding is not None else fallback.shares_outstanding,
            shares_change_percent=primary.shares_change_percent if primary.shares_change_percent is not None else fallback.shares_change_percent,
            dividend_yield=primary.dividend_yield if primary.dividend_yield is not None else fallback.dividend_yield,
            earnings_surprise=primary.earnings_surprise if primary.earnings_surprise is not None else fallback.earnings_surprise,
            source=f"{primary.source}+{fallback.source}"
        )
        
        logger.info(f"Merged fundamental data for {primary.symbol} from {primary.source} and {fallback.source}")
        return merged
    
    def _fetch_from_fmp(self, symbol: str) -> Optional[FundamentalData]:
        """Fetch data from Financial Modeling Prep API."""
        # Check rate limit BEFORE making any calls
        usage = self.fmp_rate_limiter.get_usage()
        if usage['usage_percent'] >= 80:
            logger.warning(f"FMP API usage at {usage['usage_percent']:.1f}% "
                          f"({usage['calls_made']}/{usage['max_calls']})")
        
        if not self.fmp_rate_limiter.can_make_call():
            logger.error(f"FMP rate limit exceeded ({usage['calls_made']}/{usage['max_calls']})")
            return None
        
        try:
            # Fetch multiple endpoints using new API format (query parameters)
            # Stop immediately if any call returns 429
            income_stmt = self._fmp_request("/income-statement", symbol=symbol, limit=1)
            if income_stmt is None and not self.fmp_rate_limiter.can_make_call():
                logger.warning(f"Stopping FMP requests for {symbol} - rate limit hit")
                return None
            
            balance_sheet = self._fmp_request("/balance-sheet-statement", symbol=symbol, limit=1)
            if balance_sheet is None and not self.fmp_rate_limiter.can_make_call():
                logger.warning(f"Stopping FMP requests for {symbol} - rate limit hit")
                return None
            
            key_metrics = self._fmp_request("/key-metrics", symbol=symbol, limit=1)
            if key_metrics is None and not self.fmp_rate_limiter.can_make_call():
                logger.warning(f"Stopping FMP requests for {symbol} - rate limit hit")
                return None
            
            profile = self._fmp_request("/profile", symbol=symbol)
            if profile is None and not self.fmp_rate_limiter.can_make_call():
                logger.warning(f"Stopping FMP requests for {symbol} - rate limit hit")
                return None
            
            # Parse data
            data = FundamentalData(
                symbol=symbol,
                timestamp=datetime.now(),
                source="FMP"
            )
            
            # Income statement
            if income_stmt and len(income_stmt) > 0:
                stmt = income_stmt[0]
                data.eps = stmt.get('eps') or stmt.get('epsDiluted')
                data.revenue = stmt.get('revenue')
                # Revenue growth not in single statement, would need 2 periods
                data.revenue_growth = stmt.get('revenueGrowth')  # May be None
            
            # Balance sheet
            if balance_sheet and len(balance_sheet) > 0:
                bs = balance_sheet[0]
                data.total_debt = bs.get('totalDebt')
                data.total_equity = bs.get('totalStockholdersEquity')
                if data.total_debt and data.total_equity and data.total_equity != 0:
                    data.debt_to_equity = data.total_debt / data.total_equity
            
            # Key metrics (stable API format)
            if key_metrics and len(key_metrics) > 0:
                metrics = key_metrics[0]
                data.roe = metrics.get('returnOnEquity')  # Stable API uses returnOnEquity
                data.pe_ratio = metrics.get('peRatio')
                data.market_cap = metrics.get('marketCap')
                data.dividend_yield = metrics.get('dividendYield')
            
            # Profile
            if profile and len(profile) > 0:
                prof = profile[0]
                data.market_cap = data.market_cap or prof.get('marketCap')
                price = prof.get('price')
                
                # Fallback dividend yield from profile
                if not data.dividend_yield:
                    data.dividend_yield = prof.get('lastDiv')  # lastDiv is per-share, need to convert
                    if data.dividend_yield and price and price > 0:
                        data.dividend_yield = data.dividend_yield / price  # Convert to yield
                
                # Calculate P/E ratio if not available from key metrics
                if not data.pe_ratio and price and data.eps and data.eps > 0:
                    data.pe_ratio = price / data.eps
            
            logger.info(f"Fetched fundamental data for {symbol} from FMP")
            
            # Fetch earnings surprise from earnings calendar (separate call)
            try:
                earnings_surprise = self.calculate_earnings_surprise(symbol)
                if earnings_surprise is not None:
                    data.earnings_surprise = earnings_surprise
            except Exception as e:
                logger.debug(f"Could not fetch earnings surprise for {symbol}: {e}")
            
            return data
            
        except Exception as e:
            logger.error(f"Error fetching from FMP for {symbol}: {e}")
            return None
    
    def _fmp_request(self, endpoint: str, base_url: Optional[str] = None, **params) -> Optional[Any]:
            """Make a request to FMP API with token-bucket throttling.

            Blocks until a rate-limit token is available (up to 30s) rather than
            immediately returning None. This lets concurrent workers naturally
            spread their calls across the full 300/min budget instead of all
            firing in the first second and hitting 429s.
            """
            # Block until a token is available (handles both window + bucket)
            if not self.fmp_rate_limiter.wait_for_token(timeout=30.0):
                logger.warning(f"FMP rate limit — timed out waiting for token, skipping {endpoint}")
                return None

            url = f"{base_url or self.fmp_base_url}{endpoint}"
            params['apikey'] = self.fmp_api_key

            try:
                response = requests.get(url, params=params, timeout=10)

                if response.status_code == 429:
                    logger.error(f"FMP API rate limit exceeded (429) for {endpoint}")
                    self.fmp_rate_limiter.activate_circuit_breaker()
                    return None

                response.raise_for_status()
                data = response.json()

                if isinstance(data, dict) and 'Error Message' in data:
                    logger.error(f"FMP API error for {endpoint}: {data['Error Message']}")
                    return None

                return data
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    logger.error(f"FMP API rate limit exceeded (429) for {endpoint}")
                    self.fmp_rate_limiter.activate_circuit_breaker()
                elif e.response.status_code in (403, 404):
                    logger.debug(f"FMP API {e.response.status_code} for {endpoint} — endpoint not available on current plan")
                else:
                    logger.error(f"FMP API HTTP error for {endpoint}: {e}")
                return None
            except Exception as e:
                logger.error(f"FMP API request failed for {endpoint}: {e}")
                return None

    
    def _fetch_from_alpha_vantage(self, symbol: str) -> Optional[FundamentalData]:
        """Fetch data from Alpha Vantage API (fallback)."""
        if not self.av_api_key:
            return None
        
        try:
            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'OVERVIEW',
                'symbol': symbol,
                'apikey': self.av_api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            overview = response.json()
            
            if 'Symbol' not in overview:
                logger.error(f"Alpha Vantage returned no data for {symbol}")
                return None
            
            # Parse data
            data = FundamentalData(
                symbol=symbol,
                timestamp=datetime.now(),
                source="AlphaVantage"
            )
            
            # Parse numeric fields safely
            def safe_float(value):
                try:
                    return float(value) if value and value != 'None' else None
                except (ValueError, TypeError):
                    return None
            
            data.eps = safe_float(overview.get('EPS'))
            data.revenue = safe_float(overview.get('RevenueTTM'))
            data.revenue_growth = safe_float(overview.get('QuarterlyRevenueGrowthYOY'))
            data.roe = safe_float(overview.get('ReturnOnEquityTTM'))
            data.pe_ratio = safe_float(overview.get('PERatio'))
            data.market_cap = safe_float(overview.get('MarketCapitalization'))
            data.dividend_yield = safe_float(overview.get('DividendYield'))
            
            logger.info(f"Fetched fundamental data for {symbol} from Alpha Vantage")
            return data
            
        except Exception as e:
            logger.error(f"Error fetching from Alpha Vantage for {symbol}: {e}")
            return None
    
    def get_api_usage(self) -> Dict[str, Any]:
        """Get API usage statistics — DB-backed for accuracy across restarts."""
        rate_stats = self.fmp_rate_limiter.get_usage()

        # DB cache coverage — the real picture
        db_cache_total = 0
        db_cache_fresh_7d = 0
        db_cache_fresh_24h = 0
        try:
            from src.models.database import get_database
            db = get_database()
            with db.get_session() as session:
                from sqlalchemy import text
                row = session.execute(text(
                    "SELECT COUNT(*) as total, "
                    "COUNT(CASE WHEN fetched_at > NOW() - INTERVAL '7 days' THEN 1 END) as fresh_7d, "
                    "COUNT(CASE WHEN fetched_at > NOW() - INTERVAL '24 hours' THEN 1 END) as fresh_24h "
                    "FROM fundamental_data_cache"
                )).fetchone()
                if row:
                    db_cache_total = row[0] or 0
                    db_cache_fresh_7d = row[1] or 0
                    db_cache_fresh_24h = row[2] or 0
        except Exception:
            db_cache_total = len(self.cache.cache)  # fallback to in-memory

        return {
            'fmp': rate_stats,
            'cache_size': db_cache_total,          # total symbols in DB cache
            'cache_fresh_7d': db_cache_fresh_7d,   # fresh within 7 days
            'cache_fresh_24h': db_cache_fresh_24h, # fresh within 24h
        }
    
    def clear_cache(self) -> None:
        """Clear the cache."""
        self.cache.clear()
        logger.info("Fundamental data cache cleared")
    
    def _get_from_database(self, symbol: str, allow_stale: bool = False) -> Optional[FundamentalData]:
        """
        Get fundamental data from database cache with smart TTL.
        
        Args:
            symbol: Stock symbol
            allow_stale: If True, return stale data even if expired (last resort)
        
        Returns:
            FundamentalData or None
        """
        from src.models.orm import FundamentalDataORM
        
        session = self.database.get_session()
        try:
            # Query for the symbol
            record = session.query(FundamentalDataORM).filter_by(symbol=symbol).first()
            
            if not record:
                return None
            
            # Get smart TTL based on earnings calendar
            cache_ttl = self._get_smart_cache_ttl(symbol)
            
            # Check if data is still fresh (within TTL)
            age = datetime.now() - record.fetched_at
            if age.total_seconds() > cache_ttl:
                if not allow_stale:
                    logger.debug(f"Database cache expired for {symbol} (age: {age.total_seconds():.0f}s, TTL: {cache_ttl}s)")
                    return None
                else:
                    logger.warning(f"Returning stale database cache for {symbol} (age: {age.total_seconds():.0f}s, TTL: {cache_ttl}s)")
            
            # Convert ORM to FundamentalData
            data = FundamentalData(
                symbol=record.symbol,
                timestamp=record.fetched_at,
                eps=record.eps,
                revenue=record.revenue,
                revenue_growth=record.revenue_growth,
                total_debt=record.total_debt,
                total_equity=record.total_equity,
                debt_to_equity=record.debt_to_equity,
                roe=record.roe,
                pe_ratio=record.pe_ratio,
                market_cap=record.market_cap,
                insider_net_buying=record.insider_net_buying,
                shares_outstanding=record.shares_outstanding,
                shares_change_percent=record.shares_change_percent,
                dividend_yield=record.dividend_yield if hasattr(record, 'dividend_yield') else None,
                earnings_surprise=record.earnings_surprise if hasattr(record, 'earnings_surprise') else None,
                source=record.source
            )
            
            if allow_stale:
                logger.info(f"Retrieved stale fundamental data for {symbol} from database (age: {age.total_seconds():.0f}s)")
            else:
                logger.info(f"Retrieved fundamental data for {symbol} from database (age: {age.total_seconds():.0f}s, TTL: {cache_ttl}s)")
            return data
            
        except Exception as e:
            logger.error(f"Error retrieving fundamental data from database for {symbol}: {e}")
            return None
        finally:
            session.close()
    
    def _get_smart_cache_ttl(self, symbol: str) -> int:
        """
        Get cache TTL based on earnings calendar.
        
        Returns:
            Cache TTL in seconds (24 hours during earnings period, 30 days otherwise)
        """
        if self.cache_strategy != 'earnings_aware':
            return self.default_cache_ttl
        
        try:
            # Check if we're in an earnings period
            if self._is_earnings_period(symbol):
                logger.debug(f"{symbol} is in earnings period - using short TTL ({self.earnings_period_ttl}s)")
                return self.earnings_period_ttl
            else:
                logger.debug(f"{symbol} is not in earnings period - using long TTL ({self.default_cache_ttl}s)")
                return self.default_cache_ttl
        except Exception as e:
            logger.warning(f"Error checking earnings period for {symbol}: {e}, using default TTL")
            return self.default_cache_ttl
    
    def _is_earnings_period(self, symbol: str) -> bool:
        """
        Check if we're in an earnings period (±7 days from earnings).
        
        Returns:
            True if within 7 days of earnings report, False otherwise
        """
        try:
            # Get cached earnings calendar
            earnings_data = self._get_earnings_calendar_cached(symbol)
            
            if not earnings_data:
                return False  # Assume not in earnings period if unknown
            
            # Check last earnings date
            last_earnings_str = earnings_data.get('last_earnings_date')
            if last_earnings_str:
                try:
                    last_earnings = datetime.strptime(last_earnings_str, '%Y-%m-%d')
                    days_since = (datetime.now() - last_earnings).days
                    
                    if 0 <= days_since <= 7:
                        logger.debug(f"{symbol}: {days_since} days since earnings - in earnings period")
                        return True
                except ValueError:
                    pass
            
            # TODO: Check next earnings date if available in API response
            # For now, we only check past earnings
            
            return False
            
        except Exception as e:
            logger.warning(f"Error checking earnings period for {symbol}: {e}")
            return False
    
    def _get_earnings_calendar_cached(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get earnings calendar with caching. Delegates to get_earnings_calendar which handles cache."""
        return self.get_earnings_calendar(symbol)
    
    def _save_to_database(self, data: FundamentalData) -> None:
        """Save fundamental data to database cache."""
        from src.models.orm import FundamentalDataORM
        
        session = self.database.get_session()
        try:
            # Check if record exists
            existing = session.query(FundamentalDataORM).filter_by(symbol=data.symbol).first()
            
            if existing:
                # Update existing record
                existing.eps = data.eps
                existing.revenue = data.revenue
                existing.revenue_growth = data.revenue_growth
                existing.total_debt = data.total_debt
                existing.total_equity = data.total_equity
                existing.debt_to_equity = data.debt_to_equity
                existing.roe = data.roe
                existing.pe_ratio = data.pe_ratio
                existing.market_cap = data.market_cap
                existing.insider_net_buying = data.insider_net_buying
                existing.shares_outstanding = data.shares_outstanding
                existing.shares_change_percent = data.shares_change_percent
                if hasattr(existing, 'dividend_yield'):
                    existing.dividend_yield = data.dividend_yield
                if hasattr(existing, 'earnings_surprise'):
                    existing.earnings_surprise = data.earnings_surprise
                existing.source = data.source
                existing.fetched_at = data.timestamp
                existing.updated_at = datetime.now()
                logger.debug(f"Updated database cache for {data.symbol}")
            else:
                # Create new record
                record = FundamentalDataORM(
                    symbol=data.symbol,
                    eps=data.eps,
                    revenue=data.revenue,
                    revenue_growth=data.revenue_growth,
                    total_debt=data.total_debt,
                    total_equity=data.total_equity,
                    debt_to_equity=data.debt_to_equity,
                    roe=data.roe,
                    pe_ratio=data.pe_ratio,
                    market_cap=data.market_cap,
                    insider_net_buying=data.insider_net_buying,
                    shares_outstanding=data.shares_outstanding,
                    shares_change_percent=data.shares_change_percent,
                    dividend_yield=data.dividend_yield,
                    earnings_surprise=data.earnings_surprise,
                    source=data.source,
                    fetched_at=data.timestamp
                )
                session.add(record)
                logger.debug(f"Saved fundamental data for {data.symbol} to database")
            
            session.commit()
            
        except Exception as e:
            logger.error(f"Error saving fundamental data to database for {data.symbol}: {e}")
            session.rollback()
        finally:
            session.close()
    
    
    def get_earnings_calendar(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get earnings calendar data for a symbol.

        Routes through _get_earnings_calendar_cached to avoid redundant API calls.
        The in-memory cache has a 7-day TTL (earnings_calendar_ttl).
        """
        # Non-fundamental symbols don't have earnings — ETFs, crypto, forex, indices, commodities
        # ETFs are included in full — none of them report individual earnings.
        # Calling FMP for ETFs returns [] which then triggers AV fallback (25 req/day limit).
        NON_FUNDAMENTAL_SYMBOLS = {
            # Crypto
            'BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'AVAX', 'DOT', 'LINK',
            'NEAR', 'LTC', 'BCH', 'DOGE', 'SHIB', 'MATIC', 'UNI',
            # Forex
            'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD', 'EURGBP',
            # Indices
            'SPX500', 'NSDQ100', 'DJ30', 'UK100', 'GER40',
            # Commodities
            'GOLD', 'SILVER', 'OIL', 'COPPER', 'NATGAS', 'PLATINUM', 'ALUMINUM', 'ZINC',
            'WEAT', 'DBA', 'UNG', 'USO', 'PALL',
            # All ETFs (none report individual earnings)
            'SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'VOO',
            'GLD', 'SLV', 'TLT', 'HYG', 'AGG',
            'XLE', 'XLF', 'XLK', 'XLU', 'XLV', 'XLI', 'XLP', 'XLY',
            'XHB', 'XBI', 'ARKK', 'ITA', 'FXI',
            'SMH', 'SOXX', 'SOXL', 'TQQQ', 'SQQQ', 'SPXU', 'UPRO',
            'EEM', 'EWZ', 'KWEB', 'FXI',
            'URA', 'COPX', 'DFEN', 'CIBR',
        }
        if symbol.upper() in NON_FUNDAMENTAL_SYMBOLS:
            return None

        # Check memory cache first (7-day TTL)
        if symbol in self.earnings_calendar_cache:
            cached_time = self.earnings_calendar_timestamps.get(symbol)
            if cached_time:
                age = (datetime.now() - cached_time).total_seconds()
                if age < self.earnings_calendar_ttl:
                    logger.debug(f"Using cached earnings calendar for {symbol} (age: {age:.0f}s)")
                    return self.earnings_calendar_cache[symbol]

        # Fetch from FMP (uses wait_for_token internally via _fmp_request)
        data = None
        if self.fmp_enabled:
            data = self._fetch_earnings_calendar_fmp(symbol)

        # Alpha Vantage fallback disabled — free tier is 25 req/day which is exhausted
        # immediately during cache warming. AV earnings data provides no value at this limit.
        # If FMP returns None (e.g., symbol not in FMP universe), just return None.
        if not data:
            logger.debug(f"No earnings calendar data available for {symbol} from FMP")

        if data:
            # Cache the result
            self.earnings_calendar_cache[symbol] = data
            self.earnings_calendar_timestamps[symbol] = datetime.now()

        return data
    
    def _fetch_earnings_calendar_fmp(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch earnings calendar from FMP stable API."""
        try:
            # Use the stable API earnings endpoint (not the legacy /historical/earning_calendar/)
            historical = self._fmp_request("/earnings", symbol=symbol)

            if not historical or not isinstance(historical, list):
                return None

            # Sort by date (most recent first)
            historical.sort(key=lambda x: x.get('date', ''), reverse=True)

            # Get the most recent earnings with actual data
            recent = None
            next_earnings = None

            for entry in historical:
                entry_date = entry.get('date', '')
                if not entry_date:
                    continue

                try:
                    from datetime import datetime as dt
                    earnings_dt = dt.strptime(entry_date, '%Y-%m-%d')

                    if earnings_dt > dt.now():
                        # Future earnings date
                        if next_earnings is None or earnings_dt < dt.strptime(next_earnings.get('date', '9999-12-31'), '%Y-%m-%d'):
                            next_earnings = entry
                    elif entry.get('epsActual') is not None:
                        # Most recent past earnings with actual data
                        if recent is None:
                            recent = entry
                except (ValueError, TypeError):
                    continue

            if not recent and not next_earnings:
                return None

            # Use recent past earnings for data, but include next earnings date
            source_entry = recent or next_earnings

            actual_eps = source_entry.get('epsActual')
            estimated_eps = source_entry.get('epsEstimated')
            surprise_pct = None

            if actual_eps is not None and estimated_eps is not None and estimated_eps != 0:
                surprise_pct = (actual_eps - estimated_eps) / abs(estimated_eps)

            result = {
                'symbol': symbol,
                'last_earnings_date': recent.get('date') if recent else None,
                'next_earnings_date': next_earnings.get('date') if next_earnings else None,
                'actual_eps': actual_eps,
                'estimated_eps': estimated_eps,
                'surprise_pct': surprise_pct,
                'revenue': source_entry.get('revenueActual'),
                'estimated_revenue': source_entry.get('revenueEstimated'),
                'fiscal_period': source_entry.get('fiscalDateEnding'),
                'source': 'FMP'
            }

            return result

        except Exception as e:
            logger.error(f"Error fetching earnings calendar from FMP for {symbol}: {e}")
            return None
    
    def _fetch_earnings_calendar_av(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch earnings calendar from Alpha Vantage."""
        try:
            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'EARNINGS',
                'symbol': symbol,
                'apikey': self.av_api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'quarterlyEarnings' not in data or len(data['quarterlyEarnings']) == 0:
                return None
            
            # Get most recent earnings
            recent = data['quarterlyEarnings'][0]
            
            # Parse earnings surprise
            def safe_float(value):
                try:
                    return float(value) if value and value != 'None' else None
                except (ValueError, TypeError):
                    return None
            
            actual_eps = safe_float(recent.get('reportedEPS'))
            estimated_eps = safe_float(recent.get('estimatedEPS'))
            surprise_pct = None
            
            if actual_eps is not None and estimated_eps is not None and estimated_eps != 0:
                surprise_pct = (actual_eps - estimated_eps) / abs(estimated_eps)
            
            return {
                'symbol': symbol,
                'last_earnings_date': recent.get('reportedDate'),
                'actual_eps': actual_eps,
                'estimated_eps': estimated_eps,
                'surprise_pct': surprise_pct,
                'surprise': safe_float(recent.get('surprise')),
                'surprise_percentage': safe_float(recent.get('surprisePercentage')),
                'fiscal_period': recent.get('fiscalDateEnding'),
                'source': 'AlphaVantage'
            }
            
        except Exception as e:
            logger.error(f"Error fetching earnings calendar from Alpha Vantage for {symbol}: {e}")
            return None
    
    def calculate_earnings_surprise(self, symbol: str) -> Optional[float]:
        """
        Calculate earnings surprise percentage for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Earnings surprise as a percentage (e.g., 0.05 for 5% beat), or None
        """
        earnings_data = self.get_earnings_calendar(symbol)
        if earnings_data:
            return earnings_data.get('surprise_pct')
        return None
    
    def get_days_since_earnings(self, symbol: str) -> Optional[int]:
        """
        Get number of days since last earnings announcement.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Number of days since earnings, or None if unavailable
        """
        earnings_data = self.get_earnings_calendar(symbol)
        if earnings_data and earnings_data.get('last_earnings_date'):
            try:
                earnings_date = datetime.strptime(earnings_data['last_earnings_date'], '%Y-%m-%d')
                days_since = (datetime.now() - earnings_date).days
                return days_since
            except Exception as e:
                logger.error(f"Error parsing earnings date for {symbol}: {e}")
        return None
    
    def store_earnings_history(self, earnings_data: Dict[str, Any], db_session) -> None:
        """
        Store earnings data in the database.
        
        Args:
            earnings_data: Earnings data dictionary from get_earnings_calendar
            db_session: SQLAlchemy database session
        """
        from src.models.orm import EarningsHistoryORM
        
        try:
            # Parse earnings date
            earnings_date_str = earnings_data.get('last_earnings_date')
            if not earnings_date_str:
                logger.warning(f"No earnings date in data for {earnings_data.get('symbol')}")
                return
            
            earnings_date = datetime.strptime(earnings_date_str, '%Y-%m-%d')
            
            # Check if this earnings record already exists
            existing = db_session.query(EarningsHistoryORM).filter_by(
                symbol=earnings_data['symbol'],
                earnings_date=earnings_date
            ).first()
            
            if existing:
                logger.debug(f"Earnings record already exists for {earnings_data['symbol']} on {earnings_date_str}")
                return
            
            # Calculate revenue surprise if available
            revenue_surprise_pct = None
            if earnings_data.get('revenue') and earnings_data.get('estimated_revenue'):
                revenue = earnings_data['revenue']
                estimated = earnings_data['estimated_revenue']
                if estimated != 0:
                    revenue_surprise_pct = (revenue - estimated) / abs(estimated)
            
            # Create new record
            earnings_record = EarningsHistoryORM(
                symbol=earnings_data['symbol'],
                earnings_date=earnings_date,
                fiscal_period=earnings_data.get('fiscal_period'),
                actual_eps=earnings_data.get('actual_eps'),
                estimated_eps=earnings_data.get('estimated_eps'),
                surprise_pct=earnings_data.get('surprise_pct'),
                revenue=earnings_data.get('revenue'),
                estimated_revenue=earnings_data.get('estimated_revenue'),
                revenue_surprise_pct=revenue_surprise_pct,
                source=earnings_data.get('source', 'unknown'),
                created_at=datetime.now()
            )
            
            db_session.add(earnings_record)
            db_session.commit()
            logger.info(f"Stored earnings history for {earnings_data['symbol']} on {earnings_date_str}")
            
        except Exception as e:
            logger.error(f"Error storing earnings history: {e}")
            db_session.rollback()

    def get_revenue_growth(self, symbol: str) -> Optional[float]:
        """
        Get the most recent revenue growth for a symbol.

        Uses cached fundamental data (no extra API call).

        Args:
            symbol: Stock symbol

        Returns:
            Revenue growth as a decimal (e.g., 0.10 for 10%), or None if unavailable
        """
        try:
            data = self.get_fundamental_data(symbol, use_cache=True)
            if data and data.revenue_growth is not None:
                return data.revenue_growth
        except Exception as e:
            logger.error(f"Error getting revenue growth for {symbol}: {e}")
        return None

    
    def get_historical_fundamentals(self, symbol: str, quarters: int = 8) -> List[Dict[str, Any]]:
        """
        Fetch historical quarterly fundamental data from FMP for backtesting.

        Uses /stable/ API endpoints available on the Starter plan:
        - /stable/income-statement (quarterly) — revenue, EPS
        - /stable/analyst-estimates — consensus EPS estimates for real earnings surprise
        - /stable/key-metrics (annual + quarterly) — ROE, P/E, dividend yield, D/E
        - /stable/ratios (annual) — P/E, D/E, dividend yield

        Earnings surprise is computed from analyst estimates vs actual EPS.
        Falls back to sequential EPS change when analyst estimates unavailable.
        Quarterly key-metrics preferred over annual when available.
        """
        from src.core.tradeable_instruments import (
            DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX,
            DEMO_ALLOWED_INDICES, DEMO_ALLOWED_COMMODITIES,
            DEMO_ALLOWED_ETFS,
        )
        sym = symbol.upper()
        non_equity = set(DEMO_ALLOWED_CRYPTO + DEMO_ALLOWED_FOREX + DEMO_ALLOWED_INDICES + DEMO_ALLOWED_COMMODITIES + DEMO_ALLOWED_ETFS)
        if sym in non_equity:
            return []

        # FMP starter plan only covers US-listed securities.
        # Skip non-US exchange symbols (contain '.') to avoid 402 errors.
        if '.' in sym:
            logger.debug(f"Skipping FMP fundamentals for non-US symbol {sym}")
            return []

        cached = self._get_quarterly_from_db(symbol, quarters)
        if cached and len(cached) >= max(quarters - 2, 3):
            logger.info(f"Using {len(cached)} cached quarterly fundamentals for {symbol}")
            return cached

        if not self.fmp_enabled or not self.fmp_rate_limiter.can_make_call():
            logger.warning(f"FMP unavailable for historical fundamentals of {symbol}")
            return cached or []

        try:
            # Parallelize FMP API calls — 5 independent endpoints fired concurrently
            # This cuts per-symbol fetch time from ~5s to ~1.5s
            from concurrent.futures import ThreadPoolExecutor, as_completed

            futures = {}
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures['income'] = executor.submit(
                    self._fmp_request, "/income-statement", symbol=symbol, period="quarter", limit=quarters
                )
                if not getattr(self, '_analyst_estimates_unavailable', False):
                    futures['estimates'] = executor.submit(
                        self._fmp_request, "/analyst-estimates", symbol=symbol, period="annual", limit=5
                    )
                futures['annual_metrics'] = executor.submit(
                    self._fmp_request, "/key-metrics", symbol=symbol, period="annual", limit=5
                )
                futures['annual_ratios'] = executor.submit(
                    self._fmp_request, "/ratios", symbol=symbol, period="annual", limit=5
                )
                futures['cashflow'] = executor.submit(
                    self._fmp_request, "/cash-flow-statement", symbol=symbol, period="quarter", limit=quarters
                )
                futures['balance'] = executor.submit(
                    self._fmp_request, "/balance-sheet-statement", symbol=symbol, period="quarter", limit=quarters
                )

            income_stmts = futures['income'].result()
            self.fmp_rate_limiter.record_call()

            analyst_estimates = futures.get('estimates', None)
            if analyst_estimates is not None:
                analyst_estimates = analyst_estimates.result()
                if analyst_estimates:
                    self.fmp_rate_limiter.record_call()
                elif analyst_estimates is None:
                    self._analyst_estimates_unavailable = True
                    logger.info("FMP /analyst-estimates not available on current plan — using sequential EPS fallback")
            else:
                analyst_estimates = None

            # Quarterly key-metrics: period=quarter requires premium plan
            quarterly_metrics = None

            annual_metrics = futures['annual_metrics'].result()
            if annual_metrics:
                self.fmp_rate_limiter.record_call()

            annual_ratios = futures['annual_ratios'].result()
            if annual_ratios:
                self.fmp_rate_limiter.record_call()

            cashflow_stmts = futures['cashflow'].result()
            if cashflow_stmts:
                self.fmp_rate_limiter.record_call()

            balance_sheets = futures['balance'].result()
            if balance_sheets:
                self.fmp_rate_limiter.record_call()

            if not income_stmts:
                logger.warning(f"No historical income statements from FMP for {symbol}")
                return cached or []

            # Build analyst estimates lookup by fiscal year
            # Annual estimates have date as fiscal year end (e.g., 2025-09-27)
            # and epsAvg as the consensus annual EPS estimate.
            # We match to quarters by fiscal year to compute surprise = (actual_annual_eps - estimated) / |estimated|
            estimates_by_year = {}
            if analyst_estimates:
                for est in analyst_estimates:
                    est_date = est.get("date", "")
                    est_eps = est.get("epsAvg")
                    if est_date and est_eps is not None:
                        est_year = est_date[:4]
                        estimates_by_year[est_year] = est_eps
                if estimates_by_year:
                    logger.info(f"Loaded {len(estimates_by_year)} annual analyst EPS estimates for {symbol}")

            # Build quarterly key-metrics lookup by date
            quarterly_metrics_by_date = {}
            if quarterly_metrics:
                for m in quarterly_metrics:
                    qm_date = m.get("date", "")
                    if qm_date:
                        quarterly_metrics_by_date[qm_date] = m
                if quarterly_metrics_by_date:
                    logger.info(f"Loaded {len(quarterly_metrics_by_date)} quarterly key-metrics for {symbol}")

            # Build annual lookup by fiscal year — merge metrics + ratios
            annual_by_year = {}
            if annual_metrics:
                for m in annual_metrics:
                    year = m.get("fiscalYear") or (m.get("date", "")[:4] if m.get("date") else None)
                    if year:
                        annual_by_year[str(year)] = m
            if annual_ratios:
                for r in annual_ratios:
                    year = r.get("fiscalYear") or (r.get("date", "")[:4] if r.get("date") else None)
                    if year:
                        yr = str(year)
                        if yr in annual_by_year:
                            annual_by_year[yr].update(r)  # Merge ratios into metrics
                        else:
                            annual_by_year[yr] = r

            result = []
            prev_revenue = None
            prev_eps = None

            # Phase 1: Build cash flow and balance sheet lookups by date
            cashflow_by_date = {}
            if cashflow_stmts:
                for cf in reversed(cashflow_stmts) if cashflow_stmts else []:
                    cf_date = cf.get("date", "")
                    if cf_date:
                        cashflow_by_date[cf_date] = cf

            balance_by_date = {}
            if balance_sheets:
                for bs in reversed(balance_sheets) if balance_sheets else []:
                    bs_date = bs.get("date", "")
                    if bs_date:
                        balance_by_date[bs_date] = bs

            # Phase 1: Track previous quarter values for F-Score delta checks
            prev_q_roe = None
            prev_q_current_ratio = None
            prev_q_long_term_debt_ratio = None
            prev_q_gross_margin = None
            prev_q_asset_turnover = None
            prev_q_shares = None
            # Phase 1: Track earnings surprises for SUE computation
            surprise_history = []

            for stmt in reversed(income_stmts):
                date = stmt.get("date", "")
                if not date:
                    continue

                revenue = stmt.get("revenue")
                eps = stmt.get("eps") or stmt.get("epsDiluted")

                rev_growth = None
                if revenue and prev_revenue and prev_revenue > 0:
                    rev_growth = (revenue - prev_revenue) / prev_revenue
                prev_revenue = revenue

                # Compute earnings surprise from analyst estimates (preferred)
                # Annual estimates matched by fiscal year — divide annual estimate by 4 for quarterly comparison
                # or fall back to sequential EPS change
                surprise = None
                surprise_source = None
                estimated_eps_value = None

                fiscal_year = stmt.get("fiscalYear") or (date[:4] if date else None)
                annual_est = estimates_by_year.get(str(fiscal_year)) if fiscal_year else None
                # Annual estimate / 4 gives approximate quarterly expected EPS
                quarterly_est = annual_est / 4.0 if annual_est and annual_est != 0 else None

                if eps is not None and quarterly_est is not None and quarterly_est != 0:
                    surprise = (eps - quarterly_est) / abs(quarterly_est)
                    surprise_source = "analyst_estimate"
                    estimated_eps_value = quarterly_est
                elif eps is not None and prev_eps is not None and prev_eps != 0:
                    surprise = (eps - prev_eps) / abs(prev_eps)
                    surprise_source = "sequential_fallback"
                    estimated_eps_value = prev_eps
                prev_eps = eps

                annual = annual_by_year.get(str(fiscal_year), {})

                # Prefer quarterly key-metrics over annual for ROE, D/E, dividend yield
                q_metrics = quarterly_metrics_by_date.get(date, {})
                roe = q_metrics.get("returnOnEquity") or annual.get("returnOnEquity")
                debt_to_equity = q_metrics.get("debtToEquityRatio") or annual.get("debtToEquityRatio")
                dividend_yield = q_metrics.get("dividendYield") or annual.get("dividendYield")
                pe_ratio = q_metrics.get("peRatio") or annual.get("priceToEarningsRatio")
                quality_data_source = "quarterly" if q_metrics.get("returnOnEquity") else "annual_interpolated"

                # Phase 1: Extract cash flow and balance sheet data for this quarter
                cf_data = cashflow_by_date.get(date, {})
                bs_data = balance_by_date.get(date, {})

                net_income = stmt.get("netIncome")
                operating_cf = cf_data.get("operatingCashFlow")
                capex = cf_data.get("capitalExpenditure")  # Usually negative in FMP
                total_assets = bs_data.get("totalAssets")
                gross_profit_val = stmt.get("grossProfit")
                long_term_debt_val = bs_data.get("longTermDebt")
                current_assets = bs_data.get("totalCurrentAssets")
                current_liabilities = bs_data.get("totalCurrentLiabilities")
                shares_out = bs_data.get("commonStockSharesOutstanding") or bs_data.get("weightedAverageShsOut")

                # R&D and SGA for intangibles-adjusted book value
                rd_expense = stmt.get("researchAndDevelopmentExpenses") or 0
                sga_expense = stmt.get("sellingGeneralAndAdministrativeExpenses") or 0

                # Free cash flow (capex is often negative in FMP, so we add it)
                free_cash_flow = None
                if operating_cf is not None and capex is not None:
                    free_cash_flow = operating_cf + capex if capex < 0 else operating_cf - capex

                # Accruals ratio: (net_income - operating_cf) / total_assets
                accruals_ratio = None
                if net_income is not None and operating_cf is not None and total_assets and total_assets > 0:
                    accruals_ratio = (net_income - operating_cf) / total_assets

                # FCF yield: free_cash_flow / market_cap
                fcf_yield = None
                mkt_cap = q_metrics.get("marketCap") or annual.get("marketCap")
                if free_cash_flow is not None and mkt_cap and mkt_cap > 0:
                    fcf_yield = free_cash_flow / mkt_cap

                # Current ratio
                current_ratio_val = None
                if current_assets and current_liabilities and current_liabilities > 0:
                    current_ratio_val = current_assets / current_liabilities

                # Gross margin
                gross_margin_val = None
                if gross_profit_val is not None and revenue and revenue > 0:
                    gross_margin_val = gross_profit_val / revenue

                # Asset turnover
                asset_turnover_val = None
                if revenue is not None and total_assets and total_assets > 0:
                    asset_turnover_val = revenue / total_assets

                # ROA for F-Score
                roa = None
                if net_income is not None and total_assets and total_assets > 0:
                    roa = net_income / total_assets

                # Long-term debt ratio
                lt_debt_ratio = None
                if long_term_debt_val is not None and total_assets and total_assets > 0:
                    lt_debt_ratio = long_term_debt_val / total_assets

                # ---- Piotroski F-Score (9 criteria, 1 point each) ----
                f_score = 0
                if net_income is not None and net_income > 0:
                    f_score += 1  # 1. Positive net income
                if operating_cf is not None and operating_cf > 0:
                    f_score += 1  # 2. Positive operating cash flow
                if roa is not None and prev_q_roe is not None and roa > prev_q_roe:
                    f_score += 1  # 3. ROA increasing
                if operating_cf is not None and net_income is not None and operating_cf > net_income:
                    f_score += 1  # 4. Cash flow > net income (quality)
                if lt_debt_ratio is not None and prev_q_long_term_debt_ratio is not None:
                    if lt_debt_ratio < prev_q_long_term_debt_ratio:
                        f_score += 1  # 5. Decreasing LT debt ratio
                elif lt_debt_ratio is not None and lt_debt_ratio == 0:
                    f_score += 1
                if current_ratio_val is not None and prev_q_current_ratio is not None:
                    if current_ratio_val > prev_q_current_ratio:
                        f_score += 1  # 6. Increasing current ratio
                if shares_out is not None and prev_q_shares is not None:
                    if shares_out <= prev_q_shares:
                        f_score += 1  # 7. No dilution
                elif shares_out is not None and prev_q_shares is None:
                    f_score += 1
                if gross_margin_val is not None and prev_q_gross_margin is not None:
                    if gross_margin_val > prev_q_gross_margin:
                        f_score += 1  # 8. Increasing gross margin
                if asset_turnover_val is not None and prev_q_asset_turnover is not None:
                    if asset_turnover_val > prev_q_asset_turnover:
                        f_score += 1  # 9. Increasing asset turnover

                # Update previous quarter trackers
                prev_q_roe = roa
                prev_q_current_ratio = current_ratio_val
                prev_q_long_term_debt_ratio = lt_debt_ratio
                prev_q_gross_margin = gross_margin_val
                prev_q_asset_turnover = asset_turnover_val
                prev_q_shares = shares_out

                # ---- SUE (Standardized Unexpected Earnings) ----
                sue_value = None
                if surprise is not None:
                    surprise_history.append(surprise)
                    if len(surprise_history) >= 4:
                        import statistics
                        std_surprise = statistics.stdev(surprise_history)
                        if std_surprise > 0:
                            sue_value = surprise / std_surprise
                        else:
                            sue_value = surprise * 10.0 if surprise != 0 else 0.0

                result.append({
                    "date": date,
                    "eps": eps,
                    "revenue": revenue,
                    "revenue_growth": rev_growth,
                    "pe_ratio": pe_ratio,
                    "roe": roe,
                    "dividend_yield": dividend_yield,
                    "debt_to_equity": debt_to_equity,
                    "earnings_surprise": surprise,
                    "earnings_surprise_source": surprise_source,
                    "actual_eps": eps,
                    "estimated_eps": estimated_eps_value,
                    "quality_data_source": quality_data_source,
                    # Phase 1: Institutional-grade metrics
                    "net_income": net_income,
                    "total_assets": total_assets,
                    "operating_cash_flow": operating_cf,
                    "capital_expenditure": capex,
                    "free_cash_flow": free_cash_flow,
                    "accruals_ratio": accruals_ratio,
                    "fcf_yield": fcf_yield,
                    "piotroski_f_score": f_score,
                    "sue": sue_value,
                    "gross_profit": gross_profit_val,
                    "current_ratio": current_ratio_val,
                    "long_term_debt": long_term_debt_val,
                    "gross_margin": gross_margin_val,
                    "asset_turnover": asset_turnover_val,
                    "shares_outstanding": shares_out,
                    "market_cap": mkt_cap,
                    "rd_expense": rd_expense if rd_expense else None,
                    "sga_expense": sga_expense if sga_expense else None,
                    "total_stockholders_equity": bs_data.get("totalStockholdersEquity"),
                })

            self._save_quarterly_to_db(symbol, result)
            analyst_count = sum(1 for q in result if q.get("earnings_surprise_source") == "analyst_estimate")
            quarterly_count = sum(1 for q in result if q.get("quality_data_source") == "quarterly")
            logger.info(
                f"Fetched {len(result)} quarters of fundamentals for {symbol} from FMP "
                f"({analyst_count} with analyst estimates, {quarterly_count} with quarterly metrics)"
            )
            return result

        except Exception as e:
            logger.error(f"Error fetching historical fundamentals for {symbol}: {e}")
            return cached or []

    def _get_quarterly_from_db(self, symbol: str, quarters: int) -> List[Dict[str, Any]]:
        """Load cached quarterly fundamentals from DB."""
        try:
            from src.models.orm import QuarterlyFundamentalsORM
            session = self.database.get_session()
            try:
                rows = session.query(QuarterlyFundamentalsORM).filter(
                    QuarterlyFundamentalsORM.symbol == symbol
                ).order_by(QuarterlyFundamentalsORM.quarter_date.asc()).limit(quarters).all()

                if not rows:
                    return []

                # Check freshness — if newest fetch is >7 days old, refetch
                # Use MAX (newest) not MIN (oldest) — old quarters may have stale timestamps
                # but if we fetched recently, the data is current
                newest_fetch = max(r.fetched_at for r in rows)
                if (datetime.now() - newest_fetch).days > 7:
                    return []

                return [{
                    "date": r.quarter_date,
                    "eps": r.eps,
                    "revenue": r.revenue,
                    "revenue_growth": r.revenue_growth,
                    "pe_ratio": r.pe_ratio,
                    "roe": r.roe,
                    "dividend_yield": r.dividend_yield,
                    "debt_to_equity": r.debt_to_equity,
                    "earnings_surprise": r.earnings_surprise,
                    "actual_eps": r.actual_eps,
                    "estimated_eps": r.estimated_eps,
                    "earnings_surprise_source": getattr(r, 'earnings_surprise_source', None),
                    "quality_data_source": getattr(r, 'quality_data_source', None),
                    # Phase 1: New metrics
                    "net_income": getattr(r, 'net_income', None),
                    "total_assets": getattr(r, 'total_assets', None),
                    "operating_cash_flow": getattr(r, 'operating_cash_flow', None),
                    "capital_expenditure": getattr(r, 'capital_expenditure', None),
                    "free_cash_flow": getattr(r, 'free_cash_flow', None),
                    "accruals_ratio": getattr(r, 'accruals_ratio', None),
                    "fcf_yield": getattr(r, 'fcf_yield', None),
                    "piotroski_f_score": getattr(r, 'piotroski_f_score', None),
                    "sue": getattr(r, 'sue', None),
                    "gross_profit": getattr(r, 'gross_profit', None),
                    "current_ratio": getattr(r, 'current_ratio', None),
                    "long_term_debt": getattr(r, 'long_term_debt', None),
                    "gross_margin": getattr(r, 'gross_margin', None),
                    "asset_turnover": getattr(r, 'asset_turnover', None),
                    "shares_outstanding": getattr(r, 'shares_outstanding', None),
                    "market_cap": getattr(r, 'market_cap', None),
                } for r in rows]
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"Could not load quarterly cache for {symbol}: {e}")
            return []

    def _save_quarterly_to_db(self, symbol: str, quarters: List[Dict[str, Any]]) -> None:
        """Persist quarterly fundamentals to DB cache.
        
        Compares incoming data against existing rows to detect revisions
        (restatements). If key metrics changed, logs a warning so we know
        the historical data shifted.
        """
        try:
            from src.models.orm import QuarterlyFundamentalsORM
            session = self.database.get_session()
            try:
                now = datetime.now()
                
                # Update fetched_at on ALL existing rows for this symbol
                # so the freshness check sees a recent timestamp
                session.query(QuarterlyFundamentalsORM).filter_by(
                    symbol=symbol
                ).update({"fetched_at": now}, synchronize_session=False)
                
                for q in quarters:
                    date = q.get("date", "")
                    if not date:
                        continue
                    existing = session.query(QuarterlyFundamentalsORM).filter_by(
                        symbol=symbol, quarter_date=date
                    ).first()
                    if existing:
                        # Detect data revisions (restatements) on key metrics.
                        # Use market-cap-tiered thresholds: small-caps have more
                        # volatile fundamentals, so a 3% EPS revision on a $1B company
                        # is more material than 3% on a $500B company. A PM at a
                        # systematic fund would flag restatements at different
                        # sensitivity levels based on company size.
                        revision_fields = ['eps', 'revenue', 'roe', 'piotroski_f_score']
                        
                        # Determine market-cap tier for revision threshold
                        market_cap = getattr(existing, 'market_cap', None)
                        if market_cap and market_cap > 10_000_000_000:  # >$10B = large-cap
                            revision_threshold = 0.05  # 5%
                        elif market_cap and market_cap > 2_000_000_000:  # $2B-$10B = mid-cap
                            revision_threshold = 0.03  # 3%
                        else:
                            # <$2B = small-cap, or market_cap unknown → use 5% default
                            # (unknown market cap = can't be more sensitive, risk false positives)
                            revision_threshold = 0.05
                        
                        for field in revision_fields:
                            old_val = getattr(existing, field, None)
                            new_val = q.get(field)
                            if old_val is not None and new_val is not None and old_val != 0:
                                change_pct = abs(new_val - old_val) / abs(old_val) if old_val != 0 else 0
                                if change_pct > revision_threshold:
                                    logger.warning(
                                        f"Data revision detected for {symbol} {date}: "
                                        f"{field} changed from {old_val} to {new_val} ({change_pct:.1%}) "
                                        f"[threshold: {revision_threshold:.0%}, "
                                        f"mcap: {'large' if market_cap and market_cap > 10e9 else 'mid' if market_cap and market_cap > 2e9 else 'small/unknown'}]"
                                    )
                        
                        existing.eps = q.get("eps")
                        existing.revenue = q.get("revenue")
                        existing.revenue_growth = q.get("revenue_growth")
                        existing.pe_ratio = q.get("pe_ratio")
                        existing.roe = q.get("roe")
                        existing.debt_to_equity = q.get("debt_to_equity")
                        existing.dividend_yield = q.get("dividend_yield")
                        existing.earnings_surprise = q.get("earnings_surprise")
                        existing.actual_eps = q.get("actual_eps")
                        existing.estimated_eps = q.get("estimated_eps")
                        existing.earnings_surprise_source = q.get("earnings_surprise_source")
                        existing.quality_data_source = q.get("quality_data_source")
                        # Phase 1: New metrics
                        existing.net_income = q.get("net_income")
                        existing.total_assets = q.get("total_assets")
                        existing.operating_cash_flow = q.get("operating_cash_flow")
                        existing.capital_expenditure = q.get("capital_expenditure")
                        existing.free_cash_flow = q.get("free_cash_flow")
                        existing.accruals_ratio = q.get("accruals_ratio")
                        existing.fcf_yield = q.get("fcf_yield")
                        existing.piotroski_f_score = q.get("piotroski_f_score")
                        existing.sue = q.get("sue")
                        existing.gross_profit = q.get("gross_profit")
                        existing.current_ratio = q.get("current_ratio")
                        existing.long_term_debt = q.get("long_term_debt")
                        existing.gross_margin = q.get("gross_margin")
                        existing.asset_turnover = q.get("asset_turnover")
                        existing.shares_outstanding = q.get("shares_outstanding")
                        existing.market_cap = q.get("market_cap")
                        existing.fetched_at = now
                    else:
                        session.add(QuarterlyFundamentalsORM(
                            symbol=symbol,
                            quarter_date=date,
                            eps=q.get("eps"),
                            revenue=q.get("revenue"),
                            revenue_growth=q.get("revenue_growth"),
                            pe_ratio=q.get("pe_ratio"),
                            roe=q.get("roe"),
                            debt_to_equity=q.get("debt_to_equity"),
                            dividend_yield=q.get("dividend_yield"),
                            earnings_surprise=q.get("earnings_surprise"),
                            actual_eps=q.get("actual_eps"),
                            estimated_eps=q.get("estimated_eps"),
                            earnings_surprise_source=q.get("earnings_surprise_source"),
                            quality_data_source=q.get("quality_data_source"),
                            # Phase 1: New metrics
                            net_income=q.get("net_income"),
                            total_assets=q.get("total_assets"),
                            operating_cash_flow=q.get("operating_cash_flow"),
                            capital_expenditure=q.get("capital_expenditure"),
                            free_cash_flow=q.get("free_cash_flow"),
                            accruals_ratio=q.get("accruals_ratio"),
                            fcf_yield=q.get("fcf_yield"),
                            piotroski_f_score=q.get("piotroski_f_score"),
                            sue=q.get("sue"),
                            gross_profit=q.get("gross_profit"),
                            current_ratio=q.get("current_ratio"),
                            long_term_debt=q.get("long_term_debt"),
                            gross_margin=q.get("gross_margin"),
                            asset_turnover=q.get("asset_turnover"),
                            shares_outstanding=q.get("shares_outstanding"),
                            market_cap=q.get("market_cap"),
                            fetched_at=now,
                        ))
                session.commit()
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"Could not save quarterly cache for {symbol}: {e}")

    def get_insider_trading(self, symbol: str, months: int = 6) -> List[Dict[str, Any]]:
        """
        Fetch insider trading data from FMP API.

        NOTE: /stable/search-insider-trades returns 404 and /api/v4/insider-trading
        returns 403 on the current FMP plan. This method returns [] silently.
        404/403 responses are logged at DEBUG level only to avoid log spam.

        Args:
            symbol: Stock ticker symbol
            months: Number of months of data to request (controls limit param)

        Returns:
            List of dicts with keys: date, transaction_type, shares, price, name, title
        """
        if not self.fmp_api_key:
            return []

        # Skip non-equity symbols — no insider data for ETFs, crypto, forex, indices
        from src.core.tradeable_instruments import (
            DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX,
            DEMO_ALLOWED_COMMODITIES, DEMO_ALLOWED_INDICES,
        )
        if symbol in set(DEMO_ALLOWED_CRYPTO) | set(DEMO_ALLOWED_FOREX) | set(DEMO_ALLOWED_COMMODITIES) | set(DEMO_ALLOWED_INDICES):
            return []

        limit = months * 10  # ~10 transactions per month is generous
        try:
            data = self._fmp_request(
                "/search-insider-trades",
                params={"symbol": symbol, "limit": limit},
            )
            if not data or not isinstance(data, list):
                return []

            results = []
            for item in data:
                tx_type_raw = (item.get("transactionType") or item.get("transaction_type") or "").lower()
                # Normalize: P = Purchase (buy), S = Sale (sell)
                if tx_type_raw in ("p", "purchase", "buy"):
                    tx_type = "buy"
                elif tx_type_raw in ("s", "sale", "sell"):
                    tx_type = "sell"
                else:
                    tx_type = tx_type_raw

                results.append({
                    "date": item.get("transactionDate") or item.get("date") or "",
                    "transaction_type": tx_type,
                    "shares": abs(item.get("securitiesTransacted") or item.get("shares") or 0),
                    "price": item.get("price") or 0,
                    "name": item.get("reportingName") or item.get("name") or "",
                    "title": item.get("typeOfOwner") or item.get("title") or "",
                })
            return results

        except Exception as e:
            logger.debug(f"Insider trading fetch failed for {symbol}: {e}")
            return []


    def get_insider_net_purchases(self, symbol: str, lookback_days: int = 90) -> Dict[str, Any]:
        """
        Aggregate net insider purchases over a lookback window.

        Args:
            symbol: Stock ticker symbol
            lookback_days: Number of days to look back (default 90)

        Returns:
            Dict with net_shares, net_value, buy_count, sell_count, last_buy_date
        """
        transactions = self.get_insider_trading(symbol)

        cutoff = datetime.now() - timedelta(days=lookback_days)
        buy_shares = 0
        sell_shares = 0
        buy_value = 0.0
        sell_value = 0.0
        buy_count = 0
        sell_count = 0
        last_buy_date = None

        for txn in transactions:
            txn_date_str = txn.get("date", "")
            if not txn_date_str:
                continue
            try:
                txn_date = datetime.strptime(txn_date_str, "%Y-%m-%d")
            except (ValueError, TypeError):
                continue

            if txn_date < cutoff:
                continue

            shares = txn.get("shares", 0) or 0
            price = txn.get("price", 0) or 0
            tx_type = txn.get("transaction_type", "")

            if tx_type == "buy":
                buy_shares += shares
                buy_value += shares * price
                buy_count += 1
                if last_buy_date is None or txn_date_str > last_buy_date:
                    last_buy_date = txn_date_str
            elif tx_type == "sell":
                sell_shares += shares
                sell_value += shares * price
                sell_count += 1

        return {
            "net_shares": buy_shares - sell_shares,
            "net_value": buy_value - sell_value,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "last_buy_date": last_buy_date,
        }

    # Standard sector ETFs for rotation strategies
    SECTOR_ETFS = {
        'XLE': 'Energy',
        'XLF': 'Financials',
        'XLK': 'Technology',
        'XLU': 'Utilities',
        'XLV': 'Healthcare',
        'XLI': 'Industrials',
        'XLP': 'Consumer Staples',
        'XLY': 'Consumer Discretionary',
    }

    def get_sector_performance(self) -> Dict[str, Dict[str, float]]:
        """
        Fetch sector performance from FMP /stock-price-change endpoint for sector ETFs.

        Returns:
            Dict mapping sector ETF symbol to {1m, 3m, 6m, 1y} percentage returns.
            Example: {'XLK': {'1m': 0.05, '3m': 0.12, '6m': 0.18, '1y': 0.25}}
        """
        # Check cache (24h TTL)
        if self._sector_perf_cache is not None and self._sector_perf_cache_ts is not None:
            age = (datetime.now() - self._sector_perf_cache_ts).total_seconds()
            if age < 86400:
                return self._sector_perf_cache

        result: Dict[str, Dict[str, float]] = {}

        if self.fmp_enabled and self.fmp_rate_limiter.can_make_call() and not getattr(self, '_stock_price_change_unavailable', False):
            try:
                first_attempt = True
                for etf in self.SECTOR_ETFS:
                    if not self.fmp_rate_limiter.can_make_call():
                        break
                    raw = self._fmp_request("/stock-price-change", symbol=etf)
                    if raw is None and first_attempt:
                        # Endpoint not available on current plan
                        self._stock_price_change_unavailable = True
                        logger.info("FMP /stock-price-change not available on current plan — using ETF price fallback")
                        break
                    first_attempt = False
                    if raw is not None:
                        self.fmp_rate_limiter.record_call()
                    if raw and isinstance(raw, list) and len(raw) > 0:
                        data = raw[0]
                        result[etf] = {
                            '1m': data.get('1M', 0) / 100.0 if data.get('1M') is not None else 0.0,
                            '3m': data.get('3M', 0) / 100.0 if data.get('3M') is not None else 0.0,
                            '6m': data.get('6M', 0) / 100.0 if data.get('6M') is not None else 0.0,
                            '1y': data.get('1Y', 0) / 100.0 if data.get('1Y') is not None else 0.0,
                        }
                if result:
                    logger.info(f"Fetched sector performance for {len(result)} ETFs from FMP")
                    self._sector_perf_cache = result
                    self._sector_perf_cache_ts = datetime.now()
                    return result
            except Exception as e:
                logger.warning(f"Error fetching sector performance from FMP: {e}")

        # Fallback: compute sector returns from sector ETF prices via MarketDataManager
        result = self._compute_sector_returns_from_prices()
        if result:
            self._sector_perf_cache = result
            self._sector_perf_cache_ts = datetime.now()
        return result

    def _compute_sector_returns_from_prices(self) -> Dict[str, Dict[str, float]]:
        """Fallback: compute sector returns from ETF price history using MarketDataManager."""
        result: Dict[str, Dict[str, float]] = {}
        try:
            # Try to get MarketDataManager from config or import
            from src.data.market_data import MarketDataManager
            mdm = None
            # Check if we have a reference to market data manager
            if hasattr(self, '_market_data_manager') and self._market_data_manager:
                mdm = self._market_data_manager
            else:
                # Try to create one from config
                try:
                    mdm = MarketDataManager(self.config)
                    self._market_data_manager = mdm
                except Exception:
                    pass

            if not mdm:
                logger.warning("No MarketDataManager available for sector ETF price fallback")
                return result

            now = datetime.now()
            start = now - timedelta(days=400)  # ~1 year + buffer

            for etf in self.SECTOR_ETFS:
                try:
                    data = mdm.get_historical_data(symbol=etf, start=start, end=now)
                    if not data or len(data) < 30:
                        continue
                    prices = [d.close for d in data if d.close]
                    if len(prices) < 30:
                        continue
                    current = prices[-1]
                    returns: Dict[str, float] = {}
                    for label, days in [('1m', 21), ('3m', 63), ('6m', 126), ('1y', 252)]:
                        if len(prices) > days:
                            past = prices[-(days + 1)]
                            returns[label] = (current - past) / past if past > 0 else 0.0
                        else:
                            returns[label] = 0.0
                    result[etf] = returns
                except Exception as e:
                    logger.debug(f"Could not compute returns for {etf}: {e}")

            if result:
                logger.info(f"Computed sector returns from ETF prices for {len(result)} sectors (fallback)")
        except Exception as e:
            logger.warning(f"Error computing sector returns from prices: {e}")
        return result

    def get_institutional_ownership(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch institutional ownership data from FMP /institutional-ownership endpoint.

        Returns ownership percentage and quarter-over-quarter change.
        Cached for 24 hours.

        Args:
            symbol: Stock symbol

        Returns:
            Dict with ownership_pct, change_pct, top_holders_count, or None
        """
        # Check cache
        cache_key = f"inst_own_{symbol}"
        if hasattr(self, '_inst_own_cache'):
            cached = self._inst_own_cache.get(cache_key)
            if cached and (datetime.now() - cached['ts']).total_seconds() < 86400:
                return cached['data']
        else:
            self._inst_own_cache = {}

        if not self.fmp_enabled or not self.fmp_rate_limiter.can_make_call():
            return None

        try:
            data = self._fmp_request("/institutional-ownership/symbol-ownership", symbol=symbol)

            if not data or not isinstance(data, list) or len(data) == 0:
                result = {"ownership_pct": None, "change_pct": None, "top_holders_count": 0}
                self._inst_own_cache[cache_key] = {'data': result, 'ts': datetime.now()}
                return result

            # Get the most recent filing
            latest = data[0]
            ownership_pct = latest.get("ownershipPercent")
            change_pct = latest.get("changeInOwnershipPercent")

            result = {
                "ownership_pct": ownership_pct,
                "change_pct": change_pct,
                "top_holders_count": len(data),
                "date": latest.get("date"),
            }
            self._inst_own_cache[cache_key] = {'data': result, 'ts': datetime.now()}
            return result

        except Exception as e:
            logger.debug(f"Could not fetch institutional ownership for {symbol}: {e}")
            return None

    def get_price_target_consensus(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch analyst price target consensus from FMP.

        Returns consensus target, current price, and upside percentage.
        Cached for 24 hours.
        """
        cache_key = f"pt_{symbol}"
        if hasattr(self, '_pt_cache'):
            cached = self._pt_cache.get(cache_key)
            if cached and (datetime.now() - cached['ts']).total_seconds() < 86400:
                return cached['data']
        else:
            self._pt_cache = {}

        if not self.fmp_enabled or not self.fmp_rate_limiter.can_make_call():
            return None

        try:
            data = self._fmp_request("/price-target-consensus", symbol=symbol)

            if not data or not isinstance(data, list) or len(data) == 0:
                self._pt_cache[cache_key] = {'data': None, 'ts': datetime.now()}
                return None

            latest = data[0]
            target_consensus = latest.get("targetConsensus")
            target_high = latest.get("targetHigh")
            target_low = latest.get("targetLow")
            target_median = latest.get("targetMedian")

            # Get current price for upside calculation
            current_price = None
            try:
                profile = self._fmp_request("/profile", symbol=symbol)
                if profile and len(profile) > 0:
                    current_price = profile[0].get("price")
            except Exception:
                pass

            upside_pct = None
            if target_consensus and current_price and current_price > 0:
                upside_pct = (target_consensus - current_price) / current_price

            result = {
                "target_consensus": target_consensus,
                "target_high": target_high,
                "target_low": target_low,
                "target_median": target_median,
                "current_price": current_price,
                "upside_pct": upside_pct,
            }
            self._pt_cache[cache_key] = {'data': result, 'ts': datetime.now()}
            return result

        except Exception as e:
            logger.debug(f"Could not fetch price target consensus for {symbol}: {e}")
            return None

    def get_upgrades_downgrades(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch recent analyst upgrades/downgrades from FMP.

        Returns list of recent rating changes. Cached for 24 hours.
        """
        cache_key = f"upgrades_{symbol}"
        if hasattr(self, '_upgrades_cache'):
            cached = self._upgrades_cache.get(cache_key)
            if cached and (datetime.now() - cached['ts']).total_seconds() < 86400:
                return cached['data']
        else:
            self._upgrades_cache = {}

        if not self.fmp_enabled or not self.fmp_rate_limiter.can_make_call():
            return []

        try:
            data = self._fmp_request("/upgrades-downgrades-consensus", symbol=symbol)

            if not data or not isinstance(data, list):
                self._upgrades_cache[cache_key] = {'data': [], 'ts': datetime.now()}
                return []

            result = data[:limit]
            self._upgrades_cache[cache_key] = {'data': result, 'ts': datetime.now()}
            return result

        except Exception as e:
            logger.debug(f"Could not fetch upgrades/downgrades for {symbol}: {e}")
            return []


def get_fundamental_data_provider(config: Optional[Dict] = None) -> 'FundamentalDataProvider':
    """
    Get or create the shared FundamentalDataProvider singleton.

    This is the ONLY correct way to get a FundamentalDataProvider. Direct
    instantiation creates a separate rate limiter and memory cache, causing
    redundant API calls and blowing the FMP rate limit.

    Args:
        config: Optional config dict. Only used on first call (initialization).
                Subsequent calls return the existing instance regardless of config.

    Returns:
        The shared FundamentalDataProvider instance.
    """
    global _singleton_instance
    if _singleton_instance is not None:
        return _singleton_instance

    with _singleton_lock:
        # Double-checked locking: re-check inside the lock
        if _singleton_instance is not None:
            return _singleton_instance
        instance = FundamentalDataProvider(config)
        _singleton_instance = instance
        return instance
