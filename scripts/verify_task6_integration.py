"""
Verification script for Task 6 integration.

Checks that all components are properly integrated and working.
"""

import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def verify_imports():
    """Verify all Task 6 modules can be imported."""
    logger.info("Checking imports...")
    
    try:
        from src.strategy.conviction_scorer import ConvictionScorer, ConvictionScore
        from src.strategy.trade_frequency_limiter import TradeFrequencyLimiter, TradeFrequencyCheck
        from src.strategy.transaction_cost_tracker import TransactionCostTracker, TransactionCosts
        from src.models.orm import RejectedSignalORM
        logger.info("✓ All Task 6 modules imported successfully")
        return True
    except ImportError as e:
        logger.error(f"✗ Import failed: {e}")
        return False


def verify_config():
    """Verify configuration has required Task 6 settings."""
    logger.info("Checking configuration...")
    
    try:
        import yaml
        config_path = Path("config/autonomous_trading.yaml")
        
        if not config_path.exists():
            logger.error("✗ Config file not found")
            return False
        
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        alpha_edge = config.get('alpha_edge', {})
        
        required_keys = [
            'max_active_strategies',
            'min_conviction_score',
            'min_holding_period_days',
            'max_trades_per_strategy_per_month'
        ]
        
        missing = [key for key in required_keys if key not in alpha_edge]
        
        if missing:
            logger.error(f"✗ Missing config keys: {missing}")
            return False
        
        logger.info("✓ Configuration is valid")
        logger.info(f"  - Max active strategies: {alpha_edge['max_active_strategies']}")
        logger.info(f"  - Min conviction score: {alpha_edge['min_conviction_score']}")
        logger.info(f"  - Min holding period: {alpha_edge['min_holding_period_days']} days")
        logger.info(f"  - Max trades/month: {alpha_edge['max_trades_per_strategy_per_month']}")
        return True
        
    except Exception as e:
        logger.error(f"✗ Config check failed: {e}")
        return False


def verify_database():
    """Verify database has rejected_signals table."""
    logger.info("Checking database schema...")
    
    try:
        from src.models.database import get_database
        from src.models.orm import RejectedSignalORM
        from sqlalchemy import inspect
        
        db = get_database()
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        if 'rejected_signals' not in tables:
            logger.warning("⚠ rejected_signals table not found - will be created on first use")
            # Try to create it
            from src.models.orm import Base
            Base.metadata.create_all(db.engine, tables=[RejectedSignalORM.__table__])
            logger.info("✓ Created rejected_signals table")
        else:
            logger.info("✓ rejected_signals table exists")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Database check failed: {e}")
        return False


def verify_integration():
    """Verify integration code is present in key files."""
    logger.info("Checking integration code...")
    
    checks = []
    
    # Check StrategyEngine integration
    try:
        with open('src/strategy/strategy_engine.py') as f:
            content = f.read()
            has_conviction = 'ConvictionScorer' in content
            has_frequency = 'TradeFrequencyLimiter' in content
            
            if has_conviction and has_frequency:
                logger.info("✓ StrategyEngine has conviction & frequency filtering")
                checks.append(True)
            else:
                logger.error("✗ StrategyEngine missing integration code")
                checks.append(False)
    except Exception as e:
        logger.error(f"✗ Could not check StrategyEngine: {e}")
        checks.append(False)
    
    # Check OrderExecutor integration
    try:
        with open('src/execution/order_executor.py') as f:
            content = f.read()
            has_frequency = 'TradeFrequencyLimiter' in content and 'record_trade' in content
            has_costs = 'TransactionCostTracker' in content
            
            if has_frequency and has_costs:
                logger.info("✓ OrderExecutor has trade recording & cost tracking")
                checks.append(True)
            else:
                logger.error("✗ OrderExecutor missing integration code")
                checks.append(False)
    except Exception as e:
        logger.error(f"✗ Could not check OrderExecutor: {e}")
        checks.append(False)
    
    return all(checks)


def verify_tests():
    """Verify test files exist."""
    logger.info("Checking test files...")
    
    test_files = [
        'tests/test_conviction_scorer.py',
        'tests/test_trade_frequency_limiter.py',
        'tests/test_transaction_cost_tracker.py'
    ]
    
    missing = [f for f in test_files if not Path(f).exists()]
    
    if missing:
        logger.warning(f"⚠ Missing test files: {missing}")
        return False
    
    logger.info("✓ All test files present")
    return True


def main():
    """Run all verification checks."""
    logger.info("=" * 60)
    logger.info("Task 6 Integration Verification")
    logger.info("=" * 60)
    
    results = {
        'Imports': verify_imports(),
        'Configuration': verify_config(),
        'Database': verify_database(),
        'Integration': verify_integration(),
        'Tests': verify_tests()
    }
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("Verification Results")
    logger.info("=" * 60)
    
    for check, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"{check:20s} {status}")
    
    all_passed = all(results.values())
    
    logger.info("=" * 60)
    if all_passed:
        logger.info("✓ All checks passed! Task 6 integration is ready.")
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Restart the backend to activate features")
        logger.info("2. Monitor logs for conviction scores and frequency limits")
        logger.info("3. Track transaction cost savings")
        return 0
    else:
        logger.error("✗ Some checks failed. Review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
