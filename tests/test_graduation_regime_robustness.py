"""Regime-robustness graduation gate (2026-06-19).

The proper replacement for the removed paper/WF ratio cap's "don't graduate the
regime" concern. Evidence-based: rejects ONLY when a pair has demonstrated a
losing edge (net-negative over >= REGIME_MIN_SAMPLE trades) in a regime family it
has actually traded enough to judge. Never rejects on absence of cross-regime data
(which would wrongly block trend specialists that have only traded in trends).
"""
from types import SimpleNamespace
from unittest.mock import Mock

from src.strategy import graduation_gate as gg
from src.strategy.graduation_gate import (
    is_qualified, _regime_family, REGIME_MIN_SAMPLE, load_regime_breakdown,
)

_GOOD = dict(paper_trades=20, paper_sharpe=2.0, paper_win_rate=0.60, paper_total_pnl=800.0)


# ── family mapping ───────────────────────────────────────────────────────────

def test_regime_family_mapping():
    assert _regime_family("trending_up_strong") == "trending_up"
    assert _regime_family("trending_up_weak") == "trending_up"
    assert _regime_family("TRENDING_UP") == "trending_up"
    assert _regime_family("trending_down") == "trending_down"
    assert _regime_family("ranging_low_vol") == "ranging"
    assert _regime_family("high_vol") == "high_vol"
    assert _regime_family("") is None
    assert _regime_family(None) is None
    assert _regime_family("garbage") is None


# ── gate behaviour ───────────────────────────────────────────────────────────

def test_demonstrated_regime_loss_rejected():
    # 10 ranging trades, net-negative → demonstrated regime-dependence → reject.
    rb = {
        "trending_up": {"trades": 20, "total_pnl": 1500.0},
        "ranging": {"trades": 10, "total_pnl": -300.0},
    }
    ok, reasons = is_qualified(_GOOD, 1.5, interval="4h", strategy_type="trend_following",
                               regime_breakdown=rb)
    assert ok is False
    assert any("regime_dependent" in r and "ranging" in r for r in reasons)


def test_small_other_regime_sample_does_not_block():
    # Only 3 ranging trades (below REGIME_MIN_SAMPLE) and negative — NOT enough
    # evidence; a trend specialist must not be blocked on a tiny off-regime sample.
    rb = {
        "trending_up": {"trades": 20, "total_pnl": 1500.0},
        "ranging": {"trades": 3, "total_pnl": -200.0},
    }
    ok, reasons = is_qualified(_GOOD, 1.5, interval="4h", strategy_type="trend_following",
                               regime_breakdown=rb)
    assert ok is True, reasons


def test_profitable_in_all_traded_regimes_passes():
    rb = {
        "trending_up": {"trades": 20, "total_pnl": 1500.0},
        "ranging": {"trades": 12, "total_pnl": 250.0},
    }
    ok, reasons = is_qualified(_GOOD, 1.5, interval="4h", strategy_type="trend_following",
                               regime_breakdown=rb)
    assert ok is True, reasons


def test_no_breakdown_skips_gate():
    # No regime data → gate is a no-op (does not block).
    ok, reasons = is_qualified(_GOOD, 1.5, interval="4h", strategy_type="trend_following",
                               regime_breakdown=None)
    assert ok is True, reasons
    assert not any("regime_dependent" in r for r in reasons)


def test_single_regime_concentration_not_penalized():
    # All trades in the current (up) regime, strongly positive — the classic trend
    # specialist. Absence of other-regime data must NOT reject.
    rb = {"trending_up": {"trades": 25, "total_pnl": 3000.0}}
    ok, reasons = is_qualified(_GOOD, 1.5, interval="4h", strategy_type="trend_following",
                               regime_breakdown=rb)
    assert ok is True, reasons


def test_exactly_min_sample_negative_rejected():
    rb = {
        "trending_up": {"trades": 20, "total_pnl": 1500.0},
        "trending_down": {"trades": REGIME_MIN_SAMPLE, "total_pnl": -50.0},
    }
    ok, reasons = is_qualified(_GOOD, 1.5, interval="4h", strategy_type="trend_following",
                               regime_breakdown=rb)
    assert ok is False
    assert any("trending_down" in r for r in reasons)


# ── load_regime_breakdown Python logic (mocked session — no postgres needed) ──
# Regression guard for the `text` NameError that made this return {} silently:
# we assert it actually buckets rows, filters by pair_set, and maps families.

def _fake_session(rows):
    session = Mock()
    result = Mock()
    result.fetchall.return_value = rows
    session.execute.return_value = result
    return session


def test_load_regime_breakdown_buckets_and_filters():
    rows = [
        SimpleNamespace(template_name="T", symbol="AMD", market_regime="trending_up_strong", trades=11, total_pnl=607.0),
        SimpleNamespace(template_name="T", symbol="AMD", market_regime=None, trades=4, total_pnl=1407.0),  # unknown → excluded
        SimpleNamespace(template_name="T", symbol="AMD", market_regime="ranging_low_vol", trades=9, total_pnl=-300.0),
        SimpleNamespace(template_name="T", symbol="ZZZ", market_regime="trending_up_weak", trades=20, total_pnl=900.0),  # not in pair_set
    ]
    out = load_regime_breakdown(_fake_session(rows), [("T", "AMD")])
    assert ("T", "AMD") in out
    assert ("T", "ZZZ") not in out                      # pair_set filter works
    fam = out[("T", "AMD")]
    assert fam["trending_up"] == {"trades": 11, "total_pnl": 607.0}
    assert fam["ranging"] == {"trades": 9, "total_pnl": -300.0}
    assert "unknown" not in fam                          # NULL regime excluded


def test_load_regime_breakdown_empty_pairs_noop():
    assert load_regime_breakdown(_fake_session([]), []) == {}
