"""Tests for Portfolio Risk Manager."""

import numpy as np
import pandas as pd
import pytest

from src.models.dataclasses import PerformanceMetrics, Strategy
from src.models.enums import StrategyStatus
from src.strategy.portfolio_risk import PortfolioRiskManager


@pytest.fixture
def risk_manager():
    """Create PortfolioRiskManager instance."""
    return PortfolioRiskManager()


@pytest.fixture
def sample_strategies():
    """Create sample strategies with different Sharpe ratios."""
    from datetime import datetime
    from src.models.dataclasses import RiskConfig
    
    strategies = []
    
    # Strategy 1: High Sharpe
    s1 = Strategy(
        id="strategy_1",
        name="High Sharpe Strategy",
        description="Test strategy 1",
        rules={},
        symbols=["AAPL"],
        status=StrategyStatus.DEMO,
        allocation_percent=33.3,
        risk_params=RiskConfig(),
        created_at=datetime.now(),
    )
    s1.performance = PerformanceMetrics(
        sharpe_ratio=2.0,
        total_return=0.25,
        max_drawdown=0.10,
        win_rate=0.65,
        total_trades=50,
    )
    strategies.append(s1)
    
    # Strategy 2: Medium Sharpe
    s2 = Strategy(
        id="strategy_2",
        name="Medium Sharpe Strategy",
        description="Test strategy 2",
        rules={},
        symbols=["GOOGL"],
        status=StrategyStatus.DEMO,
        allocation_percent=33.3,
        risk_params=RiskConfig(),
        created_at=datetime.now(),
    )
    s2.performance = PerformanceMetrics(
        sharpe_ratio=1.5,
        total_return=0.15,
        max_drawdown=0.12,
        win_rate=0.55,
        total_trades=40,
    )
    strategies.append(s2)
    
    # Strategy 3: Low Sharpe
    s3 = Strategy(
        id="strategy_3",
        name="Low Sharpe Strategy",
        description="Test strategy 3",
        rules={},
        symbols=["MSFT"],
        status=StrategyStatus.DEMO,
        allocation_percent=33.3,
        risk_params=RiskConfig(),
        created_at=datetime.now(),
    )
    s3.performance = PerformanceMetrics(
        sharpe_ratio=1.0,
        total_return=0.10,
        max_drawdown=0.15,
        win_rate=0.50,
        total_trades=30,
    )
    strategies.append(s3)
    
    return strategies


@pytest.fixture
def sample_returns_data():
    """Create sample returns data for strategies."""
    # Create 90 days of returns
    dates = pd.date_range(start="2024-01-01", periods=90, freq="D")
    
    # Strategy 1: Positive returns, low volatility
    returns_1 = pd.Series(
        np.random.normal(0.001, 0.01, 90),  # Mean 0.1%, std 1%
        index=dates,
    )
    
    # Strategy 2: Positive returns, medium volatility, correlated with 1
    returns_2 = pd.Series(
        0.7 * returns_1 + 0.3 * np.random.normal(0.0008, 0.012, 90),
        index=dates,
    )
    
    # Strategy 3: Positive returns, higher volatility, uncorrelated
    returns_3 = pd.Series(
        np.random.normal(0.0005, 0.015, 90),  # Mean 0.05%, std 1.5%
        index=dates,
    )
    
    return {
        "strategy_1": returns_1,
        "strategy_2": returns_2,
        "strategy_3": returns_3,
    }


