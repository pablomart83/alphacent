"""
Cross-asset DSL primitives — Sprint 1 F1 (2026-05-02).

Adds first-class support for cross-asset signals in the DSL.

Previously, templates with cross-asset edge (BTC lead-lag, cross-sectional
momentum) carried their logic as metadata flags (`btc_leader`,
`cross_sectional_rank`) which were only evaluated at live signal-generation
time in `strategy_engine.generate_signals`. The backtest and walk-forward
paths never saw the cross-asset condition, so WF systematically rejected
these templates even when they had real edge — because the backtest was
just the local technical setup (EMA + RSI) with no cross-asset filter.

This module makes the cross-asset signals first-class indicators. The DSL
parser extensions (in `trading_dsl.py`) let templates express:

  LAG_RETURN("BTC", 2, "1h") > 0.01
  RANK_IN_UNIVERSE("SELF", ["BTC","ETH","SOL","AVAX","LINK","DOT"], 14, 3) > 0

This module computes the Series for each such reference and returns them
ready to merge into the primary indicators dict. Both backtest and
signal-gen paths call this before rule evaluation, so the edge signal
computed in backtest is byte-identical to the one fired in live.

Architectural note: this is the "proper solution" replacement for the dead
runtime gates at strategy_engine.py:4265-4400. Those gates MUST be removed
after the templates are migrated — leaving them active would cause the
condition to be tested twice (once in DSL via LAG_RETURN, once in metadata
gate) which would only pass entries that satisfy both, silently tightening
the gate.
"""

import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Callable, Any

import pandas as pd

logger = logging.getLogger(__name__)


# Regex patterns matching the DSL primitives. Match what the parser produces
# on LAG_RETURN("BTC", 2, "1h") and RANK_IN_UNIVERSE("SELF", [...], 14, 3).
# We parse from the raw condition strings (not the AST) because the caller
# provides strategy.rules which are plain text. Robustness note: the regex
# tolerates arbitrary whitespace inside parens and the quoted arguments.
_RE_LAG_RETURN = re.compile(
    r'LAG_RETURN\(\s*"([A-Za-z0-9_]+)"\s*,\s*(\d+)\s*,\s*"([A-Za-z0-9_]+)"\s*\)'
)
_RE_RANK_IN_UNIVERSE = re.compile(
    r'RANK_IN_UNIVERSE\(\s*"([A-Za-z0-9_]+)"\s*,\s*'
    r'(\[[^\]]+\])'            # universe list as-is
    r'\s*,\s*(\d+)\s*,\s*(\d+)\s*\)'
)


def _universe_hash(universe: List[str]) -> str:
    """Produce an 8-char deterministic tag for a universe list.

    Must match the hashing used in `trading_dsl._rank_in_universe_key` so
    the DSL-generated lookup key is the same string we write into the
    indicators dict.
    """
    uni_sorted = sorted(str(s) for s in universe)
    return hashlib.md5(','.join(uni_sorted).encode()).hexdigest()[:8]


def extract_cross_asset_references(conditions: List[str]) -> Tuple[
    List[Tuple[str, int, str]],            # LAG_RETURN refs: (symbol, bars, interval)
    List[Tuple[str, List[str], int, int]]  # RANK_IN_UNIVERSE refs: (self_sym, universe, window, top_n)
]:
    """Scan entry+exit condition strings for cross-asset primitive references.

    Args:
        conditions: list of DSL condition strings

    Returns:
        Tuple of (lag_return_refs, rank_in_universe_refs). Each ref is a tuple
        of parsed parameters. Returns empty lists if no cross-asset refs
        found (most non-crypto templates).
    """
    lag_refs = []
    rank_refs = []
    for cond in conditions:
        for match in _RE_LAG_RETURN.finditer(cond):
            sym, bars_str, interval = match.group(1), match.group(2), match.group(3)
            ref = (sym, int(bars_str), interval)
            if ref not in lag_refs:
                lag_refs.append(ref)
        for match in _RE_RANK_IN_UNIVERSE.finditer(cond):
            self_sym, uni_str, window_str, topn_str = (
                match.group(1), match.group(2), match.group(3), match.group(4)
            )
            # Parse universe list. The grammar guarantees it's a JSON-compatible
            # string like ["BTC","ETH",...], so json.loads works.
            import json
            try:
                universe = json.loads(uni_str)
            except Exception as e:
                logger.warning(f"Cross-asset: failed to parse universe '{uni_str}': {e}")
                continue
            if not isinstance(universe, list):
                continue
            universe = [str(s) for s in universe]
            ref = (self_sym, universe, int(window_str), int(topn_str))
            if ref not in rank_refs:
                rank_refs.append(ref)
    return lag_refs, rank_refs


