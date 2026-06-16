"""Unit tests for the cross-sectional rank DSL primitives (2026-06-16).

Covers the two new rank primitives added to extend the edge-template roadmap:
  - RANK_IN_UNIVERSE_BOTTOM  → short-term reversal (Lehmann), long the laggards
  - RANK_LOW_VOL             → low-volatility factor (Frazzini-Pedersen)

The critical invariant for every cross-asset primitive is EXACT key matching
between the DSL code generator (trading_dsl.INDICATOR_MAPPING) and the compute
step (cross_asset_primitives.compute_cross_asset_indicators). A mismatch is a
silent 0-trade bug — the eval'd rule looks up a key that was never injected, so
entries resolve all-False with no error. These tests assert the keys agree AND
that each primitive produces the semantically correct selection.
"""
import numpy as np
import pandas as pd
import pytest

from src.strategy.trading_dsl import TradingDSLParser, DSLCodeGenerator
from src.strategy.cross_asset_primitives import (
    extract_cross_asset_references,
    compute_cross_asset_indicators,
    compute_short_term_reversal_series,
    compute_low_vol_rank_series,
    compute_rank_in_universe_series,
)

UNIVERSE = ["AAA", "BBB", "CCC", "DDD", "EEE"]


def _make_df(index, drift, vol, seed):
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, len(index))
    close = 100 * np.exp(np.cumsum(rets))
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1e6},
        index=index,
    )


@pytest.fixture
def universe_data():
    idx = pd.date_range("2024-01-01", periods=400, freq="D")
    # AAA: strong uptrend, lowest vol of the trenders.
    # BBB: persistent loser, high vol.
    # CCC: flat, lowest vol overall.
    # DDD/EEE: middling / volatile.
    return {
        "AAA": _make_df(idx, 0.002, 0.010, 1),
        "BBB": _make_df(idx, -0.002, 0.030, 2),
        "CCC": _make_df(idx, 0.0005, 0.004, 3),
        "DDD": _make_df(idx, 0.001, 0.020, 4),
        "EEE": _make_df(idx, -0.001, 0.040, 5),
    }, idx


def _codegen_keys(condition):
    pr = TradingDSLParser().parse(condition)
    assert pr.success, f"DSL failed to parse: {condition} ({pr.error})"
    gen = DSLCodeGenerator()
    res = gen.generate_code(pr.ast)
    assert res.success, f"codegen failed: {res.error}"
    return res.required_indicators


# ── Extraction ─────────────────────────────────────────────────────────────

def test_extract_tags_each_rank_kind():
    conds = [
        'RANK_IN_UNIVERSE("SELF", ["AAA","BBB"], 20, 2) > 0',
        'RANK_IN_UNIVERSE_BOTTOM("SELF", ["AAA","BBB"], 5, 2) > 0',
        'RANK_LOW_VOL("SELF", ["AAA","BBB"], 20, 2) > 0',
    ]
    _lag, rank_refs = extract_cross_asset_references(conds)
    kinds = sorted(r[0] for r in rank_refs)
    assert kinds == ["bottom", "lowvol", "top"]


def test_top_regex_does_not_swallow_bottom():
    # RANK_IN_UNIVERSE\( must NOT match the RANK_IN_UNIVERSE_BOTTOM( prefix,
    # otherwise the bottom primitive would be double-counted as a 'top' ref.
    _lag, rank_refs = extract_cross_asset_references(
        ['RANK_IN_UNIVERSE_BOTTOM("SELF", ["AAA","BBB"], 5, 2) > 0']
    )
    assert len(rank_refs) == 1
    assert rank_refs[0][0] == "bottom"


# ── Key matching (codegen == compute) ────────────────────────────────────────

@pytest.mark.parametrize("kind,condition,primary", [
    ("top", 'RANK_IN_UNIVERSE("SELF", ["AAA","BBB","CCC","DDD","EEE"], 20, 2) > 0', "AAA"),
    ("bottom", 'RANK_IN_UNIVERSE_BOTTOM("SELF", ["AAA","BBB","CCC","DDD","EEE"], 5, 2) > 0', "BBB"),
    ("lowvol", 'RANK_LOW_VOL("SELF", ["AAA","BBB","CCC","DDD","EEE"], 20, 2) > 0', "CCC"),
])
def test_codegen_key_equals_compute_key(kind, condition, primary, universe_data):
    data, idx = universe_data
    codegen = [k for k in _codegen_keys(condition)
               if k.startswith(("RANK_IN_UNIVERSE", "RANK_LOW_VOL"))]
    out = compute_cross_asset_indicators([condition], primary, idx,
                                         lambda s, a, b, i: data.get(s))
    assert set(codegen) == set(out.keys()), (
        f"{kind}: codegen {codegen} != compute {list(out.keys())}"
    )
    # And the produced series fires on a non-trivial number of bars.
    assert int(out[codegen[0]].sum()) > 0


# ── Semantics ────────────────────────────────────────────────────────────────

def test_reversal_selects_the_loser_not_the_winner(universe_data):
    data, idx = universe_data
    # BBB is the persistent loser → should rank in the bottom-1 by 5d return
    # far more often than the strong winner AAA.
    bbb = compute_short_term_reversal_series("BBB", data, 5, 1, idx)
    aaa = compute_short_term_reversal_series("AAA", data, 5, 1, idx)
    assert bbb.sum() > aaa.sum()


def test_reversal_is_inverse_of_top_rank(universe_data):
    data, idx = universe_data
    # The winner AAA should be selected by top-rank far more than by bottom-rank.
    top = compute_rank_in_universe_series("AAA", data, 5, 1, idx)
    bottom = compute_short_term_reversal_series("AAA", data, 5, 1, idx)
    assert top.sum() > bottom.sum()


def test_low_vol_selects_the_calmest_name(universe_data):
    data, idx = universe_data
    # CCC has the lowest realized vol → in bottom-1 by vol far more than the
    # high-vol EEE.
    ccc = compute_low_vol_rank_series("CCC", data, 20, 1, idx)
    eee = compute_low_vol_rank_series("EEE", data, 20, 1, idx)
    assert ccc.sum() > eee.sum()


def test_missing_self_returns_all_false(universe_data):
    data, idx = universe_data
    s = compute_low_vol_rank_series("NOPE", data, 20, 2, idx)
    assert not s.any()
    r = compute_short_term_reversal_series("NOPE", data, 5, 2, idx)
    assert not r.any()


def test_series_aligned_to_primary_index(universe_data):
    data, idx = universe_data
    s = compute_short_term_reversal_series("AAA", data, 5, 2, idx)
    assert s.index.equals(idx)
    assert s.dtype == bool
