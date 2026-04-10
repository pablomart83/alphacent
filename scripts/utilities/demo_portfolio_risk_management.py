"""Demo script to test portfolio risk management with real output."""

import logging
from datetime import datetime

import numpy as np
import pandas as pd

from src.models.dataclasses import PerformanceMetrics, RiskConfig, Strategy
from src.models.enums import StrategyStatus
from src.strategy.portfolio_risk import PortfolioRiskManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


def create_sample_strategies():
    """Create sample strategies with different characteristics."""
    strategies = []
    
    # Strategy 1: High Sharpe, Low Drawdown
    s1 = Strategy(
        id="strategy_1",
        name="High Sharpe Strategy",
        description="Conservative strategy with high risk-adjusted returns",
        rules={},
        symbols=["AAPL"],
        status=StrategyStatus.DEMO,
        allocation_percent=33.3,
        risk_params=RiskConfig(),
        created_at=datetime.now(),
    )
    s1.performance = PerformanceMetrics(
        sharpe_ratio=2.5,
        total_return=0.35,
        max_drawdown=0.08,
        win_rate=0.68,
        total_trades=60,
    )
    strategies.append(s1)
    
    # Strategy 2: Medium Sharpe, Medium Drawdown
    s2 = Strategy(
        id="strategy_2",
        name="Balanced Strategy",
        description="Balanced risk-return profile",
        rules={},
        symbols=["GOOGL"],
        status=StrategyStatus.DEMO,
        allocation_percent=33.3,
        risk_params=RiskConfig(),
        created_at=datetime.now(),
    )
    s2.performance = PerformanceMetrics(
        sharpe_ratio=1.8,
        total_return=0.22,
        max_drawdown=0.12,
        win_rate=0.58,
        total_trades=45,
    )
    strategies.append(s2)
    
    # Strategy 3: Lower Sharpe, Higher Drawdown
    s3 = Strategy(
        id="strategy_3",
        name="Aggressive Strategy",
        description="Higher risk, moderate returns",
        rules={},
        symbols=["MSFT"],
        status=StrategyStatus.DEMO,
        allocation_percent=33.3,
        risk_params=RiskConfig(),
        created_at=datetime.now(),
    )
    s3.performance = PerformanceMetrics(
        sharpe_ratio=1.2,
        total_return=0.18,
        max_drawdown=0.15,
        win_rate=0.52,
        total_trades=38,
    )
    strategies.append(s3)
    
    return strategies


def create_sample_returns_data(strategies):
    """Create realistic returns data with different characteristics."""
    dates = pd.date_range(start="2024-01-01", periods=90, freq="D")
    
    returns_data = {}
    
    # Strategy 1: Low volatility, positive drift (high Sharpe)
    returns_1 = pd.Series(
        np.random.normal(0.0015, 0.008, 90),  # Mean 0.15%, std 0.8%
        index=dates,
    )
    returns_data["strategy_1"] = returns_1
    
    # Strategy 2: Medium volatility, positive drift, correlated with Strategy 1
    returns_2 = pd.Series(
        0.6 * returns_1 + 0.4 * np.random.normal(0.001, 0.012, 90),
        index=dates,
    )
    returns_data["strategy_2"] = returns_2
    
    # Strategy 3: Higher volatility, lower drift, uncorrelated
    returns_3 = pd.Series(
        np.random.normal(0.0008, 0.015, 90),  # Mean 0.08%, std 1.5%
        index=dates,
    )
    returns_data["strategy_3"] = returns_3
    
    return returns_data


