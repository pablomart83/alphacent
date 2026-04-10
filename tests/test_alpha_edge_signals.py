"""Tests for Alpha Edge fundamental signal generation in StrategyEngine."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
import pandas as pd
import numpy as np

from src.strategy.strategy_engine import StrategyEngine
from src.models import (
    Strategy,
    StrategyStatus,
    RiskConfig,
    TradingSignal,
)
from src.models.enums import SignalAction


def _make_ohlcv_df(days=120, start_price=100.0, trend=0.001):
    """Create a mock OHLCV DataFrame."""
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    prices = [start_price]
    for i in range(1, days):
        prices.append(prices[-1] * (1 + trend + np.random.normal(0, 0.01)))
    prices = np.array(prices)
    df = pd.DataFrame({
        'open': prices * 0.999,
        'high': prices * 1.02,
        'low': prices * 0.98,
        'close': prices,
        'volume': np.random.randint(500000, 2000000, size=days),
    }, index=dates)
    return df


def _make_oversold_df(days=120, start_price=100.0):
    """Create OHLCV data that produces RSI < 30 (sharp recent decline)."""
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    prices = [start_price] * (days - 20)
    # Sharp decline in last 20 days
    for i in range(20):
        prices.append(prices[-1] * 0.97)
    prices = np.array(prices)
    df = pd.DataFrame({
        'open': prices * 0.999,
        'high': prices * 1.005,
        'low': prices * 0.995,
        'close': prices,
        'volume': np.random.randint(500000, 2000000, size=days),
    }, index=dates)
    return df


def _make_strategy(name, template_type, symbols=None):
    """Create a mock Alpha Edge strategy."""
    return Strategy(
        id=f"test-{template_type}",
        name=name,
        description=f"Test {template_type} strategy",
        status=StrategyStatus.DEMO,
        rules={"entry_conditions": [], "exit_conditions": [], "indicators": ["SMA:50"]},
        symbols=symbols or ["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        metadata={
            "strategy_category": "alpha_edge",
            "template_name": template_type,
        }
    )


@pytest.fixture
def engine():
    """Create StrategyEngine with mocked dependencies."""
    mock_market_data = Mock()
    with patch('src.strategy.strategy_engine.get_database') as mock_db:
        mock_db.return_value = Mock()
        eng = StrategyEngine(None, mock_market_data)
        eng._save_strategy = Mock()
        eng._load_strategy = Mock()
        eng.db = Mock()
        return eng


@pytest.fixture
def mock_provider():
    """Create a mock FundamentalDataProvider."""
    provider = Mock()
    return provider


@pytest.fixture
def base_config():
    """Base config matching autonomous_trading.yaml structure."""
    return {
        'alpha_edge': {
            'earnings_momentum': {
                'enabled': True,
                'earnings_surprise_min': 0.05,
                'revenue_growth_min': 0.10,
                'entry_delay_days': 2,
                'hold_period_days': 45,
                'profit_target': 0.10,
                'stop_loss': 0.05,
                'exit_before_earnings_days': 7,
            },
            'sector_rotation': {
                'enabled': True,
                'max_positions': 3,
                'rebalance_frequency_days': 30,
                'stop_loss_pct': 0.08,
            },
            'quality_mean_reversion': {
                'enabled': True,
                'min_roe': 0.15,
                'max_debt_equity': 0.5,
                'oversold_threshold': 30,
                'profit_target': 0.05,
                'stop_loss': 0.03,
            },
        },
        'data_sources': {
            'financial_modeling_prep': {'enabled': True, 'api_key': 'test'},
        },
    }


# ============================================================
# Alpha Edge detection tests
# ============================================================

class TestAlphaEdgeDetection:
    def test_is_alpha_edge_strategy(self, engine):
        strategy = _make_strategy("Earnings Momentum", "earnings_momentum")
        assert engine._is_alpha_edge_strategy(strategy) is True

    def test_is_not_alpha_edge_strategy(self, engine):
        strategy = Strategy(
            id="test-dsl", name="RSI Mean Reversion", description="",
            status=StrategyStatus.DEMO, rules={}, symbols=["AAPL"],
            risk_params=RiskConfig(), created_at=datetime.now(),
            metadata={"template_name": "rsi_mean_reversion"}
        )
        assert engine._is_alpha_edge_strategy(strategy) is False

    def test_get_template_type_earnings(self, engine):
        strategy = _make_strategy("Earnings Momentum", "earnings_momentum")
        assert engine._get_alpha_edge_template_type(strategy) == 'earnings_momentum'

    def test_get_template_type_sector(self, engine):
        strategy = _make_strategy("Sector Rotation", "sector_rotation")
        assert engine._get_alpha_edge_template_type(strategy) == 'sector_rotation'

    def test_get_template_type_quality(self, engine):
        strategy = _make_strategy("Quality Mean Reversion", "quality_mean_reversion")
        assert engine._get_alpha_edge_template_type(strategy) == 'quality_mean_reversion'


# ============================================================
# Earnings Momentum tests
# ============================================================

class TestEarningsMomentumSignal:
    def test_entry_signal_all_conditions_met(self, engine, mock_provider, base_config):
        """Entry when earnings surprise > 5%, revenue growth > 10%, within entry window."""
        strategy = _make_strategy("Earnings Momentum", "earnings_momentum")
        df = _make_ohlcv_df()

        mock_provider.calculate_earnings_surprise.return_value = 0.08  # 8% beat
        mock_provider.get_fundamental_data.return_value = Mock(
            revenue_growth=0.15, market_cap=500_000_000
        )
        mock_provider.get_days_since_earnings.return_value = 3  # 3 days since earnings

        engine._fundamental_data_provider = mock_provider

        signal = engine._check_earnings_momentum_signal(
            strategy, "AAPL", df, mock_provider,
            base_config['alpha_edge']['earnings_momentum'],
            has_open_position=False, open_position=None
        )

        assert signal is not None
        assert signal.action == SignalAction.ENTER_LONG
        assert signal.metadata['template_type'] == 'earnings_momentum'
        assert signal.metadata['earnings_surprise'] == 0.08

    def test_no_entry_low_surprise(self, engine, mock_provider, base_config):
        """No entry when earnings surprise < threshold."""
        strategy = _make_strategy("Earnings Momentum", "earnings_momentum")
        df = _make_ohlcv_df()

        mock_provider.calculate_earnings_surprise.return_value = 0.02  # Only 2%

        signal = engine._check_earnings_momentum_signal(
            strategy, "AAPL", df, mock_provider,
            base_config['alpha_edge']['earnings_momentum'],
            has_open_position=False, open_position=None
        )
        assert signal is None

    def test_no_entry_outside_window(self, engine, mock_provider, base_config):
        """No entry when too many days since earnings."""
        strategy = _make_strategy("Earnings Momentum", "earnings_momentum")
        df = _make_ohlcv_df()

        mock_provider.calculate_earnings_surprise.return_value = 0.10
        mock_provider.get_fundamental_data.return_value = Mock(revenue_growth=0.20)
        mock_provider.get_days_since_earnings.return_value = 15  # Too late

        signal = engine._check_earnings_momentum_signal(
            strategy, "AAPL", df, mock_provider,
            base_config['alpha_edge']['earnings_momentum'],
            has_open_position=False, open_position=None
        )
        assert signal is None

    def test_exit_profit_target(self, engine, mock_provider, base_config):
        """Exit when profit target is reached."""
        strategy = _make_strategy("Earnings Momentum", "earnings_momentum")
        df = _make_ohlcv_df(start_price=110.0)  # Price went up

        open_pos = Mock()
        open_pos.entry_price = 100.0
        open_pos.opened_at = datetime.now() - timedelta(days=10)
        open_pos.side = Mock(value='LONG')

        signal = engine._check_earnings_momentum_signal(
            strategy, "AAPL", df, mock_provider,
            base_config['alpha_edge']['earnings_momentum'],
            has_open_position=True, open_position=open_pos
        )

        assert signal is not None
        assert signal.action == SignalAction.EXIT_LONG
        assert 'Profit target' in signal.reasoning


# ============================================================
# Sector Rotation tests
# ============================================================

class TestSectorRotationSignal:
    @patch('src.strategy.market_analyzer.MarketStatisticsAnalyzer')
    def test_entry_optimal_sector(self, mock_analyzer_cls, engine, mock_provider, base_config):
        """Entry when symbol is in optimal sector set for current regime."""
        strategy = _make_strategy("Sector Rotation", "sector_rotation", symbols=["XLK"])

        # Mock regime detection
        mock_analyzer = Mock()
        mock_analyzer.detect_sub_regime.return_value = ('ranging_low_vol', 0.8, 0.9, {})
        mock_analyzer_cls.return_value = mock_analyzer

        df = _make_ohlcv_df()  # Positive momentum

        # Mock no recent orders
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        engine.db.get_session.return_value = mock_session

        signal = engine._check_sector_rotation_signal(
            strategy, "XLK", df, mock_provider,
            base_config['alpha_edge']['sector_rotation'],
            base_config, has_open_position=False, open_position=None
        )

        assert signal is not None
        assert signal.action == SignalAction.ENTER_LONG
        assert signal.metadata['template_type'] == 'sector_rotation'

    @patch('src.strategy.market_analyzer.MarketStatisticsAnalyzer')
    def test_no_entry_wrong_sector(self, mock_analyzer_cls, engine, mock_provider, base_config):
        """No entry when symbol is not in optimal sector set."""
        strategy = _make_strategy("Sector Rotation", "sector_rotation", symbols=["XLU"])

        mock_analyzer = Mock()
        # ranging_low_vol maps to XLK, XLF, XLI — not XLU
        mock_analyzer.detect_sub_regime.return_value = ('ranging_low_vol', 0.8, 0.9, {})
        mock_analyzer_cls.return_value = mock_analyzer

        df = _make_ohlcv_df()

        signal = engine._check_sector_rotation_signal(
            strategy, "XLU", df, mock_provider,
            base_config['alpha_edge']['sector_rotation'],
            base_config, has_open_position=False, open_position=None
        )

        assert signal is None


# ============================================================
# Quality Mean Reversion tests
# ============================================================

class TestQualityMeanReversionSignal:
    def test_entry_quality_oversold(self, engine, mock_provider, base_config):
        """Entry when fundamentals are strong AND RSI < 30."""
        strategy = _make_strategy("Quality Mean Reversion", "quality_mean_reversion")
        df = _make_oversold_df()  # Creates RSI < 30

        mock_provider.get_fundamental_data.return_value = Mock(
            roe=0.20, debt_to_equity=0.3, market_cap=50_000_000_000
        )

        signal = engine._check_quality_mean_reversion_signal(
            strategy, "AAPL", df, mock_provider,
            base_config['alpha_edge']['quality_mean_reversion'],
            has_open_position=False, open_position=None
        )

        assert signal is not None
        assert signal.action == SignalAction.ENTER_LONG
        assert signal.metadata['template_type'] == 'quality_mean_reversion'
        assert signal.metadata['roe'] == 0.20

    def test_no_entry_low_roe(self, engine, mock_provider, base_config):
        """No entry when ROE is below threshold."""
        strategy = _make_strategy("Quality Mean Reversion", "quality_mean_reversion")
        df = _make_oversold_df()

        mock_provider.get_fundamental_data.return_value = Mock(
            roe=0.08, debt_to_equity=0.3, market_cap=50_000_000_000
        )

        signal = engine._check_quality_mean_reversion_signal(
            strategy, "AAPL", df, mock_provider,
            base_config['alpha_edge']['quality_mean_reversion'],
            has_open_position=False, open_position=None
        )
        assert signal is None

    def test_no_entry_high_debt(self, engine, mock_provider, base_config):
        """No entry when Debt/Equity is above threshold."""
        strategy = _make_strategy("Quality Mean Reversion", "quality_mean_reversion")
        df = _make_oversold_df()

        mock_provider.get_fundamental_data.return_value = Mock(
            roe=0.20, debt_to_equity=0.8, market_cap=50_000_000_000
        )

        signal = engine._check_quality_mean_reversion_signal(
            strategy, "AAPL", df, mock_provider,
            base_config['alpha_edge']['quality_mean_reversion'],
            has_open_position=False, open_position=None
        )
        assert signal is None

    def test_no_entry_rsi_not_oversold(self, engine, mock_provider, base_config):
        """No entry when RSI is above oversold threshold."""
        strategy = _make_strategy("Quality Mean Reversion", "quality_mean_reversion")
        df = _make_ohlcv_df()  # Normal uptrend, RSI will be > 30

        mock_provider.get_fundamental_data.return_value = Mock(
            roe=0.20, debt_to_equity=0.3, market_cap=50_000_000_000
        )

        signal = engine._check_quality_mean_reversion_signal(
            strategy, "AAPL", df, mock_provider,
            base_config['alpha_edge']['quality_mean_reversion'],
            has_open_position=False, open_position=None
        )
        assert signal is None

    def test_exit_profit_target(self, engine, mock_provider, base_config):
        """Exit when profit target is reached."""
        strategy = _make_strategy("Quality Mean Reversion", "quality_mean_reversion")
        # Create stable data so SMA50 is close to current price
        dates = pd.date_range(end=datetime.now(), periods=120, freq='D')
        prices = np.full(120, 105.0)  # Flat at 105
        df = pd.DataFrame({
            'open': prices * 0.999,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'close': prices,
            'volume': np.full(120, 1000000),
        }, index=dates)

        open_pos = Mock()
        open_pos.entry_price = 100.0  # Entry at 100, current at 105 = 5% profit
        open_pos.opened_at = datetime.now() - timedelta(days=5)
        open_pos.side = Mock(value='LONG')

        signal = engine._check_quality_mean_reversion_signal(
            strategy, "AAPL", df, mock_provider,
            base_config['alpha_edge']['quality_mean_reversion'],
            has_open_position=True, open_position=open_pos
        )

        assert signal is not None
        assert signal.action == SignalAction.EXIT_LONG
        assert 'Profit target' in signal.reasoning

    def test_exit_stop_loss(self, engine, mock_provider, base_config):
        """Exit when stop loss is triggered."""
        strategy = _make_strategy("Quality Mean Reversion", "quality_mean_reversion")
        # Create data where current price is well below entry and below SMA50
        # Use a declining trend so SMA50 is above current price (no mean reversion exit)
        df = _make_ohlcv_df(days=120, start_price=105.0, trend=-0.002)
        current_price = float(df['close'].iloc[-1])

        open_pos = Mock()
        open_pos.entry_price = current_price * 1.05  # Entry was 5% higher than current
        open_pos.opened_at = datetime.now() - timedelta(days=3)
        open_pos.side = Mock(value='LONG')

        signal = engine._check_quality_mean_reversion_signal(
            strategy, "AAPL", df, mock_provider,
            base_config['alpha_edge']['quality_mean_reversion'],
            has_open_position=True, open_position=open_pos
        )

        assert signal is not None
        assert signal.action == SignalAction.EXIT_LONG
        assert 'Stop loss' in signal.reasoning


# ============================================================
# Integration: _generate_alpha_edge_signal routing
# ============================================================

class TestAlphaEdgeSignalRouting:
    def test_routes_to_earnings_momentum(self, engine, mock_provider, base_config):
        """_generate_alpha_edge_signal routes earnings_momentum correctly."""
        strategy = _make_strategy("Earnings Momentum", "earnings_momentum")
        df = _make_ohlcv_df()

        mock_provider.calculate_earnings_surprise.return_value = 0.08
        mock_provider.get_fundamental_data.return_value = Mock(
            revenue_growth=0.15, market_cap=500_000_000
        )
        mock_provider.get_days_since_earnings.return_value = 3
        engine._fundamental_data_provider = mock_provider

        # Mock no open positions
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        engine.db.get_session.return_value = mock_session

        signal = engine._generate_alpha_edge_signal(strategy, "AAPL", df, base_config)

        assert signal is not None
        assert signal.metadata['signal_engine'] == 'alpha_edge_fundamental'
        assert signal.metadata['template_type'] == 'earnings_momentum'

    def test_routes_to_quality_mean_reversion(self, engine, mock_provider, base_config):
        """_generate_alpha_edge_signal routes quality_mean_reversion correctly."""
        strategy = _make_strategy("Quality Mean Reversion", "quality_mean_reversion")
        df = _make_oversold_df()

        mock_provider.get_fundamental_data.return_value = Mock(
            roe=0.20, debt_to_equity=0.3, market_cap=50_000_000_000
        )
        engine._fundamental_data_provider = mock_provider

        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        engine.db.get_session.return_value = mock_session

        signal = engine._generate_alpha_edge_signal(strategy, "AAPL", df, base_config)

        assert signal is not None
        assert signal.metadata['signal_engine'] == 'alpha_edge_fundamental'
        assert signal.metadata['template_type'] == 'quality_mean_reversion'
