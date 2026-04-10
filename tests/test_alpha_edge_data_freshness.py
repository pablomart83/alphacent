"""Tests for Alpha Edge validation data freshness check (task 11.11.8)."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from typing import Optional


@dataclass
class MockFundamentalData:
    symbol: str
    timestamp: datetime
    eps: Optional[float] = None
    revenue_growth: Optional[float] = None
    market_cap: Optional[float] = None
    roe: Optional[float] = None
    debt_to_equity: Optional[float] = None
    source: str = "test"


@dataclass
class MockStrategy:
    name: str = "Test Alpha Edge"
    symbols: list = None
    metadata: dict = None
    rules: dict = None

    def __post_init__(self):
        if self.symbols is None:
            self.symbols = ["AAPL"]
        if self.metadata is None:
            self.metadata = {"template_name": "Earnings Momentum", "strategy_category": "alpha_edge"}
        if self.rules is None:
            self.rules = {}


class TestAlphaEdgeDataFreshness:
    """Test data freshness checks in validate_alpha_edge_strategy."""

    def _make_engine(self, fund_data):
        """Create a mock StrategyEngine with a patched fundamental data provider."""
        engine = MagicMock()
        engine._fundamental_data_provider = MagicMock()
        engine._fundamental_data_provider.get_fundamental_data.return_value = fund_data
        engine._get_alpha_edge_template_type = MagicMock(return_value='earnings_momentum')
        engine.market_data = MagicMock()

        # Import the real method and bind it
        from src.strategy.strategy_engine import StrategyEngine
        engine.validate_alpha_edge_strategy = StrategyEngine.validate_alpha_edge_strategy.__get__(engine)
        return engine

    def test_fresh_data_passes(self):
        """Data less than 7 days old should pass without warnings."""
        fund_data = MockFundamentalData(
            symbol="AAPL",
            timestamp=datetime.now() - timedelta(days=2),
            eps=5.0, revenue_growth=0.15, market_cap=3e12
        )
        engine = self._make_engine(fund_data)
        strategy = MockStrategy()

        result = engine.validate_alpha_edge_strategy(strategy)

        assert result["is_valid"] is True
        assert not any("stale" in e.lower() for e in result["errors"])
        assert not any("days old" in w for w in result["warnings"])

    def test_stale_data_warns(self):
        """Data 7-30 days old should produce a warning."""
        fund_data = MockFundamentalData(
            symbol="AAPL",
            timestamp=datetime.now() - timedelta(days=15),
            eps=5.0, revenue_growth=0.15, market_cap=3e12
        )
        engine = self._make_engine(fund_data)
        strategy = MockStrategy()

        result = engine.validate_alpha_edge_strategy(strategy)

        assert result["is_valid"] is True
        freshness_warnings = [w for w in result["warnings"] if "days old" in w]
        assert len(freshness_warnings) == 1
        assert "15 days old" in freshness_warnings[0]

    def test_very_stale_data_rejected(self):
        """Data older than 30 days should be rejected with an error."""
        fund_data = MockFundamentalData(
            symbol="AAPL",
            timestamp=datetime.now() - timedelta(days=45),
            eps=5.0, revenue_growth=0.15, market_cap=3e12
        )
        engine = self._make_engine(fund_data)
        strategy = MockStrategy()

        result = engine.validate_alpha_edge_strategy(strategy)

        assert result["is_valid"] is False
        freshness_errors = [e for e in result["errors"] if "stale" in e.lower()]
        assert len(freshness_errors) == 1
        assert "45 days old" in freshness_errors[0]

    def test_no_timestamp_warns(self):
        """Data with no timestamp should produce a warning."""
        fund_data = MockFundamentalData(
            symbol="AAPL",
            timestamp=None,
            eps=5.0, revenue_growth=0.15, market_cap=3e12
        )
        engine = self._make_engine(fund_data)
        strategy = MockStrategy()

        result = engine.validate_alpha_edge_strategy(strategy)

        assert result["is_valid"] is True
        freshness_warnings = [w for w in result["warnings"] if "freshness unknown" in w.lower()]
        assert len(freshness_warnings) == 1

    def test_sector_rotation_skips_freshness(self):
        """Sector rotation strategies should not check fundamental data freshness."""
        fund_data = MockFundamentalData(
            symbol="XLK",
            timestamp=datetime.now() - timedelta(days=45),
            eps=5.0, revenue_growth=0.15, market_cap=3e12
        )
        engine = self._make_engine(fund_data)
        engine._get_alpha_edge_template_type.return_value = 'sector_rotation'
        engine.market_data.get_historical_data.return_value = list(range(60))
        strategy = MockStrategy(symbols=["XLK"], metadata={"template_name": "Sector Rotation", "strategy_category": "alpha_edge"})

        result = engine.validate_alpha_edge_strategy(strategy)

        assert result["is_valid"] is True
        assert not any("stale" in e.lower() for e in result["errors"])

    def test_quality_mean_reversion_checks_freshness(self):
        """Quality mean reversion should also check data freshness."""
        fund_data = MockFundamentalData(
            symbol="AAPL",
            timestamp=datetime.now() - timedelta(days=35),
            roe=0.20, debt_to_equity=0.3, market_cap=3e12
        )
        engine = self._make_engine(fund_data)
        engine._get_alpha_edge_template_type.return_value = 'quality_mean_reversion'
        engine.market_data.get_historical_data.return_value = list(range(20))
        strategy = MockStrategy(metadata={"template_name": "Quality Mean Reversion", "strategy_category": "alpha_edge"})

        result = engine.validate_alpha_edge_strategy(strategy)

        assert result["is_valid"] is False
        freshness_errors = [e for e in result["errors"] if "stale" in e.lower()]
        assert len(freshness_errors) == 1
