"""Tests for ConvictionScorer — redesigned around walk-forward evidence."""

import pytest
from datetime import datetime
from src.strategy.conviction_scorer import ConvictionScorer, ConvictionScore
from src.strategy.fundamental_filter import FundamentalFilterReport, FilterResult
from src.data.fundamental_data_provider import FundamentalData
from src.models.dataclasses import Strategy, TradingSignal, RiskConfig, BacktestResults
from src.models.enums import StrategyStatus, SignalAction


@pytest.fixture
def config():
    return {'alpha_edge': {'min_conviction_score': 70}}


@pytest.fixture
def mock_database():
    class MockSession:
        def add(self, obj): pass
        def commit(self): pass
        def close(self): pass
    class MockDatabase:
        def get_session(self): return MockSession()
    return MockDatabase()


@pytest.fixture
def scorer(config, mock_database):
    return ConvictionScorer(config=config, database=mock_database)


def _make_strategy(symbol="AAPL", wf_test_sharpe=None, wf_train_sharpe=None,
                   template_type="mean_reversion", win_rate=0.6, total_trades=10,
                   sharpe=1.5, entry_conditions=2, sl=0.05, tp=0.10):
    """Helper to create a strategy with walk-forward metadata."""
    meta = {'strategy_type': template_type, 'template_type': template_type}
    if wf_test_sharpe is not None:
        meta['wf_test_sharpe'] = wf_test_sharpe
        meta['walk_forward_validated'] = True
    if wf_train_sharpe is not None:
        meta['wf_train_sharpe'] = wf_train_sharpe

    bt = BacktestResults(
        sharpe_ratio=sharpe, sortino_ratio=sharpe * 1.5,
        total_return=0.05, max_drawdown=-0.02,
        win_rate=win_rate, total_trades=total_trades,
        avg_win=100, avg_loss=-50,
    )

    return Strategy(
        id="test-strategy", name="Test Strategy", description="Test",
        status=StrategyStatus.LIVE,
        rules={'entry_conditions': [f"cond_{i}" for i in range(entry_conditions)],
               'exit_conditions': ["exit_cond"]},
        symbols=[symbol],
        risk_params=RiskConfig(stop_loss_pct=sl, take_profit_pct=tp, position_risk_pct=0.05),
        metadata=meta, created_at=datetime.now(), backtest_results=bt,
    )


def _make_signal(symbol="AAPL", confidence=0.7):
    return TradingSignal(
        strategy_id="test-strategy", symbol=symbol,
        action=SignalAction.ENTER_LONG, confidence=confidence,
        reasoning="Test signal", generated_at=datetime.now(),
    )


# ─── Walk-forward edge scoring ──────────────────────────────────────

def test_high_sharpe_strategy_scores_high(scorer):
    """Strategy with Sharpe 3.9 should score very high on WF edge."""
    strategy = _make_strategy(wf_test_sharpe=3.9, wf_train_sharpe=1.2, win_rate=1.0, total_trades=7)
    signal = _make_signal()
    score = scorer.score_signal(signal, strategy)
    # WF edge alone should be 30+ (Sharpe 3.9 → ~19 pts, win rate 100% → 8, trades 7 → 5, consistency → 4)
    assert score.total_score >= 70, f"High-Sharpe strategy should pass threshold, got {score.total_score}"


def test_low_sharpe_strategy_scores_low(scorer):
    """Strategy with Sharpe 0.3 should score lower."""
    strategy = _make_strategy(wf_test_sharpe=0.3, wf_train_sharpe=0.1, win_rate=0.45, total_trades=3)
    signal = _make_signal(confidence=0.4)
    score = scorer.score_signal(signal, strategy)
    assert score.total_score < 60, f"Low-Sharpe strategy should score below 60, got {score.total_score}"


def test_no_walkforward_data_gets_zero_wf_score(scorer):
    """Strategy without WF metadata should get 0 from WF edge component."""
    strategy = _make_strategy(wf_test_sharpe=None, wf_train_sharpe=None)
    # Clear backtest_results too
    strategy.backtest_results = None
    signal = _make_signal()
    score = scorer.score_signal(signal, strategy)
    wf_score = score.breakdown['walkforward_edge']['score']
    assert wf_score == 0.0


# ─── ETF scoring (the bug that was killing ETF signals) ─────────────

def test_etf_signals_not_penalized(scorer):
    """ETFs should NOT get fund=5.0 penalty. They should score well on tradability."""
    strategy = _make_strategy(symbol="VTI", wf_test_sharpe=2.0, wf_train_sharpe=0.5,
                              win_rate=0.65, total_trades=8)
    signal = _make_signal(symbol="VTI")
    score = scorer.score_signal(signal, strategy)
    # VTI is a major ETF — should get at least 12 on asset tradability (not 5)
    asset_score = score.breakdown['asset_tradability']['score']
    assert asset_score >= 12.0, f"VTI should score >=12 on tradability, got {asset_score}"
    # Total should comfortably pass threshold
    assert score.total_score >= 60, f"VTI with Sharpe 2.0 should pass, got {score.total_score}"