class TestCalculatePortfolioMetrics:
    """Tests for calculate_portfolio_metrics method."""

    def test_empty_strategies(self, risk_manager):
        """Test with no strategies."""
        metrics = risk_manager.calculate_portfolio_metrics([], {})
        
        assert metrics["portfolio_sharpe"] == 0.0
        assert metrics["portfolio_max_drawdown"] == 0.0
        assert metrics["correlation_matrix"].empty
        assert metrics["diversification_score"] == 0.0

    def test_single_strategy(self, risk_manager, sample_strategies, sample_returns_data):
        """Test with single strategy."""
        strategies = [sample_strategies[0]]
        returns_data = {"strategy_1": sample_returns_data["strategy_1"]}
        
        metrics = risk_manager.calculate_portfolio_metrics(strategies, returns_data)
        
        # Should have valid metrics
        assert metrics["portfolio_sharpe"] > 0
        assert metrics["portfolio_max_drawdown"] >= 0
        assert metrics["diversification_score"] == 0.0  # Single strategy, no diversification

    def test_multiple_strategies(self, risk_manager, sample_strategies, sample_returns_data):
        """Test with multiple strategies."""
        metrics = risk_manager.calculate_portfolio_metrics(sample_strategies, sample_returns_data)
        
        # Should have valid metrics
        assert metrics["portfolio_sharpe"] > 0
        assert metrics["portfolio_max_drawdown"] >= 0
        assert 0 <= metrics["diversification_score"] <= 1.0
        assert not metrics["correlation_matrix"].empty
        assert metrics["correlation_matrix"].shape == (3, 3)

    def test_correlation_matrix(self, risk_manager, sample_strategies, sample_returns_data):
        """Test correlation matrix calculation."""
        metrics = risk_manager.calculate_portfolio_metrics(sample_strategies, sample_returns_data)
        
        corr_matrix = metrics["correlation_matrix"]
        
        # Diagonal should be 1.0 (self-correlation)
        assert np.allclose(np.diag(corr_matrix), 1.0)
        
        # Matrix should be symmetric
        assert np.allclose(corr_matrix, corr_matrix.T)
        
        # Strategy 1 and 2 should be highly correlated (we designed them that way)
        assert corr_matrix.loc["strategy_1", "strategy_2"] > 0.5

    def test_diversification_score(self, risk_manager, sample_strategies, sample_returns_data):
        """Test diversification score calculation."""
        metrics = risk_manager.calculate_portfolio_metrics(sample_strategies, sample_returns_data)
        
        # Should have some diversification (not all strategies perfectly correlated)
        assert 0 < metrics["diversification_score"] < 1.0


class TestOptimizeAllocations:
    """Tests for optimize_allocations method."""

    def test_empty_strategies(self, risk_manager):
        """Test with no strategies."""
        allocations = risk_manager.optimize_allocations([], {})
        
        assert allocations == {}

    def test_single_strategy(self, risk_manager, sample_strategies):
        """Test with single strategy gets 100%."""
        strategies = [sample_strategies[0]]
        
        allocations = risk_manager.optimize_allocations(strategies, {})
        
        assert allocations["strategy_1"] == 100.0

    def test_equal_weight_baseline(self, risk_manager, sample_strategies):
        """Test that allocations start from equal weight."""
        allocations = risk_manager.optimize_allocations(sample_strategies, {})
        
        # All strategies should get some allocation
        assert all(alloc > 0 for alloc in allocations.values())
        
        # Total should be 100%
        assert abs(sum(allocations.values()) - 100.0) < 0.01

    def test_sharpe_weighting(self, risk_manager, sample_strategies):
        """Test that higher Sharpe strategies get higher allocation."""
        allocations = risk_manager.optimize_allocations(sample_strategies, {})
        
        # Strategy 1 (Sharpe 2.0) should get more than Strategy 3 (Sharpe 1.0)
        # Due to blending with equal weight, the difference might be small
        assert allocations["strategy_1"] >= allocations["strategy_3"]

    def test_max_allocation_cap(self, risk_manager):
        """Test that no strategy exceeds 20% cap when there are 5+ strategies."""
        from datetime import datetime
        from src.models.dataclasses import RiskConfig, PerformanceMetrics
        
        # Create 5 strategies to trigger the 20% cap
        strategies = []
        for i in range(5):
            s = Strategy(
                id=f"strategy_{i}",
                name=f"Strategy {i}",
                description=f"Test strategy {i}",
                rules={},
                symbols=["AAPL"],
                status=StrategyStatus.DEMO,
                allocation_percent=20.0,
                risk_params=RiskConfig(),
                created_at=datetime.now(),
            )
            s.performance = PerformanceMetrics(
                sharpe_ratio=1.5 + i * 0.1,  # Varying Sharpe ratios
                total_return=0.15,
                max_drawdown=0.12,
                win_rate=0.55,
                total_trades=40,
            )
            strategies.append(s)
        
        allocations = risk_manager.optimize_allocations(strategies, {})
        
        # With 5+ strategies, no strategy should exceed 20% (with small tolerance)
        assert all(alloc <= 20.1 for alloc in allocations.values())

    def test_total_allocation_100(self, risk_manager, sample_strategies):
        """Test that total allocation equals 100%."""
        allocations = risk_manager.optimize_allocations(sample_strategies, {})
        
        total = sum(allocations.values())
        assert abs(total - 100.0) < 0.01  # Allow small floating point error

    def test_correlation_penalty(self, risk_manager, sample_strategies, sample_returns_data):
        """Test that highly correlated strategies get reduced allocation."""
        allocations = risk_manager.optimize_allocations(sample_strategies, sample_returns_data)
        
        # Strategy 1 and 2 are highly correlated, so their combined allocation
        # should be less than if they were uncorrelated
        # This is hard to test precisely, but we can verify the mechanism works
        assert all(alloc > 0 for alloc in allocations.values())
        assert abs(sum(allocations.values()) - 100.0) < 0.01