def collect_required_cross_asset_symbols(
    conditions: List[str],
    primary_symbol: str,
) -> Dict[str, List[str]]:
    """List all external symbols a template's DSL needs pre-fetched.

    Args:
        conditions: entry + exit condition strings
        primary_symbol: the strategy's primary symbol (used to resolve "SELF")

    Returns:
        Dict mapping interval → list of unique symbol names that need pre-fetch.
        The primary symbol is NOT included (caller already has it).

    Intervals are returned separately because LAG_RETURN uses the template
    interval (1h/4h/1d) while RANK_IN_UNIVERSE always uses daily bars.
    """
    lag_refs, rank_refs = extract_cross_asset_references(conditions)
    required: Dict[str, set] = {}
    for sym, _bars, interval in lag_refs:
        if sym == primary_symbol or sym == "SELF":
            continue
        required.setdefault(interval, set()).add(sym)
    for _self_sym, universe, _window, _topn in rank_refs:
        # Rank always uses daily bars.
        day_set = required.setdefault("1d", set())
        for s in universe:
            if s != primary_symbol:
                day_set.add(s)
    return {k: sorted(list(v)) for k, v in required.items()}


def compute_lag_return_series(
    leader_df: pd.DataFrame,
    bars: int,
    primary_index: pd.DatetimeIndex,
) -> pd.Series:
    """Compute lag-return of a leader series aligned to the primary's index.

    Args:
        leader_df: DataFrame with 'close' column, indexed by timestamp at the
                   template's interval (1h/4h/1d). Must be tz-naive or aligned
                   with primary_index.
        bars: lookback bar count. Return = (close[t] - close[t - bars]) / close[t - bars]
        primary_index: DatetimeIndex of the primary symbol; output is
                       forward-filled and reindexed to this.

    Returns:
        pd.Series of floats aligned to primary_index. NaN where the leader
        hadn't accumulated enough history. Sorted ascending by timestamp.
    """
    if 'close' not in leader_df.columns:
        raise ValueError("leader_df must have 'close' column")
    leader_df = leader_df.copy()
    # Normalise timezone to match primary_index style.
    if hasattr(leader_df.index, 'tz') and leader_df.index.tz is not None:
        leader_df.index = leader_df.index.tz_localize(None)
    leader_df = leader_df[~leader_df.index.duplicated(keep='last')].sort_index()

    lag_ret = (leader_df['close'] - leader_df['close'].shift(bars)) / leader_df['close'].shift(bars)
    lag_ret = lag_ret.rename(f'lag_return_{bars}')
    # Align to primary index: forward-fill leader values onto primary bars.
    # This handles cases where leader is daily and primary is 1h (rare), or
    # where interval matches but bar counts differ by a few due to weekend/
    # gaps. Forward-fill is the correct semantic: "use the latest leader
    # return known at this bar".
    aligned = lag_ret.reindex(primary_index, method='ffill')
    return aligned


