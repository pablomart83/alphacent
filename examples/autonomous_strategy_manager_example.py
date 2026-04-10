"""Example usage of Autonomous Strategy Manager."""

import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.strategy.autonomous_strategy_manager import AutonomousStrategyManager
from src.strategy.strategy_engine import StrategyEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def main():
    """Run autonomous strategy manager example."""
    logger.info("=" * 80)
    logger.info("Autonomous Strategy Manager Example")
    logger.info("=" * 80)

    # Initialize services
    logger.info("\n1. Initializing services...")
    llm_service = LLMService()
    market_data = MarketDataManager()
    strategy_engine = StrategyEngine(llm_service, market_data)

    # Create autonomous manager with custom config
    config = {
        "autonomous": {
            "enabled": True,
            "proposal_frequency": "weekly",
            "max_active_strategies": 10,
            "min_active_strategies": 5,
            "proposal_count": 3,  # Propose 3 strategies per cycle
        },
        "activation_thresholds": {
            "min_sharpe": 1.5,
            "max_drawdown": 0.15,
            "min_win_rate": 0.5,
            "min_trades": 20,
        },
        "retirement_thresholds": {
            "max_sharpe": 0.5,
            "max_drawdown": 0.15,
            "min_win_rate": 0.4,
            "min_trades_for_evaluation": 30,
        },
        "backtest": {
            "days": 90,
        },
    }

    autonomous_manager = AutonomousStrategyManager(
        llm_service=llm_service,
        market_data=market_data,
        strategy_engine=strategy_engine,
        config=config,
    )

    logger.info("✓ Services initialized")

    # Get initial status
    logger.info("\n2. Getting initial system status...")
    status = autonomous_manager.get_status()
    logger.info(f"   Enabled: {status['enabled']}")
    logger.info(f"   Market Regime: {status['market_regime']}")
    logger.info(f"   Active Strategies: {status['active_strategies_count']}")
    logger.info(f"   Total Strategies: {status['total_strategies_count']}")

    # Run a complete autonomous cycle
    logger.info("\n3. Running autonomous strategy cycle...")
    logger.info("   This will:")
    logger.info("   - Propose 3 new strategies based on market conditions")
    logger.info("   - Backtest each proposal")
    logger.info("   - Activate high performers (Sharpe > 1.5)")
    logger.info("   - Check retirement triggers for active strategies")
    logger.info("   - Retire underperformers (Sharpe < 0.5)")
    logger.info("")

    try:
        stats = autonomous_manager.run_strategy_cycle()

        # Display results
        logger.info("\n4. Cycle Results:")
        logger.info(f"   Duration: {stats['cycle_duration_seconds']:.1f} seconds")
        logger.info(f"   Proposals Generated: {stats['proposals_generated']}")
        logger.info(f"   Proposals Backtested: {stats['proposals_backtested']}")
        logger.info(f"   Strategies Activated: {stats['strategies_activated']}")
        logger.info(f"   Strategies Retired: {stats['strategies_retired']}")

        if stats["errors"]:
            logger.warning(f"   Errors: {len(stats['errors'])}")
            for error in stats["errors"]:
                logger.warning(f"      - {error}")

    except Exception as e:
        logger.error(f"Failed to run cycle: {e}", exc_info=True)
        return

    # Get updated status
    logger.info("\n5. Getting updated system status...")
    status = autonomous_manager.get_status()
    logger.info(f"   Active Strategies: {status['active_strategies_count']}")
    logger.info(f"   Total Strategies: {status['total_strategies_count']}")
    logger.info(f"   Last Run: {status['last_run_time']}")
    logger.info(f"   Next Run: {status['next_run_time']}")

    # Display strategy breakdown
    if status["status_counts"]:
        logger.info("\n6. Strategy Status Breakdown:")
        for status_name, count in status["status_counts"].items():
            logger.info(f"   {status_name}: {count}")

    # Check if should run again
    logger.info("\n7. Checking schedule...")
    should_run = autonomous_manager.should_run_cycle()
    logger.info(f"   Should run cycle now: {should_run}")

    logger.info("\n" + "=" * 80)
    logger.info("Example completed successfully!")
    logger.info("=" * 80)


def run_scheduled_example():
    """Example of running scheduled cycles."""
    logger.info("=" * 80)
    logger.info("Scheduled Autonomous Strategy Manager Example")
    logger.info("=" * 80)

    # Initialize services
    llm_service = LLMService()
    market_data = MarketDataManager()
    strategy_engine = StrategyEngine(llm_service, market_data)

    # Create autonomous manager with daily frequency
    config = {
        "autonomous": {
            "enabled": True,
            "proposal_frequency": "daily",  # Run daily
            "max_active_strategies": 10,
            "proposal_count": 5,
        }
    }

    autonomous_manager = AutonomousStrategyManager(
        llm_service=llm_service,
        market_data=market_data,
        strategy_engine=strategy_engine,
        config=config,
    )

    logger.info("\nRunning scheduled cycle check...")
    logger.info("This will only run if it's time based on the schedule.")

    # Run scheduled cycle (only runs if it's time)
    stats = autonomous_manager.run_scheduled_cycle()

    if stats:
        logger.info("\n✓ Cycle ran successfully")
        logger.info(f"  Proposals: {stats['proposals_generated']}")
        logger.info(f"  Activated: {stats['strategies_activated']}")
        logger.info(f"  Retired: {stats['strategies_retired']}")
    else:
        logger.info("\n✗ Cycle skipped - not yet time based on schedule")

    logger.info("\n" + "=" * 80)


if __name__ == "__main__":
    # Run the main example
    main()

    # Uncomment to run scheduled example
    # run_scheduled_example()
