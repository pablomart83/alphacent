"""FMP historical OHLC adapter.

Lifts Yahoo's ~7-month 1h rolling cap by reading from FMP's
`/stable/historical-chart/{1hour,4hour,1d}` endpoints. We already pay
for FMP Starter ($29/mo, 300 req/min); this module turns that subscription
into a real non-crypto intraday data source.

Scope and constraints:
  - Starter plan — "US coverage" clause restricts some non-US indices,
    oil, copper, DAX, CAC at certain intervals. The per-interval support
    map below is built from a live probe (scripts/probe_fmp_coverage.py).
    Adding a new symbol without a probe run is a footgun — the support
    map is the single source of truth.
  - Rate limit: 300 req/min. Each historical-chart request returns up to
    ~3 months of 1h data or ~6 months of 4h data — full multi-year
    backfill requires pagination + parallel workers.
  - Max throughput at 4 parallel workers ≈ 5 req/sec ≈ 300 req/min,
    which matches the rate limit. 4 workers is a safety margin.

Fail-open semantics (mirror binance_ohlc.py):
  - Any network / parse / quota failure raises FMPAPIError.
  - `is_supported(symbol, interval) -> False` for known-blocked combos
    so callers never hit a 402 in the hot path.
  - Unknown-symbol requests fall through to Yahoo via the caller.

Symbol mapping:
  - Most stocks/ETFs use their native ticker (AAPL, SPY).
  - US indices prepend `^` (^GSPC, ^IXIC, ^DJI). The `%5E`-style URL
    encoding is handled by requests.utils.quote().
  - Forex: 6-char concat, no separator (EURUSD, GBPUSD).
  - Commodities: `{CODE}USD` (GCUSD gold, SIUSD silver, CLUSD oil, HGUSD copper).
  - Crypto: `{SYM}USD` (BTCUSD, ETHUSD). Binance is primary for crypto;
    FMP is a secondary fallback.

Bar-format note:
  - US equities 4h bars are session-aligned (09:30 + 13:30 ET), 2 bars
    per trading day. This is correct behaviour for equities — a 4h bar
    aligned to UTC midnight straddles the market open/close unhelpfully.
  - 24h assets (forex, commodities, crypto) get clock-aligned 4h bars
    (00/04/08/12/16/20 UTC), 6 bars per day with weekend gap.
  - Both modes return consistent OHLCV shape; downstream indicators
    work correctly on either.
"""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import requests
import yaml

from src.models import DataSource, MarketData

logger = logging.getLogger(__name__)


BASE_URL = "https://financialmodelingprep.com/stable/historical-chart"
TIMEOUT_S = 30.0
MAX_RETRIES = 3
RETRY_BACKOFF_S = 2.0

# Per-interval page windows — FMP truncates responses at these rough limits
# even when a wider date range is requested. Caller pages in this stride.
# Values picked to stay well inside the observed truncation point:
#   1h US stocks: ~3 months returns ~441 bars (~147/month)
#   4h stocks: ~6 months returns ~248 bars (~42/month)
#   4h 24h assets: ~6 months returns ~900 bars (6/day × ~150 days)
PAGE_WINDOW_DAYS: Dict[str, int] = {
    "1hour": 85,   # ~85 days (not exactly 90 to stay under FMP's cut)
    "4hour": 170,  # ~6 months, safe for US equity session bars
    "1day": 1825,  # 5y in a single call — 1d endpoint isn't page-limited
}


# Per-(symbol, interval) support map — built from live probes of FMP Starter.
# Philosophy: default-allow for symbols we haven't tested, default-deny for
# symbols we've confirmed don't work. FMP Starter covers virtually any
# US-listed stock/ETF; we can't enumerate every one, so unknown symbols go
# through the runtime path and any 402 response is captured in the runtime
# block-set below. Known-blocked combos short-circuit to avoid 402 roundtrips.
#
# Run scripts/probe_fmp_coverage.py to refresh the known-blocked list.
#
# Entries keyed by FMP symbol (post-SYMBOL_MAP resolution).
EXPLICIT_BLOCKED: set = {
    # Non-US indices fully blocked on Starter at every timeframe
    ("^GDAXI", "1hour"), ("^GDAXI", "4hour"), ("^GDAXI", "1day"),
    ("^FCHI",  "1hour"), ("^FCHI",  "4hour"), ("^FCHI",  "1day"),
    # Indices at 4h — Starter provides 1h but not 4h
    ("^GSPC", "4hour"),
    ("^IXIC", "4hour"),
    ("^DJI",  "4hour"),
    ("^FTSE", "4hour"),
    ("^STOXX50E", "4hour"),
    # Commodities — oil and copper are blocked at 1h but OK at 4h
    ("CLUSD", "1hour"),
    ("HGUSD", "1hour"),
    # Non-US / non-majors stocks in our universe known to be sparse or
    # premium (foreign listings that FMP only serves at EOD).
    # Add as they surface in logs (runtime-observed block-set below).
}