def compute_rank_in_universe_series(
    self_symbol: str,
    universe_daily_data: Dict[str, pd.DataFrame],
    window_days: int,
    top_n: int,
    primary_index: pd.DatetimeIndex,
) -> pd.Series:
    """Compute a boolean Series: True on bars where self_symbol is in top-N
    of the universe by window_days return.

    Args:
        self_symbol: The strategy's primary symbol (already substituted for
                     "SELF" by the caller).
        universe_daily_data: Dict {symbol: daily_df with 'close'}. Must include
                             self_symbol.
        window_days: Lookback days for the return ranking.
        top_n: How many top symbols count as "in the rank".
        primary_index: DatetimeIndex to align output to.

    Returns:
        Boolean pd.Series aligned to primary_index. True on days where
        self_symbol ranks in the top-N of the universe by N-day return.
        False elsewhere (including days with insufficient data).
    """
    if self_symbol not in universe_daily_data:
        logger.warning(
            f"Cross-asset RANK: self_symbol {self_symbol} not in universe data — "
            f"returning all-False"
        )
        return pd.Series(False, index=primary_index)

    # Compute N-day return for every symbol in the universe on their native
    # daily index.
    returns_by_sym: Dict[str, pd.Series] = {}
    for sym, df in universe_daily_data.items():
        if 'close' not in df.columns or df.empty:
            continue
        d = df.copy()
        if hasattr(d.index, 'tz') and d.index.tz is not None:
            d.index = d.index.tz_localize(None)
        d = d[~d.index.duplicated(keep='last')].sort_index()
        rets = (d['close'] - d['close'].shift(window_days)) / d['close'].shift(window_days)
        returns_by_sym[sym] = rets

    if self_symbol not in returns_by_sym:
        return pd.Series(False, index=primary_index)

    # Build a DataFrame of returns indexed by date × symbol. Align on a union
    # index so symbols with different data lengths don't drop rows we need.
    ret_df = pd.DataFrame(returns_by_sym)
    # Rank per row: True where self_symbol's return is in the top-N.
    # rank(axis=1, ascending=False, method='min') → 1 = highest return.
    ranks = ret_df.rank(axis=1, ascending=False, method='min')
    self_in_top = (ranks[self_symbol] <= top_n).fillna(False)

    # Align to primary index. Forward-fill so each bar sees the most recent
    # completed daily rank.
    aligned = self_in_top.reindex(primary_index, method='ffill').fillna(False).astype(bool)
    return aligned


