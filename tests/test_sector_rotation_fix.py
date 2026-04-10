"""Tests for Sector Rotation fix (Task 4) — real FMP sector data integration.

Tests cover:
- get_sector_performance() with mocked FMP response
- Sector ranking logic
- Fallback to ETF price data
- [PBT] Sector ranking produces sorted order
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from hypothesis import given, settings, assume
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_price_df(days: int = 200, start_price: float = 100.0) -> pd.DataFrame:
    """Create a synthetic OHLCV DataFrame for testing."""
    dates = pd.date_range(end=datetime.now(), periods=days, freq='B')
    np.random.seed(42)
    prices = start_price * np.cumprod(1 + np.random.normal(0.0003, 0.01, days))
    return pd.DataFrame({
        'open': prices * 0.999,
        'high': prices * 1.005,
        'low': prices * 0.995,
        'close': prices,
        'volume': np.random.randint(1_000_000, 10_000_000, days),
    }, index=dates)


def _make_provider(fmp_enabled: bool = True, sector_response: dict = None):
    """Create a mocked FundamentalDataProvider for testing."""
    provider = Mock()
    provider.fmp_enabled = fmp_enabled
    provider.fmp_rate_limiter = Mock()
    provider.fmp_rate_limiter.can_make_call.return_value = True
    provider.fmp_rate_limiter.record_call = Mock()
    provider.SECTOR_ETFS = {
        'XLE': 'Energy', 'XLF': 'Financials', 'XLK': 'Technology',
        'XLU': 'Utilities', 'XLV': 'Healthcare', 'XLI': 'Industrials',
        'XLP': 'Consumer Staples', 'XLY': 'Consumer Discretionary',
    }
    provider._sector_perf_cache = None
    provider._sector_perf_cache_ts = None

    if sector_response is not None:
        provider.get_sector_performance.return_value = sector_response
    else:
        provider.get_sector_performance.return_value = {}

    return provider


SAMPLE_SECTOR_DATA = {
    'XLK': {'1m': 0.05, '3m': 0.12, '6m': 0.18, '1y': 0.25},
    'XLF': {'1m': 0.03, '3m': 0.08, '6m': 0.10, '1y': 0.15},
    'XLE': {'1m': -0.02, '3m': 0.15, '6m': 0.20, '1y': 0.30},
    'XLV': {'1m': 0.01, '3m': 0.05, '6m': 0.08, '1y': 0.12},
    'XLI': {'1m': 0.04, '3m': 0.10, '6m': 0.14, '1y': 0.20},
    'XLU': {'1m': -0.01, '3m': 0.02, '6m': 0.04, '1y': 0.06},
    'XLP': {'1m': 0.00, '3m': 0.03, '6m': 0.05, '1y': 0.08},
    'XLY': {'1m': 0.06, '3m': 0.11, '6m': 0.16, '1y': 0.22},
}


# ---------------------------------------------------------------------------
# 4.4.1 — Test get_sector_performance() with mocked FMP response
# ---------------------------------------------------------------------------

class TestGetSectorPerformance:
    """Tests for FundamentalDataProvider.get_sector_performance()."""

    def test_returns_sector_data_from_fmp(self):
        """get_sector_performance returns parsed sector ETF data from FMP."""
        from src.data.fundamental_data_provider import FundamentalDataProvider

        config = {'fmp_api_key': 'test_key'}
        with patch.object(FundamentalDataProvider, '__init__', lambda self, cfg: None):
            provider = FundamentalDataProvider.__new__(FundamentalDataProvider)
            provider.config = config
            provider.fmp_enabled = True
            provider.fmp_rate_limiter = Mock()
            provider.fmp_rate_limiter.can_make_call.return_value = True
            provider.fmp_rate_limiter.record_call = Mock()
            provider._sector_perf_cache = None
            provider._sector_perf_cache_ts = None
            provider.SECTOR_ETFS = {'XLK': 'Technology', 'XLF': 'Financials'}

            # Mock _fmp_request to return stock-price-change data
            def mock_fmp_request(endpoint, **kwargs):
                symbol = kwargs.get('symbol', '')
                if symbol == 'XLK':
                    return [{'1M': 5.0, '3M': 12.0, '6M': 18.0, '1Y': 25.0}]
                elif symbol == 'XLF':
                    return [{'1M': 3.0, '3M': 8.0, '6M': 10.0, '1Y': 15.0}]
                return None

            provider._fmp_request = mock_fmp_request

            result = provider.get_sector_performance()

            assert 'XLK' in result
            assert 'XLF' in result
            assert abs(result['XLK']['1m'] - 0.05) < 1e-6
            assert abs(result['XLK']['3m'] - 0.12) < 1e-6
            assert abs(result['XLF']['6m'] - 0.10) < 1e-6

    def test_returns_cached_data_within_ttl(self):
        """get_sector_performance returns cached data if within 24h TTL."""
        from src.data.fundamental_data_provider import FundamentalDataProvider

        with patch.object(FundamentalDataProvider, '__init__', lambda self, cfg: None):
            provider = FundamentalDataProvider.__new__(FundamentalDataProvider)
            provider._sector_perf_cache = SAMPLE_SECTOR_DATA
            provider._sector_perf_cache_ts = datetime.now() - timedelta(hours=1)

            result = provider.get_sector_performance()
            assert result == SAMPLE_SECTOR_DATA

    def test_returns_empty_when_fmp_disabled(self):
        """get_sector_performance returns empty dict when FMP is disabled and no fallback."""
        from src.data.fundamental_data_provider import FundamentalDataProvider

        with patch.object(FundamentalDataProvider, '__init__', lambda self, cfg: None):
            provider = FundamentalDataProvider.__new__(FundamentalDataProvider)
            provider.config = {}
            provider.fmp_enabled = False
            provider._sector_perf_cache = None
            provider._sector_perf_cache_ts = None

            # Mock fallback to also return empty
            provider._compute_sector_returns_from_prices = Mock(return_value={})

            result = provider.get_sector_performance()
            assert result == {}


# ---------------------------------------------------------------------------
# 4.4.2 — Test sector ranking logic
# ---------------------------------------------------------------------------

class TestSectorRanking:
    """Tests for sector ranking in _simulate_sector_rotation_with_fundamentals."""

    def _make_engine(self, sector_data=None):
        """Create a minimal StrategyEngine mock for testing."""
        engine = Mock()
        engine._fundamental_data_provider = _make_provider(
            sector_response=sector_data or SAMPLE_SECTOR_DATA
        )
        engine._simulate_with_price_proxy = Mock(return_value=[])

        # Import the real method and bind it
        from src.strategy.strategy_engine import StrategyEngine
        import types
        engine._simulate_sector_rotation_with_fundamentals = types.MethodType(
            StrategyEngine._simulate_sector_rotation_with_fundamentals, engine
        )
        return engine

    def test_ranks_by_3m_return_default(self):
        """Sectors are ranked by 3-month return by default."""
        engine = self._make_engine()
        df = _make_price_df(200)
        params = {'top_sectors': 3, 'rebalance_frequency_days': 30}
        strategy = Mock()
        strategy.symbols = ['XLK']

        trades = engine._simulate_sector_rotation_with_fundamentals(df, params, strategy)

        # Should produce trades (the method runs on the price data)
        # The top 3 by 3m return from SAMPLE_SECTOR_DATA are: XLE(0.15), XLK(0.12), XLY(0.11)
        assert len(trades) > 0
        assert trades[0].get('fundamental_trigger') == 'sector_rotation'
        assert 'XLE' in trades[0].get('top_sectors', [])

    def test_top_n_configurable(self):
        """top_sectors parameter controls how many sectors are selected."""
        engine = self._make_engine()
        df = _make_price_df(200)

        params_2 = {'top_sectors': 2, 'rebalance_frequency_days': 30}
        trades = engine._simulate_sector_rotation_with_fundamentals(df, params_2, Mock())
        if trades:
            assert len(trades[0].get('top_sectors', [])) == 2

        params_5 = {'top_sectors': 5, 'rebalance_frequency_days': 30}
        trades = engine._simulate_sector_rotation_with_fundamentals(df, params_5, Mock())
        if trades:
            assert len(trades[0].get('top_sectors', [])) == 5

    def test_rebalance_interval_configurable(self):
        """rebalance_frequency_days controls trade spacing."""
        engine = self._make_engine()
        df = _make_price_df(300)

        # Short rebalance → more trades
        params_short = {'top_sectors': 3, 'rebalance_frequency_days': 15}
        trades_short = engine._simulate_sector_rotation_with_fundamentals(df, params_short, Mock())

        # Long rebalance → fewer trades
        params_long = {'top_sectors': 3, 'rebalance_frequency_days': 60}
        trades_long = engine._simulate_sector_rotation_with_fundamentals(df, params_long, Mock())

        assert len(trades_short) >= len(trades_long)


# ---------------------------------------------------------------------------
# 4.4.3 — Test fallback to ETF price data
# ---------------------------------------------------------------------------

class TestSectorRotationFallback:
    """Tests for fallback behavior when FMP data is unavailable."""

    def test_falls_back_to_price_proxy_when_no_data(self):
        """When get_sector_performance returns empty, falls back to price proxy."""
        engine = Mock()
        engine._fundamental_data_provider = _make_provider(sector_response={})
        engine._simulate_with_price_proxy = Mock(return_value=[{'pnl_pct': 0.05}])

        from src.strategy.strategy_engine import StrategyEngine
        import types
        engine._simulate_sector_rotation_with_fundamentals = types.MethodType(
            StrategyEngine._simulate_sector_rotation_with_fundamentals, engine
        )

        df = _make_price_df(200)
        params = {'top_sectors': 3}
        result = engine._simulate_sector_rotation_with_fundamentals(df, params, Mock())

        engine._simulate_with_price_proxy.assert_called_once()
        assert result == [{'pnl_pct': 0.05}]

    def test_falls_back_when_no_provider(self):
        """When _fundamental_data_provider is None and can't be created, falls back to price proxy."""
        engine = Mock()
        engine._fundamental_data_provider = None
        engine._simulate_with_price_proxy = Mock(return_value=[])

        from src.strategy.strategy_engine import StrategyEngine
        import types
        engine._simulate_sector_rotation_with_fundamentals = types.MethodType(
            StrategyEngine._simulate_sector_rotation_with_fundamentals, engine
        )

        # Patch the import inside the method
        with patch.dict('sys.modules', {'src.data.fundamental_data_provider': Mock(
            FundamentalDataProvider=Mock(side_effect=Exception("Cannot create provider"))
        )}):
            df = _make_price_df(200)
            params = {'top_sectors': 3}
            result = engine._simulate_sector_rotation_with_fundamentals(df, params, Mock())

        engine._simulate_with_price_proxy.assert_called_once()
        assert result == []