# Runtime block-set — symbols that returned 402 on a real fetch. Persisted
# for the lifetime of the process to avoid retry storms. Cleared on restart;
# rebuild on demand by allowing unknown symbols through once.
_RUNTIME_BLOCKED: set = set()


SUPPORT: Dict[Tuple[str, str], bool] = {}  # legacy placeholder; kept for backward-compat in imports


# Display → FMP symbol. We take whichever form the caller passes (most come
# as display form like "BTC", "GOLD") and normalise to the FMP ticker.
SYMBOL_MAP: Dict[str, str] = {
    # Indices (display name → FMP caret-prefixed ticker)
    "SPX500": "^GSPC",
    "NSDQ100": "^IXIC",
    "DJ30":   "^DJI",
    "UK100":  "^FTSE",
    "GER40":  "^GDAXI",
    "FR40":   "^FCHI",
    "STOXX50": "^STOXX50E",
    # Commodities (display → FMP continuous-contract ticker)
    "GOLD":     "GCUSD",
    "SILVER":   "SIUSD",
    "OIL":      "CLUSD",
    "COPPER":   "HGUSD",
    "NATGAS":   "NGUSD",      # natgas — FMP support unknown, test at runtime
    "PLATINUM": "PLUSD",
    # Crypto display → FMP pair (only used on the FMP-fallback path for crypto)
    "BTC": "BTCUSD", "ETH": "ETHUSD", "SOL": "SOLUSD",
    "AVAX": "AVAXUSD", "LINK": "LINKUSD", "DOT": "DOTUSD",
    # Forex — display form matches FMP form (EURUSD, GBPUSD, EURGBP, etc.)
    # Commodities without a 2-letter FMP continuous code (ALUMINUM, ZINC) are
    # left unmapped — they'll fail at runtime and the runtime block-set catches
    # the 402. Those are LME metals and probably EOD-only on FMP anyway.
}


INTERVAL_MAP: Dict[str, str] = {
    "1h": "1hour",
    "4h": "4hour",
    "1d": "1day",
}


class FMPAPIError(Exception):
    """Raised on any FMP fetch failure (network, quota, premium-block, parse).

    Callers should catch and fall back to Yahoo. Distinguish subtypes via
    the `.reason` attribute: "network", "premium_blocked", "rate_limited",
    "empty", "parse_error", "unsupported".
    """

    def __init__(self, message: str, reason: str = "unknown"):
        super().__init__(message)
        self.reason = reason


def _load_api_key() -> str:
    """Read FMP api_key from config/api_keys.yaml.

    Structure: top-level `financial_modeling_prep.api_key`. On EC2 this is
    written by deploy/patch-api-keys.sh from AWS Secrets Manager at boot.
    """
    for candidate in ("config/api_keys.yaml", "/home/ubuntu/alphacent/config/api_keys.yaml"):
        if os.path.exists(candidate):
            try:
                with open(candidate) as f:
                    cfg = yaml.safe_load(f) or {}
                k = (cfg.get("financial_modeling_prep") or {}).get("api_key", "")
                if k and k != "REPLACE_VIA_SECRETS_MANAGER":
                    return k
            except Exception as e:
                logger.warning(f"Could not read FMP key from {candidate}: {e}")
    return ""


def _resolve_fmp_symbol(symbol: str) -> str:
    """Normalise a display-form or wire-form symbol to FMP's expected form."""
    sym = symbol.upper().strip()
    return SYMBOL_MAP.get(sym, sym)


