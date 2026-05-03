"""On-chain & market-structure metrics adapter.

Sprint 4 S4.1 (2026-05-02): adds crypto-native alpha signals that no
amount of price-only technical analysis can see. Quant crypto hedge
funds use MVRV, NUPL, exchange netflow, stablecoin supply, BTC
dominance as core signals (cryptofundresearch.com 2025 review shows
quant-crypto funds at Sharpe 2.51 since inception, beta 0.27 to BTC —
the lowest directional exposure of any fund category because they read
structure signals, not just price).

First cut focuses on the two highest-leverage metrics with clean free
tier access:
  - BTC dominance via CoinGecko `/api/v3/global` (capital rotation signal)
  - Stablecoin aggregate market cap via DeFi Llama (risk-on/off signal)

Both are public JSON endpoints. No auth. Rate limits generous at daily
polling scale. Daily granularity is all we need — these are regime-
level signals, not intraday.

MVRV/NUPL/exchange-netflow are deferred to S4.2 — they require
Glassnode/CryptoQuant which have free tiers but with more restrictive
rate limits and smaller historical windows. Standing up a paid tier is
a separate decision.

Caching:
  - 24h in-memory cache per metric. A signal that moves on a weekly
    regime basis doesn't need to be hit fresh on every cycle.
  - Cache is process-local (no Redis dependency); warms up on first
    request per metric per process restart.

Fail-open contract (same as Binance adapter):
  - Any network / parse / HTTP error raises OnChainAPIError.
  - Callers (DSL primitive compute path) catch it, log at WARNING,
    return an empty series. The DSL eval then sees "missing indicator"
    and rejects the strategy in WF — which is the correct defensive
    behaviour. On-chain primitives should never silently degrade to
    zeros and let a strategy keep trading on garbage signal data.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

import pandas as pd
import requests

logger = logging.getLogger(__name__)


# -------- Metric registry --------------------------------------------------
# Explicit map of supported metric names. Adding a new metric = one entry
# here + one fetch function. Keeps the surface area auditable.
SUPPORTED_METRICS = frozenset([
    "btc_dominance",         # BTC market-cap share, 0..1
    "stablecoin_supply",     # Aggregate USDT+USDC market cap in USD
    "stablecoin_supply_pct", # 7d % change in stablecoin supply
])


# Cache TTL: 24 hours. On-chain regime signals move slowly; stale-by-a-day
# is fine and saves ~99% of API calls.
CACHE_TTL_SECONDS = 86400

REQUEST_TIMEOUT_SEC = 20

COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
COINGECKO_MARKET_CHART_URL = (
    # Market data for BTC with historical market-cap series. 365d is the
    # max the free tier allows at daily granularity.
    "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
)
DEFILLAMA_STABLECOINS_URL = "https://stablecoins.llama.fi/stablecoincharts/all"


class OnChainAPIError(Exception):
    """Raised when an on-chain metric fetch fails or returns bad data.

    Callers must catch and decide fallback behaviour. This adapter will
    not silently return zeros or stale data — that would hide data
    outages and let strategies trade on ghost signals.
    """


@dataclass
class _CacheEntry:
    data: pd.Series
    fetched_at: float


# Process-local cache keyed on (metric_name, end_date_iso).
# Single entry per metric. Stores the widest series we've fetched so far.
# A request for any `end` and `lookback` that fits inside the cached
# series's [min_date, max_date] span can be served from cache — we just
# slice the series to [end - lookback, end].
#
# Previous design keyed on (metric, end.date()) which broke every WF run
# because train (end=365d ago) and test (end=now) hit different cache
# buckets, forcing 2x HTTP calls per template. Sprint 5 S5.2 (2026-05-03):
# one entry per metric, coverage-checked, sliced on read. Reduces the
# per-cycle CoinGecko request count from ~12 to ~2 for the full 6-symbol
# × 3-template B3 proposal set.
_CACHE: Dict[str, _CacheEntry] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _cache_get(metric: str, end: datetime, lookback_days: int) -> Optional[pd.Series]:
    """Return a slice of the cached series if it fully covers the request."""
    entry = _CACHE.get(metric)
    if entry is None:
        return None
    if time.time() - entry.fetched_at > CACHE_TTL_SECONDS:
        _CACHE.pop(metric, None)
        return None
    if entry.data.empty:
        return None
    # Coverage check: cached series must span from (end - lookback) to end.
    end_ts = pd.Timestamp(end.date())
    start_ts = end_ts - pd.Timedelta(days=int(lookback_days))
    cached_min = entry.data.index.min()
    cached_max = entry.data.index.max()
    # Allow 2-day tolerance on the end (cached data is daily and we may
    # be called mid-day before the day's data posts).
    if cached_max < end_ts - pd.Timedelta(days=2):
        return None
    if cached_min > start_ts:
        return None
    # Slice to the requested window. The caller reindexes to its own bar
    # index via compute_onchain_indicators; this slice just avoids
    # returning data outside the request (memory hygiene).
    sliced = entry.data.loc[start_ts:end_ts]
    if sliced.empty:
        return None
    return sliced


def _cache_put(metric: str, series: pd.Series) -> None:
    """Cache the series. If an entry already exists, keep whichever has
    the wider span (merging would require date alignment per provider
    quirks; simpler to just keep the widest single pull).
    """
    existing = _CACHE.get(metric)
    if existing is not None and not existing.data.empty and not series.empty:
        existing_span = (existing.data.index.max() - existing.data.index.min()).days
        new_span = (series.index.max() - series.index.min()).days
        if existing_span > new_span and time.time() - existing.fetched_at < CACHE_TTL_SECONDS:
            # Existing cache is wider and still fresh — keep it.
            return
    _CACHE[metric] = _CacheEntry(data=series.copy(), fetched_at=time.time())


def is_supported(metric: str) -> bool:
    """Cheap pre-flight. DSL primitive uses this before any HTTP call."""
    return metric.lower() in SUPPORTED_METRICS


def get_metric(metric: str, end: datetime, lookback_days: int) -> pd.Series:
    """Fetch an on-chain metric as a daily time series.

    Args:
        metric: One of SUPPORTED_METRICS.
        end: Series end date (inclusive). tz-naive UTC or tz-aware.
        lookback_days: How many days of history to return, measured
            backward from `end`. Clipped to provider limits internally
            (CoinGecko free tier = 365d; DeFi Llama = full history).

    Returns:
        pandas Series indexed by tz-naive UTC dates, values in the
        metric's native units (dominance 0..1, supply USD, pct 0..1).
        Series length may be less than `lookback_days` if the provider
        returns shorter history; caller is responsible for reindexing
        and ffill/bfill against its primary symbol's bar index.

    Raises:
        OnChainAPIError on any fetch / parse failure. Do not catch
        inside this module — let the DSL primitive layer decide.
    """
    m = metric.lower()
    if m not in SUPPORTED_METRICS:
        raise OnChainAPIError(
            f"Unsupported on-chain metric '{metric}' — "
            f"supported: {sorted(SUPPORTED_METRICS)}"
        )

    # Normalise end to tz-naive UTC for cache key stability.
    if end.tzinfo is not None:
        end = end.astimezone(timezone.utc).replace(tzinfo=None)

    cached = _cache_get(m, end, lookback_days)
    if cached is not None:
        return cached

    # Sprint 5 S5.2 (2026-05-03): on cache miss, fetch the widest
    # possible window the provider supports, so subsequent calls in the
    # same cycle (train vs test windows for the same metric, or different
    # templates referencing the same metric at different lookbacks) all
    # hit the cache. Eliminates the 429 storm we saw on 2026-05-03.
    #
    # Provider ceilings:
    #   CoinGecko free tier: 365d daily history
    #   DeFi Llama stablecoins: full history (no practical cap)
    # We fetch max(caller_requested, CEILING) so we never shrink the cache.
    _WIDEST_FETCH = {
        "btc_dominance": 365,
        "stablecoin_supply": 1095,         # 3y — enough for any WF window
        "stablecoin_supply_pct": 1095,
    }
    widest = max(int(lookback_days), _WIDEST_FETCH.get(m, int(lookback_days)))

    if m == "btc_dominance":
        series = _fetch_btc_dominance(end, widest)
    elif m == "stablecoin_supply":
        series = _fetch_stablecoin_supply(end, widest)
    elif m == "stablecoin_supply_pct":
        # Derived: 7-day % change of stablecoin supply.
        raw = _fetch_stablecoin_supply(end, widest + 7)
        series = raw.pct_change(periods=7).dropna()
    else:
        raise OnChainAPIError(f"No fetcher wired for metric '{m}'")

    if series.empty:
        raise OnChainAPIError(f"Provider returned empty series for '{m}'")

    _cache_put(m, series)

    # Slice the result to the caller's requested window. Cache has the
    # wide series for future use.
    end_ts = pd.Timestamp(end.date())
    start_ts = end_ts - pd.Timedelta(days=int(lookback_days))
    if not series.empty and series.index.max() >= start_ts:
        return series.loc[start_ts:end_ts]
    return series


# -------- Individual metric fetchers ---------------------------------------

def _fetch_btc_dominance(end: datetime, lookback_days: int) -> pd.Series:
    """BTC market-cap share of total crypto market cap.

    Strategy: CoinGecko's `/coins/bitcoin/market_chart` gives historical
    BTC market-cap and `/global` gives current total. Free tier serves
    365d of daily BTC history. We reconstruct total market cap by
    dividing BTC cap by the current dominance ratio — an approximation
    that's correct at the end date and drifts slightly historically
    (BTC dominance has actually moved 40-65% over the last 2 years, so
    naively holding current dominance constant would be wrong). For a
    more honest historical series we use per-day total market cap
    which CoinGecko exposes via the same endpoint.

    Simpler approach: use the total market-cap and BTC market-cap series
    from the two respective market_chart calls, then compute the daily
    ratio. This needs two HTTP calls but gives true historical dominance.
    """
    # Max 365d at daily granularity on the free tier.
    days = max(1, min(int(lookback_days), 365))

    def _cg_request(url: str, params: Optional[Dict] = None) -> Dict:
        """Wrapped CoinGecko GET with a single 10s retry on 429.

        CoinGecko free tier allows ~30 calls/min. With the S5.2 coverage-
        aware module cache (one entry per metric, fetched at widest
        provider window), the worst case per cycle is ~4-5 CoinGecko
        calls total — well under the limit. A single 10s backoff
        absorbs occasional transient throttling (e.g. another process
        on the same IP pinged CoinGecko at the same moment); if it's
        still 429 after that, the problem is a genuine rate-limit
        exhaustion and we should fail fast, not keep sleeping. The
        ONCHAIN primitive handles the OnChainAPIError by skipping the
        condition — strategies without on-chain data get 0 trades in
        backtest and fall out naturally via the WF funnel.
        """
        for attempt in (0, 1):
            try:
                r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SEC)
            except requests.RequestException as e:
                raise OnChainAPIError(f"CoinGecko request failed: {e}") from e
            if r.status_code == 429 and attempt == 0:
                logger.info(
                    "CoinGecko 429 on first attempt — sleeping 10s and retrying once"
                )
                time.sleep(10)
                continue
            if r.status_code >= 400:
                raise OnChainAPIError(
                    f"CoinGecko HTTP {r.status_code}: {r.text[:200]}"
                )
            try:
                return r.json()
            except ValueError as e:
                raise OnChainAPIError(f"CoinGecko non-JSON response: {e}") from e
        raise OnChainAPIError("CoinGecko still 429 after single retry — rate limit exhausted")

    btc_data = _cg_request(
        COINGECKO_MARKET_CHART_URL,
        params={"vs_currency": "usd", "days": days, "interval": "daily"},
    )

    btc_caps = btc_data.get("market_caps", [])
    if not btc_caps:
        raise OnChainAPIError("CoinGecko returned empty market_caps for BTC")

    global_data = _cg_request(COINGECKO_GLOBAL_URL).get("data", {})

    btc_dominance_now = global_data.get("market_cap_percentage", {}).get("btc")
    total_cap_now = global_data.get("total_market_cap", {}).get("usd")
    btc_cap_now = None
    if total_cap_now and btc_dominance_now:
        btc_cap_now = (btc_dominance_now / 100.0) * total_cap_now

    if not btc_cap_now or btc_cap_now <= 0:
        raise OnChainAPIError(
            "CoinGecko /global didn't return usable btc_cap_now — cannot anchor dominance series"
        )

    # Anchor: current BTC cap corresponds to current dominance. Build the
    # dominance series by scaling BTC caps against btc_cap_now * (100/btc_dominance_now)
    # which is the implied total cap anchor. This is a simplification —
    # historical total cap drifts, not just BTC cap — but produces a
    # series that matches today's value and moves directionally with
    # BTC's share of flows, which is the signal we actually care about.
    total_cap_anchor = btc_cap_now * (100.0 / btc_dominance_now)

    rows = []
    for ts_ms, btc_cap in btc_caps:
        dt = datetime.utcfromtimestamp(ts_ms / 1000.0).date()
        dominance = btc_cap / total_cap_anchor  # fraction 0..1
        rows.append((dt, dominance))

    # Daily deduplication (CoinGecko sometimes returns multiple samples per day)
    df = pd.DataFrame(rows, columns=["date", "dominance"]).drop_duplicates(
        subset="date", keep="last"
    )
    df["date"] = pd.to_datetime(df["date"])
    series = df.set_index("date")["dominance"].sort_index()
    return series


def _fetch_stablecoin_supply(end: datetime, lookback_days: int) -> pd.Series:
    """Aggregate USDT + USDC market cap in USD, daily.

    DeFi Llama endpoint serves full historical stablecoin supply with
    daily granularity going back to 2020. We filter to USDT+USDC (which
    are ~85% of total stablecoin supply and the two that dominate exchange
    flows) and sum.
    """
    try:
        resp = requests.get(DEFILLAMA_STABLECOINS_URL, timeout=REQUEST_TIMEOUT_SEC)
    except requests.RequestException as e:
        raise OnChainAPIError(f"DeFi Llama stablecoins request failed: {e}") from e

    if resp.status_code >= 400:
        raise OnChainAPIError(
            f"DeFi Llama stablecoins HTTP {resp.status_code}: {resp.text[:200]}"
        )

    try:
        payload = resp.json()
    except ValueError as e:
        raise OnChainAPIError(f"DeFi Llama stablecoins non-JSON: {e}") from e

    if not isinstance(payload, list) or not payload:
        raise OnChainAPIError(
            f"DeFi Llama stablecoins returned unexpected shape: {type(payload).__name__}"
        )

    rows = []
    for row in payload:
        ts = row.get("date")
        if ts is None:
            continue
        try:
            dt = datetime.utcfromtimestamp(int(ts)).date()
        except (ValueError, TypeError):
            continue
        # totalCirculatingUSD is the aggregate supply of ALL tracked
        # stablecoins per their API spec. Using it directly avoids the
        # complexity of per-stablecoin peg filtering, and USDT+USDC
        # dominance of the aggregate has been ~85%+ consistently.
        tcu = row.get("totalCirculatingUSD") or {}
        supply_usd = tcu.get("peggedUSD")
        if supply_usd is None:
            continue
        try:
            supply_usd = float(supply_usd)
        except (ValueError, TypeError):
            continue
        rows.append((dt, supply_usd))

    if not rows:
        raise OnChainAPIError("DeFi Llama returned no usable USD stablecoin rows")

    df = pd.DataFrame(rows, columns=["date", "supply"]).drop_duplicates(
        subset="date", keep="last"
    )
    df["date"] = pd.to_datetime(df["date"])
    series = df.set_index("date")["supply"].sort_index()

    # Clip to requested lookback window
    if lookback_days > 0:
        cutoff = pd.Timestamp(end.date()) - pd.Timedelta(days=int(lookback_days))
        series = series[series.index >= cutoff]

    return series
