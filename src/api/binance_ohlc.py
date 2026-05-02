"""Binance public-API historical OHLC fetcher.

Sprint 4 S4.0 (2026-05-02): lifts Yahoo Finance's ~7-month cap on 1h/4h
crypto data by reading from Binance's public `/api/v3/klines` endpoint.
This is the same source real crypto trading desks use for historical
backtesting — Binance has been the deepest spot-volume venue for BTC/
ETH since 2018 and their candles are the industry reference.

Scope and constraints:
  - Public endpoint only (`api.binance.com/api/v3/klines`). No auth, no
    keys, no user data. Read-only market data.
  - Rate limit: 1200 weight/min (each klines request is weight 1-10
    depending on limit param). At our scale — maybe 20 requests per
    backfill, run once per day — this is trivially within limits.
  - Max 1000 candles per request → pagination required for multi-year
    windows.
  - Interval mapping: AlphaCent `"1h"/"4h"/"1d"` → Binance `"1h"/"4h"/"1d"`.
  - Symbol mapping: display symbols (`BTC`, `ETH`, `SOL`, `AVAX`, `LINK`,
    `DOT`) → Binance pairs (`BTCUSDT`, `ETHUSDT`, ...). All our tradeable
    crypto symbols have USDT pairs on Binance with deep liquidity; the
    symbol map below is explicit per-symbol (no magic stringifying) so
    adding a symbol is an explicit one-line edit rather than a crash-at-
    runtime surprise.

Fail-open semantics:
  - Any network/parse/quota failure raises `BinanceAPIError` — callers
    (market_data_manager) catch it and fall back to Yahoo. Do NOT swallow
    errors silently inside this module; the caller needs to know the
    primary source failed so it can try the fallback and log the switch.

Time handling:
  - Input: accepts naive or tz-aware datetimes. Internally converts to
    UTC-naive to match the rest of the pipeline (see
    steering → Data Pipeline Critical Rules).
  - Output: `List[MarketData]` with `timestamp` as tz-naive UTC datetime,
    `source=DataSource.BINANCE`.

Binance kline format (index-positional array):
  [
    0: open_time_ms,
    1: open,
    2: high,
    3: low,
    4: close,
    5: volume,
    6: close_time_ms,
    7: quote_asset_volume,
    8: number_of_trades,
    9: taker_buy_base_asset_volume,
    10: taker_buy_quote_asset_volume,
    11: ignore
  ]
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

from src.models import DataSource, MarketData

logger = logging.getLogger(__name__)


BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"

# Explicit symbol map — display → Binance pair. We only trade 6 crypto
# symbols; listing them explicitly catches unknown-symbol requests at
# the boundary instead of returning 400 from Binance at runtime.
SYMBOL_MAP: Dict[str, str] = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "SOL": "SOLUSDT",
    "AVAX": "AVAXUSDT",
    "LINK": "LINKUSDT",
    "DOT": "DOTUSDT",
}

# Intervals Binance supports that we care about. Binance also supports
# 3m/5m/15m/30m/2h/6h/8h/12h/3d/1w/1M but we only use the three below.
INTERVAL_MAP: Dict[str, str] = {
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}

# Max candles per request per Binance spec.
BINANCE_MAX_LIMIT = 1000

# Request timeout — generous since Binance occasionally has ~3-5s latency
# for large range queries.
REQUEST_TIMEOUT_SEC = 20


class BinanceAPIError(Exception):
    """Raised when Binance API request fails or returns bad data.

    Callers (market_data_manager) catch this and fall back to Yahoo. Do
    not subclass requests.RequestException — we want the fallback path
    to treat any Binance problem uniformly, not just HTTP errors.
    """


def _to_utc_naive(dt: datetime) -> datetime:
    """Normalise to tz-naive UTC. Accepts aware or naive input.

    Matches the convention documented in
    .kiro/steering/trading-system-context.md → Data Pipeline Critical
    Rules (tz-aware UTC for I/O boundaries, tz-naive UTC internally).
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _to_ms(dt: datetime) -> int:
    """Unix epoch millis for a tz-naive UTC datetime (matching Binance's wire format)."""
    return int(_to_utc_naive(dt).replace(tzinfo=timezone.utc).timestamp() * 1000)


def is_supported(symbol: str, interval: str) -> bool:
    """Cheap pre-flight check — is this combo supported by the adapter?

    Used by market_data_manager to decide whether to try Binance first
    or skip straight to Yahoo. Keeping the check local means a brand
    new symbol won't cause a 400 round-trip to Binance; we just skip
    to fallback silently.
    """
    return symbol.upper() in SYMBOL_MAP and interval in INTERVAL_MAP