def compute_cross_asset_indicators(
    conditions: List[str],
    primary_symbol: str,
    primary_index: pd.DatetimeIndex,
    data_fetcher: Callable[[str, datetime, datetime, str], Optional[pd.DataFrame]],
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Dict[str, pd.Series]:
    """Compute all cross-asset indicator Series referenced by the DSL conditions.

    This is the single entry point called by both backtest_strategy and
    generate_signals. Output keys match the keys produced by the DSL code
    generator (see `trading_dsl.INDICATOR_MAPPING['LAG_RETURN']` and
    `_rank_in_universe_key`), so the eval'd code looks them up correctly.

    Args:
        conditions: combined entry + exit condition strings
        primary_symbol: strategy's primary symbol (substituted for "SELF")
        primary_index: DatetimeIndex of the primary symbol's bars
        data_fetcher: callable (symbol, start, end, interval) → DataFrame
                      with at least 'close' column, or None on failure.
                      Caller is responsible for tz handling.
        start, end: date range bounds for fetches. Defaults to
                    [primary_index.min() - 60d, primary_index.max() + 1d] to
                    ensure enough warmup for lag/rank windows.

    Returns:
        Dict {indicator_key: pd.Series}. Empty if conditions have no
        cross-asset refs. Missing fetches produce best-effort NaN/False
        series (fail-closed in backtest: entries won't fire without data).
    """
    lag_refs, rank_refs = extract_cross_asset_references(conditions)
    out: Dict[str, pd.Series] = {}

    if not lag_refs and not rank_refs:
        return out

    if primary_index is None or len(primary_index) == 0:
        logger.warning("compute_cross_asset_indicators: empty primary_index — returning empty dict")
        return out

    # Compute fetch window with a safety margin for the longest lookback.
    if start is None:
        start = primary_index.min().to_pydatetime() - timedelta(days=60)
    if end is None:
        end = primary_index.max().to_pydatetime() + timedelta(days=1)

    # ── LAG_RETURN primitives ─────────────────────────────────────────
    for sym, bars, interval in lag_refs:
        # Resolve SELF sentinel (rare on LAG_RETURN but legal).
        target_sym = primary_symbol if sym == "SELF" else sym
        key = f'LAG_RETURN__{sym}__{bars}__{interval}'
        try:
            leader_df = data_fetcher(target_sym, start, end, interval)
            if leader_df is None or leader_df.empty or 'close' not in leader_df.columns:
                logger.warning(
                    f"Cross-asset LAG_RETURN fetch returned empty for "
                    f"{target_sym} {interval} — filling with NaN"
                )
                out[key] = pd.Series(float('nan'), index=primary_index)
                continue
            series = compute_lag_return_series(leader_df, bars, primary_index)
            out[key] = series
            logger.info(
                f"Cross-asset LAG_RETURN computed: key={key} "
                f"leader_bars={len(leader_df)} primary_bars={len(primary_index)} "
                f"non_nan={series.notna().sum()}"
            )
        except Exception as e:
            logger.error(
                f"Cross-asset LAG_RETURN failed for {target_sym} bars={bars} "
                f"interval={interval}: {e}", exc_info=True
            )
            # Fail-closed: NaN series means comparisons resolve to False.
            out[key] = pd.Series(float('nan'), index=primary_index)

    # ── RANK_IN_UNIVERSE primitives ──────────────────────────────────
    for self_sym, universe, window_days, top_n in rank_refs:
        # Substitute SELF with the strategy's primary symbol.
        resolved_self = primary_symbol if self_sym == "SELF" else self_sym
        uni_tag = _universe_hash(universe)
        key = f'RANK_IN_UNIVERSE__{self_sym}__{uni_tag}__{window_days}__{top_n}'
        try:
            # Fetch daily data for every symbol in universe (including the
            # resolved SELF — the ranking requires it).
            universe_data: Dict[str, pd.DataFrame] = {}
            for sym in universe:
                # Replace SELF in universe (uncommon but possible if author
                # literally lists SELF) to avoid double-fetching.
                actual_sym = primary_symbol if sym == "SELF" else sym
                df = data_fetcher(actual_sym, start, end, "1d")
                if df is None or df.empty:
                    logger.debug(
                        f"Cross-asset RANK: no daily data for {actual_sym} — excluded"
                    )
                    continue
                universe_data[actual_sym] = df
            if resolved_self not in universe_data:
                logger.warning(
                    f"Cross-asset RANK: primary symbol {resolved_self} has no "
                    f"daily data — key={key} will be all-False"
                )
                out[key] = pd.Series(False, index=primary_index)
                continue
            series = compute_rank_in_universe_series(
                resolved_self, universe_data, window_days, top_n, primary_index
            )
            # Store as int-coerceable (True=1, False=0) so DSL comparisons
            # like `RANK_IN_UNIVERSE(...) > 0` resolve correctly.
            out[key] = series
            logger.info(
                f"Cross-asset RANK_IN_UNIVERSE computed: key={key} "
                f"universe_size={len(universe_data)} primary_bars={len(primary_index)} "
                f"true_bars={int(series.sum())}"
            )
        except Exception as e:
            logger.error(
                f"Cross-asset RANK_IN_UNIVERSE failed for self={self_sym} "
                f"universe={universe}: {e}", exc_info=True
            )
            # Fail-closed: all-False means entries won't fire.
            out[key] = pd.Series(False, index=primary_index)

    return out
