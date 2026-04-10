"""Integration tests for ConvictionScorer with signal filtering.

Updated for the redesigned scorer that prioritizes walk-forward evidence.
"""

import pytest
from datetime import datetime
from src.strategy.conviction_scorer import ConvictionScorer
from src.models.dataclasses import Strategy, TradingSignal, RiskConfig, BacktestResults
from src.models.enums import StrategyStatus, SignalAction


@pytest.fixture
def config():
    return {'alpha_edge': {'min_conviction_score': 60}}


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


def _bt(sharpe=1.5, win_rate=0.6, trades=10):
    return BacktestResults(
        sharpe_ratio=sharpe, sortino_ratio=sharpe * 1.5,
        total_return=0.05, max_drawdown=-0.02,
        win_rate=win_rate, total_trades=trades,
        avg_win=100, avg_loss=-50,
    )


def test_signal_filtering_by_conviction_threshold(scorer):
    """Walk-forward validated strategy should pass; unvalidated should fail."""
    strong_strategy = Strategy(
        id="strong", name="Strong WF Strategy", description="",
        status=StrategyStatus.LIVE,
        rules={'entry_conditions': ["RSI < 30", "MACD bullish", "Volume spike"],
               'exit_conditions': ["RSI > 70"]},
        symbols=["AAPL"],
        risk_params=RiskConfig(stop_loss_pct=0.05, take_profit_pct=0.10, position_risk_pct=0.05),
        metadata={'strategy_type': 'mean_reversion', 'wf_test_sharpe': 2.5,
                  'wf_train_sharpe': 1.0, 'walk_forward_validated': True},
        created_at=datetime.now(), backtest_results=_bt(sharpe=2.5, win_rate=0.7, trades=12),
    )

    weak_strategy = Strategy(
        id="weak", name="Weak Strategy", description="",
        status=StrategyStatus.LIVE,
        rules={'entry_conditions': ["Price > MA"], 'exit_conditions': ["Price < MA"]},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        metadata={'strategy_type': 'trend_following'},
        created_at=datetime.now(),
    )

    strong_signal = TradingSignal(
        strategy_id="strong", symbol="AAPL", action=SignalAction.ENTER_LONG,
        confidence=0.8, reasoning="Multiple indicators", generated_at=datetime.now(),
    )
    weak_signal = TradingSignal(
        strategy_id="weak", symbol="AAPL", action=SignalAction.ENTER_LONG,
        confidence=0.3, reasoning="Weak", generated_at=datetime.now(),
    )

    strong_score = scorer.score_signal(strong_signal, strong_strategy)
    weak_score = scorer.score_signal(weak_signal, weak_strategy)

    assert strong_score.total_score >= 60, f"WF-validated strategy should pass 60, got {strong_score.total_score}"
    assert weak_score.total_score < 50, f"Unvalidated strategy should be below 50, got {weak_score.total_score}"
    assert strong_score.total_score > weak_score.total_score


def test_conviction_score_breakdown_details(scorer):
    """Breakdown should contain expected keys and details."""
    strategy = Strategy(
        id="test", name="Test", description="",
        status=StrategyStatus.LIVE,
        rules={'entry_conditions': ["RSI < 30", "Price below MA"], 'exit_conditions': ["RSI > 70"]},
        symbols=["AAPL"],
        risk_params=RiskConfig(stop_loss_pct=0.05, take_profit_pct=0.10, position_risk_pct=0.05),
        metadata={'strategy_type': 'mean_reversion', 'wf_test_sharpe': 1.5},
        created_at=datetime.now(), backtest_results=_bt(),
    )
    signal = TradingSignal(
        strategy_id="test", symbol="AAPL", action=SignalAction.ENTER_LONG,
        confidence=0.8, reasoning="RSI oversold", generated_at=datetime.now(),
    )

    score = scorer.score_signal(signal, strategy)

    # New primary keys
    assert 'walkforward_edge' in score.breakdown
    assert 'signal_quality' in score.breakdown
    assert 'regime_fit' in score.breakdown
    assert 'asset_tradability' in score.breakdown

    # Legacy keys for frontend
    assert 'signal_strength' in score.breakdown
    assert 'fundamental_quality' in score.breakdown
    assert 'regime_alignment' in score.breakdown

    # Check signal_quality details
    sq = score.breakdown['signal_quality']
    assert 'details' in sq
    assert 'entry_conditions_count' in sq['details']
    assert sq['details']['entry_conditions_count'] == 2
    assert sq['details']['has_stop_loss'] is True
    assert sq['details']['signal_confidence'] == 0.8


def test_multiple_signals_filtering(scorer):
    """Strategies with increasing WF Sharpe should score increasingly higher."""
    scores = []
    for i in range(5):
        sharpe = 0.3 + i * 0.8  # 0.3, 1.1, 1.9, 2.7, 3.5
        trades = 3 + i * 3      # 3, 6, 9, 12, 15
        wr = 0.4 + i * 0.1      # 0.4, 0.5, 0.6, 0.7, 0.8
        conf = 0.4 + i * 0.1    # 0.4, 0.5, 0.6, 0.7, 0.8

        strategy = Strategy(
            id=f"s-{i}", name=f"Strategy {i}", description="",
            status=StrategyStatus.LIVE,
            rules={'entry_conditions': [f"cond_{j}" for j in range(min(i + 1, 3))],
                   'exit_conditions': ["exit"]},
            symbols=["AAPL"],
            risk_params=RiskConfig(stop_loss_pct=0.04, take_profit_pct=0.08, position_risk_pct=0.05),
            metadata={'strategy_type': 'mean_reversion', 'wf_test_sharpe': sharpe,
                      'wf_train_sharpe': sharpe * 0.5, 'walk_forward_validated': True},
            created_at=datetime.now(), backtest_results=_bt(sharpe=sharpe, win_rate=wr, trades=trades),
        )
        signal = TradingSignal(
            strategy_id=f"s-{i}", symbol="AAPL", action=SignalAction.ENTER_LONG,
            confidence=conf, reasoning=f"Signal {i}", generated_at=datetime.now(),
        )
        score = scorer.score_signal(signal, strategy)
        scores.append(score.total_score)

    # Scores should be monotonically increasing
    for i in range(1, len(scores)):
        assert scores[i] >= scores[i - 1], \
            f"Score should increase: scores[{i}]={scores[i]:.1f} < scores[{i-1}]={scores[i-1]:.1f}"

    # Best strategy (Sharpe 3.5, 80% WR, 15 trades) should pass threshold
    assert scores[-1] >= 60, f"Best strategy should pass 60, got {scores[-1]}"
    # Worst strategy (Sharpe 0.3, 40% WR, 3 trades) should fail
    assert scores[0] < 56, f"Worst strategy should be below 56, got {scores[0]}"