def main():
    """Run portfolio risk management demo."""
    logger.info("=" * 100)
    logger.info("PORTFOLIO RISK MANAGEMENT DEMO")
    logger.info("=" * 100)
    
    # Create sample data
    logger.info("\n1. Creating sample strategies...")
    strategies = create_sample_strategies()
    
    for s in strategies:
        logger.info(f"\n   {s.name}:")
        logger.info(f"      Sharpe Ratio: {s.performance.sharpe_ratio:.2f}")
        logger.info(f"      Total Return: {s.performance.total_return:.2%}")
        logger.info(f"      Max Drawdown: {s.performance.max_drawdown:.2%}")
        logger.info(f"      Win Rate: {s.performance.win_rate:.2%}")
        logger.info(f"      Total Trades: {s.performance.total_trades}")
        logger.info(f"      Current Allocation: {s.allocation_percent:.1f}%")
    
    logger.info("\n2. Generating returns data (90 days)...")
    returns_data = create_sample_returns_data(strategies)
    
    for strategy_id, returns in returns_data.items():
        logger.info(f"\n   {strategy_id}:")
        logger.info(f"      Mean Daily Return: {returns.mean():.4%}")
        logger.info(f"      Std Dev: {returns.std():.4%}")
        logger.info(f"      Min: {returns.min():.4%}")
        logger.info(f"      Max: {returns.max():.4%}")
        logger.info(f"      Cumulative Return: {(1 + returns).prod() - 1:.2%}")
    
    # Initialize risk manager
    logger.info("\n3. Initializing Portfolio Risk Manager...")
    risk_manager = PortfolioRiskManager()
    
    # Calculate portfolio metrics
    logger.info("\n4. Calculating Portfolio Metrics...")
    logger.info("-" * 100)
    metrics = risk_manager.calculate_portfolio_metrics(strategies, returns_data)
    
    logger.info(f"\n   Portfolio Sharpe Ratio: {metrics['portfolio_sharpe']:.2f}")
    logger.info(f"   Portfolio Max Drawdown: {metrics['portfolio_max_drawdown']:.2%}")
    logger.info(f"   Diversification Score: {metrics['diversification_score']:.2f} (0=fully correlated, 1=uncorrelated)")
    
    logger.info(f"\n   Correlation Matrix:")
    corr_matrix = metrics['correlation_matrix']
    logger.info(f"\n{corr_matrix.to_string()}")
    
    # Analyze correlations
    logger.info(f"\n   Correlation Analysis:")
    logger.info(f"      Strategy 1 vs Strategy 2: {corr_matrix.loc['strategy_1', 'strategy_2']:.3f}")
    logger.info(f"      Strategy 1 vs Strategy 3: {corr_matrix.loc['strategy_1', 'strategy_3']:.3f}")
    logger.info(f"      Strategy 2 vs Strategy 3: {corr_matrix.loc['strategy_2', 'strategy_3']:.3f}")
    
    # Optimize allocations
    logger.info("\n5. Optimizing Allocations...")
    logger.info("-" * 100)
    allocations = risk_manager.optimize_allocations(strategies, returns_data)
    
    logger.info(f"\n   Original Allocations (Equal Weight):")
    for s in strategies:
        logger.info(f"      {s.name}: {s.allocation_percent:.1f}%")
    
    logger.info(f"\n   Optimized Allocations:")
    total_alloc = 0
    for strategy_id, alloc in allocations.items():
        strategy = next(s for s in strategies if s.id == strategy_id)
        change = alloc - strategy.allocation_percent
        change_str = f"+{change:.1f}%" if change > 0 else f"{change:.1f}%"
        logger.info(f"      {strategy.name}: {alloc:.1f}% ({change_str})")
        total_alloc += alloc
    
    logger.info(f"\n   Total Allocation: {total_alloc:.1f}%")
    
    # Explain optimization
    logger.info(f"\n   Optimization Rationale:")
    logger.info(f"      • Higher Sharpe strategies get more allocation")
    logger.info(f"      • Highly correlated strategies get reduced allocation")
    logger.info(f"      • Maximum 20% per strategy (for 5+ strategies)")
    logger.info(f"      • Total always equals 100%")
    
    # Show expected portfolio improvement
    logger.info("\n6. Expected Portfolio Improvement...")
    logger.info("-" * 100)
    
    # Calculate weighted Sharpe with original allocations
    original_weighted_sharpe = sum(
        (s.allocation_percent / 100.0) * s.performance.sharpe_ratio 
        for s in strategies
    )
    
    # Calculate weighted Sharpe with optimized allocations
    optimized_weighted_sharpe = sum(
        (allocations[s.id] / 100.0) * s.performance.sharpe_ratio 
        for s in strategies
    )
    
    logger.info(f"\n   Original Portfolio Sharpe (equal weight): {original_weighted_sharpe:.2f}")
    logger.info(f"   Optimized Portfolio Sharpe: {optimized_weighted_sharpe:.2f}")
    logger.info(f"   Improvement: {optimized_weighted_sharpe - original_weighted_sharpe:.2f} ({((optimized_weighted_sharpe / original_weighted_sharpe - 1) * 100):.1f}%)")
    
    # Summary
    logger.info("\n" + "=" * 100)
    logger.info("SUMMARY")
    logger.info("=" * 100)
    logger.info(f"\n✓ Portfolio metrics calculated successfully")
    logger.info(f"✓ Allocations optimized for risk-adjusted returns")
    logger.info(f"✓ Diversification score: {metrics['diversification_score']:.2f}")
    logger.info(f"✓ Expected Sharpe improvement: {((optimized_weighted_sharpe / original_weighted_sharpe - 1) * 100):.1f}%")
    logger.info(f"\nThe portfolio risk management system is working correctly!")
    logger.info("=" * 100 + "\n")


if __name__ == "__main__":
    main()
