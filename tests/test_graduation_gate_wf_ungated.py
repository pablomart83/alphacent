"""Graduation gate: the paper/WF qualification-ratio gate is removed (2026-06-19).

The ratio gate (min 0.6×, regime-adjusted max ~2-3.5×) divided a per-trade √252
paper Sharpe by vectorbt's per-bar vol-scaled WF Sharpe — incompatible bases, so
the ratio ran ~3× high by construction and the cap rejected strong-paper pairs
(AMD 6.01/1.62=3.71×, SPY 4.90/1.16=4.22×) on an artifact. Every protection it
nominally provided is enforced more correctly elsewhere:
  - real, validated edge: WF acceptance + activation min_sharpe=1.0 + MC bootstrap
  - edge still alive in paper: paper_pnl>0 + win-rate floor + Wilson LB
  - small-sample luck: min_trades floor + Wilson LB + DSR

These tests pin the new behaviour: WF no longer gates, and the ratio bounds no
longer block. The paper-side gates (trades / pnl / win-rate / Wilson) still bite.
"""
from src.strategy.graduation_gate import is_qualified

# A clean trend pair that passes the paper-side gates.
_GOOD = dict(paper_trades=20, paper_sharpe=2.0, paper_win_rate=0.60, paper_total_pnl=800.0)


# ── WF is no longer a gate input ─────────────────────────────────────────────

def test_missing_wf_no_longer_blocks():
    ok, reasons = is_qualified(_GOOD, None, interval="4h", strategy_type="trend_following")
    assert ok is True, reasons
    assert not any("wf_sharpe" in r for r in reasons)


def test_zero_wf_no_longer_blocks():
    ok, reasons = is_qualified(_GOOD, 0.0, interval="4h", strategy_type="trend_following")
    assert ok is True, reasons


def test_high_paper_to_wf_ratio_no_longer_rejected():
    # paper 6.0 vs wf 1.6 = 3.75× — the AMD case, previously rejected by the cap.
    stats = dict(_GOOD, paper_sharpe=6.0)
    ok, reasons = is_qualified(stats, 1.6, interval="4h", strategy_type="trend_following",
                               _precomputed_max_ratio=3.0)
    assert ok is True, reasons
    assert not any("qualification_ratio" in r for r in reasons)


def test_low_paper_to_wf_ratio_no_longer_rejected():
    # paper 0.5 vs wf 2.0 = 0.25 — previously rejected by the 0.6 floor.
    stats = dict(_GOOD, paper_sharpe=0.5)
    ok, reasons = is_qualified(stats, 2.0, interval="4h", strategy_type="trend_following")
    assert ok is True, reasons
    assert not any("qualification_ratio" in r for r in reasons)


def test_valid_wf_still_qualifies():
    ok, reasons = is_qualified(_GOOD, 1.5, interval="4h", strategy_type="trend_following")
    assert ok is True, reasons


# ── paper-side gates still enforced ──────────────────────────────────────────

def test_paper_sharpe_none_still_reported():
    stats = dict(_GOOD, paper_sharpe=None)
    ok, reasons = is_qualified(stats, 1.5, interval="4h", strategy_type="trend_following")
    assert ok is False
    assert any("paper_sharpe not computable" in r for r in reasons)


def test_negative_pnl_still_rejected():
    stats = dict(_GOOD, paper_total_pnl=-100.0)
    ok, reasons = is_qualified(stats, 1.5, interval="4h", strategy_type="trend_following")
    assert ok is False
    assert any("paper_pnl" in r for r in reasons)


def test_too_few_trades_still_rejected():
    stats = dict(_GOOD, paper_trades=5)
    ok, reasons = is_qualified(stats, 1.5, interval="4h", strategy_type="trend_following")
    assert ok is False
    assert any("paper_trades" in r for r in reasons)


def test_low_win_rate_still_rejected():
    # 30% win rate is below even the 45% trend-following floor.
    stats = dict(_GOOD, paper_win_rate=0.30)
    ok, reasons = is_qualified(stats, 1.5, interval="4h", strategy_type="trend_following")
    assert ok is False
    assert any("win_rate" in r for r in reasons)