def is_supported(symbol: str, interval: str) -> bool:
    """Return True if (symbol, interval) is expected to be accessible on Starter.

    Default-allow semantics: unknown symbols get True (let the runtime path
    probe FMP). Known-blocked combos (from live probe + runtime-observed
    402s) short-circuit to False. This keeps the support set open-ended
    — we don't need to enumerate every US stock.
    """
    itv = INTERVAL_MAP.get(interval)
    if itv is None:
        return False
    fmp_sym = _resolve_fmp_symbol(symbol)
    if (fmp_sym, itv) in EXPLICIT_BLOCKED:
        return False
    if (fmp_sym, itv) in _RUNTIME_BLOCKED:
        return False
    return True


def _mark_blocked(fmp_sym: str, itv_fmp: str) -> None:
    """Runtime record that (fmp_sym, itv_fmp) responded 402. Prevents
    future retries for this process lifetime."""
    _RUNTIME_BLOCKED.add((fmp_sym, itv_fmp))
    logger.info(
        f"FMP runtime block-set updated: {fmp_sym} @ {itv_fmp} "
        f"(Starter plan does not cover this combo)"
    )


def _parse_bars(payload: list, symbol: str) -> List[MarketData]:
    """Convert FMP JSON list → List[MarketData]. One item per bar.

    Robust to float vs str in fields; drops any bar with non-numeric OHLC.
    """
    bars: List[MarketData] = []
    for row in payload:
        try:
            ts_str = row["date"]
            # FMP timestamps are tz-naive local (US market time for equities,
            # UTC for 24h assets). Parse as naive and trust downstream
            # consumers — market_data_manager normalises tz on DB write.
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            bars.append(MarketData(
                symbol=symbol,
                timestamp=ts,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0) or 0),
                source=DataSource.FMP,
            ))
        except (KeyError, ValueError, TypeError) as e:
            logger.debug(f"Skipping malformed FMP bar for {symbol}: {e}")
            continue
    # FMP returns newest-first; downstream expects oldest-first.
    bars.sort(key=lambda b: b.timestamp)
    return bars


def _fetch_page(
    api_key: str,
    fmp_symbol: str,
    interval_fmp: str,
    page_from: datetime,
    page_to: datetime,
) -> List[MarketData]:
    """Fetch one page (up to PAGE_WINDOW_DAYS[interval] span) with retries."""
    url = f"{BASE_URL}/{interval_fmp}"
    params = {
        "symbol": fmp_symbol,
        "from": page_from.strftime("%Y-%m-%d"),
        "to":   page_to.strftime("%Y-%m-%d"),
        "apikey": api_key,
    }
    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT_S)
            if r.status_code == 402:
                # Premium-blocked — fail-fast, no retry (the block is permanent)
                _mark_blocked(fmp_symbol, interval_fmp)
                raise FMPAPIError(
                    f"FMP premium-blocked: {fmp_symbol} {interval_fmp}",
                    reason="premium_blocked",
                )
            if r.status_code == 429:
                raise FMPAPIError(
                    f"FMP rate-limited (HTTP 429) for {fmp_symbol}",
                    reason="rate_limited",
                )
            if r.status_code != 200:
                raise FMPAPIError(
                    f"FMP HTTP {r.status_code} for {fmp_symbol}: {r.text[:200]}",
                    reason="network",
                )
            body = r.text
            # FMP returns {"Error Message": "..."} for invalid symbols,
            # "Premium Query Parameter..." for blocked, "[]" for empty.
            if "Premium Query Parameter" in body or "not available under your current subscription" in body:
                _mark_blocked(fmp_symbol, interval_fmp)
                raise FMPAPIError(
                    f"FMP premium-blocked: {fmp_symbol} {interval_fmp}",
                    reason="premium_blocked",
                )
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as je:
                raise FMPAPIError(
                    f"FMP parse error for {fmp_symbol}: {je}",
                    reason="parse_error",
                )
            if isinstance(payload, dict) and "Error Message" in payload:
                raise FMPAPIError(
                    f"FMP error for {fmp_symbol}: {payload['Error Message']}",
                    reason="network",
                )
            if not isinstance(payload, list):
                raise FMPAPIError(
                    f"FMP unexpected response shape for {fmp_symbol}",
                    reason="parse_error",
                )
            return _parse_bars(payload, fmp_symbol)
        except FMPAPIError:
            raise  # don't retry on classified errors
        except requests.RequestException as e:
            last_exc = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF_S * (attempt + 1))
                continue
            raise FMPAPIError(
                f"FMP network failure after {MAX_RETRIES} attempts: {e}",
                reason="network",
            ) from e
    raise FMPAPIError(f"FMP fetch exhausted retries: {last_exc}", reason="network")


