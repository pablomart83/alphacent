#!/usr/bin/env python3
"""
One-off diagnostic: verify the RPT / edge_ratio unit mismatch in
portfolio_manager.evaluate_for_activation + cost_model.edge_ratio.

Canonical case: Crypto BTC Follower 4H ETH LONG, cycle_1777803232,
from real log output 2026-05-03 10:19:27 UTC.

Production log lines (verbatim from alphacent.log):
    Position sizing statistics:
      Mean size: $11,956   Min: $11,874   Max: $12,002   Std dev: $44
    TRANSACTION COST ANALYSIS:
      Total trades: 6
      Commission cost: $1,434.69 (1.4347%)
      Slippage cost:   $143.47   (0.1435%)
      Spread cost:     $545.18   (0.5452%)
      Total tx costs:  $2,123.34 (2.1233%)
      Gross return (before costs): 7.11%
      Net return (after costs):    4.99%
    Edge-ratio thin at activation: gross/trade=1.185%, cost/trade=2.200%,
                                   edge_ratio=0.54
    Strategy failed activation: Return/trade 0.831% < 1.800% min
                                (crypto_4h+template_override, 6 trades, gross 5.0%)

No imports from src/ — pure math against observed log values.
"""

# ======================================================================
# OBSERVED VALUES (verbatim from logs)
# ======================================================================
INIT_CASH = 100_000.0
AVG_POSITION_SIZE = 11_956.0  # log: "Mean size: $11,956"
POSITION_SIZE_PCT = AVG_POSITION_SIZE / INIT_CASH  # ≈ 11.96%
N_TRADES = 6
NET_RETURN_INIT_CASH = 0.0499
GROSS_RETURN_INIT_CASH = 0.0711  # from log: "Gross return (before costs): 7.11%"

# Backtest engine used the generic crypto asset-class costs (1% + 0.38% + 0.1% per side)
# NOT the ETH per_symbol override (1% + 0.05% + 0.05%).
# This is the first finding — per_symbol is not read by strategy_engine.
CRYPTO_ASSET_CLASS_COST_PER_SIDE = 0.01 + 0.0038 + 0.001   # 1.48%
CRYPTO_ASSET_CLASS_ROUND_TRIP = 2 * CRYPTO_ASSET_CLASS_COST_PER_SIDE  # 2.96%

# ETH per_symbol override (what round_trip_cost_pct returns because cost_model
# DOES read per_symbol — so edge_ratio reports a cost that the backtest
# engine never actually used)
ETH_PER_SYMBOL_COST_PER_SIDE = 0.01 + 0.0005 + 0.0005
ETH_PER_SYMBOL_ROUND_TRIP = 2 * ETH_PER_SYMBOL_COST_PER_SIDE  # 2.20%

# Activation gate threshold
CRYPTO_4H_YAML_FLOOR = 0.030
TEMPLATE_REQUESTED = 0.015
SAFETY_FLOOR_60PCT = CRYPTO_4H_YAML_FLOOR * 0.6  # 0.018
EFFECTIVE_RPT_FLOOR = max(TEMPLATE_REQUESTED, SAFETY_FLOOR_60PCT)  # 0.018


