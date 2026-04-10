"""
Test Parameter Optimization for Strategy Templates.

Tests the ParameterOptimizer class with real market data and backtesting.
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
from src.models.enums import TradingMode
from src.strategy.indicator_library import IndicatorLibrary
from src.strategy.strategy_engine import StrategyEngine
from src.strategy.strategy_proposer import StrategyProposer
from src.strategy.strategy_templates import StrategyTemplateLibrary, MarketRegime
from src.strategy.market_analyzer import MarketStatisticsAnalyzer
from src.strategy.parameter_optimizer import ParameterOptimizer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_parameter_optimization():
    """Test parameter optimization with real market data."""
    logger.info("=" * 80)
    logger.info("TESTING PARAMETER OPTIMIZATION")
    logger.info("=" * 80)
    
    try:
        # 1. Initialize components
        logger.info("\n[1/5] Initializing components...")
        
        # Initialize database
        db = Database()
        logger.info("   ✓ Database initialized")
        
        # Initialize configuration manager
        config_manager = get_config()
        logger.info("   ✓ Configuration manager initialized")
        
        # Initialize eToro client
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
        
        # Initialize indicator library
        indicator_library = IndicatorLibrary()
        logger.info("   ✓ Indicator library initialized")
        
        # Initialize template library
        template_library = StrategyTemplateLibrary()
        logger.info("   ✓ Strategy template library initialized")
        
        # Initialize market analyzer
        market_analyzer = MarketStatisticsAnalyzer(market_data)
        logger.info("   ✓ Market statistics analyzer initialized")
        
        # Initialize strategy engine
        strategy_engine = StrategyEngine(
            llm_service=llm_service,
            market_data=market_data
        )
        logger.info("   ✓ Strategy engine initialized")
        
        # Initialize strategy proposer
        strategy_proposer = StrategyProposer(
            llm_service=llm_service,
            market_data=market_data
        )
        # Set required attributes
        strategy_proposer.template_library = template_library
        strategy_proposer.market_analyzer = market_analyzer
        strategy_proposer.strategy_engine = strategy_engine
        logger.info("   ✓ Strategy proposer initialized")
        
        # Initialize parameter optimizer
        optimizer = ParameterOptimizer(strategy_engine)
        logger.info("   ✓ Parameter optimizer initialized")
        
        # 2. Get a template to optimize
        logger.info("\n[2/5] Getting strategy template...")
        templates = template_library.get_templates_for_regime(MarketRegime.RANGING)
        
        if not templates:
            logger.error("No templates found for RANGING market")
            return False
        
        template = templates[0]  # Use first template (RSI Mean Reversion)
        logger.info(f"   ✓ Using template: {template.name}")
        logger.info(f"   Description: {template.description}")
        
        # 3. Generate a strategy from the template
        logger.info("\n[3/5] Generating strategy from template...")
        
        symbols = ["SPY"]
        
        # Get market statistics
        market_statistics = {}
        indicator_distributions = {}
        
        for symbol in symbols:
            try:
                stats = market_analyzer.analyze_symbol(symbol, period_days=90)
                market_statistics[symbol] = stats
                
                distributions = market_analyzer.analyze_indicator_distributions(symbol, period_days=90)
                indicator_distributions[symbol] = distributions
            except Exception as e:
                logger.warning(f"Failed to analyze {symbol}: {e}")
        
        # Get market context
        try:
            market_context = market_analyzer.get_market_context()
        except Exception as e:
            logger.warning(f"Failed to get market context: {e}")
            market_context = {}
        
        # Generate strategy without optimization
        strategy = strategy_proposer.generate_from_template(
            template=template,
            symbols=symbols,
            market_statistics=market_statistics,
            indicator_distributions=indicator_distributions,
            market_context=market_context,
            optimize_parameters=False
        )
        
        logger.info(f"   ✓ Strategy generated: {strategy.name}")
        logger.info(f"   Entry conditions: {strategy.rules['entry_conditions']}")
        logger.info(f"   Exit conditions: {strategy.rules['exit_conditions']}")
        
        # 4. Run parameter optimization
        logger.info("\n[4/5] Running parameter optimization...")
        
        # Calculate optimization date range (last 365 days)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        
        logger.info(f"   Optimization period: {start_date.date()} to {end_date.date()}")
        
        optimization_result = optimizer.optimize(
            template=template,
            strategy=strategy,
            start=start_date,
            end=end_date,
            min_out_of_sample_sharpe=0.3
        )
        
        # 5. Display results
        logger.info("\n[5/5] Optimization Results:")
        logger.info("=" * 80)
        
        if optimization_result.get('optimization_failed', False):
            logger.warning("   ⚠ Optimization failed - using default parameters")
            logger.info(f"   Reason: Out-of-sample Sharpe ({optimization_result['out_of_sample_sharpe']:.2f}) below minimum (0.3)")
        else:
            logger.info(f"   ✓ Optimization succeeded!")
            logger.info(f"   Best parameters: {optimization_result['best_params']}")
            logger.info(f"   In-sample Sharpe: {optimization_result['in_sample_sharpe']:.2f}")
            logger.info(f"   Out-of-sample Sharpe: {optimization_result['out_of_sample_sharpe']:.2f}")
            logger.info(f"   Sharpe improvement: {optimization_result['sharpe_improvement']:.1f}%")
            logger.info(f"   Tested combinations: {optimization_result['tested_combinations']}")
        
        # Test with optimization enabled in generate_from_template
        logger.info("\n[BONUS] Testing optimization in generate_from_template...")
        
        optimized_strategy = strategy_proposer.generate_from_template(
            template=template,
            symbols=symbols,
            market_statistics=market_statistics,
            indicator_distributions=indicator_distributions,
            market_context=market_context,
            optimize_parameters=True,
            optimization_start=start_date,
            optimization_end=end_date
        )
        
        logger.info(f"   ✓ Optimized strategy generated: {optimized_strategy.name}")
        
        if hasattr(optimized_strategy, 'metadata') and optimized_strategy.metadata:
            opt_params = optimized_strategy.metadata.get('optimized_parameters', {})
            if opt_params:
                logger.info(f"   Optimized parameters applied: {opt_params}")
            else:
                logger.info("   No optimized parameters (using defaults)")
        
        logger.info("\n" + "=" * 80)
        logger.info("PARAMETER OPTIMIZATION TEST COMPLETE")
        logger.info("=" * 80)
        
        return True
    
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_parameter_optimization()
    sys.exit(0 if success else 1)
