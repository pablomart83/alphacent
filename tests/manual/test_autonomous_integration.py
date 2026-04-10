"""Integration test for Autonomous Strategy Manager."""

import logging
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService, StrategyDefinition
from src.models.dataclasses import (
    BacktestResults,
    PerformanceMetrics,
    RiskConfig,
    Strategy,
)
from src.models.enums import StrategyStatus
from src.strategy.autonomous_strategy_manager import AutonomousStrategyManager
from src.strategy.strategy_engine import StrategyEngine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_autonomous_manager_integration():
    """Integration test for autonomous strategy manager."""
    logger.info("=" * 80)
    logger.info("Running Autonomous Strategy Manager Integration Test")
    logger.info("=" * 80)

    # Create mocks
    mock_llm = Mock(spec=LLMService)
    mock_market_data = Mock(spec=MarketDataManager)
    mock_strategy_engine = Mock(spec=StrategyEngine)

    # Mock strategy generation
    mock_strategy_def = StrategyDefinition(
        name="Test Momentum Strategy",
        description="A test momentum strategy",
        rules={"entry": ["RSI < 30"], "exit": ["RSI > 70"]},
        symbols=["AAPL", "GOOGL"],
        risk_params=RiskConfig(),
        reasoning=None,
    )
    mock_llm.generate_strategy = Mock(return_value=mock_strategy_def)

    # Mock market data for regime detection
    mock_bar = Mock()
    mock_bar.close = 100.0
    mock_market_data.get_historical_data = Mock(
        return_value=[mock_bar] * 60  # 60 days of data
    )

    # Mock backtest results (good performance)
    good_backtest = BacktestResults(
        total_return=0.25,
        sharpe_ratio=2.0,
        sortino_ratio=2.5,
        max_drawdown=0.10,
        win_rate=0.60,
        avg_win=0.02,
        avg_loss=-0.01,
        total_trades=50,
    )
    mock_strategy_engine.backtest_strategy = Mock(return_value=good_backtest)

    # Mock active strategies (empty initially)
    mock_strategy_engine.get_active_strategies = Mock(return_value=[])
    mock_strategy_engine.get_all_strategies = Mock(return_value=[])

    # Create autonomous manager
    config = {
        "autonomous": {
            "enabled": True,
            "proposal_frequency": "weekly",
            "max_active_strategies": 10,
            "proposal_count": 2,  # Propose 2 strategies
        },
        "activation_thresholds": {
            "min_sharpe": 1.5,
            "max_drawdown": 0.15,
            "min_win_rate": 0.5,
            "min_trades": 20,
        },
        "backtest": {
            "days": 90,
        },
    }

    manager = AutonomousStrategyManager(
        llm_service=mock_llm,
        market_data=mock_market_data,
        strategy_engine=mock_strategy_engine,
        config=config,
    )

    logger.info("\n1. Testing initial status...")
    status = manager.get_status()
    assert status["enabled"] is True
    assert status["active_strategies_count"] == 0
    logger.info("   ✓ Initial status correct")

    logger.info("\n2. Testing should_run_cycle (first run)...")
    assert manager.should_run_cycle() is True
    logger.info("   ✓ Should run cycle on first run")

    logger.info("\n3. Running autonomous cycle...")
    stats = manager.run_strategy_cycle()

    # Verify cycle ran successfully
    assert stats["proposals_generated"] == 2
    assert stats["proposals_backtested"] == 2
    assert stats["strategies_activated"] == 2  # Both should pass criteria
    assert stats["strategies_retired"] == 0
    assert len(stats["errors"]) == 0
    logger.info("   ✓ Cycle completed successfully")
    logger.info(f"      Proposals: {stats['proposals_generated']}")
    logger.info(f"      Backtested: {stats['proposals_backtested']}")
    logger.info(f"      Activated: {stats['strategies_activated']}")

    logger.info("\n4. Testing should_run_cycle (after recent run)...")
    assert manager.should_run_cycle() is False  # Just ran, shouldn't run again
    logger.info("   ✓ Should not run cycle immediately after")

    logger.info("\n5. Testing run_scheduled_cycle (should skip)...")
    result = manager.run_scheduled_cycle()
    assert result is None  # Should skip
    logger.info("   ✓ Scheduled cycle correctly skipped")

    logger.info("\n6. Testing should_run_cycle (after time elapsed)...")
    # Simulate time passing
    manager.last_run_time = datetime.now() - timedelta(weeks=2)
    assert manager.should_run_cycle() is True
    logger.info("   ✓ Should run cycle after time elapsed")

    logger.info("\n" + "=" * 80)
    logger.info("Integration Test PASSED")
    logger.info("=" * 80)


if __name__ == "__main__":
    test_autonomous_manager_integration()