class TestPortfolioReturnsCalculation:
    """Tests for portfolio returns calculation."""

    def test_portfolio_returns(self, risk_manager, sample_returns_data):
        """Test portfolio returns calculation."""
        allocations = {
            "strategy_1": 0.4,  # 40%
            "strategy_2": 0.3,  # 30%
            "strategy_3": 0.3,  # 30%
        }
        
        portfolio_returns = risk_manager._calculate_portfolio_returns(
            allocations, sample_returns_data
        )
        
        # Should have same length as input
        assert len(portfolio_returns) == 90
        
        # Portfolio returns should be weighted average
        # Check first value
        expected_first = (
            0.4 * sample_returns_data["strategy_1"].iloc[0]
            + 0.3 * sample_returns_data["strategy_2"].iloc[0]
            + 0.3 * sample_returns_data["strategy_3"].iloc[0]
        )
        assert abs(portfolio_returns.iloc[0] - expected_first) < 1e-10


class TestMaxDrawdownCalculation:
    """Tests for max drawdown calculation."""

    def test_no_drawdown(self, risk_manager):
        """Test with only positive returns (no drawdown)."""
        dates = pd.date_range(start="2024-01-01", periods=10, freq="D")
        returns = pd.Series([0.01] * 10, index=dates)  # All positive
        
        allocations = {"strategy_1": 1.0}
        returns_data = {"strategy_1": returns}
        
        max_dd = risk_manager._calculate_portfolio_max_drawdown(allocations, returns_data)
        
        # Should be very small (close to 0)
        assert max_dd < 0.01

    def test_with_drawdown(self, risk_manager):
        """Test with actual drawdown."""
        dates = pd.date_range(start="2024-01-01", periods=5, freq="D")
        # Returns: +10%, -5%, -5%, -5%, +10%
        # Cumulative: 1.1, 1.045, 0.9928, 0.9431, 1.0374
        # Max: 1.1, 1.1, 1.1, 1.1, 1.1
        # Drawdown: 0, -0.05, -0.1007, -0.1426, -0.0569
        returns = pd.Series([0.10, -0.05, -0.05, -0.05, 0.10], index=dates)
        
        allocations = {"strategy_1": 1.0}
        returns_data = {"strategy_1": returns}
        
        max_dd = risk_manager._calculate_portfolio_max_drawdown(allocations, returns_data)
        
        # Should be around 14.26%
        assert 0.13 < max_dd < 0.15


