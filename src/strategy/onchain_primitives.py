"""On-chain DSL primitives — Sprint 4 S4.1 (2026-05-02).

Adds first-class ONCHAIN("metric_name", lookback_days) support to the
DSL. Mirrors the architectural pattern of Sprint 1 F1 cross-asset
primitives: regex-extract references from condition strings, compute
series, return dict of {indicator_key: pd.Series} for merge into the
primary indicators dict before DSL eval.

The ONCHAIN primitive lets templates reference market-structure signals
that no price-only technical indicator can see:

  ONCHAIN("btc_dominance", 7) < 0.55 AND ADX(14) > 20
  ONCHAIN("stablecoin_supply_pct", 7) > 0.05

All metrics defined in src/api/onchain_client.SUPPORTED_METRICS are
accessible. Each metric is fetched once per process (24h TTL cache) and
aligned to the primary symbol's bar index via forward-fill — the same
alignment strategy used for cross-asset series.

Indicator key format: `ONCHAIN__<metric>__<lookback>` (no symbol in the
key because on-chain metrics are global, not per-symbol).

Fail-closed semantics (matches cross-asset primitives): fetch failures
produce an empty/NaN series; DSL eval sees missing values and the
comparison resolves to False, which correctly rejects the strategy in
WF rather than firing entries on garbage data.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


# Match ONCHAIN("metric_name", N) references. metric_name is quoted
# lowercase identifier; N is positive integer lookback days.
_RE_ONCHAIN = re.compile(
    r'ONCHAIN\(\s*"([a-zA-Z_][a-zA-Z0-9_]*)"\s*,\s*(\d+)\s*\)'
)


def extract_onchain_references(conditions: List[str]) -> List[Tuple[str, int]]:
    """Scan entry+exit condition strings for ONCHAIN references.

    Returns:
        List of (metric_name, lookback_days) tuples. Deduplicated.
    """
    refs: List[Tuple[str, int]] = []
    for cond in conditions:
        for m in _RE_ONCHAIN.finditer(cond):
            ref = (m.group(1), int(m.group(2)))
            if ref not in refs:
                refs.append(ref)
    return refs


def indicator_key(metric: str, lookback: int) -> str:
    """Deterministic indicator key for DSL lookup.

    Must match `trading_dsl.INDICATOR_MAPPING['ONCHAIN']` so the eval'd
    code finds the series we compute here.
    """
    return f"ONCHAIN__{metric.lower()}__{lookback}"


def compute_onchain_indicators(
    conditions: List[str],
    primary_index: pd.DatetimeIndex,
) -> Dict[str, pd.Series]:
    """Compute all ONCHAIN indicator Series referenced by DSL conditions.

    Single entry point called by backtest + live signal-gen paths, same
    contract as cross_asset_primitives.compute_cross_asset_indicators.

    Args:
        conditions: combined entry + exit condition strings
        primary_index: DatetimeIndex of the primary symbol's bars

    Returns:
        Dict {indicator_key: pd.Series} — one entry per unique
        (metric, lookback). Empty if conditions have no ONCHAIN refs
        (most templates). Series are aligned to `primary_index` via
        forward-fill; missing data produces NaN so DSL comparisons
        evaluate False and the strategy correctly rejects entries.
    """
    refs = extract_onchain_references(conditions)
    out: Dict[str, pd.Series] = {}

    if not refs:
        return out

    if primary_index is None or len(primary_index) == 0:
        logger.warning(
            "compute_onchain_indicators: empty primary_index — returning empty dict"
        )
        return out

    try:
        from src.api.onchain_client import get_metric, is_supported, OnChainAPIError
    except ImportError as e:
        logger.warning(
            f"OnChain client import failed ({e}) — ONCHAIN primitives will fail-closed"
        )
        for metric, lookback in refs:
            out[indicator_key(metric, lookback)] = pd.Series(
                float("nan"), index=primary_index
            )
        return out

    # Fetch the widest lookback window we need for each metric (saves HTTP
    # calls when multiple rules reference the same metric at different
    # lookbacks — e.g. one rule uses 7d and another uses 30d; we fetch
    # once for 30d and the 7d derivation is free).
    by_metric: Dict[str, int] = {}
    for metric, lookback in refs:
        by_metric[metric] = max(by_metric.get(metric, 0), lookback)

    # Use primary_index.max() as the anchor end date so the on-chain series
    # matches the backtest period rather than "now".
    end_dt = primary_index.max().to_pydatetime()
    if hasattr(end_dt, "tzinfo") and end_dt.tzinfo is not None:
        end_dt = end_dt.replace(tzinfo=None)

    # A little safety margin so a 7d-lookback rule on day-1 of the primary
    # index still has 7d of on-chain history to reference. 60 days covers
    # the longest practical regime-level lookback we'd use (quarterly).
    SAFETY_MARGIN_DAYS = 60

    metric_series: Dict[str, pd.Series] = {}
    for metric, max_lookback in by_metric.items():
        if not is_supported(metric):
            logger.warning(
                f"ONCHAIN: unsupported metric '{metric}' — series will be NaN"
            )
            continue
        try:
            fetched = get_metric(
                metric, end=end_dt, lookback_days=max_lookback + SAFETY_MARGIN_DAYS
            )
        except OnChainAPIError as e:
            logger.warning(f"ONCHAIN fetch failed for '{metric}': {e}")
            continue
        except Exception as e:
            logger.error(
                f"ONCHAIN unexpected error for '{metric}': {e}", exc_info=True
            )
            continue
        metric_series[metric] = fetched

    # Now emit the indicator dict, one entry per unique (metric, lookback).
    # Series are reindexed+ffilled onto primary_index so the DSL eval
    # sees an aligned value at every bar.
    for metric, lookback in refs:
        key = indicator_key(metric, lookback)
        raw = metric_series.get(metric)
        if raw is None or raw.empty:
            out[key] = pd.Series(float("nan"), index=primary_index)
            continue
        # Forward-fill the daily on-chain series onto the primary bar
        # index. On-chain signals are inherently daily; when the primary
        # is intraday (1h/4h), every bar within a day gets the same value.
        aligned = raw.reindex(primary_index, method="ffill")
        out[key] = aligned
        logger.info(
            f"ONCHAIN computed: key={key} primary_bars={len(primary_index)} "
            f"non_nan={int(aligned.notna().sum())} "
            f"last_value={aligned.iloc[-1] if len(aligned) else 'N/A'}"
        )

    return out
