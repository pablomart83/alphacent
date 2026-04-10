"""Tests for Market Hours Awareness in Strategy Proposals (Task 11.7.4).

Validates that strategies get asset-class-specific risk parameters and metadata
based on the symbol's asset class (stock, etf, forex, crypto, index, commodity).
"""

import logging
from unittest.mock import Mock, patch
from datetime import datetime

import pytest

from src.strategy.strategy_proposer import StrategyProposer
from src.strategy.strategy_templates import StrategyTemplate, StrategyType, MarketRegime
from src.models.dataclasses import RiskConfig

logger = logging.getLogger(__name__)


@pytest.fixture
def proposer():
    """Create a StrategyProposer with mocked dependencies."""
    mock_llm = Mock()
    mock_market_data = Mock()
    return StrategyProposer(mock_llm, mock_market_data)


@pytest.fixture
def sample_template():
    """Create a simple strategy template for testing."""
    return StrategyTemplate(
        name="Test RSI Mean Reversion",
        description="Test template",
        strategy_type=StrategyType.MEAN_REVERSION,
        market_regimes=[MarketRegime.RANGING],
        entry_conditions=["RSI(14) < 30"],
        exit_conditions=["RSI(14) > 70"],
        required_indicators=["RSI_14"],
        default_parameters={
            "rsi_period": 14,
            "oversold_threshold": 30,
            "overbought_threshold": 70,
            "stop_loss_pct": 0.03,
            "take_profit_pct": 0.06,
        },
        expected_trade_frequency="2-4 trades/month",
        expected_holding_period="3-7 days",
        risk_reward_ratio=2.5,
        metadata={},
    )


class TestGetAssetClass:
    """Test _get_asset_class correctly classifies symbols."""

    def test_stock_classification(self, proposer):
        assert proposer._get_asset_class("AAPL") == "stock"
        assert proposer._get_asset_class("MSFT") == "stock"
        assert proposer._get_asset_class("NVDA") == "stock"

    def test_etf_classification(self, proposer):
        assert proposer._get_asset_class("SPY") == "etf"
        assert proposer._get_asset_class("QQQ") == "etf"
        assert proposer._get_asset_class("XLE") == "etf"

    def test_forex_classification(self, proposer):
        assert proposer._get_asset_class("EURUSD") == "forex"
        assert proposer._get_asset_class("GBPUSD") == "forex"
        assert proposer._get_asset_class("USDJPY") == "forex"

    def test_crypto_classification(self, proposer):
        assert proposer._get_asset_class("BTC") == "crypto"
        assert proposer._get_asset_class("ETH") == "crypto"
        assert proposer._get_asset_class("SOL") == "crypto"

    def test_index_classification(self, proposer):
        assert proposer._get_asset_class("SPX500") == "index"
        assert proposer._get_asset_class("NSDQ100") == "index"

    def test_commodity_classification(self, proposer):
        assert proposer._get_asset_class("GOLD") == "commodity"
        assert proposer._get_asset_class("OIL") == "commodity"

    def test_unknown_defaults_to_stock(self, proposer):
        assert proposer._get_asset_class("UNKNOWN_SYM") == "stock"

    def test_case_insensitive(self, proposer):
        assert proposer._get_asset_class("eurusd") == "forex"
        assert proposer._get_asset_class("btc") == "crypto"


class TestApplyAssetClassOverrides:
    """Test _apply_asset_class_overrides adjusts risk params per asset class."""

    def test_forex_gets_tighter_stops(self, proposer):
        """Forex should blend toward tighter stop losses (0.8% config)."""
        base_config = RiskConfig(stop_loss_pct=0.04, take_profit_pct=0.10)
        result = proposer._apply_asset_class_overrides(base_config, "EURUSD")
        # Blended: (0.04 + 0.008) / 2 = 0.024
        assert result.stop_loss_pct < 0.04, "Forex SL should be tighter than stock default"
        assert result.stop_loss_pct == pytest.approx(0.024, abs=0.001)

    def test_crypto_maintains_wider_stops(self, proposer):
        """Crypto config has 4% SL, same as stock baseline — should stay similar."""
        base_config = RiskConfig(stop_loss_pct=0.04, take_profit_pct=0.10)
        result = proposer._apply_asset_class_overrides(base_config, "BTC")
        # Blended: (0.04 + 0.04) / 2 = 0.04
        assert result.stop_loss_pct == pytest.approx(0.04, abs=0.001)

    def test_commodity_gets_medium_stops(self, proposer):
        """Commodity should blend toward 3% SL."""
        base_config = RiskConfig(stop_loss_pct=0.04, take_profit_pct=0.10)
        result = proposer._apply_asset_class_overrides(base_config, "GOLD")
        # Blended: (0.04 + 0.03) / 2 = 0.035
        assert result.stop_loss_pct == pytest.approx(0.035, abs=0.001)

    def test_stock_stays_near_baseline(self, proposer):
        """Stock should blend toward 4% SL (same as typical baseline)."""
        base_config = RiskConfig(stop_loss_pct=0.04, take_profit_pct=0.10)
        result = proposer._apply_asset_class_overrides(base_config, "AAPL")
        assert result.stop_loss_pct == pytest.approx(0.04, abs=0.001)

    def test_tp_always_exceeds_sl(self, proposer):
        """Take profit must always be at least 1.5x stop loss."""
        # Forex: very tight SL, TP should still be >= 1.5x SL
        base_config = RiskConfig(stop_loss_pct=0.01, take_profit_pct=0.01)
        result = proposer._apply_asset_class_overrides(base_config, "EURUSD")
        assert result.take_profit_pct >= result.stop_loss_pct * 1.5


