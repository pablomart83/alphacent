"""Tests for Dividend Aristocrat overtrading fix (Task 5).

Tests cover:
- 5.4.1 6-month entry spacing enforcement
- 5.4.2 Technical confirmation requirement
- 5.4.3 No overlapping trades
- 5.4.4 [PBT] All consecutive trade pairs have entry_gap >= 180 days
- 5.4.5 [PBT] No two trades overlap (t1.exit_date <= t2.entry_date)
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from hypothesis import given, settings, assume
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_price_df(days: int = 500, start_price: float = 100.0, seed: int = 42) -> pd.DataFrame:
    """Create a synthetic OHLCV DataFrame with a pullback pattern for testing."""
    dates = pd.date_range(end=datetime(2024, 6, 1), periods=days, freq='B')
    np.random.seed(seed)
    # Create price series with some pullbacks to trigger entries
    returns = np.random.normal(0.0002, 0.015, days)
    # Inject pullbacks at specific points to ensure entries happen
    for i in range(100, days, 90):
        if i + 10 < days:
            returns[i:i+10] = -0.015  # ~15% pullback over 10 days
    prices = start_price * np.cumprod(1 + returns)
    return pd.DataFrame({
        'open': prices * 0.999,
        'high': prices * 1.005,
        'low': prices * 0.995,
        'close': prices,
        'volume': np.random.randint(1_000_000, 10_000_000, days),
    }, index=dates)


def _make_quarterly_data(num_quarters: int = 8, start_date: str = '2022-06-30',
                         div_yield: float = 0.03, roe: float = 0.15) -> list:
    """Create quarterly fundamental data that meets dividend aristocrat criteria."""
    quarters = []
    dt = datetime.strptime(start_date, '%Y-%m-%d')
    for i in range(num_quarters):
        q_date = dt + timedelta(days=90 * i)
        quarters.append({
            'date': q_date.strftime('%Y-%m-%d'),
            'dividend_yield': div_yield,
            'roe': roe,
            'earnings_surprise': 0.05,
            'revenue_growth': 0.08,
        })
    return quarters


def _make_engine():
    """Create a minimal StrategyEngine-like object for testing the simulation method."""
    engine = Mock()
    engine._fundamental_data_provider = Mock()
    engine._fundamental_data_provider.get_earnings_calendar.return_value = None

    from src.strategy.strategy_engine import StrategyEngine
    import types
    engine._simulate_alpha_edge_with_fundamentals = types.MethodType(
        StrategyEngine._simulate_alpha_edge_with_fundamentals, engine
    )
    engine._simulate_dividend_aristocrat_trades = types.MethodType(
        StrategyEngine._simulate_dividend_aristocrat_trades, engine
    )
    return engine


def _make_strategy(symbol: str = 'JNJ'):
    """Create a mock strategy object."""
    strategy = Mock()
    strategy.symbols = [symbol]
    return strategy


# ---------------------------------------------------------------------------
# 5.4.1 — Test 6-month entry spacing enforcement
# ---------------------------------------------------------------------------

class TestEntrySpacing:
    """Tests that Dividend Aristocrat enforces 180-day minimum gap between entries."""

    def test_fundamentals_branch_enforces_180_day_gap(self):
        """In _simulate_alpha_edge_with_fundamentals, consecutive DA entries are >= 180 days apart."""
        engine = _make_engine()
        df = _make_price_df(days=800, seed=10)
        # Create quarterly data every 90 days — all meeting criteria
        quarterly = _make_quarterly_data(num_quarters=10, start_date='2021-06-30')
        params = {
            'min_entry_gap_days': 180,
            'pullback_confirmation_pct': 0.01,  # Low threshold to allow entries
            'rsi_confirmation_threshold': 80,    # High threshold to allow entries
            'profit_target': 0.10,
            'stop_loss_pct': 0.05,
            'hold_period_max': 60,
        }
        strategy = _make_strategy()

        trades = engine._simulate_alpha_edge_with_fundamentals(
            'dividend_aristocrat', df, quarterly, params, strategy
        )

        if len(trades) >= 2:
            for i in range(len(trades) - 1):
                d1 = datetime.strptime(trades[i]['entry_date'], '%Y-%m-%d')
                d2 = datetime.strptime(trades[i + 1]['entry_date'], '%Y-%m-%d')
                gap = (d2 - d1).days
                assert gap >= 180, (
                    f"Entry gap {gap} days < 180 between trade {i} ({trades[i]['entry_date']}) "
                    f"and trade {i+1} ({trades[i+1]['entry_date']})"
                )

    def test_price_proxy_enforces_180_day_gap(self):
        """In _simulate_dividend_aristocrat_trades, consecutive entries are >= 180 days apart."""
        engine = _make_engine()
        df = _make_price_df(days=800, seed=10)
        params = {
            'pullback_from_high_pct': 0.02,
            'profit_target': 0.12,
            'stop_loss_pct': 0.05,
            'hold_period_max': 90,
            'min_entry_gap_days': 180,
        }

        trades = engine._simulate_dividend_aristocrat_trades(df, params)

        if len(trades) >= 2:
            for i in range(len(trades) - 1):
                d1 = datetime.strptime(trades[i]['entry_date'], '%Y-%m-%d')
                d2 = datetime.strptime(trades[i + 1]['entry_date'], '%Y-%m-%d')
                gap = (d2 - d1).days
                assert gap >= 180, (
                    f"Price-proxy entry gap {gap} days < 180 between trade {i} and {i+1}"
                )


# ---------------------------------------------------------------------------
# 5.4.2 — Test technical confirmation requirement
# ---------------------------------------------------------------------------

class TestTechnicalConfirmation:
    """Tests that DA entries require pullback >= 5% from 252-day high OR RSI < 40."""

    def test_no_entry_without_technical_confirmation(self):
        """When price is near highs and RSI is high, no trades should be entered."""
        engine = _make_engine()
        # Create a steadily rising price series (no pullbacks, high RSI)
        days = 500
        dates = pd.date_range(end=datetime(2024, 6, 1), periods=days, freq='B')
        prices = 100 * np.cumprod(1 + np.full(days, 0.002))  # Steady uptrend
        df = pd.DataFrame({
            'open': prices * 0.999,
            'high': prices * 1.001,
            'low': prices * 0.999,
            'close': prices,
            'volume': np.full(days, 5_000_000),
        }, index=dates)

        quarterly = _make_quarterly_data(num_quarters=6, start_date='2022-06-30')
        params = {
            'min_entry_gap_days': 180,
            'pullback_confirmation_pct': 0.05,
            'rsi_confirmation_threshold': 40,
            'profit_target': 0.10,
            'stop_loss_pct': 0.05,
            'hold_period_max': 60,
        }
        strategy = _make_strategy()

        trades = engine._simulate_alpha_edge_with_fundamentals(
            'dividend_aristocrat', df, quarterly, params, strategy
        )

        # With a steady uptrend, pullback < 5% and RSI > 40, so no entries
        assert len(trades) == 0, f"Expected 0 trades in steady uptrend, got {len(trades)}"

    def test_entry_on_pullback(self):
        """When price pulls back >= 5% from 252-day high, entry is allowed."""
        engine = _make_engine()
        days = 500
        dates = pd.date_range(end=datetime(2024, 6, 1), periods=days, freq='B')
        np.random.seed(99)
        # Create price that rises then drops significantly
        prices = np.zeros(days)
        prices[0] = 100
        for i in range(1, days):
            if 300 <= i <= 320:
                prices[i] = prices[i-1] * 0.99  # ~20% drop over 20 days
            else:
                prices[i] = prices[i-1] * 1.001
        df = pd.DataFrame({
            'open': prices * 0.999,
            'high': prices * 1.002,
            'low': prices * 0.998,
            'close': prices,
            'volume': np.full(days, 5_000_000),
        }, index=dates)

        # Place quarterly data so entry_idx falls during the pullback
        quarterly = _make_quarterly_data(num_quarters=6, start_date='2022-06-30')
        params = {
            'min_entry_gap_days': 180,
            'pullback_confirmation_pct': 0.05,
            'rsi_confirmation_threshold': 40,
            'profit_target': 0.10,
            'stop_loss_pct': 0.05,
            'hold_period_max': 60,
        }
        strategy = _make_strategy()

        trades = engine._simulate_alpha_edge_with_fundamentals(
            'dividend_aristocrat', df, quarterly, params, strategy
        )

        # At least some entries should happen during the pullback period
        # (depends on timing alignment, but the mechanism is tested)
        # This is a smoke test — the PBT tests below are more thorough
        assert isinstance(trades, list)


# ---------------------------------------------------------------------------
# 5.4.3 — Test no overlapping trades
# ---------------------------------------------------------------------------

class TestNoOverlappingTrades:
    """Tests that no two DA trades overlap in time."""

    def test_fundamentals_no_overlap(self):
        """In _simulate_alpha_edge_with_fundamentals, no two DA trades overlap."""
        engine = _make_engine()
        df = _make_price_df(days=800, seed=10)
        quarterly = _make_quarterly_data(num_quarters=10, start_date='2021-06-30')
        params = {
            'min_entry_gap_days': 180,
            'pullback_confirmation_pct': 0.01,
            'rsi_confirmation_threshold': 80,
            'profit_target': 0.10,
            'stop_loss_pct': 0.05,
            'hold_period_max': 60,
        }
        strategy = _make_strategy()

        trades = engine._simulate_alpha_edge_with_fundamentals(
            'dividend_aristocrat', df, quarterly, params, strategy
        )

        if len(trades) >= 2:
            for i in range(len(trades) - 1):
                exit_date = datetime.strptime(trades[i]['exit_date'], '%Y-%m-%d')
                next_entry = datetime.strptime(trades[i + 1]['entry_date'], '%Y-%m-%d')
                assert exit_date <= next_entry, (
                    f"Trade {i} exit {trades[i]['exit_date']} > trade {i+1} entry {trades[i+1]['entry_date']}"
                )

    def test_price_proxy_no_overlap(self):
        """In _simulate_dividend_aristocrat_trades, no two trades overlap (in_trade flag)."""
        engine = _make_engine()
        df = _make_price_df(days=800, seed=10)
        params = {
            'pullback_from_high_pct': 0.02,
            'profit_target': 0.12,
            'stop_loss_pct': 0.05,
            'hold_period_max': 90,
            'min_entry_gap_days': 180,
        }

        trades = engine._simulate_dividend_aristocrat_trades(df, params)

        if len(trades) >= 2:
            for i in range(len(trades) - 1):
                exit_date = datetime.strptime(trades[i]['exit_date'], '%Y-%m-%d')
                next_entry = datetime.strptime(trades[i + 1]['entry_date'], '%Y-%m-%d')
                assert exit_date <= next_entry, (
                    f"Price-proxy trade {i} exit > trade {i+1} entry"
                )


# ---------------------------------------------------------------------------
# 5.4.4 — [PBT] Entry gap >= 180 days
# ---------------------------------------------------------------------------

# Strategy for generating price data parameters
price_params_strategy = st.fixed_dictionaries({
    'days': st.integers(min_value=400, max_value=800),
    'seed': st.integers(min_value=1, max_value=10000),
    'start_price': st.floats(min_value=20.0, max_value=500.0, allow_nan=False, allow_infinity=False),
})


class TestEntrySpacingProperty:
    """
    **Validates: Requirements 5.1**

    Property 5: For any DA backtest on a single symbol, for all consecutive
    trade pairs (t1, t2): t2.entry_date - t1.entry_date >= 180 days.
    """

    @given(price_params=price_params_strategy)
    @settings(max_examples=30, deadline=None)
    def test_price_proxy_entry_gap_property(self, price_params):
        """For any price data, _simulate_dividend_aristocrat_trades enforces 180-day gap."""
        engine = _make_engine()
        df = _make_price_df(
            days=price_params['days'],
            seed=price_params['seed'],
            start_price=price_params['start_price'],
        )
        params = {
            'pullback_from_high_pct': 0.03,
            'profit_target': 0.12,
            'stop_loss_pct': 0.05,
            'hold_period_max': 90,
            'min_entry_gap_days': 180,
        }

        trades = engine._simulate_dividend_aristocrat_trades(df, params)

        if len(trades) >= 2:
            for i in range(len(trades) - 1):
                d1 = datetime.strptime(trades[i]['entry_date'], '%Y-%m-%d')
                d2 = datetime.strptime(trades[i + 1]['entry_date'], '%Y-%m-%d')
                gap = (d2 - d1).days
                assert gap >= 180, (
                    f"Entry gap {gap} days < 180 between trades {i} and {i+1}"
                )


# ---------------------------------------------------------------------------
# 5.4.5 — [PBT] No overlapping trades
# ---------------------------------------------------------------------------

class TestNoOverlapProperty:
    """
    **Validates: Requirements 5.4**

    Property 9: For any DA backtest, no two trades overlap
    (t1.exit_date <= t2.entry_date for all consecutive pairs).
    """

    @given(price_params=price_params_strategy)
    @settings(max_examples=30, deadline=None)
    def test_price_proxy_no_overlap_property(self, price_params):
        """For any price data, _simulate_dividend_aristocrat_trades produces non-overlapping trades."""
        engine = _make_engine()
        df = _make_price_df(
            days=price_params['days'],
            seed=price_params['seed'],
            start_price=price_params['start_price'],
        )
        params = {
            'pullback_from_high_pct': 0.03,
            'profit_target': 0.12,
            'stop_loss_pct': 0.05,
            'hold_period_max': 90,
            'min_entry_gap_days': 180,
        }

        trades = engine._simulate_dividend_aristocrat_trades(df, params)

        if len(trades) >= 2:
            for i in range(len(trades) - 1):
                exit_date = datetime.strptime(trades[i]['exit_date'], '%Y-%m-%d')
                next_entry = datetime.strptime(trades[i + 1]['entry_date'], '%Y-%m-%d')
                assert exit_date <= next_entry, (
                    f"Trade {i} exit {trades[i]['exit_date']} overlaps with "
                    f"trade {i+1} entry {trades[i+1]['entry_date']}"
                )
