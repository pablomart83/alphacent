"""Unit tests for the Forex Carry alpha-edge handler + backtest simulator (2026-06-16).

Carry harvests the central-bank interest-rate differential between a pair's two
currencies, gated by a price-trend filter (carry+trend overlay). The signal comes
from FRED policy-rate spreads (get_carry_rates live / get_historical_carry in
backtest), not the DSL or FMP paths.
"""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.strategy.strategy_engine import StrategyEngine
from src.models.enums import SignalAction, PositionSide


@pytest.fixture(scope="module")
def engine():
    return StrategyEngine(llm_service=None, market_data=None)


def _df(values):
    idx = pd.date_range("2023-01-01", periods=len(values), freq="D")
    v = np.asarray(values, dtype=float)
    return pd.DataFrame(
        {"open": v, "high": v, "low": v, "close": v, "volume": 1e6}, index=idx
    )


def _strategy():
    return SimpleNamespace(id="carry-test", name="Forex Carry Trend EURUSD",
                           symbols=["EURUSD"], metadata={})


# ── Backtest simulator ───────────────────────────────────────────────────────

def test_long_carry_uptrend_produces_long_trades(engine):
    n = 220
    df = _df(np.linspace(1.00, 1.30, n))           # steady uptrend
    carry = pd.Series(1.5, index=df.index)          # strongly positive carry
    params = {"sma_period": 50, "carry_entry_threshold": 0.5, "take_profit_pct": 0.05,
              "stop_loss_pct": 0.02, "hold_period_max": 90}
    trades = engine._simulate_forex_carry_trades(df, carry, params, _strategy())
    assert len(trades) > 0
    assert all(t["direction"] == "long" for t in trades)


def test_short_carry_downtrend_produces_short_trades(engine):
    n = 220
    df = _df(np.linspace(1.30, 1.00, n))            # steady downtrend
    carry = pd.Series(-1.5, index=df.index)         # strongly negative carry
    params = {"sma_period": 50, "carry_entry_threshold": 0.5, "take_profit_pct": 0.05,
              "stop_loss_pct": 0.02, "hold_period_max": 90}
    trades = engine._simulate_forex_carry_trades(df, carry, params, _strategy())
    assert len(trades) > 0
    assert all(t["direction"] == "short" for t in trades)


def test_flat_carry_produces_no_trades(engine):
    # Carry below the entry threshold => no edge => no trades regardless of trend.
    n = 220
    df = _df(np.linspace(1.00, 1.30, n))
    carry = pd.Series(0.1, index=df.index)
    params = {"sma_period": 50, "carry_entry_threshold": 0.5}
    trades = engine._simulate_forex_carry_trades(df, carry, params, _strategy())
    assert trades == []


# ── Live handler ─────────────────────────────────────────────────────────────

def _engine_with_carry(monkeypatch, engine, pair_carry):
    analyzer = SimpleNamespace(get_carry_rates=lambda: {"carry": pair_carry, "rates": {}})
    monkeypatch.setattr(engine, "market_analyzer", analyzer)
    return engine


def test_handler_enters_long_on_positive_carry_uptrend(engine, monkeypatch):
    _engine_with_carry(monkeypatch, engine, {"EURUSD": 1.2})
    df = _df(np.linspace(1.00, 1.20, 60))  # uptrend: last price > SMA(50)
    sig = engine._handle_forex_carry(_strategy(), "EURUSD", df, {"sma_period": 50},
                                     has_open_position=False, open_position=None)
    assert sig is not None and sig.action == SignalAction.ENTER_LONG


def test_handler_enters_short_on_negative_carry_downtrend(engine, monkeypatch):
    _engine_with_carry(monkeypatch, engine, {"USDJPY": -1.2})
    df = _df(np.linspace(150.0, 130.0, 60))  # downtrend
    strat = SimpleNamespace(id="c", name="Forex Carry Trend USDJPY", symbols=["USDJPY"], metadata={})
    sig = engine._handle_forex_carry(strat, "USDJPY", df, {"sma_period": 50},
                                     has_open_position=False, open_position=None)
    assert sig is not None and sig.action == SignalAction.ENTER_SHORT


def test_handler_no_signal_when_carry_unavailable(engine, monkeypatch):
    _engine_with_carry(monkeypatch, engine, {})  # no carry for EURUSD
    df = _df(np.linspace(1.00, 1.20, 60))
    sig = engine._handle_forex_carry(_strategy(), "EURUSD", df, {"sma_period": 50},
                                     has_open_position=False, open_position=None)
    assert sig is None


def test_handler_exits_long_on_trend_reversal(engine, monkeypatch):
    _engine_with_carry(monkeypatch, engine, {"EURUSD": 1.2})
    # Price rose then fell below SMA(50) at the end → long exit.
    up = np.linspace(1.00, 1.25, 40)
    down = np.linspace(1.25, 1.05, 30)
    df = _df(np.concatenate([up, down]))
    pos = SimpleNamespace(side=PositionSide.LONG, entry_price=1.10)
    sig = engine._handle_forex_carry(_strategy(), "EURUSD", df, {"sma_period": 50},
                                     has_open_position=True, open_position=pos)
    assert sig is not None and sig.action == SignalAction.EXIT_LONG