def fetch_klines(
    symbol: str,
    start: datetime,
    end: datetime,
    interval: str,
) -> List[MarketData]:
    """Fetch historical candles from Binance public API.

    Args:
        symbol: Display symbol (`BTC`, `ETH`, etc.). Converted to the
            Binance USDT pair internally.
        start: Window start (inclusive). Naive-UTC or tz-aware.
        end: Window end (exclusive, matches Binance semantics). Naive-UTC
            or tz-aware.
        interval: `"1h"`, `"4h"`, or `"1d"`.

    Returns:
        Chronologically-sorted list of `MarketData` with
        `source=DataSource.BINANCE`. Empty list if Binance returns zero
        candles for the window (genuine no-data, not an error).

    Raises:
        BinanceAPIError: on HTTP error, JSON parse failure, quota
            exceeded, or unsupported symbol/interval. Callers must
            handle this and fall back to Yahoo.
    """
    sym_upper = symbol.upper()
    if sym_upper not in SYMBOL_MAP:
        raise BinanceAPIError(
            f"Unsupported symbol '{symbol}' — add to SYMBOL_MAP to trade it via Binance"
        )
    if interval not in INTERVAL_MAP:
        raise BinanceAPIError(
            f"Unsupported interval '{interval}' — Binance adapter handles 1h/4h/1d only"
        )

    binance_pair = SYMBOL_MAP[sym_upper]
    binance_interval = INTERVAL_MAP[interval]

    start_ms = _to_ms(start)
    end_ms = _to_ms(end)

    if end_ms <= start_ms:
        # Not an error, just no window. Mirror yfinance behaviour
        # (empty return, not exception).
        return []

    all_bars: List[list] = []
    cursor_ms = start_ms
    # Pagination loop — Binance returns max 1000 candles per request.
    # Each candle bins at `interval`, so we advance the cursor by
    # `last_bar_open_time + 1ms` to avoid the boundary duplicate.
    loop_guard = 0
    MAX_LOOPS = 200  # 200k candles upper bound; 4-year 4h window = ~8760 candles
    while cursor_ms < end_ms and loop_guard < MAX_LOOPS:
        loop_guard += 1
        params = {
            "symbol": binance_pair,
            "interval": binance_interval,
            "startTime": cursor_ms,
            "endTime": end_ms,
            "limit": BINANCE_MAX_LIMIT,
        }
        try:
            resp = requests.get(
                BINANCE_KLINES_URL, params=params, timeout=REQUEST_TIMEOUT_SEC
            )
        except requests.RequestException as e:
            raise BinanceAPIError(
                f"Binance request failed for {binance_pair} {binance_interval}: {e}"
            ) from e

        if resp.status_code == 429:
            # Rate-limited. Unusual at our scale — surface as error so
            # the operator sees it rather than silently retrying in a
            # loop. Caller will fall back to Yahoo.
            raise BinanceAPIError(
                f"Binance rate limit hit (HTTP 429) for {binance_pair}; "
                f"back off and fall through to Yahoo"
            )
        if resp.status_code >= 400:
            raise BinanceAPIError(
                f"Binance HTTP {resp.status_code} for {binance_pair} "
                f"{binance_interval}: {resp.text[:200]}"
            )

        try:
            page = resp.json()
        except ValueError as e:
            raise BinanceAPIError(
                f"Binance returned non-JSON for {binance_pair}: {e}"
            ) from e

        if not isinstance(page, list):
            # Binance surfaces error bodies as JSON objects, not arrays.
            raise BinanceAPIError(
                f"Binance returned error body instead of candle array "
                f"for {binance_pair}: {page}"
            )

        if not page:
            # No more candles in the requested range — done.
            break

        all_bars.extend(page)

        # Advance cursor. Binance kline[0] is open_time_ms.
        last_open_ms = int(page[-1][0])
        # If Binance returned less than a full page we're at the end of
        # the available data — break to avoid an extra round-trip.
        if len(page) < BINANCE_MAX_LIMIT:
            break
        # Otherwise advance past the last bar's open. +1 ms prevents
        # boundary duplicates (consecutive pages would otherwise repeat
        # the last bar of the previous page).
        cursor_ms = last_open_ms + 1

    if loop_guard >= MAX_LOOPS:
        raise BinanceAPIError(
            f"Pagination guard tripped for {binance_pair} {binance_interval} "
            f"at {len(all_bars)} bars — window too wide or Binance misbehaving"
        )

    # Convert to MarketData. Candle indices per Binance API spec
    # (see module docstring).
    out: List[MarketData] = []
    for bar in all_bars:
        try:
            open_time_ms = int(bar[0])
            ts = datetime.utcfromtimestamp(open_time_ms / 1000.0)  # tz-naive UTC
            md = MarketData(
                symbol=sym_upper,
                timestamp=ts,
                open=float(bar[1]),
                high=float(bar[2]),
                low=float(bar[3]),
                close=float(bar[4]),
                volume=float(bar[5]),
                source=DataSource.BINANCE,
            )
            out.append(md)
        except (IndexError, ValueError, TypeError) as e:
            # One malformed bar shouldn't kill the whole fetch — skip
            # with a debug log, let callers see the bar count they got.
            logger.debug(f"Binance: skipping malformed bar for {binance_pair}: {e}")
            continue

    # Deduplicate on timestamp (pagination can overlap if the +1ms cursor
    # race doesn't exactly align to bar boundaries on fast follow-up runs).
    seen: Dict[datetime, MarketData] = {}
    for md in out:
        seen[md.timestamp] = md
    dedup = sorted(seen.values(), key=lambda m: m.timestamp)

    logger.info(
        f"Binance: fetched {len(dedup)} {binance_interval} bars for "
        f"{sym_upper} ({binance_pair}) "
        f"range {dedup[0].timestamp if dedup else 'N/A'} → "
        f"{dedup[-1].timestamp if dedup else 'N/A'}"
    )

    return dedup