class TestStrategyCreationWithAssetClass:
    """Test that strategy creation methods add asset_class to metadata."""

    def test_generate_strategy_with_params_adds_asset_class(self, proposer, sample_template):
        """_generate_strategy_with_params should set asset_class in metadata."""
        strategy = proposer._generate_strategy_with_params(
            template=sample_template,
            symbols=["EURUSD"],
            params={"oversold_threshold": 30, "overbought_threshold": 70},
            variation_number=0,
        )
        assert strategy.metadata.get("asset_class") == "forex"

    def test_create_strategy_from_params_adds_asset_class(self, proposer, sample_template):
        """_create_strategy_from_params should set asset_class in metadata."""
        strategy = proposer._create_strategy_from_params(
            template=sample_template,
            symbols=["BTC"],
            params={},
        )
        assert strategy.metadata.get("asset_class") == "crypto"

    def test_stock_strategy_metadata(self, proposer, sample_template):
        strategy = proposer._generate_strategy_with_params(
            template=sample_template,
            symbols=["AAPL"],
            params={},
            variation_number=0,
        )
        assert strategy.metadata["asset_class"] == "stock"

    def test_etf_strategy_metadata(self, proposer, sample_template):
        strategy = proposer._generate_strategy_with_params(
            template=sample_template,
            symbols=["SPY"],
            params={},
            variation_number=0,
        )
        assert strategy.metadata["asset_class"] == "etf"

    def test_forex_strategy_risk_params_differ_from_stock(self, proposer, sample_template):
        """Forex and stock strategies for the same template should have different risk params."""
        forex_strategy = proposer._generate_strategy_with_params(
            template=sample_template,
            symbols=["EURUSD"],
            params={},
            variation_number=0,
        )
        stock_strategy = proposer._generate_strategy_with_params(
            template=sample_template,
            symbols=["AAPL"],
            params={},
            variation_number=0,
        )
        # Forex should have tighter SL than stock
        assert forex_strategy.risk_params.stop_loss_pct < stock_strategy.risk_params.stop_loss_pct


class TestAssetClassConfig:
    """Test that the YAML config has the expected asset_class_parameters."""

    def test_config_has_all_asset_classes(self):
        """Config should define parameters for all 6 asset classes."""
        import yaml
        from pathlib import Path

        config_path = Path("config/autonomous_trading.yaml")
        assert config_path.exists(), "Config file must exist"

        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        ac_params = config.get("asset_class_parameters", {})
        expected_classes = {"stock", "etf", "forex", "crypto", "index", "commodity"}
        assert set(ac_params.keys()) == expected_classes

    def test_forex_config_values(self):
        """Forex should have tight stops and 24/5 signal hours."""
        import yaml
        from pathlib import Path

        with open(Path("config/autonomous_trading.yaml"), 'r') as f:
            config = yaml.safe_load(f)

        forex = config["asset_class_parameters"]["forex"]
        assert forex["stop_loss_pct"] == 0.008
        assert forex["signal_hours"] == "24/5"
        assert forex["holding_period_days_min"] == 14

    def test_crypto_config_values(self):
        """Crypto should have 24/7 signal hours and high volatility tolerance."""
        import yaml
        from pathlib import Path

        with open(Path("config/autonomous_trading.yaml"), 'r') as f:
            config = yaml.safe_load(f)

        crypto = config["asset_class_parameters"]["crypto"]
        assert crypto["signal_hours"] == "24/7"
        assert crypto["volatility_tolerance"] == "high"

    def test_stock_config_values(self):
        """Stock should have market_hours signal hours."""
        import yaml
        from pathlib import Path

        with open(Path("config/autonomous_trading.yaml"), 'r') as f:
            config = yaml.safe_load(f)

        stock = config["asset_class_parameters"]["stock"]
        assert stock["signal_hours"] == "market_hours"
        assert stock["volatility_tolerance"] == "standard"
