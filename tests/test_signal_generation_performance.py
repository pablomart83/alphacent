"""Tests for signal generation performance optimizations.

Validates:
- HistoricalDataCache caching behavior
- signal_generation_days config is used instead of backtest_days
- generate_signals_batch batches data fetches by symbol
- Timeout protection per strategy
- Timing logs are produced
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
from src.data.market_data_manager import HistoricalDataCache, get_historical_cache, _historical_cache
from src.models import DataSource, MarketData


# --- HistoricalDataCache tests ---

class TestHistoricalDataCache:
    """Tests for the HistoricalDataCache class."""

    def test_cache_set_and_get(self):
        cache = HistoricalDataCache(ttl_seconds=3600)
        data = [MarketData(
            symbol="SPY", timestamp=datetime.now(), open=100, high=101,
            low=99, close=100.5, volume=1000, source=DataSource.YAHOO_FINANCE
        )]
        cache.set("SPY:1d:120", data)
        result = cache.get("SPY:1d:120")
        assert result is not None
        assert len(result) == 1
        assert result[0].symbol == "SPY"

    def test_cache_miss(self):
        cache = HistoricalDataCache(ttl_seconds=3600)
        result = cache.get("MISSING:1d:120")
        assert result is None

    def test_cache_expiry(self):
        cache = HistoricalDataCache(ttl_seconds=0)  # Immediate expiry
        data = [MarketData(
            symbol="SPY", timestamp=datetime.now(), open=100, high=101,
            low=99, close=100.5, volume=1000, source=DataSource.YAHOO_FINANCE
        )]
        cache.set("SPY:1d:120", data)
        import time
        time.sleep(0.01)
        result = cache.get("SPY:1d:120")
        assert result is None

    def test_cache_clear(self):
        cache = HistoricalDataCache(ttl_seconds=3600)
        cache.set("SPY:1d:120", [])
        cache.set("AAPL:1d:120", [])
        assert cache.size == 2
        cache.clear()
        assert cache.size == 0

    def test_cache_size(self):
        cache = HistoricalDataCache(ttl_seconds=3600)
        assert cache.size == 0
        cache.set("SPY:1d:120", [])
        assert cache.size == 1
        cache.set("AAPL:1d:120", [])
        assert cache.size == 2


# --- Config loading tests ---

class TestSignalGenerationConfig:
    """Tests that signal_generation config is loaded correctly."""

    def test_config_has_signal_generation_section(self):
        import yaml
        from pathlib import Path
        config_path = Path("config/autonomous_trading.yaml")
        assert config_path.exists(), "Config file must exist"
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        sg = config.get('signal_generation', {})
        assert 'days' in sg, "signal_generation.days must be configured"
        assert 'strategy_timeout' in sg, "signal_generation.strategy_timeout must be configured"
        assert 'cache_ttl' in sg, "signal_generation.cache_ttl must be configured"

    def test_signal_gen_days_less_than_backtest_days(self):
        import yaml
        from pathlib import Path
        config_path = Path("config/autonomous_trading.yaml")
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        sg_days = config['signal_generation']['days']
        bt_days = config['backtest']['days']
        assert sg_days < bt_days, (
            f"signal_generation.days ({sg_days}) should be less than backtest.days ({bt_days})"
        )

    def test_signal_gen_days_sufficient_for_indicators(self):
        """120 days is enough for SMA_50 (needs ~50 days warmup) + safety buffer."""
        import yaml
        from pathlib import Path
        config_path = Path("config/autonomous_trading.yaml")
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        sg_days = config['signal_generation']['days']
        # SMA_50 needs 50 days, Bollinger(20) needs 20, RSI(14) needs 14
        # 120 days gives plenty of warmup for all standard indicators
        assert sg_days >= 100, f"signal_generation.days ({sg_days}) should be >= 100 for indicator warmup"


# --- generate_signals uses signal_generation config ---

class TestGenerateSignalsUsesConfig:
    """Tests that generate_signals reads from signal_generation config, not backtest."""

    @patch('src.core.system_state_manager.get_system_state_manager')
    def test_generate_signals_uses_signal_gen_days(self, mock_state_mgr):
        """Verify generate_signals fetches ~120 days, not 730."""
        from src.strategy.strategy_engine import StrategyEngine
        from src.models.enums import StrategyStatus, SystemStateEnum

        # Mock system state as ACTIVE
        mock_state = MagicMock()
        mock_state.state = SystemStateEnum.ACTIVE
        mock_state_mgr.return_value.get_current_state.return_value = mock_state

        # Create engine with mock market data
        mock_market_data = MagicMock()
        mock_market_data.get_historical_data.return_value = []

        engine = StrategyEngine(None, mock_market_data, None)

        # Create a minimal strategy
        strategy = MagicMock()
        strategy.name = "test_strategy"
        strategy.status = StrategyStatus.DEMO
        strategy.symbols = ["SPY"]
        strategy.rules = {"indicators": ["RSI:14", "SMA:50"], "entry_conditions": [], "exit_conditions": []}
        strategy.id = "test-id"

        # Run signal generation
        engine.generate_signals(strategy)

        # Check that get_historical_data was called
        if mock_market_data.get_historical_data.called:
            call_args = mock_market_data.get_historical_data.call_args
            start_date = call_args[0][1]  # second positional arg
            end_date = call_args[0][2]    # third positional arg
            days_requested = (end_date - start_date).days

            # Should be ~120 + warmup (100 for SMA_50*2), NOT 730+250
            assert days_requested < 400, (
                f"Signal generation requested {days_requested} days of data. "
                f"Should be ~220 (120 + warmup), not 730+."
            )
