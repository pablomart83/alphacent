"""Test portfolio risk management with real market data and services.

This test verifies that the portfolio risk management system works correctly
with real eToro API, real market data, and real strategy backtesting.
"""

import logging
from datetime import datetime, timedelta

import pandas as pd

from src.api.etoro_client import EToroAPIClient
from src.core.config import Configuration
from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.models.dataclasses import PerformanceMetrics, RiskConfig, Strategy
from src.models.enums import StrategyStatus, TradingMode
from src.strategy.portfolio_manager import PortfolioManager
from src.strategy.strategy_engine import StrategyEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_portfolio_risk_with_real_data():
    """Test portfolio risk management with real market data."""
    logger.info("=" * 100)
    logger.info("PORTFOLIO RISK MANAGEMENT WITH REAL DATA TEST")
    logger.info("=" * 100)
    
    # 1. Initialize real components
    logger.info("\n1. Initializing real components...")
    
    config = Configuration()
    try:
        credentials = config.load_credentials(TradingMode.DEMO)
        logger.info("   ✓ Credentials loaded")
    except Exception as e:
        logger.error(f"   ✗ Failed to load credentials: {e}")
        logger.error("   Please run: python scripts/test_api_keys.py")
        return False
    
    try:
        etoro_client = EToroAPIClient(
            public_key=credentials['public_key'],
            user_key=credentials['user_key'],
            mode=TradingMode.DEMO
        )
        logger.info("   ✓ Real eToro client initialized")
    except Exception as e:
        logger.error(f"   ✗ Failed to initialize eToro client: {e}")
        return False
    
    market_data = MarketDataManager(etoro_client=etoro_client)
    logger.info("   ✓ Market data manager initialized")
    
    llm_service = LLMService()
    logger.info("   ✓ LLM service initialized")
    
    strategy_engine = StrategyEngine(llm_service=llm_service, market_data=market_data)
    logger.info("   ✓ Strategy engine initialized")
    
    portfolio_manager = PortfolioManager(
        strategy_engine,
        max_correlation=0.7,
        min_trades=5  # Lower for testing
    )
    logger.info("   ✓ Portfolio manager initialized")
    
    # 2. Create test strategies
    logger.info("\n2. Creating test strategies...")
    
    strategies = []
    strategy_configs = [
        {
            "name": "RSI Mean Reversion",
            "indicators": ["RSI"],
            "entry": ["RSI_14 < 30"],
            "exit": ["RSI_14 > 70"]
        },
        {
            "name": "SMA Crossover",
            "indicators": ["SMA"],
            "entry": ["SMA_20 > close"],
            "exit": ["SMA_20 < close"]
        },
        {
            "name": "Bollinger Bands",
            "indicators": ["Bollinger Bands"],
            "entry": ["close < Lower_Band_20"],
            "exit": ["close > Upper_Band_20"]
        }
    ]
    
    for i, config in enumerate(strategy_configs):
        strategy = Strategy(
            id=f"test_real_data_{i}",
            name=config["name"],
            description=f"Test strategy: {config['name']}",
            rules={
                "indicators": config["indicators"],
                "entry_conditions": config["entry"],
                "exit_conditions": config["exit"]
            },
            symbols=["AAPL"],
            status=StrategyStatus.PROPOSED,
            risk_params=RiskConfig(),
            created_at=datetime.now(),
            performance=PerformanceMetrics()
        )
        strategies.append(strategy)
        logger.info(f"   Created: {strategy.name}")
    
    # 3. Backtest with real market data
    logger.info("\n3. Backtesting with real market data...")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    backtested_strategies = []
    for strategy in strategies:
        logger.info(f"\n   Testing: {strategy.name}")
        
        try:
            # Backtest with real market data
            results = strategy_engine.backtest_strategy(
                strategy=strategy,
                start=start_date,
                end=end_date,
                commission=1.0,
                slippage_bps=5
            )
            
            logger.info(f"      Trades: {results.total_trades}")
            logger.info(f"      Return: {results.total_return:.2%}")
            logger.info(f"      Sharpe: {results.sharpe_ratio:.2f}")
            logger.info(f"      Max DD: {results.max_drawdown:.2%}")
            logger.info(f"      Win Rate: {results.win_rate:.2%}")
            
            if results.total_trades >= 5:
                strategy.backtest_results = results
                strategy.performance.sharpe_ratio = results.sharpe_ratio
                strategy.performance.total_return = results.total_return
                strategy.performance.max_drawdown = results.max_drawdown
                strategy.performance.win_rate = results.win_rate
                strategy.performance.total_trades = results.total_trades
                strategy.status = StrategyStatus.BACKTESTED
                
                backtested_strategies.append(strategy)
                logger.info(f"      ✓ Strategy validated")
            else:
                logger.warning(f"      ⚠️  Insufficient trades ({results.total_trades} < 5)")
                
        except Exception as e:
            logger.error(f"      ✗ Backtest failed: {e}")
            continue
    
    if len(backtested_strategies) < 2:
        logger.error("\n✗ Need at least 2 validated strategies")
        return False
    
    logger.info(f"\n   ✓ {len(backtested_strategies)} strategies backtested successfully")
    
    # 4. Extract returns data from real backtests
    logger.info("\n4. Extracting returns data from real backtests...")
    
    returns_data = {}
    for strategy in backtested_strategies:
        if hasattr(strategy.backtest_results, 'equity_curve') and strategy.backtest_results.equity_curve is not None:
            equity = strategy.backtest_results.equity_curve
            returns = equity.pct_change().fillna(0)
            returns_data[strategy.id] = returns
            
            logger.info(f"   {strategy.name}:")
            logger.info(f"      Days: {len(returns)}")
            logger.info(f"      Mean: {returns.mean():.4%}")
            logger.info(f"      Std: {returns.std():.4%}")
        else:
            logger.warning(f"   ⚠️  No equity curve for {strategy.name}")
    
    # 5. Calculate portfolio metrics
    logger.info("\n5. Calculating portfolio metrics...")
    
    metrics = portfolio_manager.calculate_portfolio_metrics(
        backtested_strategies,
        returns_data
    )
    
    logger.info(f"\n   Portfolio Sharpe: {metrics['portfolio_sharpe']:.2f}")
    logger.info(f"   Portfolio Max DD: {metrics['portfolio_max_drawdown']:.2%}")
    logger.info(f"   Diversification: {metrics['diversification_score']:.2f}")
    
    # 6. Check correlation matrix
    if not metrics['correlation_matrix'].empty:
        logger.info("\n   Correlation Matrix:")
        corr_matrix = metrics['correlation_matrix']
        logger.info(f"\n{corr_matrix.to_string()}")
        
        # Check for high correlations
        high_corr_count = 0
        for i in range(len(corr_matrix)):
            for j in range(i+1, len(corr_matrix)):
                corr = corr_matrix.iloc[i, j]
                if abs(corr) > 0.7:
                    high_corr_count += 1
                    logger.warning(f"      ⚠️  High correlation: {corr:.3f}")
        
        if high_corr_count == 0:
            logger.info("      ✓ No high correlations detected")
    
    # 7. Optimize allocations
    logger.info("\n6. Optimizing allocations...")
    
    allocations = portfolio_manager.optimize_allocations(
        backtested_strategies,
        returns_data
    )
    
    logger.info("\n   Optimized Allocations:")
    total_alloc = 0
    for strategy_id, alloc in allocations.items():
        strategy = next(s for s in backtested_strategies if s.id == strategy_id)
        logger.info(f"      {strategy.name}: {alloc:.1f}%")
        total_alloc += alloc
    
    logger.info(f"\n   Total: {total_alloc:.1f}%")
    
    # Verify allocations sum to 100%
    assert abs(total_alloc - 100.0) < 0.01, f"Allocations don't sum to 100%: {total_alloc}"
    
    # 8. Summary
    logger.info("\n" + "=" * 100)
    logger.info("TEST SUMMARY")
    logger.info("=" * 100)
    logger.info(f"\n✓ Real eToro client initialized")
    logger.info(f"✓ Real market data retrieved")
    logger.info(f"✓ {len(backtested_strategies)} strategies backtested with real data")
    logger.info(f"✓ Portfolio metrics calculated")
    logger.info(f"✓ Allocations optimized")
    logger.info(f"✓ Portfolio Sharpe: {metrics['portfolio_sharpe']:.2f}")
    logger.info(f"✓ Diversification: {metrics['diversification_score']:.2f}")
    logger.info("\n✓ ALL TESTS PASSED WITH REAL DATA")
    logger.info("=" * 100 + "\n")
    
    return True


if __name__ == "__main__":
    success = test_portfolio_risk_with_real_data()
    exit(0 if success else 1)
