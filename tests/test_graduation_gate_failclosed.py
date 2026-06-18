"""Tests for the graduation-gate fail-closed-on-missing-WF behaviour (2026-06-18).

Previously a missing/zero wf_sharpe SILENTLY SKIPPED the qualification-ratio gate,
so a pair could graduate to real capital without its paper-vs-WF edge ever being
validated. Now it fails closed. (The queue applies a per-template best-WF fallback
before is_qualified, so this only bites when no WF Sharpe exists anywhere.)
"""
from src.strategy.graduation_gate import is_qualified

# A clean trend pair that should pass everything when wf_sharpe is present.
_GOOD = dict(paper_trades=20, paper_sharpe=2.0, paper_win_rate=0.60, paper_total_pnl=800.0)


def test_missing_wf_sharpe_fails_closed():
    ok, reasons = is_qualified(_GOOD, None, interval="4h", strategy_type="trend_following")
    assert ok is False
    assert any("wf_sharpe" in r and "fail-closed" in r for r in reasons)


def test_zero_wf_sharpe_fails_closed():
    ok, reasons = is_qualified(_GOOD, 0.0, interval="4h", strategy_type="trend_following")
    assert ok is False
    assert any("wf_sharpe" in r for r in reasons)


def test_valid_wf_sharpe_qualifies():
    ok, reasons = is_qualified(_GOOD, 1.5, interval="4h", strategy_type="trend_following")
    assert ok is True, reasons


def test_ratio_over_cap_rejected():
    # paper_sharpe 8.0 vs wf 1.0 = 8x, well over any regime cap → rejected.
    stats = dict(_GOOD, paper_sharpe=8.0)
    ok, reasons = is_qualified(stats, 1.0, interval="4h", strategy_type="trend_following",
                               _precomputed_max_ratio=3.0)
    assert ok is False
    assert any("qualification_ratio" in r and ">" in r for r in reasons)


def test_ratio_below_floor_rejected():
    # paper_sharpe 0.5 vs wf 2.0 = 0.25 < 0.6 floor → rejected.
    stats = dict(_GOOD, paper_sharpe=0.5)
    ok, reasons = is_qualified(stats, 2.0, interval="4h", strategy_type="trend_following")
    assert ok is False
    assert any("qualification_ratio" in r and "<" in r for r in reasons)


def test_paper_sharpe_none_reported():
    stats = dict(_GOOD, paper_sharpe=None)
    ok, reasons = is_qualified(stats, 1.5, interval="4h", strategy_type="trend_following")
    assert ok is False
    assert any("paper_sharpe not computable" in r for r in reasons)
