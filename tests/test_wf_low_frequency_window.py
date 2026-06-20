"""Frequency-aware walk-forward window for low-frequency factor templates (2026-06-20).

Low-frequency factor/rank templates were being rejected at WF with
has_enough_trades=False — they trade too rarely to clear the 8-trade floor in a
180-day test window, so their edge was never assessed (root cause of the book's
single-factor momentum monoculture). Fix: route them to a long-horizon WF window
so they accumulate a real sample at their natural cadence; the trade-count floor
is NOT lowered.

These tests exercise `_is_low_frequency_template` + `_select_wf_window` routing
without the heavy StrategyProposer.__init__ (object.__new__ + manual state).
"""
from datetime import datetime
from types import SimpleNamespace

from src.strategy.strategy_proposer import StrategyProposer


def _make_proposer():
    p = object.__new__(StrategyProposer)
    # Minimal state the two methods touch.
    p._wf_long_horizon_templates = set(StrategyProposer._LOW_FREQUENCY_TEMPLATE_DEFAULTS)
    p._wf_asset_class_windows = {}          # force the code fallback for *_longhorizon
    p._wf_fallback_train_days = 365
    p._wf_fallback_test_days = 180
    return p


def _strat(name="X", symbols=("AAPL",), interval="1d", rules=None, alpha_edge_type=None):
    meta = {"template_name": name, "interval": interval}
    if alpha_edge_type:
        meta["alpha_edge_type"] = alpha_edge_type
    return SimpleNamespace(name=name, symbols=list(symbols), metadata=meta, rules=rules or {})


# ── classification ───────────────────────────────────────────────────────────

def test_factor_template_is_low_frequency():
    p = _make_proposer()
    assert p._is_low_frequency_template(_strat(name="Low Volatility Factor Long")) is True
    assert p._is_low_frequency_template(_strat(name="Cross-Sectional Momentum Long")) is True


def test_rank_primitive_in_rules_is_low_frequency():
    p = _make_proposer()
    s = _strat(name="Some Custom Rank Strat", rules={"entry": ["RANK_IN_UNIVERSE(...) <= 5"]})
    assert p._is_low_frequency_template(s) is True


def test_alpha_edge_monthly_is_low_frequency():
    p = _make_proposer()
    assert p._is_low_frequency_template(_strat(name="Forex Carry Trend", alpha_edge_type="forex_carry")) is True


def test_high_frequency_momentum_is_not_low_frequency():
    p = _make_proposer()
    s = _strat(name="Price Momentum Breakout", rules={"entry": ["CLOSE > SMA(20)"]})
    assert p._is_low_frequency_template(s) is False


# ── window routing ───────────────────────────────────────────────────────────

def test_low_freq_1d_gets_longhorizon_window():
    p = _make_proposer()
    s = _strat(name="Low Volatility Factor Long", interval="1d")
    train, test, start, end = p._select_wf_window(s, datetime(2026, 6, 20))
    fb = StrategyProposer._LONGHORIZON_WINDOW_FALLBACK
    assert (train, test) == (fb["train"], fb["test"])
    assert test > 180  # materially longer than the standard window


def test_standard_template_keeps_standard_window():
    p = _make_proposer()
    s = _strat(name="Price Momentum Breakout", interval="1d", rules={"entry": ["CLOSE > SMA(20)"]})
    train, test, start, end = p._select_wf_window(s, datetime(2026, 6, 20))
    # No asset_class_windows configured → yaml fallback (365/180), NOT long-horizon.
    assert (train, test) == (365, 180)


def test_longhorizon_window_spans_more_than_standard():
    p = _make_proposer()
    lo = p._select_wf_window(_strat(name="Cross-Sectional Momentum Long"), datetime(2026, 6, 20))
    hi = p._select_wf_window(_strat(name="Price Momentum Breakout", rules={"x": "y"}), datetime(2026, 6, 20))
    # low-freq total span > standard total span
    assert (lo[0] + lo[1]) > (hi[0] + hi[1])
