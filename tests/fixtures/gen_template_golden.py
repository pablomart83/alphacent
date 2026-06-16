"""Generate the golden-master snapshot of the LEGACY template library output.

Run ONCE from the legacy (pre-catalog) code to freeze the 214 effective templates.
The permanent round-trip test (test_template_catalog_roundtrip.py) asserts the new
YAML-catalog loader reproduces this snapshot byte-for-byte.

    ./venv/bin/python tests/fixtures/gen_template_golden.py
"""
import json
import os

from src.strategy.strategy_templates import StrategyTemplateLibrary

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "template_catalog_golden.json")


def to_record(t):
    return {
        "name": t.name,
        "description": t.description,
        "strategy_type": t.strategy_type.value,
        "market_regimes": [r.value for r in t.market_regimes],
        "entry_conditions": list(t.entry_conditions or []),
        "exit_conditions": list(t.exit_conditions or []),
        "required_indicators": list(t.required_indicators or []),
        "default_parameters": dict(t.default_parameters or {}),
        "expected_trade_frequency": t.expected_trade_frequency,
        "expected_holding_period": t.expected_holding_period,
        "risk_reward_ratio": t.risk_reward_ratio,
        "metadata": dict(t.metadata or {}),
    }


if __name__ == "__main__":
    lib = StrategyTemplateLibrary()
    # ORDER MATTERS — get_all_templates() returns this order; freeze it as a list.
    records = [to_record(t) for t in lib.templates]
    with open(OUT, "w") as f:
        json.dump(records, f, indent=2, sort_keys=True, default=str)
    print(f"Wrote {len(records)} templates to {OUT}")
