"""Example usage of StrategyEngine for generating and managing trading strategies."""

import logging
from datetime import datetime, timedelta

from src.core.config import Config
from src.api.etoro_client import EToroAPIClient
from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.strategy.strategy_engine import StrategyEngine
from src.models import RiskConfig, TradingMode
from src.models.database import init_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Demonstrate StrategyEngine functionality."""
    
    # Initialize database
    init_database("alphacent_example.db")
    
    # Load configuration
    config = Config()
    
    # Initialize components
    logger.info("Initializing components...")
    
    # eToro API client (demo mode)
    etoro_client = EToroAPIClient(
        public_key=config.get("etoro_public_key", "demo_key"),
        user_key=config.get("etoro_user_key", "demo_key"),
        mode=TradingMode.DEMO
    )
    
    # Market data manager
    market_data = MarketDataManager(etoro_client, cache_ttl=60)
    
    # LLM service
    llm_service = LLMService(model="qwen2.5-coder:7b")
    
    # Strategy engine
    strategy_engine = StrategyEngine(llm_service, market_data)
    
    # Example 1: Generate a new strategy
    logger.info("\n=== Example 1: Generate Strategy ===")
    
    prompt = "Create a momentum strategy for tech stocks that buys on upward trends"
    constraints = {
        "risk_config": RiskConfig(
            max_position_size_pct=0.10,
            stop_loss_pct=0.02,
            take_profit_pct=0.04
        ),
        "available_symbols": ["AAPL", "MSFT", "GOOGL", "NVDA"]
    }
    
    try:
        strategy = strategy_engine.generate_strategy(prompt, constraints)
        logger.info(f"Generated strategy: {strategy.name}")
        logger.info(f"Description: {strategy.description}")
        logger.info(f"Symbols: {strategy.symbols}")
        logger.info(f"Status: {strategy.status}")
    except Exception as e:
        logger.error(f"Failed to generate strategy: {e}")
        logger.info("Note: Make sure Ollama is running (ollama serve)")
        return
    
    # Example 2: Backtest the strategy
    logger.info("\n=== Example 2: Backtest Strategy ===")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)  # 1 year backtest
    
    try:
        results = strategy_engine.backtest_strategy(strategy, start_date, end_date)
        logger.info(f"Backtest results:")
        logger.info(f"  Total return: {results.total_return:.2%}")
        logger.info(f"  Sharpe ratio: {results.sharpe_ratio:.2f}")
        logger.info(f"  Max drawdown: {results.max_drawdown:.2%}")
        logger.info(f"  Win rate: {results.win_rate:.2%}")
        logger.info(f"  Total trades: {results.total_trades}")
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        return
    
    # Example 3: Activate strategy in demo mode
    logger.info("\n=== Example 3: Activate Strategy ===")
    
    try:
        strategy_engine.activate_strategy(strategy.id, TradingMode.DEMO)
        logger.info(f"Strategy activated in DEMO mode")
        logger.info(f"Status: {strategy.status}")
    except Exception as e:
        logger.error(f"Failed to activate strategy: {e}")
        return
    
    # Example 4: Generate trading signals
    logger.info("\n=== Example 4: Generate Signals ===")
    
    try:
        signals = strategy_engine.generate_signals(strategy)
        logger.info(f"Generated {len(signals)} signals")
        
        for signal in signals:
            logger.info(f"  {signal.symbol}: {signal.action.value}")
            logger.info(f"    Confidence: {signal.confidence:.2f}")
            logger.info(f"    Reasoning: {signal.reasoning}")
    except Exception as e:
        logger.error(f"Failed to generate signals: {e}")
    
    # Example 5: Monitor performance
    logger.info("\n=== Example 5: Monitor Performance ===")
    
    try:
        performance = strategy_engine.monitor_performance(strategy.id)
        logger.info(f"Current performance metrics:")
        logger.info(f"  Total return: {performance.total_return:.2f}")
        logger.info(f"  Sharpe ratio: {performance.sharpe_ratio:.2f}")
        logger.info(f"  Win rate: {performance.win_rate:.2%}")
        logger.info(f"  Total trades: {performance.total_trades}")
    except Exception as e:
        logger.error(f"Failed to monitor performance: {e}")
    
    # Example 6: Check retirement triggers
    logger.info("\n=== Example 6: Check Retirement Triggers ===")
    
    try:
        retirement_reason = strategy_engine.check_retirement_triggers(strategy.id)
        if retirement_reason:
            logger.info(f"Strategy should be retired: {retirement_reason}")
        else:
            logger.info("Strategy performance is acceptable, no retirement needed")
    except Exception as e:
        logger.error(f"Failed to check retirement triggers: {e}")
    
    # Example 7: Optimize allocations across multiple strategies
    logger.info("\n=== Example 7: Optimize Allocations ===")
    
    try:
        # Get all active strategies
        active_strategies = strategy_engine.get_active_strategies()
        
        if active_strategies:
            allocations = strategy_engine.optimize_allocations(active_strategies)
            logger.info("Optimal allocations:")
            for strategy_id, allocation in allocations.items():
                strat = strategy_engine.get_strategy(strategy_id)
                logger.info(f"  {strat.name}: {allocation:.1%}")
        else:
            logger.info("No active strategies for allocation optimization")
    except Exception as e:
        logger.error(f"Failed to optimize allocations: {e}")
    
    # Example 8: Deactivate strategy
    logger.info("\n=== Example 8: Deactivate Strategy ===")
    
    try:
        strategy_engine.deactivate_strategy(strategy.id)
        logger.info(f"Strategy deactivated")
        logger.info(f"Status: {strategy.status}")
    except Exception as e:
        logger.error(f"Failed to deactivate strategy: {e}")
    
    logger.info("\n=== Example Complete ===")


if __name__ == "__main__":
    main()
