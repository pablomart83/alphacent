"""Regression test for the momentum-aware RSI semantic validator (2026-06-16).

Latent bug: strategy_engine.validate_rule_semantics treated ANY `RSI(N) < X`
ENTRY as an oversold (mean-reversion) signal and capped X at ~55. A momentum
template that uses `RSI < 80` as a blow-off CEILING filter (ride the breakout
only while not yet overbought) had its entry rule silently DROPPED — entries
went all-False, 0 trades, no error. The fix makes the cap momentum-aware: it is
skipped when the condition also carries a trend / breakout / momentum component
(or an RSI lower bound).
"""
import pandas as pd
import pytest

from src.strategy.strategy_engine import StrategyEngine


@pytest.fixture(scope="module")
def engine():
    return StrategyEngine(llm_service=None, market_data=None)


def _series(values):
    idx = pd.date_range("2024-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=idx, dtype=float)


def test_momentum_rsi_ceiling_filter_is_not_dropped(engine):
    # Breakout entry with RSI<80 as a blow-off filter. RSI=70 (<80) everywhere;
    # CLOSE crosses above the Donchian upper on the second half of the window.
    n = 60
    close = _series([100 + i for i in range(n)])
    indicators = {
        "DONCHIAN_UPPER_50": _series([130] * n),
        "RSI_14": _series([70] * n),
    }
    rules = {
        "entry_conditions": ["CLOSE > DONCHIAN_UPPER(50) AND RSI(14) < 80"],
        "exit_conditions": ["RSI(14) > 90"],
    }
    entries, _exits = engine._parse_strategy_rules(
        close, close, close, indicators, rules
    )
    # The rule must NOT be dropped: entries fire on the bars where CLOSE > 130.
    assert entries.any(), "momentum RSI<80 ceiling filter was silently dropped"
    assert bool(entries.iloc[-1]) is True


def test_pure_oversold_misconfig_still_capped(engine):
    # Negative control: a bare `RSI(14) < 80` ENTRY with no momentum sibling is a
    # genuinely mis-set oversold threshold. The cap must STILL drop it (RSI=70<80
    # everywhere would otherwise fire every bar).
    n = 30
    close = _series([100 + i for i in range(n)])
    indicators = {"RSI_14": _series([70] * n)}
    rules = {
        "entry_conditions": ["RSI(14) < 80"],
        "exit_conditions": ["RSI(14) > 90"],
    }
    entries, _exits = engine._parse_strategy_rules(
        close, close, close, indicators, rules
    )
    assert not entries.any(), "oversold cap should still reject a bare RSI<80 entry"


def test_validate_rsi_thresholds_skips_momentum(engine):
    # The sibling validator (validate_strategy_rules path) matches PROSE-style
    # RSI conditions ("RSI_14 below 80"). It must not flag a momentum template's
    # RSI ceiling filter as an invalid oversold threshold.
    result = {"errors": [], "suggestions": []}
    engine._validate_rsi_thresholds(
        ["CLOSE > SMA(200) AND RSI_14 below 80"], ["RSI_14 above 85"], result
    )
    assert result["errors"] == []


def test_validate_rsi_thresholds_still_flags_bare_oversold(engine):
    result = {"errors": [], "suggestions": []}
    engine._validate_rsi_thresholds(["RSI_14 below 80"], ["RSI_14 above 85"], result)
    assert result["errors"], "bare RSI below 80 oversold misconfig should still be flagged"
