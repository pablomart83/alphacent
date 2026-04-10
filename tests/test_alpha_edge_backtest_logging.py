"""Tests for Alpha Edge backtest per-trade logging (task 11.11.12)."""
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


def _make_price_df(days=200, start_price=100.0, seed=42):
    """Create a synthetic price DataFrame with realistic movements."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range(start=datetime(2023, 1, 1), periods=days, freq='B')
    returns = rng.normal(0.0005, 0.02, size=days)
    # Inject a few sharp moves to trigger earnings momentum entries
    for spike_idx in [30, 80, 130, 170]:
        if spike_idx < days:
            returns[spike_idx] = 0.05  # 5% spike
    prices = start_price * np.cumprod(1 + returns)
    df = pd.DataFrame({
        'open': prices * (1 - rng.uniform(0, 0.005, days)),
        'high': prices * (1 + rng.uniform(0, 0.01, days)),
        'low': prices * (1 - rng.uniform(0, 0.01, days)),
        'close': prices,
        'volume': rng.randint(1_000_000, 10_000_000, days),
    }, index=dates)
    return df


class TestAlphaEdgeBacktestLogging:
    """Test that simulation methods include entry_date and exit_date in trade dicts."""

    def test_earnings_momentum_trades_have_dates(self):
        """Earnings momentum trades should include entry_date and exit_date."""
        from src.strategy.strategy_engine import StrategyEngine
        engine = StrategyEngine.__new__(StrategyEngine)
        df = _make_price_df(days=200)
        params = {'profit_target': 0.05, 'stop_loss_pct': 0.03, 'hold_period_max': 30, 'entry_delay_days': 2}
        trades = engine._simulate_earnings_momentum_trades(df, params)
        assert len(trades) > 0, "Expected at least one trade from earnings momentum simulation"
        for t in trades:
            assert 'entry_date' in t, "Trade missing entry_date"
            assert 'exit_date' in t, "Trade missing exit_date"
            assert 'entry_price' in t
            assert 'exit_price' in t
            assert 'pnl_pct' in t
            assert 'days_held' in t
            assert 'exit_reason' in t
            # Dates should be parseable strings
            datetime.strptime(t['entry_date'], '%Y-%m-%d')
            datetime.strptime(t['exit_date'], '%Y-%m-%d')

    def test_sector_rotation_trades_have_dates(self):
        """Sector rotation trades should include entry_date and exit_date."""
        from src.strategy.strategy_engine import StrategyEngine
        engine = StrategyEngine.__new__(StrategyEngine)
        df = _make_price_df(days=300)
        params = {'rebalance_frequency_days': 30, 'momentum_lookback_days': 60, 'stop_loss_pct': 0.08, 'take_profit_pct': 0.15}
        trades = engine._simulate_sector_rotation_trades(df, params)
        assert len(trades) > 0, "Expected at least one trade from sector rotation simulation"
        for t in trades:
            assert 'entry_date' in t
            assert 'exit_date' in t

    def test_quality_mean_reversion_trades_have_dates(self):
        """Quality mean reversion trades should include entry_date and exit_date."""
        from src.strategy.strategy_engine import StrategyEngine
        engine = StrategyEngine.__new__(StrategyEngine)
        # Create data with RSI oversold conditions
        rng = np.random.RandomState(99)
        days = 300
        dates = pd.date_range(start=datetime(2023, 1, 1), periods=days, freq='B')
        prices = np.zeros(days)
        prices[0] = 100.0
        for i in range(1, days):
            if 80 <= i <= 95:
                prices[i] = prices[i-1] * 0.97  # Sharp decline to trigger RSI oversold
            else:
                prices[i] = prices[i-1] * (1 + rng.normal(0.001, 0.01))
        df = pd.DataFrame({
            'open': prices, 'high': prices * 1.005, 'low': prices * 0.995,
            'close': prices, 'volume': np.full(days, 5_000_000),
        }, index=dates)
        params = {'rsi_period': 14, 'oversold_threshold': 25, 'profit_target': 0.05, 'stop_loss_pct': 0.05}
        trades = engine._simulate_quality_mean_reversion_trades(df, params)
        # May or may not produce trades depending on exact RSI values, but if it does, dates should be present
        for t in trades:
            assert 'entry_date' in t
            assert 'exit_date' in t

    def test_backtest_logging_output(self, caplog):
        """backtest_alpha_edge_strategy should log per-trade details."""
        from src.strategy.strategy_engine import StrategyEngine
        from src.models.dataclasses import Strategy

        engine = StrategyEngine.__new__(StrategyEngine)
        engine.market_data = MagicMock()

        # Create mock market data
        df = _make_price_df(days=200)
        mock_data = []
        for idx, row in df.iterrows():
            md = MagicMock()
            md.timestamp = idx
            md.open = row['open']
            md.high = row['high']
            md.low = row['low']
            md.close = row['close']
            md.volume = row['volume']
            mock_data.append(md)
        engine.market_data.get_historical_data.return_value = mock_data

        # Mock fundamental data provider with quarterly data that triggers earnings momentum
        mock_provider = MagicMock()
        quarterly_data = []
        base_date = datetime(2023, 1, 1)
        prev_eps = 1.0
        for i in range(8):
            q_date = (base_date + timedelta(days=90 * i)).strftime('%Y-%m-%d')
            eps = prev_eps * 1.1  # Growing EPS
            quarterly_data.append({
                'date': q_date,
                'eps': eps,
                'revenue': 50_000_000_000 * (1 + 0.05 * i),
                'revenue_growth': 0.12,
                'earnings_surprise': 0.08,  # 8% beat — triggers earnings_momentum
                'earnings_surprise_source': 'analyst_estimate',
                'pe_ratio': 25.0,
                'roe': 0.20,
                'dividend_yield': 0.01,
                'debt_to_equity': 0.5,
                'piotroski_f_score': 7,
                'accruals_ratio': 0.02,
                'fcf_yield': 0.04,
                'sue': 2.0,
            })
            prev_eps = eps
        mock_provider.get_historical_fundamentals.return_value = quarterly_data
        mock_provider.get_earnings_calendar.return_value = None
        engine._fundamental_data_provider = mock_provider

        # Mock _get_asset_class to return 'stock'
        engine._get_asset_class = lambda symbol: 'stock'

        strategy = MagicMock(spec=Strategy)
        strategy.name = "Test Earnings Momentum AAPL"
        strategy.symbols = ["AAPL"]
        strategy.metadata = {
            'strategy_category': 'alpha_edge',
            'template_name': 'earnings_momentum',
            'alpha_edge_template': 'earnings_momentum',
            'default_parameters': {'profit_target': 0.05, 'stop_loss_pct': 0.03, 'hold_period_max': 30, 'entry_delay_days': 2}
        }
        strategy.parameters = {}

        with caplog.at_level(logging.INFO, logger="src.strategy.strategy_engine"):
            result = engine.backtest_alpha_edge_strategy(
                strategy,
                start=datetime(2023, 1, 1),
                end=datetime(2023, 12, 31)
            )

        # Should have logged AE backtest info
        log_text = caplog.text
        assert "[AlphaEdgeBacktest]" in log_text
        assert "AAPL" in log_text
        # With real fundamental data mocked, we should get trades
        assert result.total_trades > 0
        assert "Trade 1:" in log_text
        assert "P&L=" in log_text
        assert "entry=$" in log_text