def fetch_klines(
    symbol: str,
    start: datetime,
    end: datetime,
    interval: str,
    api_key: Optional[str] = None,
) -> List[MarketData]:
    """Fetch a full (start, end) window, paginated as needed.

    Args:
        symbol: Display form (AAPL, SPY, GOLD, EURUSD). Resolved to FMP
            ticker internally via SYMBOL_MAP.
        start: tz-naive or tz-aware UTC datetime (naive treated as UTC).
        end: tz-naive or tz-aware UTC datetime.
        interval: AlphaCent form (1h / 4h / 1d). Mapped to FMP's 1hour /
            4hour / 1day.
        api_key: Optional override; otherwise loaded from api_keys.yaml.

    Returns:
        List[MarketData] in ascending timestamp order. May be empty if
        the window has no bars (e.g. requested window before first listing).

    Raises:
        FMPAPIError: on unsupported symbol/interval, network failure,
            premium-blocked, rate-limit, or parse error.
    """
    itv_fmp = INTERVAL_MAP.get(interval)
    if itv_fmp is None:
        raise FMPAPIError(f"Unsupported interval '{interval}'", reason="unsupported")

    fmp_sym = _resolve_fmp_symbol(symbol)
    if (fmp_sym, itv_fmp) in EXPLICIT_BLOCKED or (fmp_sym, itv_fmp) in _RUNTIME_BLOCKED:
        raise FMPAPIError(
            f"FMP Starter does not cover {fmp_sym} @ {itv_fmp}",
            reason="premium_blocked",
        )

    key = api_key or _load_api_key()
    if not key:
        raise FMPAPIError("FMP api_key not configured", reason="unsupported")

    # Normalise tz to naive UTC for consistent math
    def _to_naive_utc(dt: datetime) -> datetime:
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    start_naive = _to_naive_utc(start)
    end_naive = _to_naive_utc(end)
    if start_naive >= end_naive:
        return []

    page_days = PAGE_WINDOW_DAYS[itv_fmp]

    # Generate (page_from, page_to) ranges covering [start, end].
    pages: List[Tuple[datetime, datetime]] = []
    cursor = start_naive
    while cursor < end_naive:
        page_to = min(cursor + timedelta(days=page_days), end_naive)
        pages.append((cursor, page_to))
        cursor = page_to

    # Single page: just fetch directly. Multi-page: parallel with 4 workers.
    if len(pages) == 1:
        return _fetch_page(key, fmp_sym, itv_fmp, pages[0][0], pages[0][1])

    all_bars: List[MarketData] = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {
            ex.submit(_fetch_page, key, fmp_sym, itv_fmp, pf, pt): (pf, pt)
            for pf, pt in pages
        }
        for fut in as_completed(futures):
            pf, pt = futures[fut]
            try:
                all_bars.extend(fut.result())
            except FMPAPIError as e:
                # Premium-blocked mid-pagination shouldn't happen (support
                # map already checked at the top). Network errors on one
                # page shouldn't kill the whole fetch — log and continue.
                if e.reason == "premium_blocked":
                    raise  # blocking error, propagate
                logger.warning(
                    f"FMP page fetch failed for {fmp_sym} {pf.date()}→{pt.date()} "
                    f"({e.reason}): {e}"
                )
                continue

    # Dedupe any overlap (pages are contiguous but returning bar-boundary
    # overlaps is a known FMP behaviour on some symbols).
    seen: set = set()
    deduped: List[MarketData] = []
    for b in all_bars:
        k = b.timestamp
        if k in seen:
            continue
        seen.add(k)
        deduped.append(b)
    deduped.sort(key=lambda b: b.timestamp)
    return deduped
