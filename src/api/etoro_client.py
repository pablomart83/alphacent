"""eToro API client with authentication, rate limiting, and circuit breaker."""

import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.models import (
    AccountInfo,
    DataSource,
    MarketData,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    SmartPortfolio,
    SocialInsights,
    TradingMode,
)

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Authentication-related errors."""
    pass


class EToroAPIError(Exception):
    """eToro API errors."""
    pass


class CircuitBreakerOpen(EToroAPIError):
    """Raised when circuit breaker is open and request is rejected."""
    def __init__(self, category: str, message: str = ""):
        self.category = category
        super().__init__(message or f"Circuit breaker OPEN for '{category}' — requests rejected")


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"       # Normal operation — requests flow through
    OPEN = "open"           # Failing — requests rejected or return cached data
    HALF_OPEN = "half_open" # Testing — one probe request allowed


class CircuitBreaker:
    """Per-category circuit breaker for eToro API calls.

    States:
        CLOSED  — normal, all requests pass through
        OPEN    — after `failure_threshold` consecutive failures, reject/cache for `cooldown_seconds`
        HALF_OPEN — after cooldown, allow one test request; success → CLOSED, failure → OPEN
    """

    def __init__(
        self,
        category: str,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
    ):
        self.category = category
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds

        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures: int = 0
        self._last_failure_time: float = 0.0
        self._opened_at: float = 0.0
        self._last_state_change: float = time.time()

    # -- public API ----------------------------------------------------------

    @property
    def state(self) -> CircuitBreakerState:
        """Return the current state, auto-transitioning OPEN → HALF_OPEN after cooldown."""
        if self._state == CircuitBreakerState.OPEN:
            if time.time() - self._opened_at >= self.cooldown_seconds:
                self._transition(CircuitBreakerState.HALF_OPEN)
        return self._state

    def allow_request(self) -> bool:
        """Return True if a request should be attempted."""
        current = self.state  # triggers auto-transition
        if current == CircuitBreakerState.CLOSED:
            return True
        if current == CircuitBreakerState.HALF_OPEN:
            return True  # allow the probe request
        return False  # OPEN

    def record_success(self) -> None:
        """Record a successful API call."""
        if self._state in (CircuitBreakerState.HALF_OPEN, CircuitBreakerState.OPEN):
            logger.info(f"Circuit breaker [{self.category}]: test request succeeded — closing circuit")
        self._consecutive_failures = 0
        if self._state != CircuitBreakerState.CLOSED:
            self._transition(CircuitBreakerState.CLOSED)

    def record_failure(self) -> None:
        """Record a failed API call."""
        self._consecutive_failures += 1
        self._last_failure_time = time.time()

        if self._state == CircuitBreakerState.HALF_OPEN:
            # Probe failed — reopen
            logger.warning(
                f"Circuit breaker [{self.category}]: half-open probe failed — reopening circuit"
            )
            self._transition(CircuitBreakerState.OPEN)
        elif self._consecutive_failures >= self.failure_threshold:
            if self._state != CircuitBreakerState.OPEN:
                logger.warning(
                    f"Circuit breaker [{self.category}]: {self._consecutive_failures} consecutive failures "
                    f"— opening circuit (cooldown {self.cooldown_seconds}s)"
                )
                self._transition(CircuitBreakerState.OPEN)

    def get_state_info(self) -> Dict[str, Any]:
        """Return a serialisable snapshot of the breaker state."""
        current = self.state  # triggers auto-transition
        return {
            "category": self.category,
            "state": current.value,
            "consecutive_failures": self._consecutive_failures,
            "failure_threshold": self.failure_threshold,
            "cooldown_seconds": self.cooldown_seconds,
            "last_failure_time": datetime.fromtimestamp(self._last_failure_time).isoformat() if self._last_failure_time else None,
            "opened_at": datetime.fromtimestamp(self._opened_at).isoformat() if self._opened_at and current != CircuitBreakerState.CLOSED else None,
            "last_state_change": datetime.fromtimestamp(self._last_state_change).isoformat(),
        }

    # -- internals -----------------------------------------------------------

    def _transition(self, new_state: CircuitBreakerState) -> None:
        old = self._state
        self._state = new_state
        self._last_state_change = time.time()
        if new_state == CircuitBreakerState.OPEN:
            self._opened_at = time.time()
        logger.info(f"Circuit breaker [{self.category}]: {old.value} → {new_state.value}")


# AuthToken class removed - eToro uses header-based authentication, not token-based


class EToroAPIClient:
    """Client for eToro Public API with header-based authentication."""

    # eToro API endpoints
    BASE_URL = "https://public-api.etoro.com"  # For authenticated endpoints
    PUBLIC_URL = "https://www.etoro.com"        # For public data endpoints

    # Rate limiting: 1 request per second to avoid 429 errors
    MIN_REQUEST_INTERVAL = 1.0  # seconds

    def __init__(
        self,
        public_key: str,
        user_key: str,
        mode: TradingMode,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """Initialize eToro API client.
        
        Args:
            public_key: eToro API public key (x-api-key)
            user_key: eToro API user key (x-user-key)
            mode: Trading mode (DEMO or LIVE) - determines which keys are used
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.public_key = public_key
        self.user_key = user_key
        self.mode = mode
        self.timeout = timeout
        self.max_retries = max_retries

        # Rate limiting
        self._last_request_time = 0.0

        # Circuit breakers per endpoint category
        self._circuit_breakers: Dict[str, CircuitBreaker] = {
            "orders": CircuitBreaker("orders", failure_threshold=5, cooldown_seconds=60.0),
            "positions": CircuitBreaker("positions", failure_threshold=5, cooldown_seconds=60.0),
            "market_data": CircuitBreaker("market_data", failure_threshold=5, cooldown_seconds=60.0),
        }

        # Last-known-good caches for positions and market data (used when circuit is open)
        self._cached_positions: Optional[List[Position]] = None
        self._cached_market_data: Dict[str, MarketData] = {}

        # Setup session with retry logic
        self._session = self._create_session()

        logger.info(f"Initialized eToro API client in {mode.value} mode")

    def _create_session(self) -> requests.Session:
        """Create requests session with retry configuration.
        
        Returns:
            Configured requests session
        """
        session = requests.Session()

        # Configure retry strategy with exponential backoff
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,  # 1s, 2s, 4s, 8s...
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with API keys.
        
        eToro uses header-based authentication, not token-based.
        
        Returns:
            Headers dictionary with API keys
        """
        import uuid
        return {
            "x-request-id": str(uuid.uuid4()),
            "x-api-key": self.public_key,
            "x-user-key": self.user_key,
            "Content-Type": "application/json"
        }

    def _enforce_rate_limit(self):
        """Enforce rate limiting: 1 request per second."""
        current_time = time.time()
        time_since_last_request = current_time - self._last_request_time
        
        if time_since_last_request < self.MIN_REQUEST_INTERVAL:
            sleep_time = self.MIN_REQUEST_INTERVAL - time_since_last_request
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        self._last_request_time = time.time()

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        base_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Make authenticated API request with retry logic and rate limiting.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON request body
            base_url: Base URL to use (defaults to BASE_URL)
            
        Returns:
            Response data as dictionary
            
        Raises:
            EToroAPIError: If request fails
        """
        # Enforce rate limiting
        self._enforce_rate_limit()
        
        url = f"{base_url or self.BASE_URL}{endpoint}"
        headers = self._get_headers()

        logger.debug(f"{method} {url}")
        if params:
            logger.debug(f"Params: {params}")
        if json_data:
            logger.debug(f"Body: {json_data}")

        try:
            response = self._session.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_data,
                timeout=self.timeout
            )

            logger.debug(f"Response: {response.status_code}")

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(f"Rate limit exceeded, waiting {retry_after}s")
                time.sleep(retry_after)
                return self._make_request(method, endpoint, params, json_data, base_url)

            # Check for errors
            if response.status_code >= 400:
                error_msg = f"API request failed: {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = f"{error_msg} - {error_data.get('message', 'Unknown error')}"
                    logger.error(f"{error_msg}, Response: {error_data}")
                except (ValueError, requests.exceptions.JSONDecodeError):
                    # Non-JSON error body — fall back to raw text
                    logger.error(f"{error_msg}, Response: {response.text}")
                raise EToroAPIError(error_msg)

            # Parse response
            try:
                result = response.json()
                logger.debug(f"Response data: {result}")
                return result
            except (ValueError, requests.exceptions.JSONDecodeError):
                # Some endpoints (e.g., DELETE) return empty bodies with 2xx status.
                # This is expected; empty dict signals "success, no data".
                logger.debug("Empty / non-JSON response body — returning {}")
                return {}

        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise EToroAPIError(f"API request failed: {e}")

    def is_authenticated(self) -> bool:
        """Check if client has valid API keys.
        
        Returns:
            True if API keys are configured
        """
        return bool(self.public_key and self.user_key)

    # -- Circuit breaker helpers ---------------------------------------------

    def _get_category_for_method(self, method_name: str) -> str:
        """Map a public method name to its circuit breaker category."""
        _METHOD_CATEGORY = {
            "place_order": "orders",
            "place_order_with_retry": "orders",
            "cancel_order": "orders",
            "get_order_status": "orders",
            "get_positions": "positions",
            "update_position_stop_loss": "positions",
            "close_position": "positions",
            "get_market_data": "market_data",
            "get_historical_data": "market_data",
        }
        return _METHOD_CATEGORY.get(method_name, "")

    def _check_circuit_breaker(self, category: str) -> None:
        """Check circuit breaker before making a request.

        For 'orders' category, raises CircuitBreakerOpen (orders cannot be cached).
        For 'positions' and 'market_data', the caller handles returning cached data.

        Raises:
            CircuitBreakerOpen: if the circuit is open for the given category
        """
        cb = self._circuit_breakers.get(category)
        if cb and not cb.allow_request():
            raise CircuitBreakerOpen(category)

    def _record_success(self, category: str) -> None:
        cb = self._circuit_breakers.get(category)
        if cb:
            cb.record_success()

    def _record_failure(self, category: str) -> None:
        cb = self._circuit_breakers.get(category)
        if cb:
            cb.record_failure()

    def get_circuit_breaker_states(self) -> Dict[str, Dict[str, Any]]:
        """Return the state of all circuit breakers (for monitoring dashboard)."""
        return {name: cb.get_state_info() for name, cb in self._circuit_breakers.items()}

    def disconnect(self) -> None:
        """Disconnect from eToro API and close session."""
        logger.info("Disconnecting from eToro API")
        self._session.close()

    def get_market_data(
        self,
        symbol: str,
        instrument_id: Optional[int] = None
    ) -> MarketData:
        """Fetch real-time market data for symbol.
        
        Uses public eToro endpoint (no authentication required).
        Falls back to Yahoo Finance if eToro data is stale.
        
        Args:
            symbol: Instrument symbol (e.g., "AAPL", "BTC", "EURUSD")
            instrument_id: eToro instrument ID (if known, otherwise uses mapping)
            
        Returns:
            Market data with current price
            
        Raises:
            EToroAPIError: If request fails
        """
        logger.debug(f"Fetching market data for {symbol}")

        # Circuit breaker check — return cached market data if circuit is open
        try:
            self._check_circuit_breaker("market_data")
        except CircuitBreakerOpen:
            cached = self._cached_market_data.get(symbol)
            if cached is not None:
                logger.warning(f"Circuit breaker [market_data] OPEN — returning cached data for {symbol}")
                return cached
            raise  # No cache available, propagate

        try:
            # Get instrument ID
            if not instrument_id:
                instrument_id = self._get_instrument_id(symbol)
            
            # Enforce rate limiting
            self._enforce_rate_limit()
            
            # Get current price (public endpoint - no auth needed)
            response = self._session.get(
                f"{self.PUBLIC_URL}/sapi/trade-real/rates/{instrument_id}",
                timeout=self.timeout
            )
            
            logger.debug(f"Market data response: {response.status_code}")
            
            if response.status_code != 200:
                raise EToroAPIError(f"Failed to fetch rate: HTTP {response.status_code}")
            
            data = response.json()

            # Parse response
            rate = data.get("Rate", {})
            if not rate:
                raise EToroAPIError(f"No rate data for {symbol}")

            # Parse rate timestamp
            rate_date_str = rate.get("Date", "")
            rate_timestamp = datetime.now()
            try:
                rate_timestamp = datetime.fromisoformat(rate_date_str.replace("Z", "+00:00"))
                age_hours = (datetime.now(rate_timestamp.tzinfo) - rate_timestamp).total_seconds() / 3600
                
                if age_hours > 1:
                    # Log staleness but still use eToro price — it's the price the
                    # broker validates SL/TP against.  Yahoo Finance returns split-
                    # adjusted prices that can differ dramatically from eToro's
                    # trading price (e.g. after stock splits).
                    logger.info(f"eToro data for {symbol} is {age_hours:.1f} hours old (market likely closed), using eToro price anyway")
            except Exception as e:
                logger.warning(f"Could not parse eToro rate date: {e}")

            # Use mid-price as close
            ask = float(rate["Ask"])
            bid = float(rate["Bid"])
            mid_price = (ask + bid) / 2

            market_data = MarketData(
                symbol=symbol,
                timestamp=rate_timestamp,
                open=mid_price,  # Not available in real-time endpoint
                high=mid_price,
                low=mid_price,
                close=mid_price,
                volume=0.0,  # Not available in real-time endpoint
                source=DataSource.ETORO
            )

            logger.debug(f"Retrieved market data for {symbol}: close={market_data.close}")

            # Update cache and record success
            self._cached_market_data[symbol] = market_data
            self._record_success("market_data")
            return market_data

        except CircuitBreakerOpen:
            raise
        except Exception as e:
            self._record_failure("market_data")
            logger.error(f"Failed to fetch market data for {symbol}: {e}")
            raise EToroAPIError(f"Failed to fetch market data: {e}")
    
    def _get_yahoo_finance_data(self, symbol: str) -> MarketData:
        """Fallback to Yahoo Finance for current price.
        
        Args:
            symbol: Instrument symbol
            
        Returns:
            Market data from Yahoo Finance
            
        Raises:
            EToroAPIError: If Yahoo Finance request fails
        """
        try:
            import yfinance as yf
            from src.utils.symbol_mapper import to_yahoo_ticker
            
            yahoo_symbol = to_yahoo_ticker(symbol)
            logger.info(f"Fetching {symbol} price from Yahoo Finance as {yahoo_symbol}")
            
            ticker = yf.Ticker(yahoo_symbol)
            info = ticker.info
            
            current_price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
            
            if not current_price:
                raise ValueError(f"No price data available for {yahoo_symbol}")
            
            market_data = MarketData(
                symbol=symbol,
                timestamp=datetime.now(),
                open=current_price,
                high=current_price,
                low=current_price,
                close=current_price,
                volume=0.0,
                source=DataSource.YAHOO_FINANCE
            )
            
            logger.info(f"Retrieved {symbol} price from Yahoo Finance: ${current_price:,.2f}")
            return market_data
            
        except ImportError:
            logger.error("yfinance not installed, cannot fallback to Yahoo Finance")
            raise EToroAPIError("yfinance package required for price fallback")
        except Exception as e:
            logger.error(f"Failed to fetch Yahoo Finance data: {e}")
            raise EToroAPIError(f"Failed to fetch Yahoo Finance data: {e}")

    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        instrument_id: Optional[int] = None
    ) -> List[MarketData]:
        """Fetch historical market data for symbol.

        Falls back to Yahoo Finance for historical data since eToro API
        doesn't provide a reliable historical data endpoint.

        Args:
            symbol: Instrument symbol (e.g., "AAPL", "BTC", "EURUSD")
            start_date: Start date for historical data (defaults to 90 days ago)
            end_date: End date for historical data (defaults to today)
            instrument_id: eToro instrument ID (not used, kept for compatibility)

        Returns:
            List of MarketData objects with OHLCV data

        Raises:
            EToroAPIError: If request fails
        """
        # Set default date range to 90 days
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=90)

        logger.info(f"Fetching historical data for {symbol} from {start_date.date()} to {end_date.date()}")

        # Sprint 4 S4.0 (2026-05-02): Binance-first for crypto.
        # This is the eToro-fallback path in the market_data_manager chain
        # (Yahoo → FMP → eToro). Crypto should continue through Binance
        # even on this fallback — there's no point falling back to the
        # Yahoo branch below when Binance still works fine. Matches the
        # same early-exit in market_data_manager._fetch_historical_from_yahoo_finance.
        try:
            from src.api.binance_ohlc import (
                fetch_klines as _bn_fetch_e,
                is_supported as _bn_supported_e,
                BinanceAPIError as _BnErr_e,
            )
            # Normalise eToro wire → display for the adapter's symbol map
            _CRYPTO_WIRE_TO_DISPLAY = {
                "BTCUSD": "BTC", "ETHUSD": "ETH", "SOLUSD": "SOL",
                "AVAXUSD": "AVAX", "LINKUSD": "LINK", "DOTUSD": "DOT",
                "XRPUSD": "XRP", "ADAUSD": "ADA", "NEARUSD": "NEAR",
                "LTCUSD": "LTC", "BCHUSD": "BCH",
            }
            _bn_sym = symbol.upper().strip()
            if _bn_sym in _CRYPTO_WIRE_TO_DISPLAY:
                _bn_sym = _CRYPTO_WIRE_TO_DISPLAY[_bn_sym]
            # This fallback path has no explicit interval param — eToro
            # fallback has always been 1d. Same default here.
            if _bn_supported_e(_bn_sym, "1d"):
                try:
                    bars = _bn_fetch_e(_bn_sym, start_date, end_date, "1d")
                    if bars:
                        logger.info(
                            f"Binance (eToro-fallback path): {len(bars)} 1d bars "
                            f"for {_bn_sym}"
                        )
                        return bars
                    logger.warning(
                        f"Binance returned 0 bars for {_bn_sym} 1d; "
                        f"falling through to Yahoo"
                    )
                except _BnErr_e as be:
                    logger.info(
                        f"Binance unavailable for {_bn_sym} 1d ({be}); "
                        f"falling through to Yahoo"
                    )
        except ImportError:
            pass

        try:
            import yfinance as yf
            import pandas as pd

            # Map symbols to Yahoo Finance format using centralized mapper
            from src.utils.symbol_mapper import to_yahoo_ticker
            yahoo_symbol = to_yahoo_ticker(symbol)

            logger.debug(f"Fetching {symbol} historical data from Yahoo Finance as {yahoo_symbol}")

            # Fetch historical data.
            # Pass tz-aware UTC bounds to yfinance — naive datetimes trigger internal
            # local-tz inference that crashes on DST ambiguous hours. See
            # src/utils/yfinance_compat.py for the full rationale.
            from src.utils.yfinance_compat import to_tz_aware_utc, normalize_yf_index_to_utc_naive
            start_utc = to_tz_aware_utc(start_date)
            end_utc = to_tz_aware_utc(end_date)

            ticker = yf.Ticker(yahoo_symbol)
            hist = ticker.history(start=start_utc, end=end_utc)

            if hist.empty:
                raise ValueError(f"No historical data available for {yahoo_symbol}")

            # Normalise index to UTC-naive before iterating. Belt-and-braces
            # on top of the tz-aware input above — output can still be tz-aware.
            hist = normalize_yf_index_to_utc_naive(hist)

            # Convert to list of MarketData objects
            market_data_list = []
            for timestamp, row in hist.iterrows():
                market_data = MarketData(
                    symbol=symbol,
                    timestamp=timestamp.to_pydatetime(),
                    open=float(row['Open']),
                    high=float(row['High']),
                    low=float(row['Low']),
                    close=float(row['Close']),
                    volume=float(row['Volume']),
                    source=DataSource.YAHOO_FINANCE
                )
                market_data_list.append(market_data)

            logger.info(f"Retrieved {len(market_data_list)} days of historical data for {symbol}")
            return market_data_list

        except ImportError:
            logger.error("yfinance not installed, cannot fetch historical data")
            raise EToroAPIError("yfinance package required for historical data")
        except Exception as e:
            logger.error(f"Failed to fetch historical data for {symbol}: {e}")
            raise EToroAPIError(f"Failed to fetch historical data: {e}")

    
    def _get_instrument_id(self, symbol: str) -> int:
        """Get eToro instrument ID for symbol.
        
        Supports common aliases (BTC -> BTCUSD, ETH -> ETHUSD, etc.)
        
        Args:
            symbol: Instrument symbol or alias
            
        Returns:
            eToro instrument ID
            
        Raises:
            EToroAPIError: If symbol not found
        """
        # Normalize symbol to uppercase
        symbol = symbol.upper()
        
        # Symbol aliases - map common names to eToro format
        SYMBOL_ALIASES = {
            "BTC": "BTCUSD",
            "ETH": "ETHUSD",
            "LTC": "LTCUSD",
            "XRP": "XRPUSD",
            "BCH": "BCHUSD",
            "ADA": "ADAUSD",
            "DOT": "DOTUSD",
            "LINK": "LINKUSD",
            "EUR": "EURUSD",
            "GBP": "GBPUSD",
            "JPY": "USDJPY",
            "AUD": "AUDUSD",
            "CAD": "USDCAD",
            "CHF": "USDCHF",
        }
        
        # Apply alias if exists
        if symbol in SYMBOL_ALIASES:
            symbol = SYMBOL_ALIASES[symbol]
        
        # Verified instrument IDs from eToro instrumentsmetadata API (2026-02-19)
        # All IDs confirmed tradeable via $10 market orders on DEMO
        INSTRUMENT_IDS = {
            # Forex
            "EURUSD": 1,
            "GBPUSD": 2,
            "USDJPY": 5,
            "AUDUSD": 7,
            "USDCAD": 4,
            "USDCHF": 6,

            # Commodities
            "OIL": 17,
            "GOLD": 18,
            "SILVER": 19,
            "COPPER": 21,

            # Indices
            "SPX500": 27,
            "NSDQ100": 28,
            "DJ30": 29,
            "UK100": 30,
            "GER40": 32,

            # Cryptocurrencies — verified IDs from eToro metadata (2026-02-20)
            # eToro uses plain symbols (BTC) but aliases map BTCUSD -> BTC
            "BTC": 100000,
            "BTCUSD": 100000,
            "ETH": 100001,
            "ETHUSD": 100001,
            "SOL": 100063,
            "XRP": 100003,
            "XRPUSD": 100003,
            "DOGE": 100043,
            "ADA": 100017,
            "ADAUSD": 100017,
            "AVAX": 100085,
            "LINK": 100040,
            "LINKUSD": 100040,
            "DOT": 100037,
            "DOTUSD": 100037,
            "NEAR": 100337,
            "SUI": 100340,
            "APT": 100315,
            "ARB": 100333,
            "OP": 100335,
            "RENDER": 100334,
            "INJ": 100330,
            "LTC": 100005,
            "LTCUSD": 100005,
            "BCH": 100002,
            "BCHUSD": 100002,

            # US Stocks — verified IDs from eToro metadata API
            "AAPL": 1001,
            "META": 1003,
            "MSFT": 1004,
            "AMZN": 1005,
            "BA": 1010,
            "CSCO": 1013,
            "DIS": 1016,
            "GE": 1017,
            "HD": 1018,
            "INTC": 1021,
            "JNJ": 1022,
            "JPM": 1023,
            "KO": 1024,
            "MCD": 1025,
            "PG": 1029,
            "UNH": 1032,
            "WMT": 1035,
            "MA": 1041,
            "NKE": 1042,
            "PEP": 1043,
            "V": 1046,
            "TSLA": 1111,
            "ADBE": 1126,
            "NFLX": 1127,
            "ORCL": 1135,
            "NVDA": 1137,
            "SBUX": 1142,
            "BABA": 1155,
            "UBER": 1186,
            "COST": 1461,
            "LOW": 1474,
            "PYPL": 1484,
            "TGT": 1490,
            "AMD": 1832,
            "CRM": 1839,
            "SNAP": 1979,
            "COIN": 6168,
            "GOOGL": 6434,
            "PLTR": 7991,
            "ABNB": 8047,

            # US Stocks (additional — verified 2026-03-06 against eToro metadata API)
            "CAT": 1012,
            "MS": 1976,
            "GS": 1467,
            "AXP": 1009,
            "MRK": 1027,
            "PFE": 1028,
            "RTX": 1033,
            "XOM": 1036,
            "HON": 1469,
            "MU": 1130,
            "SCHW": 1802,
            "LMT": 1136,
            "FDX": 1138,
            "AMGN": 1143,
            # "UPS": 1275,  # Removed — flagged untradable on eToro DEMO
            "ABBV": 1452,
            "QCOM": 1485,
            "COP": 1510,
            "LLY": 1567,
            "TMO": 1592,
            "TXN": 1634,
            "BLK": 1661,
            "AMAT": 1706,
            "CMG": 1945,
            "SHOP": 4148,
            "NOW": 4260,
            "PANW": 4124,
            "AVGO": 4236,
            "ISRG": 4251,
            "SLB": 4253,
            "LULU": 4309,
            "DXCM": 4382,
            "MRNA": 6152,
            # CVX on eToro is "CVX.US" (ID 1014) = Chevron stock.
            # NOT 100512 which is "Convex Finance" crypto token.
            "CVX": 1014,

            # ETFs
            "SPY": 3000,
            "IWM": 3005,
            "QQQ": 3006,
            "DIA": 3026,
            "GLD": 3025,
            "VTI": 4237,
            "VOO": 4238,
            "SLV": 4430,

            # Sector ETFs (additional — verified 2026-02-24)
            "XLF": 3004,
            "XLE": 3008,
            "XLU": 3013,
            "XLV": 3017,
            "XLI": 3019,
            "TLT": 3020,
            "XLK": 3021,
            "XLP": 3022,
            "HYG": 3023,
            "XLY": 3024,
        }
        
        # Try direct lookup
        instrument_id = INSTRUMENT_IDS.get(symbol)
        if instrument_id:
            return instrument_id
        
        # Try to search for instrument (require exact symbol match)
        # IMPORTANT: eToro has symbol collisions (e.g., CVX = Convex Finance crypto
        # AND CVX.US = Chevron stock). When searching, prefer stock instruments
        # (type 5) over crypto (type 10) for symbols in our stock universe.
        try:
            logger.info(f"Instrument ID not in local mapping, searching for {symbol}")
            search_results = self.search_instruments(symbol)
            if search_results:
                # Determine if this symbol is expected to be a stock
                is_expected_stock = False
                try:
                    from src.core.tradeable_instruments import DEMO_ALLOWED_STOCKS, DEMO_ALLOWED_ETFS
                    is_expected_stock = symbol in set(DEMO_ALLOWED_STOCKS) or symbol in set(DEMO_ALLOWED_ETFS)
                except ImportError:
                    pass

                # CRITICAL: Only accept exact symbol matches to prevent wrong instrument trades
                # Try exact match first, then .US suffix for stocks
                candidates = []
                for result in search_results:
                    result_symbol = (result.get("SymbolFull") or result.get("symbol") or "").upper()
                    inst_type = result.get("InstrumentTypeID", 0)
                    inst_id = result.get("InstrumentID") or result.get("instrumentId")
                    if result_symbol == symbol.upper() or result_symbol == f"{symbol.upper()}.US":
                        candidates.append((result_symbol, inst_id, inst_type))

                if candidates:
                    # If we expect a stock and have multiple matches, prefer type 5 (stock)
                    if is_expected_stock and len(candidates) > 1:
                        stock_candidates = [(s, i, t) for s, i, t in candidates if t == 5]
                        if stock_candidates:
                            chosen = stock_candidates[0]
                            logger.info(
                                f"Found stock match (preferred over crypto): {chosen[0]} "
                                f"instrument ID {chosen[1]} for {symbol}"
                            )
                            return chosen[1]

                    # Single match or no stock preference needed
                    chosen = candidates[0]
                    logger.info(f"Found match: {chosen[0]} instrument ID {chosen[1]} for {symbol}")
                    return chosen[1]
                
                # No exact match found — do NOT fall back to first result
                logger.warning(
                    f"No exact symbol match found for '{symbol}' in eToro search results. "
                    f"Top results: {[r.get('SymbolFull', r.get('symbol', '?')) for r in search_results[:3]]}"
                )
        except Exception as e:
            logger.warning(f"Failed to search for instrument {symbol}: {e}")
        
        # If not found, raise error with helpful message
        raise EToroAPIError(
            f"Instrument ID not found for {symbol}. "
            f"Available symbols: {', '.join(sorted(INSTRUMENT_IDS.keys()))}. "
            f"Use search_instruments() to discover new symbols."
        )


    def get_instrument_metadata(self, instrument_id: int) -> Dict[str, Any]:
        """Get instrument metadata from eToro.
        
        Uses public eToro endpoint (no authentication required).
        
        Args:
            instrument_id: eToro instrument ID
            
        Returns:
            Instrument metadata including symbol, name, type, etc.
            
        Raises:
            EToroAPIError: If request fails
        """
        logger.debug(f"Fetching instrument metadata for ID {instrument_id}")

        try:
            # Enforce rate limiting
            self._enforce_rate_limit()
            
            # Get metadata (public endpoint - no auth needed)
            response = self._session.get(
                f"{self.PUBLIC_URL}/sapi/instrumentsmetadata/V1.1/instruments/{instrument_id}",
                timeout=self.timeout
            )
            
            logger.debug(f"Instrument metadata response: {response.status_code}")
            
            if response.status_code != 200:
                raise EToroAPIError(f"Failed to fetch instrument metadata: HTTP {response.status_code}")
            
            data = response.json()
            logger.debug(f"Instrument metadata: {data}")
            
            return data

        except Exception as e:
            logger.error(f"Failed to fetch instrument metadata for ID {instrument_id}: {e}")
            raise EToroAPIError(f"Failed to fetch instrument metadata: {e}")

    def search_instruments(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for instruments by name or symbol.

        Uses eToro's public instruments metadata endpoint.

        Args:
            query: Search query (symbol or name)
            limit: Maximum number of results

        Returns:
            List of matching instruments with metadata

        Raises:
            EToroAPIError: If request fails
        """
        logger.info(f"Searching for instruments matching '{query}'")

        try:
            self._enforce_rate_limit()

            # Use the instruments metadata endpoint (confirmed working)
            response = self._session.get(
                f"{self.PUBLIC_URL}/sapi/instrumentsmetadata/V1.1/instruments",
                timeout=self.timeout
            )

            logger.debug(f"Instrument metadata response: {response.status_code}")

            if response.status_code != 200:
                logger.warning(f"Instrument metadata fetch failed: HTTP {response.status_code}")
                return []

            data = response.json()
            if isinstance(data, list):
                instruments = data
            elif isinstance(data, dict):
                instruments = data.get("InstrumentDisplayDatas", [])
            else:
                return []

            # Filter by query — EXACT symbol match only to prevent wrong instruments
            # (e.g., "CAT" matching "LiveCattle" via name substring)
            # Also match .US suffix (eToro uses CVX.US for Chevron stock vs CVX for crypto)
            query_upper = query.upper()
            results = []
            for inst in instruments:
                sym = (inst.get("SymbolFull") or "").upper()
                if query_upper == sym or f"{query_upper}.US" == sym:
                    results.append(inst)
                    if len(results) >= limit:
                        break

            logger.info(f"Found {len(results)} instruments matching '{query}'")
            return results

        except Exception as e:
            logger.warning(f"Failed to search instruments for '{query}': {e}")
            return []

    def _validate_market_data(self, data: Dict[str, Any]) -> bool:
        """Validate market data integrity.
        
        Args:
            data: Market data dictionary
            
        Returns:
            True if data is valid
        """
        required_fields = ["timestamp", "open", "high", "low", "close", "volume"]

        # Check all required fields present
        if not all(field in data for field in required_fields):
            logger.warning("Market data missing required fields")
            return False

        # Check no null values
        if any(data[field] is None for field in required_fields):
            logger.warning("Market data contains null values")
            return False

        try:
            # Check reasonable values
            open_price = float(data["open"])
            high_price = float(data["high"])
            low_price = float(data["low"])
            close_price = float(data["close"])
            volume = float(data["volume"])

            # Prices must be positive
            if any(p <= 0 for p in [open_price, high_price, low_price, close_price]):
                logger.warning("Market data contains non-positive prices")
                return False

            # Volume must be non-negative
            if volume < 0:
                logger.warning("Market data contains negative volume")
                return False

            # High must be >= low
            if high_price < low_price:
                logger.warning("Market data has high < low")
                return False

            # High must be >= open and close
            if high_price < open_price or high_price < close_price:
                logger.warning("Market data has high < open or close")
                return False

            # Low must be <= open and close
            if low_price > open_price or low_price > close_price:
                logger.warning("Market data has low > open or close")
                return False

            return True

        except (ValueError, TypeError) as e:
            logger.warning(f"Market data validation error: {e}")
            return False

    def get_account_info(self) -> AccountInfo:
        """Retrieve account balance, buying power, margin, and positions.
        
        Uses eToro's official portfolio endpoint:
        - DEMO: GET /api/v1/trading/info/demo/portfolio
        - LIVE: GET /api/v1/trading/info/portfolio
        
        Returns:
            Account information
            
        Raises:
            EToroAPIError: If request fails or endpoint not available
        """
        logger.debug(f"Fetching account information from eToro portfolio endpoint ({self.mode.value} mode)")

        try:
            # Use demo-specific endpoints for DEMO mode
            portfolio_endpoint = "/api/v1/trading/info/demo/portfolio" if self.mode == TradingMode.DEMO else "/api/v1/trading/info/portfolio"
            pnl_endpoint = "/api/v1/trading/info/demo/pnl" if self.mode == TradingMode.DEMO else "/api/v1/trading/info/real/pnl"
            
            # Get full portfolio data
            portfolio_data = self._make_request(
                method="GET",
                endpoint=portfolio_endpoint
            )

            # Get PnL data
            pnl_data = self._make_request(
                method="GET",
                endpoint=pnl_endpoint
            )

            # Extract account info from portfolio response
            # Demo mode returns nested structure: { "clientPortfolio": { ... } }
            # Live mode returns flat structure: { "Credit": ..., "Equity": ..., ... }
            if self.mode == TradingMode.DEMO:
                client_portfolio = portfolio_data.get("clientPortfolio", {})
                credit = float(client_portfolio.get("credit", 0))
                positions = client_portfolio.get("positions", [])
                
                # eToro DEMO doesn't provide an equity field.
                # Equity = credit (available cash) + sum of position invested amounts + unrealized P&L
                # The 'amount' field on each position is the invested capital.
                try:
                    invested = sum(float(p.get("amount", 0)) for p in positions)
                except Exception:
                    invested = 0.0
                equity = credit + invested  # Will add unrealized P&L below
            else:
                credit = float(portfolio_data.get("Credit", 0))
                equity = float(portfolio_data.get("Equity", credit))
                positions = portfolio_data.get("Positions", [])
            
            # Calculate metrics
            positions_count = len([p for p in positions if p.get("isBuy") is not None or p.get("IsBuy") is not None])
            
            # Get unrealized PnL from pnl endpoint
            if self.mode == TradingMode.DEMO:
                pnl_portfolio = pnl_data.get("clientPortfolio", {})
                # Fetch live positions (with enriched prices) for accurate PnL
                try:
                    live_positions = self.get_positions()
                    unrealized_pnl = sum(p.unrealized_pnl for p in live_positions)
                except Exception:
                    unrealized_pnl = 0.0
                realized_pnl = 0.0
            else:
                unrealized_pnl = float(pnl_data.get("UnrealizedPnL", 0))
                realized_pnl = float(pnl_data.get("RealizedPnL", 0))
            
            # Calculate buying power and margin
            if self.mode == TradingMode.DEMO:
                # Demo: equity already includes invested capital from above
                # Add unrealized P&L for the final equity figure
                actual_equity = equity + unrealized_pnl
                try:
                    used_margin = sum(float(p.get("amount", 0)) for p in positions)
                except Exception:
                    used_margin = 0.0
                available_margin = max(0.0, credit)
                buying_power = available_margin
            else:
                used_margin = float(portfolio_data.get("UsedMargin", 0))
                actual_equity = equity  # Live mode has real equity from eToro
                available_margin = equity - used_margin
                buying_power = available_margin

            account_info = AccountInfo(
                account_id=f"{self.mode.value.lower()}_account_001",
                mode=self.mode,
                balance=credit,
                buying_power=buying_power,
                margin_used=used_margin,
                margin_available=available_margin,
                daily_pnl=unrealized_pnl,  # Using unrealized as daily (can be refined)
                total_pnl=realized_pnl + unrealized_pnl,
                positions_count=positions_count,
                updated_at=datetime.now(),
                equity=actual_equity,
            )

            logger.debug(f"Account balance: {account_info.balance}, positions: {account_info.positions_count}")
            return account_info

        except Exception as e:
            logger.error(f"Failed to fetch account info: {e}")
            raise EToroAPIError(f"Failed to fetch account info: {e}")

    def get_positions(self) -> List[Position]:
        """Retrieve all open positions.
        
        Uses eToro's official portfolio endpoint:
        - DEMO: GET /api/v1/trading/info/demo/portfolio
        - LIVE: GET /api/v1/trading/info/portfolio
        
        Returns:
            List of open positions
            
        Raises:
            EToroAPIError: If request fails or endpoint not available
        """
        logger.debug(f"Fetching open positions from eToro portfolio endpoint ({self.mode.value} mode)")

        # Circuit breaker check — return cached positions if circuit is open
        try:
            self._check_circuit_breaker("positions")
        except CircuitBreakerOpen:
            if self._cached_positions is not None:
                logger.warning("Circuit breaker [positions] OPEN — returning cached positions")
                return list(self._cached_positions)
            raise  # No cache available, propagate

        try:
            # Use demo-specific endpoints for DEMO mode
            portfolio_endpoint = "/api/v1/trading/info/demo/portfolio" if self.mode == TradingMode.DEMO else "/api/v1/trading/info/portfolio"
            
            # Get full portfolio data
            portfolio_data = self._make_request(
                method="GET",
                endpoint=portfolio_endpoint
            )

            positions = []
            
            # Extract positions based on mode
            # Demo mode returns nested structure: { "clientPortfolio": { "positions": [...] } }
            # Live mode returns flat structure: { "Positions": [...] }
            if self.mode == TradingMode.DEMO:
                position_list = portfolio_data.get("clientPortfolio", {}).get("positions", [])
            else:
                position_list = portfolio_data.get("Positions", [])
            
            for item in position_list:
                # Parse position data from eToro format
                # Demo uses lowercase keys, Live uses PascalCase
                if self.mode == TradingMode.DEMO:
                    is_buy = item.get("isBuy", True)
                    position_id = str(item.get("positionID", ""))
                    instrument_id = int(item.get("instrumentID", 0))
                    amount = float(item.get("amount", 0))
                    open_rate = float(item.get("openRate", 0))
                    current_rate = float(item.get("currentRate", open_rate))
                    open_datetime = item.get("openDateTime")
                    stop_loss = float(item.get("stopLossRate", 0)) if item.get("stopLossRate") and not item.get("isNoStopLoss", False) else None
                    take_profit = float(item.get("takeProfitRate", 0)) if item.get("takeProfitRate") and not item.get("isNoTakeProfit", False) else None
                    
                    # Get actual units (quantity) - this is the correct field for position size
                    units = float(item.get("units", 0))
                    
                    # Calculate PnL for demo
                    # units = amount (dollars invested) in demo mode, not actual shares
                    # P&L = invested_amount * price_change_pct
                    if open_rate > 0:
                        if is_buy:
                            net_profit = amount * (current_rate - open_rate) / open_rate
                        else:
                            net_profit = amount * (open_rate - current_rate) / open_rate
                    else:
                        net_profit = 0.0
                else:
                    is_buy = item.get("IsBuy", True)
                    position_id = str(item.get("PositionID", ""))
                    instrument_id_raw = item.get("InstrumentID", "")
                    instrument_id = int(instrument_id_raw) if instrument_id_raw else 0  # Keep as int for mapping
                    amount = float(item.get("Amount", 0))
                    open_rate = float(item.get("OpenRate", 0))
                    current_rate = float(item.get("CurrentRate", open_rate))
                    open_datetime = item.get("OpenDateTime")
                    stop_loss = float(item["StopLossRate"]) if item.get("StopLossRate") else None
                    take_profit = float(item["TakeProfitRate"]) if item.get("TakeProfitRate") else None
                    net_profit = float(item.get("NetProfit", 0))
                    
                    # Calculate units from amount and open rate for live mode
                    units = amount / open_rate if open_rate > 0 else 0
                
                position = Position(
                    id=position_id,
                    strategy_id="etoro_position",  # Default strategy for eToro positions
                    symbol=INSTRUMENT_ID_TO_SYMBOL.get(instrument_id, f"ID_{instrument_id}"),  # Map instrument ID to symbol
                    side=PositionSide.LONG if is_buy else PositionSide.SHORT,
                    quantity=units,
                    entry_price=open_rate,
                    current_price=current_rate,
                    unrealized_pnl=net_profit,
                    realized_pnl=0.0,  # Not provided in positions endpoint
                    opened_at=datetime.fromisoformat(open_datetime.replace("Z", "+00:00")) if open_datetime else datetime.now(),
                    etoro_position_id=position_id,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    closed_at=None,  # Open positions only
                    invested_amount=amount,  # Actual capital invested (not leveraged notional)
                )
                positions.append(position)

            # Enrich positions with live prices from the rates endpoint.
            # The DEMO portfolio endpoint does NOT return currentRate, so
            # current_price == entry_price and PnL == 0 without this step.
            self._enrich_positions_with_live_prices(positions)

            logger.debug(f"Retrieved {len(positions)} open positions")

            # Update cache and record success
            self._cached_positions = list(positions)
            self._record_success("positions")
            return positions

        except CircuitBreakerOpen:
            raise
        except Exception as e:
            self._record_failure("positions")
            logger.error(f"Failed to fetch positions: {e}")
            raise EToroAPIError(f"Failed to fetch positions: {e}")

    def _enrich_positions_with_live_prices(self, positions: List) -> None:
        """Fetch current market prices and update position PnL in-place.

        The DEMO portfolio endpoint omits ``currentRate``, so every position
        comes back with ``current_price == entry_price`` and ``unrealized_pnl == 0``.
        This helper calls the batch rates endpoint ONCE for all instruments
        and patches each position with the live mid-price.
        """
        if not positions:
            return

        from src.utils.instrument_mappings import SYMBOL_TO_INSTRUMENT_ID

        # Collect unique instrument IDs that need a price lookup
        symbol_to_iid: Dict[str, int] = {}
        for pos in positions:
            sym = pos.symbol
            if sym.startswith("ID_") or sym in symbol_to_iid:
                continue
            iid = SYMBOL_TO_INSTRUMENT_ID.get(sym)
            if iid is not None:
                symbol_to_iid[sym] = iid

        if not symbol_to_iid:
            return

        # Fetch all prices in a single batch API call
        live_prices: Dict[str, float] = {}
        try:
            ids_str = ",".join(str(iid) for iid in symbol_to_iid.values())
            response = self._session.get(
                f"{self.PUBLIC_URL}/sapi/trade-real/rates?instrumentIds={ids_str}",
                timeout=self.timeout,
            )
            if response.status_code == 200:
                rates = response.json().get("Rates", [])
                # Build reverse map: instrument_id -> symbol
                iid_to_symbol = {iid: sym for sym, iid in symbol_to_iid.items()}
                for rate in rates:
                    iid = rate.get("InstrumentID")
                    sym = iid_to_symbol.get(iid)
                    if sym:
                        ask = float(rate.get("Ask", 0))
                        bid = float(rate.get("Bid", 0))
                        mid = (ask + bid) / 2 if ask > 0 and bid > 0 else ask or bid
                        if mid > 0:
                            live_prices[sym] = mid
            else:
                logger.warning(f"Batch rates endpoint returned {response.status_code} — falling back to individual fetches")
        except Exception as exc:
            logger.warning(f"Batch rates fetch failed: {exc} — falling back to individual fetches")

        # Fallback: fetch individually for any symbols not in batch response
        missing = [sym for sym in symbol_to_iid if sym not in live_prices]
        for sym in missing:
            try:
                md = self.get_market_data(sym, instrument_id=symbol_to_iid[sym])
                live_prices[sym] = md.close
            except Exception as exc:
                logger.debug(f"Could not fetch live price for {sym}: {exc}")

        if not live_prices:
            logger.debug("No live prices retrieved — positions will keep entry prices")
            return

        # Patch each position
        updated = 0
        for pos in positions:
            price = live_prices.get(pos.symbol)
            if price is None:
                continue
            pos.current_price = price
            if pos.entry_price and pos.entry_price > 0:
                # Use invested_amount (dollar value) for PnL calculation.
                # quantity can be either dollars (stocks/ETFs) or units (forex/crypto/commodities).
                # invested_amount is always the dollar value invested.
                invested = getattr(pos, 'invested_amount', None) or pos.quantity or 0
                if invested > 0:
                    if pos.side == PositionSide.LONG:
                        pos.unrealized_pnl = invested * (price - pos.entry_price) / pos.entry_price
                    else:
                        pos.unrealized_pnl = invested * (pos.entry_price - price) / pos.entry_price
                else:
                    pos.unrealized_pnl = 0.0
            else:
                pos.unrealized_pnl = 0.0
            updated += 1

        logger.info(f"Enriched {updated}/{len(positions)} positions with live prices ({len(live_prices)} symbols, batch API)")


    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Check status of submitted order.

        NOTE: This endpoint may not be available in eToro's public API.
        The platform uses local database tracking for order status.

        Args:
            order_id: eToro order ID

        Returns:
            Order status information

        Raises:
            EToroAPIError: If request fails or endpoint not available
        """
        logger.debug(f"Fetching order status for {order_id}")

        # Circuit breaker — orders cannot be cached, reject if open
        self._check_circuit_breaker("orders")

        try:
            # Use demo-specific endpoints for DEMO mode
            if self.mode == TradingMode.DEMO:
                endpoint = f"/api/v1/trading/info/demo/orders/{order_id}"
            else:
                endpoint = f"/api/v1/trading/orders/{order_id}"
            
            data = self._make_request(
                method="GET",
                endpoint=endpoint
            )

            logger.debug(f"Order {order_id} status: {data.get('status')}")
            self._record_success("orders")
            return data

        except Exception as e:
            self._record_failure("orders")
            logger.error(f"Failed to fetch order status for {order_id}: {e}")
            logger.info("Order status endpoint may not be available - using local database tracking")
            raise EToroAPIError(f"Failed to fetch order status: {e}")

    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        take_profit_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """Submit order to eToro.
        
        Supports Market, Limit, Stop Loss, and Take Profit order types.
        Uses eToro's authenticated trading API endpoint.
        
        NOTE: This uses the market-open-orders endpoint which requires authentication.
        The actual endpoint structure may vary based on eToro's API documentation.
        
        Args:
            symbol: Instrument symbol
            side: Order side (BUY or SELL)
            order_type: Order type (MARKET, LIMIT, STOP_LOSS, TAKE_PROFIT)
            quantity: Order quantity (in units or amount depending on instrument)
            price: Limit price (required for LIMIT orders)
            stop_price: Stop loss rate (optional, sent as StopLossRate)
            take_profit_price: Take profit rate (optional, sent as TakeProfitRate)
            
        Returns:
            Order response with order ID and status
            
        Raises:
            EToroAPIError: If order placement fails
        """
        logger.info(f"Placing {order_type.value} {side.value} order for {quantity} {symbol}")

        # Circuit breaker — orders cannot be cached, reject if open
        self._check_circuit_breaker("orders")

        # Check if instrument is tradeable
        from src.core.tradeable_instruments import is_tradeable, get_blocked_reason
        
        if not is_tradeable(symbol, self.mode):
            reason = get_blocked_reason(symbol, self.mode)
            raise EToroAPIError(
                f"Cannot place order for {symbol}: {reason}. "
                f"Please use one of the verified tradeable instruments."
            )

        # Validate minimum order size (eToro requires minimum $10)
        if quantity < 10.0:
            raise ValueError(
                f"Order size must be at least $10.00 (eToro minimum). "
                f"Requested: ${quantity:.2f}"
            )

        # Validate order parameters
        if order_type == OrderType.LIMIT and price is None:
            raise ValueError("Price required for LIMIT orders")
        if order_type == OrderType.STOP_LOSS and stop_price is None:
            raise ValueError("Stop price required for STOP_LOSS orders")

        try:
            # Get instrument ID
            instrument_id = self._get_instrument_id(symbol)
            
            # Build order payload
            # Note: eToro API expects amount-based orders, not quantity-based
            payload = {
                "InstrumentID": instrument_id,
                "Amount": quantity,  # Amount in account currency
                "IsBuy": side == OrderSide.BUY,
                "Leverage": 1,  # Default leverage
                "OrderType": order_type.value
            }

            if price is not None:
                payload["Rate"] = price
            if stop_price is not None:
                payload["StopLossRate"] = stop_price
            if take_profit_price is not None:
                payload["TakeProfitRate"] = take_profit_price

            # Submit order to eToro
            # Use demo-specific endpoints for DEMO mode
            if self.mode == TradingMode.DEMO:
                endpoint = "/api/v1/trading/execution/demo/market-open-orders/by-amount"
            else:
                endpoint = "/api/v1/trading/execution/market-open-orders/by-amount"
            
            data = self._make_request(
                method="POST",
                endpoint=endpoint,
                json_data=payload
            )

            # Extract order ID from response
            # Demo response format: { "orderForOpen": { "orderID": 123, ... }, "token": "..." }
            # Live response format may differ
            order_id = None
            if "orderForOpen" in data:
                order_id = data["orderForOpen"].get("orderID") or data["orderForOpen"].get("OrderID") or data["orderForOpen"].get("orderId")
            elif "OrderID" in data:
                order_id = data.get("OrderID")
            elif "order_id" in data:
                order_id = data.get("order_id")
            elif "orderId" in data:
                order_id = data.get("orderId")
            elif "orderID" in data:
                order_id = data.get("orderID")
            
            # Last resort: search nested response for any order ID field
            if not order_id and isinstance(data, dict):
                for key in ["orderForOpen", "order", "result"]:
                    if key in data and isinstance(data[key], dict):
                        order_id = data[key].get("orderID") or data[key].get("OrderID") or data[key].get("orderId") or data[key].get("order_id")
                        if order_id:
                            break
            
            logger.info(f"Order placed successfully: Order ID = {order_id}")
            
            self._record_success("orders")
            # Return normalized response with order_id field
            return {
                "order_id": str(order_id) if order_id else None,
                "status": data.get("orderForOpen", {}).get("statusID") if "orderForOpen" in data else None,
                "raw_response": data
            }

        except Exception as e:
            self._record_failure("orders")
            logger.error(f"Failed to place order: {e}")
            raise EToroAPIError(f"Failed to place order: {e}")

    def cancel_order(self, order_id: str) -> bool:
        """Cancel pending order.

        Args:
            order_id: eToro order ID

        Returns:
            True if cancellation successful

        Raises:
            EToroAPIError: If cancellation fails or endpoint not available
        """
        logger.info(f"Cancelling order {order_id}")

        # Circuit breaker — orders cannot be cached, reject if open
        self._check_circuit_breaker("orders")

        try:
            # Use the correct cancel endpoint matching eToro's API pattern.
            # Demo uses POST to market-cancel-orders (mirrors market-open-orders
            # and market-close-orders patterns). Live uses the same pattern.
            if self.mode == TradingMode.DEMO:
                endpoint = f"/api/v1/trading/execution/demo/market-cancel-orders/{order_id}"
            else:
                endpoint = f"/api/v1/trading/execution/market-cancel-orders/{order_id}"

            logger.debug(f"Cancelling order via POST {endpoint}")
            data = self._make_request(
                method="POST",
                endpoint=endpoint
            )

            success = data.get("success", False) or data.get("status") == "cancelled"
            if success:
                logger.info(f"Order {order_id} cancelled successfully")
                self._record_success("orders")
                return True

            # A 200 response without error is treated as success
            logger.info(f"Order {order_id} cancel request completed (response: {data})")
            self._record_success("orders")
            return True

        except CircuitBreakerOpen:
            raise
        except Exception as e:
            self._record_failure("orders")
            logger.error(f"Failed to cancel order {order_id}: {e}")
            if not isinstance(e, EToroAPIError):
                raise EToroAPIError(f"Failed to cancel order: {e}")
            raise

    def close_position(self, position_id: str, instrument_id: int = None, amount: float = None) -> Dict[str, Any]:
        """Close an open position.

        Per eToro API docs (api-portal.etoro.com/guides/market-orders):
        - Full close: POST to market-close-orders/positions/{positionId} with NO UnitsToDeduct
        - Partial close: include UnitsToDeduct in the payload

        Args:
            position_id: eToro position ID
            instrument_id: eToro instrument ID (required for demo close endpoint)
            amount: Ignored for full close — full close omits UnitsToDeduct entirely

        Returns:
            Close order response

        Raises:
            EToroAPIError: If position close fails
        """
        logger.info(f"Closing position {position_id}")

        # Circuit breaker — position mutations cannot be cached, reject if open
        self._check_circuit_breaker("positions")

        try:
            if self.mode == TradingMode.DEMO:
                endpoint = f"/api/v1/trading/execution/demo/market-close-orders/positions/{position_id}"
            else:
                endpoint = f"/api/v1/trading/execution/market-close-orders/positions/{position_id}"

            # Full close: only send InstrumentID, omit UnitsToDeduct entirely
            payload = {}
            if instrument_id is not None:
                payload["InstrumentID"] = instrument_id

            data = self._make_request(
                method="POST",
                endpoint=endpoint,
                json_data=payload
            )

            logger.info(f"Position {position_id} close order submitted")
            self._record_success("positions")
            return data

        except CircuitBreakerOpen:
            raise
        except Exception as e:
            self._record_failure("positions")
            logger.error(f"Failed to close position {position_id}: {e}")
            raise EToroAPIError(f"Failed to close position: {e}")

    def partial_close_position(self, position_id: str, amount: float, instrument_id: int = None) -> Dict[str, Any]:
        """Partially close an open position by dollar amount.

        Uses eToro's market-close-orders endpoint with an Amount parameter
        to reduce the position size without opening an opposite-side position.

        Args:
            position_id: eToro position ID
            amount: Dollar amount to close (must be less than total invested)
            instrument_id: eToro instrument ID (required for demo close endpoint)

        Returns:
            Close order response

        Raises:
            EToroAPIError: If partial close fails
        """
        logger.info(f"Partially closing position {position_id} — amount: ${amount:.2f}")

        self._check_circuit_breaker("positions")

        try:
            if self.mode == TradingMode.DEMO:
                endpoint = f"/api/v1/trading/execution/demo/market-close-orders/positions/{position_id}"
            else:
                endpoint = f"/api/v1/trading/positions/{position_id}/close"

            payload = {"UnitsToDeduct": amount}
            if instrument_id is not None:
                payload["InstrumentID"] = instrument_id

            data = self._make_request(
                method="POST",
                endpoint=endpoint,
                json_data=payload
            )

            logger.info(f"Position {position_id} partial close submitted (${amount:.2f})")
            self._record_success("positions")
            return data

        except CircuitBreakerOpen:
            raise
        except Exception as e:
            self._record_failure("positions")
            logger.error(f"Failed to partially close position {position_id}: {e}")
            raise EToroAPIError(f"Failed to partially close position: {e}")

    def update_position_stop_loss(self, position_id: str, stop_loss_rate: float, instrument_id: int = None) -> Dict[str, Any]:
        """Update stop-loss for an open position.

        Args:
            position_id: eToro position ID
            stop_loss_rate: New stop-loss rate/price
            instrument_id: eToro instrument ID (may be required for some endpoints)

        Returns:
            Update response

        Raises:
            EToroAPIError: If update fails
        """
        logger.info(f"Updating stop-loss for position {position_id} to {stop_loss_rate}")

        # eToro's Public API does not expose a stop-loss update endpoint.
        # Trailing stops are enforced DB-side by the monitoring service (checks every 30s
        # and closes positions that breach the stop). The initial SL is set correctly
        # on eToro at order creation time via the open-position payload.
        return {"status": "db_only", "position_id": position_id, "stop_loss_rate": stop_loss_rate}

    def place_order_with_retry(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        max_retries: int = 3,
        base_delay: float = 1.0
    ) -> Dict[str, Any]:
        """Place order with exponential backoff retry logic.
        
        Args:
            symbol: Instrument symbol
            side: Order side
            order_type: Order type
            quantity: Order quantity
            price: Limit price (optional)
            stop_price: Stop loss rate (optional)
            take_profit_price: Take profit rate (optional)
            max_retries: Maximum retry attempts
            base_delay: Base delay in seconds for exponential backoff
            
        Returns:
            Order response
            
        Raises:
            EToroAPIError: If all retries fail
        """
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return self.place_order(symbol, side, order_type, quantity, price, stop_price, take_profit_price)

            except EToroAPIError as e:
                last_error = e

                # Don't retry on certain errors
                if "Invalid" in str(e) or "Forbidden" in str(e):
                    logger.error(f"Non-retryable error: {e}")
                    raise

                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"Order placement failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay}s: {e}")
                    time.sleep(delay)
                else:
                    logger.error(f"Order placement failed after {max_retries + 1} attempts")

        raise EToroAPIError(f"Order placement failed after {max_retries + 1} attempts: {last_error}")

    def get_social_insights(self, symbol: str) -> Dict[str, Any]:
        """Retrieve social sentiment, trending status, and Pro Investor activity.

        NOTE: This endpoint may not be available in eToro's public API.

        Args:
            symbol: Instrument symbol

        Returns:
            Social insights data including sentiment scores and trending info

        Raises:
            EToroAPIError: If request fails or endpoint not available
        """
        logger.debug(f"Fetching social insights for {symbol}")

        try:
            data = self._make_request(
                method="GET",
                endpoint=f"/api/v1/social/insights/{symbol}"
            )

            logger.debug(f"Social insights for {symbol}: sentiment={data.get('sentiment_score')}")
            return data

        except Exception as e:
            logger.error(f"Failed to fetch social insights for {symbol}: {e}")
            logger.info("Social insights endpoint may not be available")
            raise EToroAPIError(f"Failed to fetch social insights: {e}")

    def get_smart_portfolios(self) -> List[Dict[str, Any]]:
        """Retrieve available Smart Portfolios with composition and performance.

        NOTE: This endpoint may not be available in eToro's public API.

        Returns:
            List of Smart Portfolio information

        Raises:
            EToroAPIError: If request fails or endpoint not available
        """
        logger.debug("Fetching Smart Portfolios")

        try:
            data = self._make_request(
                method="GET",
                endpoint="/api/v1/smart-portfolios"
            )

            portfolios = data.get("portfolios", [])
            logger.debug(f"Retrieved {len(portfolios)} Smart Portfolios")
            return portfolios

        except Exception as e:
            logger.error(f"Failed to fetch Smart Portfolios: {e}")
            logger.info("Smart Portfolios endpoint may not be available")
            raise EToroAPIError(f"Failed to fetch Smart Portfolios: {e}")

    def get_smart_portfolio_details(self, portfolio_id: str) -> Dict[str, Any]:
        """Retrieve detailed information for a specific Smart Portfolio.

        NOTE: This endpoint may not be available in eToro's public API.

        Args:
            portfolio_id: Smart Portfolio ID

        Returns:
            Detailed Smart Portfolio information

        Raises:
            EToroAPIError: If request fails or endpoint not available
        """
        logger.debug(f"Fetching Smart Portfolio details for {portfolio_id}")

        try:
            data = self._make_request(
                method="GET",
                endpoint=f"/api/v1/smart-portfolios/{portfolio_id}"
            )

            logger.debug(f"Retrieved Smart Portfolio {portfolio_id}: {data.get('name')}")
            return data

        except Exception as e:
            logger.error(f"Failed to fetch Smart Portfolio details for {portfolio_id}: {e}")
            logger.info("Smart Portfolio details endpoint may not be available")
            raise EToroAPIError(f"Failed to fetch Smart Portfolio details: {e}")


# Import instrument mappings from centralized location
from src.utils.instrument_mappings import INSTRUMENT_ID_TO_SYMBOL, SYMBOL_TO_INSTRUMENT_ID

