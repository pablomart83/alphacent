"""Example demonstrating performance attribution and benchmarking features."""

import logging
from datetime import datetime, timedelta

from src.strategy.strategy_engine import StrategyEngine
from src.llm.llm_service import LLMService
from src.data.market_data_manager import MarketDataManager
from src.api.etoro_client import EToroAPIClient
from src.core.config import Config
from src.models import TradingMode

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Demonstrate performance attribution and benchmarking."""
    
    logger.info("=== Performance Attribution and Benchmarking Example ===")
    
    # Load configuration
    config = Config()
    
    # Initialize components
    etoro_client = EToroAPIClient(
        public_key=config.etoro_public_key,
        user_key=config.etoro_user_key,
        mode=TradingMode.DEMO
    )
    
    market_data = MarketDataManager(etoro_client)
    llm_service = LLMService()
    strategy_engine = StrategyEngine(llm_service, market_data)
    
    # Get all active strategies
    strategies = strategy_engine.get_active_strategies()
    
    if not strategies:
        logger.warning("No active strategies found. Please activate some strategies first.")
        return
    
    logger.info(f"Found {len(strategies)} active strategies")
    
    # Example 1: Compare each strategy to benchmark
    logger.info("\n=== Benchmark Comparison ===")
    
    for strategy in strategies:
        logger.info(f"\nStrategy: {strategy.name}")
        
        try:
            # Compare to S&P 500 (SPY)
            spy_comparison = strategy_engine.compare_to_benchmark(
                strategy.id,
                "SPY",
                start=strategy.activated_at,
                end=datetime.now()
            )
            
            logger.info(f"  vs SPY:")
            logger.info(f"    Strategy Return: {spy_comparison['strategy_return']:.2%}")
            logger.info(f"    Benchmark Return: {spy_comparison['benchmark_return']:.2%}")
            logger.info(f"    Relative Performance: {spy_comparison['relative_performance']:.2%}")
            logger.info(f"    Alpha: {spy_comparison['alpha']:.2%}")
            logger.info(f"    Beta: {spy_comparison['beta']:.2f}")
            
            # If strategy trades crypto, also compare to Bitcoin
            if any(symbol.endswith("-USD") or "BTC" in symbol for symbol in strategy.symbols):
                btc_comparison = strategy_engine.compare_to_benchmark(
                    strategy.id,
                    "BTC-USD",
                    start=strategy.activated_at,
                    end=datetime.now()
                )
                
                logger.info(f"  vs BTC:")
                logger.info(f"    Strategy Return: {btc_comparison['strategy_return']:.2%}")
                logger.info(f"    Benchmark Return: {btc_comparison['benchmark_return']:.2%}")
                logger.info(f"    Relative Performance: {btc_comparison['relative_performance']:.2%}")
                logger.info(f"    Alpha: {btc_comparison['alpha']:.2%}")
                logger.info(f"    Beta: {btc_comparison['beta']:.2f}")
        
        except Exception as e:
            logger.error(f"  Failed to compare to benchmark: {e}")
    
    # Example 2: P&L Attribution by Strategy
    logger.info("\n=== P&L Attribution by Strategy (Last 30 Days) ===")
    
    try:
        start = datetime.now() - timedelta(days=30)
        end = datetime.now()
        
        strategy_attribution = strategy_engine.attribute_pnl(
            start=start,
            end=end,
            group_by="strategy"
        )
        
        if strategy_attribution:
            logger.info(f"\nTotal Strategies: {len(strategy_attribution)}")
            
            # Sort by P&L (highest first)
            sorted_strategies = sorted(
                strategy_attribution.items(),
                key=lambda x: x[1]["pnl"],
                reverse=True
            )
            
            for strategy_id, data in sorted_strategies:
                logger.info(f"\n  {data['name']}:")
                logger.info(f"    P&L: ${data['pnl']:.2f}")
                logger.info(f"    Contribution: {data['contribution_pct']:.1f}%")
                logger.info(f"    Trades: {data['trades']}")
                logger.info(f"    Winning Trades: {data['winning_trades']}")
                logger.info(f"    Losing Trades: {data['losing_trades']}")
                
                if data['trades'] > 0:
                    win_rate = (data['winning_trades'] / data['trades']) * 100
                    logger.info(f"    Win Rate: {win_rate:.1f}%")
        else:
            logger.info("No positions found in the last 30 days")
    
    except Exception as e:
        logger.error(f"Failed to attribute P&L by strategy: {e}")
    
    # Example 3: P&L Attribution by Position
    logger.info("\n=== P&L Attribution by Position (Top 10) ===")
    
    try:
        position_attribution = strategy_engine.attribute_pnl(
            start=start,
            end=end,
            group_by="position"
        )
        
        if position_attribution:
            # Sort by absolute P&L (largest impact first)
            sorted_positions = sorted(
                position_attribution.items(),
                key=lambda x: abs(x[1]["pnl"]),
                reverse=True
            )
            
            # Show top 10
            for pos_id, data in sorted_positions[:10]:
                logger.info(f"\n  {data['symbol']} ({data['strategy_name']}):")
                logger.info(f"    P&L: ${data['pnl']:.2f}")
                logger.info(f"    Contribution: {data['contribution_pct']:.1f}%")
                logger.info(f"    Quantity: {data['quantity']}")
                logger.info(f"    Entry Price: ${data['entry_price']:.2f}")
                logger.info(f"    Current Price: ${data['current_price']:.2f}")
                logger.info(f"    Opened: {data['opened_at']}")
                
                if data['closed_at']:
                    logger.info(f"    Closed: {data['closed_at']}")
                else:
                    logger.info(f"    Status: OPEN")
        else:
            logger.info("No positions found")
    
    except Exception as e:
        logger.error(f"Failed to attribute P&L by position: {e}")
    
    # Example 4: P&L Attribution by Time Period
    logger.info("\n=== P&L Attribution by Time Period (Last 30 Days) ===")
    
    try:
        time_attribution = strategy_engine.attribute_pnl(
            start=start,
            end=end,
            group_by="time_period"
        )
        
        if time_attribution:
            logger.info(f"\nTotal Periods: {len(time_attribution)}")
            
            for period, data in time_attribution.items():
                logger.info(f"\n  {period}:")
                logger.info(f"    P&L: ${data['pnl']:.2f}")
                logger.info(f"    Trades: {data['trades']}")
                logger.info(f"    Active Strategies: {data['strategies']}")
                logger.info(f"    Winning Trades: {data['winning_trades']}")
                logger.info(f"    Losing Trades: {data['losing_trades']}")
        else:
            logger.info("No time periods found")
    
    except Exception as e:
        logger.error(f"Failed to attribute P&L by time period: {e}")
    
    logger.info("\n=== Example Complete ===")


if __name__ == "__main__":
    main()
