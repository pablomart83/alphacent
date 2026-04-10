"""Integration tests for PortfolioManager with PortfolioRiskManager.

These tests use real components to verify portfolio risk management functionality.
"""

import logging
from datetime import datetime
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from src.api.etoro_client import EToroAPIClient
from src.core.config import Configuration
from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.models.database import Database
from src.models.dataclasses import PerformanceMetrics, RiskConfig, Strategy
from src.models.enums import StrategyStatus, TradingMode
from src.strategy.indicator_library import IndicatorLibrary
from src.strategy.portfolio_manager import PortfolioManager
from src.strategy.strategy_engine import StrategyEngine

logger = logging.getLogger(__name__)


def get_etoro_client():
    """Get eToro client with real credentials (or mock if unavailable)."""
    try:
        config = Configuration()
        credentials = config.load_credentials(TradingMode.DEMO)
        etoro_client = EToroAPIClient(
            public_key=credentials['public_key'],
            user_key=credentials['user_key'],
            mode=TradingMode.DEMO
        )
        logger.info("✓ Using real eToro client with credentials")
        return etoro_client
    except Exception as e:
        logger.warning(f"Failed to create real eToro client: {e}, using mock")
        return Mock(spec=EToroAPIClient)


@pytest.fixture
def llm_service():
    """Create LLM service."""
    return LLMService()


@pytest.fixture
def etoro_client():
    """Create eToro client."""
    return get_etoro_client()


@pytest.fixture
def market_data_manager(etoro_client):
    """Create market data manager."""
    return MarketDataManager(etoro_client=etoro_client)


@pytest.fixture
def strategy_engine(llm_service, market_data_manager):
    """Create StrategyEngine instance."""
    return StrategyEngine(
        llm_service=llm_service,
        market_data=market_data_manager,
    )


@pytest.fixture
def portfolio_manager(strategy_engine):
    """Create PortfolioManager instance."""
    return PortfolioManager(strategy_engine)


@pytest.fixture
def sample_strategies(strategy_engine):
    """Create and save sample strategies to database."""
    strategies = []
    
    for i in range(3):
        strategy = Strategy(
            id=f"test_risk_strategy_{i}",
            name=f"Test Risk Strategy {i}",
            description=f"Test strategy {i} for portfolio risk management",
            rules={
                "indicators": ["RSI_14", "SMA_20"],
                "entry_conditions": ["RSI_14 < 30"],
                "exit_conditions": ["RSI_14 > 70"],
            },
            symbols=["AAPL"],
            status=StrategyStatus.BACKTESTED,
            allocation_percent=0.0,
            risk_params=RiskConfig(),
            created_at=datetime.now(),
        )
        strategy.performance = PerformanceMetrics(
            sharpe_ratio=1.5 + i * 0.2,
            total_return=0.15 + i * 0.05,
            max_drawdown=0.12,
            win_rate=0.55,
            total_trades=40,
        )
        
        # Save to database
        strategy_engine._save_strategy(strategy)
        strategies.append(strategy)
    
    return strategies


@pytest.fixture
def sample_returns_data(sample_strategies):
    """Create sample returns data."""
    dates = pd.date_range(start="2024-01-01", periods=90, freq="D")
    
    returns_data = {}
    for strategy in sample_strategies:
        returns_data[strategy.id] = pd.Series(
            np.random.normal(0.001, 0.01, 90),
            index=dates,
        )
    
    return returns_data


class TestPortfolioMetrics:
    """Tests for portfolio metrics calculation."""

    def test_calculate_portfolio_metrics(self, portfolio_manager, sample_strategies, sample_returns_data):
        """Test portfolio metrics calculation with real components."""
        metrics = portfolio_manager.calculate_portfolio_metrics(
            sample_strategies, sample_returns_data
        )
        
        # Verify all metrics are present
        assert "portfolio_sharpe" in metrics
        assert "portfolio_max_drawdown" in metrics
        assert "correlation_matrix" in metrics
        assert "diversification_score" in metrics
        
        # Verify metrics are valid (Sharpe can be 0 or positive with random data)
        assert metrics["portfolio_sharpe"] >= 0
        assert 0 <= metrics["portfolio_max_drawdown"] <= 1.0
        assert 0 <= metrics["diversification_score"] <= 1.0
        assert not metrics["correlation_matrix"].empty
        
        logger.info(f"Portfolio Sharpe: {metrics['portfolio_sharpe']:.2f}")
        logger.info(f"Portfolio Max Drawdown: {metrics['portfolio_max_drawdown']:.2%}")
        logger.info(f"Diversification Score: {metrics['diversification_score']:.2f}")

    def test_calculate_portfolio_metrics_without_returns(self, portfolio_manager, sample_strategies):
        """Test portfolio metrics calculation without returns data."""
        metrics = portfolio_manager.calculate_portfolio_metrics(sample_strategies, None)
        
        # Should still return metrics (using strategy performance)
        assert "portfolio_sharpe" in metrics
        assert metrics["portfolio_sharpe"] >= 0