def main() -> None:
    print("=" * 78)
    print("AlphaCent — BTC Follower 4H ETH cost / RPT / edge_ratio arithmetic")
    print("=" * 78)

    # ── Finding #1: config cost mismatch between backtest and edge_ratio ──
    print("\n── Finding #1: per_symbol cost override NOT read by backtest engine ──")
    expected_cost_eth = N_TRADES * 2 * AVG_POSITION_SIZE * ETH_PER_SYMBOL_COST_PER_SIDE
    expected_pct_eth = expected_cost_eth / INIT_CASH
    actual_cost = 2_123.34
    actual_pct = 0.021233

    print(f"  If backtest HAD read per_symbol.ETH (1%+0.05%+0.05% per side):")
    print(f"    Expected total cost: $"
          f"{expected_cost_eth:,.2f} ({expected_pct_eth:.3%} of init_cash)")
    print(f"  What backtest ACTUALLY computed (per_asset_class.crypto 1%+0.38%+0.1%):")
    print(f"    Actual total cost:   ${actual_cost:,.2f} ({actual_pct:.3%} of init_cash)")
    print(f"    Delta: ${actual_cost - expected_cost_eth:,.2f} — ETH backtest pays altcoin-rate.")
    print(f"    Root cause: strategy_engine.py:1247-1249 reads per_asset_class only.")

    # ── Finding #2: what the RPT gate measures vs what threshold meant ──
    print("\n── Finding #2: RPT gate unit mismatch ──")
    rpt_as_coded = NET_RETURN_INIT_CASH / N_TRADES  # 0.831%
    per_position_net = NET_RETURN_INIT_CASH / N_TRADES / POSITION_SIZE_PCT  # 6.95%
    per_position_gross = GROSS_RETURN_INIT_CASH / N_TRADES / POSITION_SIZE_PCT  # 9.90%

    print(f"  Gate code (portfolio_manager.py:1307):")
    print(f"    return_per_trade = total_return / total_trades")
    print(f"                     = {NET_RETURN_INIT_CASH:.3%} / {N_TRADES} = {rpt_as_coded:.3%}")
    print(f"    This is per-trade contribution to INIT_CASH (not per-position return)")
    print(f"  Threshold intent (Sprint 1 F3):")
    print(f"    'round_trip_cost (2.96%) + 50bps edge = 3.5%'")
    print(f"    → derived as PER-POSITION threshold")
    print(f"  Actual per-position economics on this strategy:")
    print(f"    Per-position gross:  {per_position_gross:.2%}")
    print(f"    Per-position net:    {per_position_net:.2%}")
    print(f"    Round-trip cost:     {CRYPTO_ASSET_CLASS_ROUND_TRIP:.2%}")
    print(f"    Per-position NET margin over cost: "
          f"{per_position_net - CRYPTO_ASSET_CLASS_ROUND_TRIP:+.2%}")
    print(f"    Per-position GROSS / cost ratio:   {per_position_gross / CRYPTO_ASSET_CLASS_ROUND_TRIP:.2f}x")

    gate_effective_demand_per_pos = EFFECTIVE_RPT_FLOOR / POSITION_SIZE_PCT
    print(f"  Effective gate demand on per-POSITION basis:")
    print(f"    {EFFECTIVE_RPT_FLOOR:.3%} / {POSITION_SIZE_PCT:.1%} = "
          f"{gate_effective_demand_per_pos:.2%} per position")
    print(f"    That is {gate_effective_demand_per_pos / CRYPTO_ASSET_CLASS_ROUND_TRIP:.1f}x "
          f"the real round-trip cost — a very high hurdle.")

    # ── Finding #3: edge_ratio unit mismatch ──
    print("\n── Finding #3: edge_ratio unit mismatch (observability-only) ──")
    gross_per_trade_init_cash = GROSS_RETURN_INIT_CASH / N_TRADES  # 1.185%
    edge_ratio_as_coded = gross_per_trade_init_cash / ETH_PER_SYMBOL_ROUND_TRIP  # 0.54
    # "Correct" edge ratio: compare gross/trade to cost/trade on the same basis.
    # On init_cash basis:
    cost_per_trade_init_cash = actual_pct / N_TRADES
    edge_ratio_correct_init_cash = gross_per_trade_init_cash / cost_per_trade_init_cash
    # On per-position basis:
    edge_ratio_correct_per_pos = per_position_gross / CRYPTO_ASSET_CLASS_ROUND_TRIP

    print(f"  AS CODED (cost_model.edge_ratio):")
    print(f"    numerator = gross_return / n_trades = {gross_per_trade_init_cash:.3%} (% of init_cash)")
    print(f"    denominator = round_trip_cost_pct = {ETH_PER_SYMBOL_ROUND_TRIP:.3%} (% of position)")
    print(f"    edge_ratio = {edge_ratio_as_coded:.2f}  ← matches log '0.54'")
    print(f"    BUG: numerator and denominator are on different bases.")
    print(f"")
    print(f"  CORRECT — both on per-position basis:")
    print(f"    gross/position    = {per_position_gross:.2%}")
    print(f"    cost/position     = {CRYPTO_ASSET_CLASS_ROUND_TRIP:.2%}")
    print(f"    edge_ratio        = {edge_ratio_correct_per_pos:.2f}  ← real: strong edge")
    print(f"")
    print(f"  CORRECT — both on init_cash-per-trade basis:")
    print(f"    gross/trade(IC)   = {gross_per_trade_init_cash:.3%}")
    print(f"    cost/trade(IC)    = {cost_per_trade_init_cash:.3%}")
    print(f"    edge_ratio        = {edge_ratio_correct_init_cash:.2f}  ← same conclusion")

    # ── Summary ──
    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print("""
Two interacting bugs cause the BTC Follower 4H ETH activation rejection:

(A) STRATEGY_ENGINE: per_symbol cost override NOT consulted.
    ETH backtest pays altcoin-rate 2.96% round-trip instead of 2.20%.
    Impact: real dollar cost on 6 trades × $12K avg is $808 higher than
    configured (~0.81% of init_cash of "phantom cost"). Net return is
    4.18% instead of what it "should" be.

(B) PORTFOLIO_MANAGER RPT: unit mismatch.
    total_return/N is a per-init_cash per-trade metric but is compared
    against a threshold derived as per-position (Sprint 1 F3). At
    position sizing of 12% of init_cash, the gate effectively demands
    15% gross per position to pass — 5x the real round-trip cost.

(C) COST_MODEL EDGE_RATIO: same unit mismatch (observability-only).
    Reported edge_ratio=0.54 vs real per-position edge_ratio=3.34.

The strategy's REAL edge: 9.90% gross per position vs 2.96% cost per
position = 3.34x over break-even. Comfortable live-tradable margin.
The pipeline is rejecting a strategy with strong, genuine edge.
""")


if __name__ == "__main__":
    main()