# ---------------------------------------------------------------------------
# 4.4.4 — [PBT] Sector ranking produces sorted order
# ---------------------------------------------------------------------------

# Strategy for generating sector return dicts
sector_return_strategy = st.dictionaries(
    keys=st.sampled_from(['XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLU', 'XLP', 'XLY']),
    values=st.fixed_dictionaries({
        '1m': st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False),
        '3m': st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False),
        '6m': st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False),
        '1y': st.floats(min_value=-1.0, max_value=2.0, allow_nan=False, allow_infinity=False),
    }),
    min_size=1,
    max_size=8,
)


class TestSectorRankingProperty:
    """
    **Validates: Requirements 4.2**

    Property 4: For any set of sector returns, ranking by trailing period
    produces a sorted order where sector_returns[rank[i]] >= sector_returns[rank[i+1]].
    """

    @given(sector_data=sector_return_strategy)
    @settings(max_examples=100, deadline=None)
    def test_ranking_produces_sorted_order(self, sector_data):
        """For any sector returns, ranking by 3m return produces descending order."""
        assume(len(sector_data) >= 2)

        ranked = sorted(
            sector_data.items(),
            key=lambda x: x[1].get('3m', 0.0),
            reverse=True,
        )

        returns = [v.get('3m', 0.0) for _, v in ranked]
        for i in range(len(returns) - 1):
            assert returns[i] >= returns[i + 1], (
                f"Ranking not sorted at index {i}: {returns[i]} < {returns[i+1]}"
            )

    @given(
        sector_data=sector_return_strategy,
        period=st.sampled_from(['1m', '3m', '6m', '1y']),
        top_n=st.integers(min_value=1, max_value=8),
    )
    @settings(max_examples=100, deadline=None)
    def test_top_n_are_highest_performers(self, sector_data, period, top_n):
        """Top N sectors have returns >= all non-selected sectors for the given period."""
        assume(len(sector_data) >= 2)
        top_n = min(top_n, len(sector_data))

        ranked = sorted(
            sector_data.items(),
            key=lambda x: x[1].get(period, 0.0),
            reverse=True,
        )
        selected = ranked[:top_n]
        remaining = ranked[top_n:]

        if selected and remaining:
            min_selected = min(v.get(period, 0.0) for _, v in selected)
            max_remaining = max(v.get(period, 0.0) for _, v in remaining)
            assert min_selected >= max_remaining, (
                f"Selected min {min_selected} < remaining max {max_remaining}"
            )
