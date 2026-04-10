"""Demo portfolio risk management with real strategies from StrategyProposer."""

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

# Configure logging with file and console output (tee-like)
log_filename = f"portfolio_risk_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Create formatters
verbose_formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(name)s - %(funcName)s:%(lineno)d - %(message)s'
)
console_formatter = logging.Formatter('%(levelname)s - %(name)s - %(message)s')

# File handler (verbose)
file_handler = logging.FileHandler(log_filename)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(verbose_formatter)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(console_formatter)

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)
logger.info(f"Logging to file: {log_filename}")


def main():
    """Run portfolio risk management with real strategies."""
    logger.info("=" * 100)
    logger.info("PORTFOLIO RISK MANAGEMENT WITH REAL STRATEGIES")
    logger.info("=" * 100)
    
    # Initialize components
    logger.info("\n1. Initializing components...")
    
    # Load credentials
    config = Configuration()
    try:
        credentials = config.load_credentials(TradingMode.DEMO)
        logger.info("   ✓ Credentials loaded")
    except Exception as e:
        logger.error(f"   ✗ Failed to load credentials: {e}")
        logger.error("   Cannot proceed without credentials")
        logger.info("\n   Please ensure:")
        logger.info("   1. API credentials are configured in .env file")
        logger.info("   2. Run: python scripts/test_api_keys.py to verify setup")
        return
    
    # Initialize eToro client with credentials
    try:
        etoro_client = EToroAPIClient(
            public_key=credentials['public_key'],
            user_key=credentials['user_key'],
            mode=TradingMode.DEMO
        )
        logger.info("   ✓ eToro client initialized")
    except Exception as e:
        logger.error(f"   ✗ Failed to initialize eToro client: {e}")
        logger.error("   Cannot proceed without real API client")
        return
    
    market_data = MarketDataManager(etoro_client=etoro_client)
    logger.info("   ✓ Market data manager initialized")
    
    llm_service = LLMService()
    logger.info("   ✓ LLM service initialized")
    
    strategy_engine = StrategyEngine(llm_service=llm_service, market_data=market_data)
    logger.info("   ✓ Strategy engine initialized")
    
    strategy_proposer = StrategyProposer(llm_service=llm_service, market_data=market_data)
    logger.info("   ✓ Strategy proposer initialized")
    
    portfolio_manager = PortfolioManager(strategy_engine)
    logger.info("   ✓ Portfolio manager initialized")
    
    # Generate strategies using templates
    logger.info("\n2. Generating strategies using templates...")
    logger.info("-" * 100)
    
    symbols = ["AAPL", "GOOGL", "MSFT"]
    strategies = strategy_proposer.propose_strategies(count=10, symbols=symbols)  # Generate more for filtering
    
    logger.info(f"\n   Generated {len(strategies)} strategies:")
    for i, strategy in enumerate(strategies, 1):
        logger.info(f"\n   Strategy {i}: {strategy.name}")
        logger.info(f"      Description: {strategy.description}")
        logger.info(f"      Symbols: {', '.join(strategy.symbols)}")
        logger.info(f"      Indicators: {', '.join(strategy.rules.get('indicators', []))}")
        logger.info(f"      Entry: {strategy.rules.get('entry_conditions', [])[:2]}")  # First 2
        logger.info(f"      Exit: {strategy.rules.get('exit_conditions', [])[:2]}")   # First 2
    
    # Backtest strategies with transaction costs
    logger.info("\n3. Backtesting strategies with transaction costs...")
    logger.info("-" * 100)
    
    # Transaction cost assumptions
    COMMISSION_PER_TRADE = 1.0  # $1 per trade
    SLIPPAGE_BPS = 5  # 5 basis points (0.05%)
    
    logger.info(f"\n   Transaction Cost Model:")
    logger.info(f"      Commission: ${COMMISSION_PER_TRADE} per trade")
    logger.info(f"      Slippage: {SLIPPAGE_BPS} bps ({SLIPPAGE_BPS/100:.2%})")
    
    # Walk-forward optimization: Train on first 2/3, test on last 1/3
    end_date = datetime.now()
    total_days = 365  # 1 year of data
    train_days = int(total_days * 2/3)  # 243 days for training
    test_days = total_days - train_days  # 122 days for testing
    
    train_start = end_date - timedelta(days=total_days)
    train_end = end_date - timedelta(days=test_days)
    test_start = train_end
    test_end = end_date
    
    logger.info(f"\n   Walk-Forward Optimization:")
    logger.info(f"      Training Period: {train_start.date()} to {train_end.date()} ({train_days} days)")
    logger.info(f"      Testing Period: {test_start.date()} to {test_end.date()} ({test_days} days)")
    logger.info(f"      Train/Test Split: {train_days}/{test_days} days ({train_days/total_days:.0%}/{test_days/total_days:.0%})")
    
    backtested_strategies = []
    for i, strategy in enumerate(strategies, 1):
        logger.info(f"\n   Strategy {i}: {strategy.name}")
        
        # Train on in-sample data
        logger.info(f"      Training (in-sample)...")
        try:
            train_results = strategy_engine.backtest_strategy(
                strategy=strategy,
                start=train_start,
                end=train_end
            )
            
            logger.info(f"         Trades: {train_results.total_trades}")
            logger.info(f"         Return: {train_results.total_return:.2%}")
            logger.info(f"         Sharpe: {train_results.sharpe_ratio:.2f}")
            
            # Require minimum trades in training
            if train_results.total_trades < 10:
                logger.warning(f"         ⚠️  Insufficient training trades ({train_results.total_trades} < 10), skipping")
                continue
            
            # Test on out-of-sample data
            logger.info(f"      Testing (out-of-sample)...")
            test_results = strategy_engine.backtest_strategy(
                strategy=strategy,
                start=test_start,
                end=test_end
            )
            
            logger.info(f"         Trades: {test_results.total_trades}")
            logger.info(f"         Return: {test_results.total_return:.2%}")
            logger.info(f"         Sharpe: {test_results.sharpe_ratio:.2f}")
            
            # Apply transaction costs to test results
            if test_results.total_trades > 0:
                total_commission = test_results.total_trades * 2 * COMMISSION_PER_TRADE
                slippage_cost = test_results.total_trades * 2 * (SLIPPAGE_BPS / 10000)
                total_cost_pct = (total_commission / 10000) + slippage_cost
                adjusted_return = test_results.total_return - total_cost_pct
                
                logger.info(f"         Transaction Costs: {total_cost_pct:.2%}")
                logger.info(f"         Adjusted Return: {adjusted_return:.2%}")
                
                # Check for overfitting: test performance should be reasonable vs train
                performance_ratio = test_results.sharpe_ratio / train_results.sharpe_ratio if train_results.sharpe_ratio > 0 else 0
                logger.info(f"         Test/Train Sharpe Ratio: {performance_ratio:.2f}")
                
                if performance_ratio < 0.3:
                    logger.warning(f"         ⚠️  Possible overfitting (test Sharpe much worse than train)")
                elif performance_ratio > 1.5:
                    logger.info(f"         ✓ Strategy improved out-of-sample!")
                
                # Use test results for portfolio (out-of-sample performance)
                strategy.backtest_results = test_results
                strategy.performance.sharpe_ratio = test_results.sharpe_ratio
                strategy.performance.total_return = adjusted_return
                strategy.performance.max_drawdown = test_results.max_drawdown
                strategy.performance.win_rate = test_results.win_rate
                strategy.performance.total_trades = test_results.total_trades
                
                # Require minimum trades in test period
                MIN_TEST_TRADES = 5
                if test_results.total_trades >= MIN_TEST_TRADES:
                    backtested_strategies.append(strategy)
                    logger.info(f"         ✓ Strategy validated out-of-sample")
                else:
                    logger.warning(f"         ⚠️  Insufficient test trades ({test_results.total_trades} < {MIN_TEST_TRADES})")
            else:
                logger.warning(f"         ⚠️  No trades in test period")
                
        except Exception as e:
            logger.error(f"      ✗ Backtest failed: {e}")
            continue
    
    if len(backtested_strategies) < 2:
        logger.error("\n✗ Not enough strategies with valid backtests for portfolio analysis")
        logger.info("   Need at least 2 strategies with trades")
        return
    
    logger.info(f"\n   ✓ {len(backtested_strategies)} strategies successfully backtested")
    
    # Extract returns data from backtests
    logger.info("\n4. Extracting returns data and testing across market regimes...")
    logger.info("-" * 100)
    
    returns_data = {}
    for strategy in backtested_strategies:
        if hasattr(strategy.backtest_results, 'equity_curve') and strategy.backtest_results.equity_curve is not None:
            # Calculate daily returns from equity curve
            equity = strategy.backtest_results.equity_curve
            returns = equity.pct_change().fillna(0)
            returns_data[strategy.id] = returns
            
            logger.info(f"\n   {strategy.name}:")
            logger.info(f"      Days: {len(returns)}")
            logger.info(f"      Mean Daily Return: {returns.mean():.4%}")
            logger.info(f"      Std Dev: {returns.std():.4%}")
            logger.info(f"      Cumulative Return: {(1 + returns).prod() - 1:.2%}")
            
            # Analyze performance in different market regimes
            # Split test period into thirds to simulate different regimes
            third = len(returns) // 3
            regime1_returns = returns[:third]
            regime2_returns = returns[third:2*third]
            regime3_returns = returns[2*third:]
            
            logger.info(f"      Performance by Period:")
            logger.info(f"         Period 1: {(1 + regime1_returns).prod() - 1:.2%}")
            logger.info(f"         Period 2: {(1 + regime2_returns).prod() - 1:.2%}")
            logger.info(f"         Period 3: {(1 + regime3_returns).prod() - 1:.2%}")
            
            # Check consistency across periods
            period_returns = [
                (1 + regime1_returns).prod() - 1,
                (1 + regime2_returns).prod() - 1,
                (1 + regime3_returns).prod() - 1
            ]
            positive_periods = sum(1 for r in period_returns if r > 0)
            logger.info(f"         Positive Periods: {positive_periods}/3")
            
            if positive_periods >= 2:
                logger.info(f"         ✓ Consistent performance across periods")
            else:
                logger.warning(f"         ⚠️  Inconsistent performance (only {positive_periods}/3 positive)")
        else:
            logger.warning(f"   ⚠️  No equity curve for {strategy.name}, using synthetic returns")
            # Create synthetic returns based on performance metrics
            dates = pd.date_range(start=test_start, end=test_end, freq='D')
            daily_return = strategy.performance.total_return / len(dates)
            daily_vol = 0.01  # Assume 1% daily volatility
            returns = pd.Series(
                [daily_return + daily_vol * (i % 3 - 1) * 0.5 for i in range(len(dates))],
                index=dates
            )
            returns_data[strategy.id] = returns
    
    # Calculate portfolio metrics
    logger.info("\n5. Calculating Portfolio Metrics...")
    logger.info("-" * 100)
    
    metrics = portfolio_manager.calculate_portfolio_metrics(
        backtested_strategies, 
        returns_data
    )
    
    logger.info(f"\n   Portfolio Sharpe Ratio: {metrics['portfolio_sharpe']:.2f}")
    logger.info(f"   Portfolio Max Drawdown: {metrics['portfolio_max_drawdown']:.2%}")
    logger.info(f"   Diversification Score: {metrics['diversification_score']:.2f}")
    
    if not metrics['correlation_matrix'].empty:
        logger.info(f"\n   Correlation Matrix:")
        corr_matrix = metrics['correlation_matrix']
        
        # Print correlation matrix with strategy names
        strategy_names = {s.id: s.name[:20] for s in backtested_strategies}
        logger.info(f"\n{corr_matrix.to_string()}")
        
        # Analyze correlations and filter highly correlated strategies
        MAX_CORRELATION = 0.7
        logger.info(f"\n   Correlation Analysis (Max allowed: {MAX_CORRELATION}):")
        
        strategies_to_remove = set()
        if len(backtested_strategies) >= 2:
            for i, s1 in enumerate(backtested_strategies):
                for s2 in backtested_strategies[i+1:]:
                    if s1.id in corr_matrix.index and s2.id in corr_matrix.columns:
                        corr = corr_matrix.loc[s1.id, s2.id]
                        logger.info(f"      {s1.name[:20]} vs {s2.name[:20]}: {corr:.3f}")
                        
                        # Flag highly correlated strategies
                        if abs(corr) > MAX_CORRELATION:
                            logger.warning(f"      ⚠️  High correlation detected ({corr:.3f} > {MAX_CORRELATION})")
                            # Keep the better performing strategy (higher Sharpe)
                            if s1.performance.sharpe_ratio < s2.performance.sharpe_ratio:
                                strategies_to_remove.add(s1.id)
                                logger.info(f"         Removing {s1.name[:20]} (lower Sharpe: {s1.performance.sharpe_ratio:.2f})")
                            else:
                                strategies_to_remove.add(s2.id)
                                logger.info(f"         Removing {s2.name[:20]} (lower Sharpe: {s2.performance.sharpe_ratio:.2f})")
        
        # Filter out highly correlated strategies
        if strategies_to_remove:
            logger.info(f"\n   Filtering {len(strategies_to_remove)} highly correlated strategies...")
            backtested_strategies = [s for s in backtested_strategies if s.id not in strategies_to_remove]
            
            # Recalculate returns data
            returns_data = {k: v for k, v in returns_data.items() if k not in strategies_to_remove}
            
            # Recalculate metrics
            if len(backtested_strategies) >= 2:
                metrics = portfolio_manager.calculate_portfolio_metrics(
                    backtested_strategies, 
                    returns_data
                )
                logger.info(f"   Updated Portfolio Sharpe: {metrics['portfolio_sharpe']:.2f}")
                logger.info(f"   Updated Diversification Score: {metrics['diversification_score']:.2f}")
            else:
                logger.warning("   Not enough strategies remaining after correlation filtering")
    
    # Optimize allocations
    logger.info("\n6. Optimizing Allocations...")
    logger.info("-" * 100)
    
    allocations = portfolio_manager.optimize_allocations(
        backtested_strategies,
        returns_data
    )
    
    # Set equal weight for comparison
    equal_weight = 100.0 / len(backtested_strategies)
    for strategy in backtested_strategies:
        strategy.allocation_percent = equal_weight
    
    logger.info(f"\n   Original Allocations (Equal Weight: {equal_weight:.1f}% each):")
    for strategy in backtested_strategies:
        logger.info(f"      {strategy.name}: {strategy.allocation_percent:.1f}%")
    
    logger.info(f"\n   Optimized Allocations:")
    total_alloc = 0
    for strategy_id, alloc in allocations.items():
        strategy = next(s for s in backtested_strategies if s.id == strategy_id)
        change = alloc - strategy.allocation_percent
        change_str = f"+{change:.1f}%" if change > 0 else f"{change:.1f}%"
        logger.info(f"      {strategy.name}: {alloc:.1f}% ({change_str})")
        total_alloc += alloc
    
    logger.info(f"\n   Total Allocation: {total_alloc:.1f}%")
    
    # Calculate expected improvement
    logger.info("\n7. Expected Portfolio Improvement...")
    logger.info("-" * 100)
    
    # Original weighted Sharpe (equal weight)
    original_weighted_sharpe = sum(
        (s.allocation_percent / 100.0) * s.performance.sharpe_ratio 
        for s in backtested_strategies
    )
    
    # Optimized weighted Sharpe
    optimized_weighted_sharpe = sum(
        (allocations[s.id] / 100.0) * s.performance.sharpe_ratio 
        for s in backtested_strategies
    )
    
    logger.info(f"\n   Original Portfolio Sharpe (equal weight): {original_weighted_sharpe:.2f}")
    logger.info(f"   Optimized Portfolio Sharpe: {optimized_weighted_sharpe:.2f}")
    
    if original_weighted_sharpe > 0:
        improvement_pct = ((optimized_weighted_sharpe / original_weighted_sharpe - 1) * 100)
        logger.info(f"   Improvement: {optimized_weighted_sharpe - original_weighted_sharpe:.2f} ({improvement_pct:.1f}%)")
    else:
        logger.info(f"   Improvement: {optimized_weighted_sharpe - original_weighted_sharpe:.2f}")
    
    # Summary
    logger.info("\n" + "=" * 100)
    logger.info("SUMMARY")
    logger.info("=" * 100)
    logger.info(f"\n✓ Generated {len(strategies)} strategies using templates")
    logger.info(f"✓ Successfully backtested {len(backtested_strategies)} strategies")
    logger.info(f"✓ Portfolio metrics calculated")
    logger.info(f"✓ Allocations optimized for risk-adjusted returns")
    logger.info(f"✓ Diversification score: {metrics['diversification_score']:.2f}")
    
    if original_weighted_sharpe > 0:
        logger.info(f"✓ Expected Sharpe improvement: {improvement_pct:.1f}%")
    
    logger.info(f"\nPortfolio risk management with real strategies completed successfully!")
    logger.info("=" * 100 + "\n")


if __name__ == "__main__":
    main()
