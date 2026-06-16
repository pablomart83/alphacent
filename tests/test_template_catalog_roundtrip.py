"""Behavior-preservation gate for the strategy-template catalog migration.

Asserts the declarative YAML catalog (config/strategy_catalog/*.yaml), loaded and
normalized by template_catalog.load_catalog(), reproduces the frozen legacy library
output (tests/fixtures/template_catalog_golden.json) byte-for-byte and in order.

If this fails, a template was silently dropped, mutated, reordered or renamed — which
changes what the live system proposes/trades. Regenerate the golden ONLY via a
deliberate, reviewed change (tests/fixtures/gen_template_golden.py against legacy code).
"""
import json
import os

import pytest

from src.strategy.template_catalog import load_catalog

HERE = os.path.dirname(__file__)
GOLDEN = os.path.join(HERE, "fixtures", "template_catalog_golden.json")


def _to_record(t):
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


@pytest.fixture(scope="module")
def golden():
    with open(GOLDEN) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def catalog():
    # json round-trip to normalize tuples->lists exactly like the golden serializer
    return json.loads(json.dumps([_to_record(t) for t in load_catalog()],
                                  sort_keys=True, default=str))


def test_same_count(golden, catalog):
    assert len(catalog) == len(golden), (
        f"catalog has {len(catalog)} templates, golden has {len(golden)}"
    )


def test_same_names_and_order(golden, catalog):
    assert [c["name"] for c in catalog] == [g["name"] for g in golden], (
        "template names or ORDER differ from golden (breaks proposer rotation / DB joins)"
    )


def test_no_duplicate_names(catalog):
    names = [c["name"] for c in catalog]
    assert len(names) == len(set(names)), "duplicate template names in catalog"


def test_each_template_identical(golden, catalog):
    g_by_name = {g["name"]: g for g in golden}
    mismatches = []
    for c in catalog:
        g = g_by_name.get(c["name"])
        if g != c:
            diff_fields = [k for k in c if c.get(k) != g.get(k)] if g else ["<missing>"]
            mismatches.append((c["name"], diff_fields))
    assert not mismatches, f"templates differ from golden: {mismatches}"
