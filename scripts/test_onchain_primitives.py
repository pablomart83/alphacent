#!/usr/bin/env python3
"""Smoke test for Sprint 4 S4.1 on-chain DSL primitives.

Exercises:
  1. src.api.onchain_client live fetches against CoinGecko + DeFi Llama
  2. DSL parse of ONCHAIN("metric", N) references
  3. DSL codegen for composite rules mixing ONCHAIN with regular indicators
  4. compute_onchain_indicators end-to-end alignment to a primary index

Run from project root on the service host so venv and configs are picked up:
    source venv/bin/activate && python3 scripts/test_onchain_primitives.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.api.onchain_client import SUPPORTED_METRICS, get_metric, is_supported
from src.strategy.onchain_primitives import compute_onchain_indicators
from src.strategy.trading_dsl import DSLCodeGenerator, TradingDSLParser


def section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def main() -> int:
    section("Registry")
    print("Supported metrics:", sorted(SUPPORTED_METRICS))
    for m in SUPPORTED_METRICS:
        assert is_supported(m)
    assert not is_supported("mvrv_zscore"), "mvrv_zscore should not be supported yet"

    section("Live fetches")
    end = datetime.utcnow()

    dom = get_metric("btc_dominance", end, 90)
    print(
        f"btc_dominance 90d: n={len(dom)} "
        f"head={dom.iloc[0]:.4f} tail={dom.iloc[-1]:.4f} "
        f"min={dom.min():.4f} max={dom.max():.4f}"
    )
    assert 0.25 < dom.iloc[-1] < 0.80, "current BTC dominance should be in realistic range"

    supply = get_metric("stablecoin_supply", end, 90)
    print(
        f"stablecoin_supply 90d: n={len(supply)} "
        f"head=${supply.iloc[0] / 1e9:.1f}B tail=${supply.iloc[-1] / 1e9:.1f}B"
    )
    assert supply.iloc[-1] > 100e9, "stablecoin supply should be well over $100B"

    supply_pct = get_metric("stablecoin_supply_pct", end, 90)
    print(
        f"stablecoin_supply_pct 90d: n={len(supply_pct)} "
        f"head={supply_pct.iloc[0]:.4f} tail={supply_pct.iloc[-1]:.4f}"
    )

    section("DSL parse + codegen")
    parser = TradingDSLParser()
    avail = [
        "RSI_14",
        "ADX_14",
        "ONCHAIN__btc_dominance__7",
        "ONCHAIN__stablecoin_supply_pct__7",
    ]
    gen = DSLCodeGenerator(available_indicators=avail)
    for expr in [
        'ONCHAIN("btc_dominance", 7) < 0.55 AND ADX(14) > 20',
        'ONCHAIN("stablecoin_supply_pct", 7) > 0.05',
    ]:
        parse = parser.parse(expr)
        if not parse.success:
            print("PARSE ERR:", expr, parse.error[:120])
            return 1
        code = gen.generate_code(parse.ast)
        status = "OK" if code.success else "ERR"
        print(f"{status}: {expr}")
        print(f"  code: {(code.code or code.error)[:180]}")

    section("compute_onchain_indicators alignment")
    # Build a fake primary index covering the last 60 days at daily cadence.
    idx = pd.date_range(end=end, periods=60, freq="D")
    conditions = [
        'ONCHAIN("btc_dominance", 7) < 0.55',
        'ONCHAIN("stablecoin_supply_pct", 7) > 0.05',
    ]
    out = compute_onchain_indicators(conditions, idx)
    for k, v in out.items():
        print(
            f"{k}: n={len(v)} non_nan={int(v.notna().sum())} "
            f"last={v.iloc[-1] if not v.empty else 'N/A'}"
        )
        assert len(v) == len(idx), "series must be aligned to primary index"
        assert int(v.notna().sum()) > 0, "series must have some data"

    section("All smoke tests PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
