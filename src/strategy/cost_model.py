"""
Round-trip transaction cost model and edge-ratio helper (observability-only).

Centralizes cost-per-trade computation so analytics, logs, and the strategy
metadata all see a single consistent number. This module does NOT gate any
acceptance decision — it is pure measurement.

### Why observability-only (and not a filter)

Sprint 3 S3.0b (commit 25c9051) made a deliberate choice to loosen crypto
activation thresholds on DEMO for signal-data collection:

    min_sharpe_crypto:       0.5 → 0.3
    min_return_per_trade.crypto_{1d,4h,1h}: 0.035 → 0.030

with a documented revert path to 0.5 / 0.035 for live trading. Adding a
strict edge-ratio filter on top of that loosen would silently undo the
S3.0b intent. If the team decides to escalate edge-ratio to a gate, it
should be a deliberate Sprint 5 decision with yaml-configured thresholds
and a documented revert path — same pattern as S3.0b.

Until then, this module exposes:
  - `round_trip_cost_pct(symbol)` — per-symbol round-trip cost (read from
    config/autonomous_trading.yaml::backtest.transaction_costs)
  - `edge_ratio(gross_return, n_trades, symbol)` — gross_per_trade /
    round_trip_cost. Values: <1 unprofitable, 1.0 break-even,
    1.5+ live-tradable margin. Returned; never enforced by this module.
  - `format_edge_log(...)` — human-readable log line for cycle output.

Consumers:
  - `portfolio_manager._check_activation_criteria` — writes edge_ratio,
    gross_per_trade, cost_per_trade onto strategy.strategy_metadata for
    the Data Page. Does NOT gate activation.
  - `strategy_proposer` WF validation — logs thin-edge strategies at INFO
    for funnel visibility, stamps metrics on decision-log rows. Does NOT
    gate validation.

### Where the numbers come from

`round_trip_cost_pct` reads (in precedence order):
  1. `transaction_costs.per_symbol.<SYMBOL>.<field>` — per-instrument override
  2. `transaction_costs.per_asset_class.<class>.<field>` — asset-class config
  3. `transaction_costs.<field>`                        — global default
  4. Hard-coded fallback in this module (if yaml missing/malformed)

A round trip sums commission + spread + slippage, each applied on both entry
and exit sides. For crypto on eToro this comes to ~2.96% (1% commission ×2
+ 0.38% spread ×2 + 0.1% slippage ×2).

### What `edge_ratio` actually measures

  edge_ratio = (gross_return / n_trades) / round_trip_cost

It asks: "for every trade this strategy places, does the pre-cost move
cover the round-trip cost, and by how much?"

  <1.0   strategy cannot be profitable after costs
  1.0    break-even gross (net-zero after costs)
  1.5    comfortable live-trading margin
  2.0+   strong edge

Sharpe on hourly crypto can be artefactually high — vectorbt annualises
bar-level returns by sqrt(8760) and most bars are flat (out-of-market),
so a strategy with 0.02% gross-per-trade can show Sharpe 5. edge_ratio
surfaces the real per-trade economics independent of that artefact.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Config-file location. Matches the convention used elsewhere in the package.
_CONFIG_PATH = Path("config/autonomous_trading.yaml")

# Fallback values if the config is missing or malformed. Kept intentionally
# conservative so a mis-loaded config never silently relaxes the gate.
_FALLBACK_COSTS_PER_SIDE = {
    "stock": 0.0019,      # 15bps spread + 4bps slippage
    "etf": 0.0019,
    "forex": 0.0002,      # 1.5bps spread + 0.5bps slippage
    "crypto": 0.0148,     # 100bps commission + 38bps spread + 10bps slippage — eToro reality
    "index": 0.00025,
    "commodity": 0.0006,
}

# Minimum edge-ratio values used only as reference points in logs and on
# the Data Page. Nothing in this codebase uses them to gate a decision —
# they are purely documentary markers of where live-tradable edge starts.
EDGE_RATIO_BREAKEVEN = 1.0            # gross covers cost exactly (net=0)
EDGE_RATIO_LIVE_MARGIN = 1.5          # conservative live-trade margin (50% above cost)
# If and when the team decides to promote edge_ratio to a gate, the filter
# threshold should be added to config/autonomous_trading.yaml alongside
# min_sharpe / min_return_per_trade — NOT hardcoded here. That keeps the
# S3.0b revert-path convention consistent.


@lru_cache(maxsize=1)
def _load_cost_config() -> dict:
    """Read transaction_costs block once per process. LRU-cached."""
    try:
        import yaml
        if not _CONFIG_PATH.exists():
            logger.warning(
                f"cost_model: config not found at {_CONFIG_PATH} — using fallback"
            )
            return {}
        with open(_CONFIG_PATH, "r") as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("backtest", {}).get("transaction_costs", {}) or {}
    except Exception as exc:
        logger.warning(f"cost_model: failed to load config — using fallback: {exc}")
        return {}


def _asset_class_of(symbol: str) -> str:
    """Best-effort asset class inference from tradeable_instruments."""
    if not symbol:
        return "stock"
    try:
        from src.core.tradeable_instruments import (
            DEMO_ALLOWED_ETFS,
            DEMO_ALLOWED_FOREX,
            DEMO_ALLOWED_CRYPTO,
            DEMO_ALLOWED_INDICES,
            DEMO_ALLOWED_COMMODITIES,
        )
    except ImportError:
        return "stock"
    sym_u = symbol.upper()
    if sym_u in set(DEMO_ALLOWED_CRYPTO):
        return "crypto"
    if sym_u in set(DEMO_ALLOWED_FOREX):
        return "forex"
    if sym_u in set(DEMO_ALLOWED_ETFS):
        return "etf"
    if sym_u in set(DEMO_ALLOWED_INDICES):
        return "index"
    if sym_u in set(DEMO_ALLOWED_COMMODITIES):
        return "commodity"
    return "stock"


def round_trip_cost_pct(
    symbol: str,
    interval: str = "1d",
    asset_class: Optional[str] = None,
) -> float:
    """
    Return the round-trip (entry + exit) transaction cost as a decimal fraction.

    Example: 0.0296 for a 2.96% round-trip cost on crypto.

    Precedence (most specific wins):
      1. `transaction_costs.per_symbol.<SYMBOL>.<field>`       — per-instrument override
      2. `transaction_costs.per_asset_class.<class>.<field>`   — asset-class config
      3. `transaction_costs.<field>`                            — global default
      4. Hard-coded fallback in this module

    A round trip = commission + spread + slippage, all ×2 (entry + exit side).

    Args:
        symbol: Primary instrument symbol (BTC, AAPL, EURUSD, etc.)
        interval: Strategy bar interval — reserved for future per-interval
                  adjustments (not yet used, but callers pass it so we can
                  add it without signature changes).
        asset_class: Optional pre-computed asset class. If None, inferred
                     from symbol via tradeable_instruments.

    Returns:
        Round-trip cost as decimal fraction (0.0296 == 2.96%).
    """
    del interval  # Reserved for per-interval cost variations (not yet needed).
    tx = _load_cost_config()
    if asset_class is None:
        asset_class = _asset_class_of(symbol)

    # Per-symbol override — highest precedence.
    per_symbol = tx.get("per_symbol", {}) or {}
    sym_override = per_symbol.get(symbol.upper() if symbol else "", {}) or {}
    # Per-asset-class
    per_ac = tx.get("per_asset_class", {}).get(asset_class, {}) or {}

    def _resolve(field: str) -> float:
        if field in sym_override:
            return float(sym_override[field])
        if field in per_ac:
            return float(per_ac[field])
        if field in tx:
            return float(tx[field])
        # Module-level fallback so a malformed config can never yield 0.
        # We don't have per-field fallbacks — use the asset-class bundle.
        return _FALLBACK_COSTS_PER_SIDE.get(asset_class, 0.0019) / 3  # rough split

    commission_pct = _resolve("commission_percent")
    spread_pct = _resolve("spread_percent")
    slippage_pct = _resolve("slippage_percent")

    # One-way cost — commission is typically charged per side, spread is
    # half-spread per side (full bid-ask is a round-trip), slippage is
    # per-fill. Use the config numbers as already-per-side values, which
    # is the convention the backtest engine uses.
    one_side = commission_pct + spread_pct + slippage_pct

    # Sanity floor — if the config yields something absurdly low (<1bps),
    # fall back to asset-class default. Prevents a mis-typed 0 from silently
    # turning the edge-ratio gate off.
    if one_side < 0.0001:
        fallback = _FALLBACK_COSTS_PER_SIDE.get(asset_class, 0.0019)
        logger.warning(
            f"cost_model: computed one-side cost for {symbol} {asset_class} "
            f"is {one_side:.5%}, below 1bps floor — using fallback {fallback:.4%}"
        )
        return fallback * 2  # round trip

    return one_side * 2


def edge_ratio(
    gross_return: float,
    n_trades: int,
    symbol: str,
    interval: str = "1d",
    asset_class: Optional[str] = None,
) -> tuple[float, float, float]:
    """
    Compute the edge ratio for a backtest result.

    Edge ratio = gross_per_trade / round_trip_cost_per_trade

    Values:
      < 1.0   strategy is economically unprofitable — gross edge doesn't cover cost
      1.0     break-even gross (net-zero after costs)
      1.5     comfortable margin for live trading (our activation floor)
      2.0+    strong edge — real alpha

    Args:
        gross_return: Total gross return across the backtest (pre-cost).
                      For vectorbt backtests this is `portfolio.total_return()`.
        n_trades: Number of complete trades (entries).
        symbol: Primary instrument symbol.
        interval: Bar interval.
        asset_class: Optional pre-computed asset class.

    Returns:
        Tuple of (edge_ratio, gross_per_trade, round_trip_cost_pct).
        If n_trades <= 0, returns (0.0, 0.0, round_trip_cost_pct).
    """
    rtc = round_trip_cost_pct(symbol, interval, asset_class)
    if n_trades <= 0 or rtc <= 0:
        return 0.0, 0.0, rtc
    gross_per_trade = gross_return / n_trades
    return gross_per_trade / rtc, gross_per_trade, rtc


def format_edge_log(
    strategy_name: str,
    gross_return: float,
    n_trades: int,
    symbol: str,
    interval: str = "1d",
    asset_class: Optional[str] = None,
) -> str:
    """Human-readable edge-ratio log line for use in WF and activation logs."""
    ratio, gpt, rtc = edge_ratio(gross_return, n_trades, symbol, interval, asset_class)
    return (
        f"{strategy_name}: gross={gross_return:.2%} on {n_trades} trades "
        f"→ gross/trade={gpt:.3%}, cost/trade={rtc:.3%}, edge_ratio={ratio:.2f}"
    )
