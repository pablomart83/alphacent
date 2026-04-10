"""
Test transaction costs and slippage in backtests.

This test verifies that:
1. Transaction costs are loaded from config
2. Commission, slippage, and spread are calculated correctly
3. Returns are adjusted for costs
4. Cost analysis is included in backtest results
"""

import logging
import sys
import yaml
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.models.database import Database
from src.models.enums import TradingMode, StrategyStatus
from src.models.dataclasses import Strategy, RiskConfig
from src.strategy.strategy_engine import StrategyEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_transaction_costs():
    """Test that transaction costs are properly applied to backtests."""
    logger.info("=" * 80)
    logger.info("TESTING TRANSACTION COSTS IN BACKTESTS")
    logger.info("=" * 80)
    
    try:
        # 1. Initialize components
        logger.info("\n[1/5] Initializing components...")
        
        # Load configuration
        config_path = Path("config/autonomous_trading.yaml")
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info("   ✓ Configuration loaded")
            
            # Verify transaction costs are in config
            tx_costs = config.get('backtest', {}).get('transaction_costs', {})
            logger.info(f"   ✓ Transaction costs config: {tx_costs}")
        else:
            logger.error("   ✗ Config file not found")
            return False
        
        # Initialize database
        db = Database()
        logger.info("   ✓ Database initialized")
        
        # Initialize configuration manager
        config_manager = get_config()
        logger.info("   ✓ Configuration manager initialized")
        
        # Initialize eToro client (mock if credentials not available)
        try:
            credentials = config_manager.load_credentials(TradingMode.DEMO)
            etoro_client = EToroAPIClient(
                public_key=credentials['public_key'],
                user_key=credentials['user_key'],
                mode=TradingMode.DEMO
            )
            logger.info("   ✓ eToro client initialized")
        except Exception as e:
            logger.warning(f"   ⚠ Could not initialize eToro client: {e}")
            logger.info("   Using mock eToro client for testing")
            from unittest.mock import Mock
            etoro_client = Mock()
        
        # Initialize LLM service
        llm_service = LLMService()
        logger.info("   ✓ LLM service initialized")
        
        # Initialize market data manager
        market_data = MarketDataManager(etoro_client=etoro_client)
        logger.info("   ✓ Market data manager initialized")
        
        # Initialize strategy engine
        strategy_engine = StrategyEngine(
            llm_service=llm_service,
            market_data=market_data
        )
        logger.info("   ✓ Strategy engine initialized")
        
        # 2. Create a simple test strategy
        logger.info("\n[2/5] Creating test strategy...")
        
        strategy = Strategy(
            id="test_tx_costs",
            name="Transaction Cost Test Strategy",
            description="Simple RSI mean reversion strategy for testing transaction costs",
            status=StrategyStatus.PROPOSED,
            rules={
                "indicators": ["RSI:14"],
                "entry_conditions": ["RSI(14) < 30"],
                "exit_conditions": ["RSI(14) > 70"]
            },
            symbols=["AAPL"],
            risk_params=RiskConfig(),
            created_at=datetime.now()
        )
        
        logger.info(f"   ✓ Created strategy: {strategy.name}")
        logger.info(f"   Entry: {strategy.rules['entry_conditions']}")
        logger.info(f"   Exit: {strategy.rules['exit_conditions']}")
        
        # 3. Run backtest WITHOUT transaction costs
        logger.info("\n[3/5] Running backtest WITHOUT transaction costs...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        
        results_no_costs = strategy_engine.backtest_strategy(
            strategy=strategy,
            start=start_date,
            end=end_date,
            commission=0.0,
            slippage_bps=0.0
        )
        
        logger.info(f"   ✓ Backtest complete (no costs)")
        logger.info(f"   Total return: {results_no_costs.total_return:.2%}")
        logger.info(f"   Sharpe ratio: {results_no_costs.sharpe_ratio:.2f}")
        logger.info(f"   Total trades: {results_no_costs.total_trades}")
        logger.info(f"   Transaction costs: ${results_no_costs.total_transaction_costs:,.2f}")
        
        # 4. Run backtest WITH transaction costs (from config)
        logger.info("\n[4/5] Running backtest WITH transaction costs (from config)...")
        
        # Reset strategy status
        strategy.status = StrategyStatus.PROPOSED
        strategy.id = "test_tx_costs_with_costs"
        
        results_with_costs = strategy_engine.backtest_strategy(
            strategy=strategy,
            start=start_date,
            end=end_date
            # commission and slippage will be loaded from config
        )
        
        logger.info(f"   ✓ Backtest complete (with costs)")
        logger.info(f"   Gross return: {results_with_costs.gross_return:.2%}")
        logger.info(f"   Net return: {results_with_costs.net_return:.2%}")
        logger.info(f"   Sharpe ratio: {results_with_costs.sharpe_ratio:.2f}")
        logger.info(f"   Total trades: {results_with_costs.total_trades}")
        logger.info(f"   Commission cost: ${results_with_costs.total_commission_cost:,.2f}")
        logger.info(f"   Slippage cost: ${results_with_costs.total_slippage_cost:,.2f}")
        logger.info(f"   Spread cost: ${results_with_costs.total_spread_cost:,.2f}")
        logger.info(f"   Total transaction costs: ${results_with_costs.total_transaction_costs:,.2f}")
        logger.info(f"   Costs as % of capital: {results_with_costs.transaction_costs_pct:.4%}")
        
        # 5. Verify results
        logger.info("\n[5/5] Verifying results...")
        
        # Check that costs were applied
        if results_with_costs.total_transaction_costs > 0:
            logger.info("   ✓ Transaction costs were calculated")
        else:
            logger.error("   ✗ Transaction costs were NOT calculated")
            return False
        
        # Check that net return is less than gross return (if there were trades)
        if results_with_costs.total_trades > 0:
            if results_with_costs.net_return < results_with_costs.gross_return:
                logger.info("   ✓ Net return is less than gross return (costs applied)")
            else:
                logger.error("   ✗ Net return should be less than gross return")
                return False
        
        # Check that all cost components are present
        if results_with_costs.total_commission_cost > 0:
            logger.info("   ✓ Commission costs calculated")
        else:
            logger.warning("   ⚠ Commission costs are zero")
        
        if results_with_costs.total_slippage_cost > 0:
            logger.info("   ✓ Slippage costs calculated")
        else:
            logger.warning("   ⚠ Slippage costs are zero")
        
        if results_with_costs.total_spread_cost > 0:
            logger.info("   ✓ Spread costs calculated")
        else:
            logger.warning("   ⚠ Spread costs are zero")
        
        # Calculate impact of costs
        if results_with_costs.total_trades > 0:
            cost_impact = results_with_costs.gross_return - results_with_costs.net_return
            logger.info(f"\n   Cost impact: {cost_impact:.4%} ({cost_impact/results_with_costs.gross_return*100:.2f}% of gross return)")
        
        logger.info("\n" + "=" * 80)
        logger.info("✓ TRANSACTION COSTS TEST PASSED")
        logger.info("=" * 80)
        
        return True
        
    except Exception as e:
        logger.error(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_transaction_costs()
    sys.exit(0 if success else 1)
