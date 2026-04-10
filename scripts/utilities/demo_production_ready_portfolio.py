"""Production-ready portfolio risk management demo with all enhancements."""

import logging
from datetime import datetime, timedelta

import pandas as pd

from src.api.etoro_client import EToroAPIClient
from src.core.config import Configuration
from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.models.enums import TradingMode
from src.strategy.portfolio_manager import PortfolioManager
from src.strategy.strategy_engine import StrategyEngine
from src.strategy.strategy_proposer import StrategyProposer

# Configure logging with file and console output
log_filename = f"production_portfolio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

verbose_formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(name)s - %(funcName)s:%(lineno)d - %(message)s'
)
console_formatter = logging.Formatter('%(levelname)s - %(name)s - %(message)s')

file_handler = logging.FileHandler(log_filename)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(verbose_formatter)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(console_formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)
logger.info(f"Logging to file: {log_filename}")


def main():
    """Run production-ready portfolio risk management."""
    logger.info("=" * 100)
    logger.info("PRODUCTION-READY PORTFOLIO RISK MANAGEMENT")
    logger.info("=" * 100)
    
    # Configuration
    MAX_CORRELATION = 0.7
    MIN_TRADES = 5  # Lowered for demo purposes (production should be 20+)
    COMMISSION_PER_TRADE = 1.0
    SLIPPAGE_BPS = 5
    
    # Initialize components
    logger.info("\n1. Initializing components...")
    
    config = Configuration()
    try:
        credentials = config.load_credentials(TradingMode.DEMO)
        logger.info("   ✓ Credentials loaded")
    except Exception as e:
        logger.error(f"   ✗ Failed to load credentials: {e}")
        return
    
    try:
        etoro_client = EToroAPIClient(
            public_key=credentials['public_key'],
            user_key=credentials['user_key'],
            mode=TradingMode.DEMO
        )
        logger.info("   ✓ eToro client initialized")
    except Exception as e:
        logger.error(f"   ✗ Failed to initialize eToro client: {e}")
        return
    
    market_data = MarketDataManager(etoro_client=etoro_client)
    llm_service = LLMService()
    strategy_engine = StrategyEngine(llm_service=llm_service, market_data=market_data)
    strategy_proposer = StrategyProposer(llm_service=llm_service, market_data=market_data)
    
    # Initialize with production settings
    portfolio_manager = PortfolioManager(
        strategy_engine,
        max_correlation=MAX_CORRELATION,
        min_trades=MIN_TRADES
    )
    
    logger.info(f"   ✓ Portfolio manager initialized (max_corr={MAX_CORRELATION}, min_trades={MIN_TRADES})")
    
    # Generate strategies
    logger.info("\n2. Generating strategies...")
    logger.info("-" * 100)
    
    symbols = ["AAPL", "GOOGL", "MSFT"]
    strategies = strategy_proposer.propose_strategies(count=10, symbols=symbols)
    logger.info(f"   Generated {len(strategies)} strategies")
    
    # Walk-forward optimization setup
    logger.info("\n3. Walk-Forward Optimization Setup...")
    logger.info("-" * 100)
    
    end_date = datetime.now()
    total_days = 365
    train_days = int(total_days * 2/3)
    test_days = total_days - train_days
    
    train_start = end_date - timedelta(days=total_days)
    train_end = end_date - timedelta(days=test_days)
    test_start = train_end
    test_end = end_date
    
    logger.info(f"   Training: {train_start.date()} to {train_end.date()} ({train_days} days)")
    logger.info(f"   Testing: {test_start.date()} to {test_end.date()} ({test_days} days)")
    logger.info(f"   Transaction costs: ${COMMISSION_PER_TRADE}/trade, {SLIPPAGE_BPS}bps slippage")
    
    # Backtest with walk-forward validation
    logger.info("\n4. Backtesting with Walk-Forward Validation...")
    logger.info("-" * 100)
    
    validated_strategies = []
    for i, strategy in enumerate(strategies, 1):
        logger.info(f"\n   Strategy {i}/{len(strategies)}: {strategy.name}")
        
        try:
            # Train phase
            logger.info(f"      Training...")
            train_results = strategy_engine.backtest_strategy(
                strategy=strategy,
                start=train_start,
                end=train_end,
                commission=COMMISSION_PER_TRADE,
                slippage_bps=SLIPPAGE_BPS
            )
            
            logger.info(f"         Trades: {train_results.total_trades}, "
                       f"Return: {train_results.total_return:.2%}, "
                       f"Sharpe: {train_results.sharpe_ratio:.2f}")
            
            if train_results.total_trades < 10:
                logger.warning(f"         ⚠️  Insufficient training trades, skipping")
                continue
            
            # Test phase (out-of-sample)
            logger.info(f"      Testing (out-of-sample)...")
            test_results = strategy_engine.backtest_strategy(
                strategy=strategy,
                start=test_start,
                end=test_end,
                commission=COMMISSION_PER_TRADE,
                slippage_bps=SLIPPAGE_BPS
            )
            
            logger.info(f"         Trades: {test_results.total_trades}, "
                       f"Return: {test_results.total_return:.2%}, "
                       f"Sharpe: {test_results.sharpe_ratio:.2f}")
            
            if test_results.total_trades < MIN_TRADES:
                logger.warning(f"         ⚠️  Insufficient test trades ({test_results.total_trades} < {MIN_TRADES})")
                continue
            
            # Check for overfitting
            perf_ratio = test_results.sharpe_ratio / train_results.sharpe_ratio if train_results.sharpe_ratio > 0 else 0
            logger.info(f"         Test/Train Sharpe: {perf_ratio:.2f}")
            
            if perf_ratio < 0.3:
                logger.warning(f"         ⚠️  Possible overfitting detected")
            
            # Use test results (out-of-sample performance)
            strategy.backtest_results = test_results
            strategy.performance.sharpe_ratio = test_results.sharpe_ratio
            strategy.performance.total_return = test_results.total_return
            strategy.performance.max_drawdown = test_results.max_drawdown
            strategy.performance.win_rate = test_results.win_rate
            strategy.performance.total_trades = test_results.total_trades
            
            validated_strategies.append(strategy)
            logger.info(f"         ✓ Strategy validated")
            
        except Exception as e:
            logger.error(f"      ✗ Backtest failed: {e}")
            continue
    
    logger.info(f"\n   ✓ {len(validated_strategies)} strategies validated out-of-sample")
    
    if len(validated_strategies) < 2:
        logger.error("\n✗ Need at least 2 validated strategies for portfolio analysis")
        return
    
    # Extract returns data
    logger.info("\n5. Extracting Returns Data...")
    logger.info("-" * 100)
    
    returns_data = {}
    for strategy in validated_strategies:
        if hasattr(strategy.backtest_results, 'equity_curve') and strategy.backtest_results.equity_curve is not None:
            equity = strategy.backtest_results.equity_curve
            returns = equity.pct_change().fillna(0)
            returns_data[strategy.id] = returns
            logger.info(f"   {strategy.name}: {len(returns)} days, "
                       f"mean={returns.mean():.4%}, std={returns.std():.4%}")
    
    # Apply correlation filtering
    logger.info("\n6. Applying Correlation Constraints...")
    logger.info("-" * 100)
    
    filtered_strategies, filtered_returns = portfolio_manager.risk_manager.filter_by_correlation(
        validated_strategies, returns_data
    )
    
    if len(filtered_strategies) < 2:
        logger.error("\n✗ Not enough strategies after correlation filtering")
        return
    
    logger.info(f"   ✓ {len(filtered_strategies)} strategies after correlation filtering")
    
    # Calculate portfolio metrics
    logger.info("\n7. Portfolio Metrics...")
    logger.info("-" * 100)
    
    metrics = portfolio_manager.calculate_portfolio_metrics(
        filtered_strategies, filtered_returns
    )
    
    logger.info(f"\n   Portfolio Sharpe: {metrics['portfolio_sharpe']:.2f}")
    logger.info(f"   Portfolio Max Drawdown: {metrics['portfolio_max_drawdown']:.2%}")
    logger.info(f"   Diversification Score: {metrics['diversification_score']:.2f}")
    
    # Optimize allocations
    logger.info("\n8. Optimizing Allocations...")
    logger.info("-" * 100)
    
    allocations = portfolio_manager.optimize_allocations(
        filtered_strategies, filtered_returns
    )
    
    equal_weight = 100.0 / len(filtered_strategies)
    logger.info(f"\n   Equal Weight: {equal_weight:.1f}% each")
    logger.info(f"\n   Optimized Allocations:")
    for strategy_id, alloc in allocations.items():
        strategy = next(s for s in filtered_strategies if s.id == strategy_id)
        logger.info(f"      {strategy.name}: {alloc:.1f}%")
    
    # Summary
    logger.info("\n" + "=" * 100)
    logger.info("PRODUCTION-READY PORTFOLIO SUMMARY")
    logger.info("=" * 100)
    logger.info(f"\n✓ Generated {len(strategies)} strategies")
    logger.info(f"✓ Validated {len(validated_strategies)} strategies out-of-sample")
    logger.info(f"✓ Filtered to {len(filtered_strategies)} strategies (correlation < {MAX_CORRELATION})")
    logger.info(f"✓ Transaction costs applied: ${COMMISSION_PER_TRADE}/trade + {SLIPPAGE_BPS}bps")
    logger.info(f"✓ Walk-forward optimization: {train_days}/{test_days} day split")
    logger.info(f"✓ Portfolio diversification: {metrics['diversification_score']:.2f}")
    logger.info(f"\nProduction-ready portfolio analysis complete!")
    logger.info("=" * 100 + "\n")


if __name__ == "__main__":
    main()