class TestAllocationOptimization:
    """Tests for allocation optimization."""

    def test_optimize_allocations(self, portfolio_manager, sample_strategies, sample_returns_data):
        """Test allocation optimization with real components."""
        allocations = portfolio_manager.optimize_allocations(
            sample_strategies, sample_returns_data
        )
        
        # Verify allocations sum to 100%
        assert abs(sum(allocations.values()) - 100.0) < 0.01
        
        # Verify all strategies have positive allocation
        assert all(alloc > 0 for alloc in allocations.values())
        
        # Verify higher Sharpe gets higher or equal allocation
        assert allocations[sample_strategies[2].id] >= allocations[sample_strategies[0].id]
        
        logger.info("Optimized allocations:")
        for strategy in sample_strategies:
            logger.info(f"  {strategy.name}: {allocations[strategy.id]:.1f}%")

    def test_optimize_allocations_without_returns(self, portfolio_manager, sample_strategies):
        """Test allocation optimization without returns data."""
        allocations = portfolio_manager.optimize_allocations(sample_strategies, None)
        
        # Should still return valid allocations
        assert abs(sum(allocations.values()) - 100.0) < 0.01
        assert all(alloc > 0 for alloc in allocations.values())


class TestPortfolioRebalancing:
    """Tests for portfolio rebalancing."""

    def test_rebalance_portfolio(self, portfolio_manager, strategy_engine, sample_strategies, sample_returns_data):
        """Test portfolio rebalancing with real strategies."""
        # First activate the strategies
        for strategy in sample_strategies:
            strategy_engine.activate_strategy(
                strategy.id, 
                mode=TradingMode.DEMO, 
                allocation_percent=33.3
            )
        
        # Get active strategies
        active_strategies = strategy_engine.get_active_strategies()
        assert len(active_strategies) == 3
        
        # Store original allocations
        original_allocations = {s.id: s.allocation_percent for s in active_strategies}
        logger.info("Original allocations:")
        for s in active_strategies:
            logger.info(f"  {s.name}: {s.allocation_percent:.1f}%")
        
        # Rebalance portfolio
        portfolio_manager.rebalance_portfolio(active_strategies, sample_returns_data)
        
        # Get updated strategies
        updated_strategies = strategy_engine.get_active_strategies()
        
        # Verify allocations were updated
        new_allocations = {s.id: s.allocation_percent for s in updated_strategies}
        
        logger.info("New allocations:")
        for s in updated_strategies:
            logger.info(f"  {s.name}: {s.allocation_percent:.1f}%")
        
        # At least one allocation should have changed
        assert any(
            abs(new_allocations[sid] - original_allocations[sid]) > 0.01
            for sid in new_allocations
        )
        
        # Total allocation should still be 100%
        assert abs(sum(new_allocations.values()) - 100.0) < 0.01

    def test_rebalance_empty_portfolio(self, portfolio_manager):
        """Test rebalancing with no strategies."""
        # Should not raise error
        portfolio_manager.rebalance_portfolio([], {})


class TestIntegration:
    """Integration tests."""

    def test_full_risk_management_workflow(
        self, portfolio_manager, strategy_engine, sample_strategies, sample_returns_data
    ):
        """Test complete risk management workflow with real components."""
        logger.info("\n" + "=" * 80)
        logger.info("INTEGRATION TEST: Full Risk Management Workflow")
        logger.info("=" * 80)
        
        # 1. Activate strategies
        logger.info("\n1. Activating strategies...")
        for strategy in sample_strategies:
            strategy_engine.activate_strategy(
                strategy.id,
                mode=TradingMode.DEMO,
                allocation_percent=33.3
            )
        
        # Get active strategies
        active_strategies = strategy_engine.get_active_strategies()
        assert len(active_strategies) == 3
        logger.info(f"   ✓ {len(active_strategies)} strategies activated")
        
        # 2. Calculate portfolio metrics
        logger.info("\n2. Calculating portfolio metrics...")
        metrics = portfolio_manager.calculate_portfolio_metrics(
            active_strategies, sample_returns_data
        )
        
        assert metrics["portfolio_sharpe"] > 0
        assert 0 <= metrics["diversification_score"] <= 1.0
        assert 0 <= metrics["portfolio_max_drawdown"] <= 1.0
        
        logger.info(f"   Portfolio Sharpe: {metrics['portfolio_sharpe']:.2f}")
        logger.info(f"   Portfolio Max Drawdown: {metrics['portfolio_max_drawdown']:.2%}")
        logger.info(f"   Diversification Score: {metrics['diversification_score']:.2f}")
        
        # 3. Optimize allocations
        logger.info("\n3. Optimizing allocations...")
        allocations = portfolio_manager.optimize_allocations(
            active_strategies, sample_returns_data
        )
        
        assert abs(sum(allocations.values()) - 100.0) < 0.01
        assert all(alloc > 0 for alloc in allocations.values())
        
        logger.info("   Optimized allocations:")
        for strategy_id, alloc in allocations.items():
            logger.info(f"     {strategy_id}: {alloc:.1f}%")
        
        # 4. Rebalance portfolio
        logger.info("\n4. Rebalancing portfolio...")
        portfolio_manager.rebalance_portfolio(active_strategies, sample_returns_data)
        
        # 5. Verify allocations were updated in database
        logger.info("\n5. Verifying database updates...")
        updated_strategies = strategy_engine.get_active_strategies()
        new_allocations = {s.id: s.allocation_percent for s in updated_strategies}
        
        # Verify allocations match optimized allocations
        for strategy_id, expected_alloc in allocations.items():
            actual_alloc = new_allocations[strategy_id]
            assert abs(actual_alloc - expected_alloc) < 0.01
            logger.info(f"   ✓ {strategy_id}: {actual_alloc:.1f}% (expected {expected_alloc:.1f}%)")
        
        # Total should be 100%
        assert abs(sum(new_allocations.values()) - 100.0) < 0.01
        logger.info(f"\n   ✓ Total allocation: {sum(new_allocations.values()):.1f}%")
        
        logger.info("\n" + "=" * 80)
        logger.info("✓ INTEGRATION TEST PASSED")
        logger.info("=" * 80 + "\n")
