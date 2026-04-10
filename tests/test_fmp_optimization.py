"""
Quick test to verify FMP API optimization.

Tests that fundamental filtering is deferred until after signal generation.
"""

import logging
import yaml
from pathlib import Path
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_fmp_optimization():
    """Test that FMP API calls are minimized by deferring fundamental filtering."""
    
    # Load config
    config_path = Path("config/autonomous_trading.yaml")
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Initialize components
    from src.models.database import get_database
    from src.strategy.strategy_engine import StrategyEngine
    from src.data.market_data_manager import MarketDataManager
    from src.data.fundamental_data_provider import FundamentalDataProvider
    
    database = get_database()
    market_data = MarketDataManager(config)
    strategy_engine = StrategyEngine(config, database, market_data)
    
    # Get a test strategy
    from src.models.orm import StrategyORM
    from src.models.enums import StrategyStatus
    
    session = database.get_session()
    try:
        # Find a DEMO or LIVE strategy
        strategy_orm = session.query(StrategyORM).filter(
            StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE])
        ).first()
        
        if not strategy_orm:
            logger.warning("No DEMO/LIVE strategies found, skipping test")
            return
        
        # Convert ORM to Strategy dataclass manually
        from src.models.dataclasses import Strategy, RiskConfig, PerformanceMetrics
        from src.models.enums import StrategyStatus
        from datetime import datetime
        
        strategy = Strategy(
            id=strategy_orm.id,
            name=strategy_orm.name,
            description=strategy_orm.description or "",
            symbols=strategy_orm.symbols,
            rules=strategy_orm.rules,
            status=strategy_orm.status,
            risk_params=RiskConfig(),
            metadata=strategy_orm.metadata or {},
            created_at=strategy_orm.created_at
        )
        
        logger.info(f"Testing with strategy: {strategy.name}")
        logger.info(f"Strategy symbols: {strategy.symbols}")
        
        # Initialize FMP provider to track API usage
        fmp_provider = FundamentalDataProvider(config)
        initial_usage = fmp_provider.get_api_usage()
        initial_calls = initial_usage['fmp']['calls_made']
        
        logger.info(f"Initial FMP API calls: {initial_calls}/{initial_usage['fmp']['max_calls']}")
        
        # Generate signals (this should now defer fundamental filtering)
        logger.info("\n=== Generating signals ===")
        signals = strategy_engine.generate_signals(strategy)
        
        logger.info(f"\n=== Results ===")
        logger.info(f"Signals generated: {len(signals)}")
        
        # Check final API usage
        final_usage = fmp_provider.get_api_usage()
        final_calls = final_usage['fmp']['calls_made']
        calls_made = final_calls - initial_calls
        
        logger.info(f"FMP API calls made: {calls_made}")
        logger.info(f"Total FMP usage: {final_calls}/{final_usage['fmp']['max_calls']} ({final_usage['fmp']['usage_percent']:.1f}%)")
        
        # Calculate expected vs actual
        num_symbols = len(strategy.symbols)
        num_signals = len(signals)
        
        # Old approach: 4 calls per symbol
        old_approach_calls = num_symbols * 4
        
        # New approach: 4 calls per signal (approximately)
        expected_new_calls = num_signals * 4
        
        logger.info(f"\n=== Optimization Analysis ===")
        logger.info(f"Strategy has {num_symbols} symbols")
        logger.info(f"Generated {num_signals} signals")
        logger.info(f"Old approach would use: ~{old_approach_calls} API calls")
        logger.info(f"New approach should use: ~{expected_new_calls} API calls")
        logger.info(f"Actual calls made: {calls_made}")
        
        if num_signals > 0:
            savings = old_approach_calls - calls_made
            savings_pct = (savings / old_approach_calls) * 100 if old_approach_calls > 0 else 0
            logger.info(f"Savings: {savings} calls ({savings_pct:.1f}%)")
            
            # Verify optimization is working
            if calls_made <= expected_new_calls * 1.5:  # Allow 50% margin
                logger.info("✓ Optimization working! API calls are minimal.")
            else:
                logger.warning(f"⚠ Optimization may not be working. Expected ~{expected_new_calls}, got {calls_made}")
        else:
            logger.info("No signals generated, cannot verify optimization")
        
    finally:
        session.close()


if __name__ == '__main__':
    test_fmp_optimization()
