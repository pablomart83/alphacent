"""Tests for the PAPER health-demote relaxation (should_demote_on_health).

Background: the health=0 demote previously fired at 5 closed trades, which —
on a positively-skewed trend book — benches strategies during normal early
drawdowns right before they recover (forward-P&L test 2026-06-18: negative-
first-5 pairs went on to +$19.91/trade, 67% recovered). PAPER now requires the
graduation min_trades before demoting, with a catastrophic-loss fast-kill, while
LIVE keeps the aggressive 5-trade bar.
"""
from src.core.monitoring_service import should_demote_on_health


def test_paper_small_sample_drawdown_not_demoted():
    # PAPER, health=0, only 8 closed trades, modest loss → must NOT demote.
    demote, fast_kill = should_demote_on_health(
        0, 8, is_paper=True, total_realized=-50.0, total_invested=8000.0,
        paper_min_trades=15, catastrophic_loss_pct=0.15,
    )
    assert demote is False
    assert fast_kill is False


def test_paper_demotes_once_sample_meaningful():
    # PAPER, health=0, 15 closed trades → demote (meaningful sample).
    demote, fast_kill = should_demote_on_health(
        0, 15, is_paper=True, total_realized=-300.0, total_invested=15000.0,
        paper_min_trades=15,
    )
    assert demote is True
    assert fast_kill is False


def test_paper_catastrophic_loss_fast_kills_below_floor():
    # PAPER, health=0, only 6 trades but realized loss > 15% of deployed → fast-kill.
    demote, fast_kill = should_demote_on_health(
        0, 6, is_paper=True, total_realized=-2000.0, total_invested=10000.0,
        paper_min_trades=15, catastrophic_loss_pct=0.15,
    )
    assert demote is True
    assert fast_kill is True


def test_live_keeps_aggressive_5_trade_bar():
    # LIVE, health=0, 5 closed trades → demote (LIVE bar unchanged).
    demote, fast_kill = should_demote_on_health(
        0, 5, is_paper=False, total_realized=-100.0, total_invested=5000.0,
        live_min_trades=5,
    )
    assert demote is True
    assert fast_kill is False


def test_healthy_score_never_demotes():
    for hs in (None, 1, 3, 5):
        demote, fast_kill = should_demote_on_health(
            hs, 50, is_paper=True, total_realized=-9999.0, total_invested=1000.0,
        )
        assert demote is False
        assert fast_kill is False


def test_paper_non_catastrophic_below_floor_holds():
    # Loss just under the catastrophic threshold (14% < 15%) at low sample → hold.
    demote, fast_kill = should_demote_on_health(
        0, 10, is_paper=True, total_realized=-1400.0, total_invested=10000.0,
        paper_min_trades=15, catastrophic_loss_pct=0.15,
    )
    assert demote is False
    assert fast_kill is False
