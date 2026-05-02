"""Verify the 2026-05-02 crypto updates after deploy.

Checks:
  1. symbols.yaml loads SOL/AVAX/LINK/DOT as tradeable crypto.
  2. New templates (21W MA, Vol-Compression) are in the library.
  3. Cost filter correctly keeps/drops crypto templates based on TP>=6%.
  4. Per-asset crypto transaction cost config reads commission_percent=0.01.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> int:
    failures: list[str] = []

    # 1. Crypto universe
    from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO
    crypto_list = list(DEMO_ALLOWED_CRYPTO)
    print(f"Crypto universe: {crypto_list}")
    expected = {"BTC", "ETH", "SOL", "AVAX", "LINK", "DOT"}
    actual = set(crypto_list)
    missing = expected - actual
    if missing:
        failures.append(f"Missing crypto symbols: {sorted(missing)}")

    # 2. New templates present
    from src.strategy.strategy_templates import StrategyTemplateLibrary
    templates = StrategyTemplateLibrary().templates
    template_names = {t.name for t in templates}
    expected_new = {"Crypto 21W MA Trend Follow", "Crypto Vol-Compression Momentum"}
    missing_new = expected_new - template_names
    if missing_new:
        failures.append(f"New templates missing from library: {sorted(missing_new)}")
    else:
        print(f"New templates loaded: {sorted(expected_new)}")

    # 3. Cost filter enforces 6% TP on crypto templates
    crypto_templates = [t for t in templates if t.metadata and t.metadata.get("crypto_optimized")]
    below_floor = []
    for t in crypto_templates:
        tp = float(t.default_parameters.get("take_profit_pct", 0) or 0)
        if tp < 0.06:
            below_floor.append((t.name, tp))
    print(f"Crypto templates loaded: {len(crypto_templates)}")
    if below_floor:
        failures.append(f"Crypto templates below 6% TP floor survived filter: {below_floor}")

    print("Crypto templates by TP:")
    for t in sorted(crypto_templates, key=lambda x: x.default_parameters.get("take_profit_pct", 0) or 0):
        tp = t.default_parameters.get("take_profit_pct", 0)
        sl = t.default_parameters.get("stop_loss_pct", 0)
        print(f"  - {t.name:40s} TP={tp*100:4.1f}%  SL={sl*100:4.1f}%  rr={(tp/sl if sl else 0):.2f}")

    # 4. Config has commission_percent=0.01 for crypto
    import yaml
    with open(Path(__file__).resolve().parents[2] / "config" / "autonomous_trading.yaml") as f:
        cfg = yaml.safe_load(f)
    crypto_cost = cfg.get("backtest", {}).get("transaction_costs", {}).get("per_asset_class", {}).get("crypto", {})
    commission = crypto_cost.get("commission_percent")
    spread = crypto_cost.get("spread_percent")
    slippage = crypto_cost.get("slippage_percent")
    print(f"\nCrypto tx cost: commission={commission}, spread={spread}, slippage={slippage}")
    print(f"Round-trip: {(2 * (commission + spread + slippage)):.4%}")
    if commission != 0.01:
        failures.append(f"Crypto commission not 1% per side (got {commission})")

    # 5. min_trades tiers
    at = cfg.get("activation_thresholds", {})
    for key in ("min_trades_crypto_1d", "min_trades_crypto_4h"):
        v = at.get(key)
        print(f"{key}: {v}")
        if v is None:
            failures.append(f"Missing {key} in activation_thresholds")

    if failures:
        print("\nFAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