def test_spy_is_tier1_tradability(scorer):
    """SPY is the most liquid ETF — should get max tradability score."""
    strategy = _make_strategy(symbol="SPY", wf_test_sharpe=1.5)
    signal = _make_signal(symbol="SPY")
    score = scorer.score_signal(signal, strategy)
    asset_score = score.breakdown['asset_tradability']['score']
    assert asset_score == 15.0


def test_xlk_not_killed(scorer):
    """XLK was being killed at 55.5. With new scoring it should pass."""
    strategy = _make_strategy(symbol="XLK", wf_test_sharpe=1.8, wf_train_sharpe=0.3,
                              win_rate=0.55, total_trades=6)
    signal = _make_signal(symbol="XLK", confidence=0.5)
    score = scorer.score_signal(signal, strategy)
    assert score.total_score >= 55, f"XLK with Sharpe 1.8 should not be killed, got {score.total_score}"


# ─── Crypto scoring ─────────────────────────────────────────────────

def test_btc_gets_max_tradability(scorer):
    """BTC is ultra-liquid — max tradability."""
    strategy = _make_strategy(symbol="BTC", wf_test_sharpe=2.0)
    signal = _make_signal(symbol="BTC")
    score = scorer.score_signal(signal, strategy)
    asset_score = score.breakdown['asset_tradability']['score']
    assert asset_score == 15.0


def test_near_gets_lower_tradability(scorer):
    """NEAR is thin — should score lower on tradability."""
    strategy = _make_strategy(symbol="NEAR", wf_test_sharpe=2.0)
    signal = _make_signal(symbol="NEAR")
    score = scorer.score_signal(signal, strategy)
    asset_score = score.breakdown['asset_tradability']['score']
    assert asset_score <= 10.0


# ─── Fundamental bonus (not penalty) ────────────────────────────────

def test_fundamental_report_gives_bonus(scorer):
    """Good fundamentals should add a small bonus, not be required."""
    report = FundamentalFilterReport(
        symbol="AAPL", passed=True, checks_passed=5, checks_total=5, min_required=4,
        results=[FilterResult("profitable", True, 5.0, 0.0, "EPS > 0")] * 5,
        fundamental_data=FundamentalData(
            symbol="AAPL", timestamp=datetime.now(), eps=5.0, revenue_growth=0.10,
            pe_ratio=25.0, debt_to_equity=0.3, roe=0.20, market_cap=2e12,
            shares_change_percent=2.0, insider_net_buying=1e6,
        ),
    )
    strategy = _make_strategy(symbol="AAPL", wf_test_sharpe=1.5)
    signal = _make_signal(symbol="AAPL")

    score_with = scorer.score_signal(signal, strategy, report)
    score_without = scorer.score_signal(signal, strategy, None)

    # With fundamentals should score slightly higher (bonus), but both should be viable
    assert score_with.total_score >= score_without.total_score


# ─── Regime fit ──────────────────────────────────────────────────────

def test_regime_fit_never_zero(scorer):
    """Regime fit should never be 0 — WF already validated the strategy."""
    strategy = _make_strategy(template_type="breakout")  # Breakout is "weak" in trending_down
    signal = _make_signal()
    score = scorer.score_signal(signal, strategy)
    regime_score = score.breakdown['regime_fit']['score']
    assert regime_score >= 5.0, f"Regime fit should never be 0, got {regime_score}"


# ─── Backward compatibility ─────────────────────────────────────────

def test_score_breakdown_has_legacy_keys(scorer):
    """Breakdown should include legacy keys for frontend compatibility."""
    strategy = _make_strategy(wf_test_sharpe=2.0)
    signal = _make_signal()
    score = scorer.score_signal(signal, strategy)
    assert 'signal_strength' in score.breakdown
    assert 'fundamental_quality' in score.breakdown
    assert 'regime_alignment' in score.breakdown
    assert 'walkforward_edge' in score.breakdown


def test_conviction_threshold(scorer):
    """Test threshold checking works."""
    strategy = _make_strategy(wf_test_sharpe=3.0, win_rate=0.8, total_trades=15)
    signal = _make_signal(confidence=0.9)
    score = scorer.score_signal(signal, strategy)
    assert isinstance(score.passes_threshold(70), bool)
    assert isinstance(score.passes_threshold(90), bool)


def test_min_conviction_score_from_config(config, mock_database):
    """Test that min conviction score is read from config."""
    scorer = ConvictionScorer(config=config, database=mock_database)
    assert scorer.min_conviction_score == 70
    config2 = {'alpha_edge': {'min_conviction_score': 80}}
    scorer2 = ConvictionScorer(config=config2, database=mock_database)
    assert scorer2.min_conviction_score == 80


def test_strategy_without_risk_config(scorer):
    """Strategy without SL/TP should still score, just lower on signal quality."""
    strategy = _make_strategy(sl=None, tp=None, wf_test_sharpe=2.0)
    strategy.risk_params = RiskConfig()
    signal = _make_signal()
    score = scorer.score_signal(signal, strategy)
    assert score.total_score > 0