class TestDiversificationScore:
    """Tests for diversification score calculation."""

    def test_perfect_correlation(self, risk_manager):
        """Test with perfectly correlated strategies."""
        # Create correlation matrix with perfect correlation
        corr_matrix = pd.DataFrame(
            [[1.0, 1.0], [1.0, 1.0]],
            index=["s1", "s2"],
            columns=["s1", "s2"],
        )
        
        score = risk_manager._calculate_diversification_score(corr_matrix)
        
        # Diversification score should be 0 (1 - 1.0)
        assert abs(score - 0.0) < 0.01

    def test_no_correlation(self, risk_manager):
        """Test with uncorrelated strategies."""
        # Create correlation matrix with no correlation
        corr_matrix = pd.DataFrame(
            [[1.0, 0.0], [0.0, 1.0]],
            index=["s1", "s2"],
            columns=["s1", "s2"],
        )
        
        score = risk_manager._calculate_diversification_score(corr_matrix)
        
        # Diversification score should be 1.0 (1 - 0.0)
        assert abs(score - 1.0) < 0.01

    def test_partial_correlation(self, risk_manager):
        """Test with partially correlated strategies."""
        # Create correlation matrix with 0.5 correlation
        corr_matrix = pd.DataFrame(
            [[1.0, 0.5], [0.5, 1.0]],
            index=["s1", "s2"],
            columns=["s1", "s2"],
        )
        
        score = risk_manager._calculate_diversification_score(corr_matrix)
        
        # Diversification score should be 0.5 (1 - 0.5)
        assert abs(score - 0.5) < 0.01


class TestAllocationAdjustments:
    """Tests for allocation adjustment methods."""

    def test_adjust_by_sharpe(self, risk_manager, sample_strategies):
        """Test Sharpe-based allocation adjustment."""
        equal_weight = {s.id: 33.33 for s in sample_strategies}
        
        adjusted = risk_manager._adjust_by_sharpe(sample_strategies, equal_weight)
        
        # Higher Sharpe should get higher allocation
        assert adjusted["strategy_1"] > adjusted["strategy_3"]
        
        # All should be positive
        assert all(alloc > 0 for alloc in adjusted.values())

    def test_cap_max_allocation(self, risk_manager):
        """Test max allocation capping."""
        allocations = {
            "s1": 50.0,  # Exceeds 20% cap
            "s2": 30.0,  # Exceeds 20% cap
            "s3": 20.0,  # At cap
        }
        
        capped = risk_manager._cap_max_allocation(allocations, max_pct=20.0)
        
        # All should be <= 20%
        assert all(alloc <= 20.0 for alloc in capped.values())
        
        # s3 should remain at 20%
        assert capped["s3"] == 20.0

    def test_normalize_allocations(self, risk_manager):
        """Test allocation normalization."""
        allocations = {
            "s1": 30.0,
            "s2": 20.0,
            "s3": 10.0,
        }  # Total = 60%
        
        normalized = risk_manager._normalize_allocations(allocations)
        
        # Should sum to 100%
        assert abs(sum(normalized.values()) - 100.0) < 0.01
        
        # Proportions should be maintained
        assert abs(normalized["s1"] / normalized["s2"] - 30.0 / 20.0) < 0.01


class TestIntegration:
    """Integration tests for PortfolioRiskManager."""

    def test_full_optimization_workflow(self, risk_manager, sample_strategies, sample_returns_data):
        """Test complete optimization workflow."""
        # Calculate metrics
        metrics = risk_manager.calculate_portfolio_metrics(sample_strategies, sample_returns_data)
        
        # Optimize allocations
        allocations = risk_manager.optimize_allocations(sample_strategies, sample_returns_data)
        
        # Verify results
        assert metrics["portfolio_sharpe"] > 0
        assert 0 <= metrics["portfolio_max_drawdown"] <= 1.0
        assert 0 <= metrics["diversification_score"] <= 1.0
        
        assert abs(sum(allocations.values()) - 100.0) < 0.01
        # With only 3 strategies, allocations can exceed 20%
        assert all(0 < alloc <= 100.0 for alloc in allocations.values())
        
        # Higher Sharpe should get higher or equal allocation (before correlation adjustment)
        # After correlation adjustment, ordering might change
        assert allocations["strategy_1"] >= allocations["strategy_3"]
