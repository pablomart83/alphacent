"""
Test adaptive walk-forward analysis with parameter optimization.
"""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.strategy.strategy_engine import StrategyEngine
from src.strategy.strategy_proposer import StrategyProposer
from src.strategy.parameter_optimizer import ParameterOptimizer
from src.strategy.adaptive_walk_forward import AdaptiveWalkForwardAnalyzer
from src.strategy.market_analyzer import MarketStatisticsAnalyzer
from src.strategy.strategy_templates import MarketRegime
from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.models.dataclasses import Strategy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_adaptive_walk_forward_basic():
    """Test basic adaptive walk-forward analysis."""
    logger.info("=" * 80)
    logger.info("TEST: Basic Adaptive Walk-Forward Analysis")
    logger.info("=" * 80)
    
    # Initialize services (following test_full_lifecycle_50_strategies.py pattern)
    from src.api.etoro_client import EToroAPIClient
    from src.core.config import get_config
    from src.models.enums import TradingMode
    
    try:
        config_manager = get_config()
        credentials = config_manager.load_credentials(TradingMode.DEMO)
        etoro_client = EToroAPIClient(
            public_key=credentials['public_key'],
            user_key=credentials['user_key'],
            mode=TradingMode.DEMO
        )
        logger.info("✓ eToro client initialized")
    except Exception as e:
        logger.warning(f"Could not initialize eToro client: {e}")
        logger.info("Using mock eToro client for testing")
        from unittest.mock import Mock
        etoro_client = Mock()
    
    market_data = MarketDataManager(etoro_client)
    llm_service = LLMService()
    strategy_engine = StrategyEngine(
        llm_service=llm_service,
        market_data=market_data,
        websocket_manager=None
    )
    market_analyzer = MarketStatisticsAnalyzer(market_data)
    parameter_optimizer = ParameterOptimizer(strategy_engine)
    
    # Initialize adaptive walk-forward analyzer
    awf_analyzer = AdaptiveWalkForwardAnalyzer(
        strategy_engine=strategy_engine,
        parameter_optimizer=parameter_optimizer,
        market_analyzer=market_analyzer
    )
    
    # Generate a simple strategy using templates
    strategy_proposer = StrategyProposer(llm_service, market_data)
    
    strategies = strategy_proposer.propose_strategies(
        count=1,
        symbols=["SPY"],
        market_regime=MarketRegime.RANGING,
        use_walk_forward=False,
        optimize_parameters=False
    )
    
    if not strategies:
        logger.error("Failed to generate strategy")
        return False
    
    strategy = strategies[0]
    logger.info(f"Testing strategy: {strategy.name}")
    
    # Get the template used
    from src.strategy.strategy_templates import StrategyTemplateLibrary
    template_lib = StrategyTemplateLibrary()
    templates = template_lib.get_templates_for_regime(MarketRegime.RANGING)
    template = templates[0] if templates else None
    
    if not template:
        logger.error("No template found")
        return False
    
    # Run adaptive walk-forward analysis
    # Use 2 years of data with rolling windows
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)  # 2 years
    
    logger.info(f"\nRunning adaptive walk-forward analysis...")
    logger.info(f"Period: {start_date.date()} to {end_date.date()}")
    
    try:
        results = awf_analyzer.analyze(
            template=template,
            strategy=strategy,
            start=start_date,
            end=end_date,
            window_size_days=240,  # 8 months per window
            step_size_days=60,  # 2 months step
            min_test_sharpe=0.3,
            max_param_variance=0.5,
            max_degradation_slope=-0.1
        )
        
        # Verify results
        logger.info("\n" + "=" * 80)
        logger.info("VERIFICATION")
        logger.info("=" * 80)
        
        assert results.total_windows > 0, "Should have at least 1 window"
        logger.info(f"✓ Generated {results.total_windows} windows")
        
        assert len(results.window_results) == results.total_windows, "Window count mismatch"
        logger.info(f"✓ All windows completed")
        
        # Check parameter stability
        logger.info(f"✓ Parameter stability score: {results.parameter_stability_score:.2f}")
        logger.info(f"  Parameter variance: {results.parameter_variance}")
        
        # Check performance trend
        logger.info(f"✓ Performance trend: {results.performance_trend}")
        logger.info(f"  Trend slope: {results.trend_slope:.3f}")
        
        # Check regime analysis
        logger.info(f"✓ Regime consistency: {results.regime_consistency:.1%}")
        logger.info(f"  Regime-specific performance:")
        for regime, sharpe in results.regime_specific_performance.items():
            logger.info(f"    {regime.value}: {sharpe:.2f}")
        
        # Check validation flags
        logger.info(f"✓ Is stable: {results.is_stable}")
        logger.info(f"✓ Is degrading: {results.is_degrading}")
        logger.info(f"✓ Is regime adaptive: {results.is_regime_adaptive}")
        logger.info(f"✓ Passes validation: {results.passes_validation}")
        
        # Verify window details
        logger.info("\nWindow Details:")
        for window in results.window_results:
            logger.info(f"  Window {window.window_id}:")
            logger.info(f"    Train: {window.train_start.date()} to {window.train_end.date()}")
            logger.info(f"    Test: {window.test_start.date()} to {window.test_end.date()}")
            logger.info(f"    Train Sharpe: {window.train_sharpe:.2f}, Test Sharpe: {window.test_sharpe:.2f}")
            logger.info(f"    Degradation: {window.performance_degradation:.1f}%")
            logger.info(f"    Train Regime: {window.train_regime.value}, Test Regime: {window.test_regime.value}")
            logger.info(f"    Optimized Params: {window.optimized_params}")
        
        logger.info("\n✓ Adaptive walk-forward analysis completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Adaptive walk-forward analysis failed: {e}", exc_info=True)
        return False


def test_parameter_stability_detection():
    """Test that parameter instability is detected."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: Parameter Stability Detection")
    logger.info("=" * 80)
    
    # Initialize services
    from src.api.etoro_client import EToroAPIClient
    from src.core.config import get_config
    from src.models.enums import TradingMode
    
    try:
        config_manager = get_config()
        credentials = config_manager.load_credentials(TradingMode.DEMO)
        etoro_client = EToroAPIClient(
            public_key=credentials['public_key'],
            user_key=credentials['user_key'],
            mode=TradingMode.DEMO
        )
    except Exception as e:
        logger.warning(f"Could not initialize eToro client: {e}")
        from unittest.mock import Mock
        etoro_client = Mock()
    
    market_data = MarketDataManager(etoro_client)
    llm_service = LLMService()
    strategy_engine = StrategyEngine(
        llm_service=llm_service,
        market_data=market_data,
        websocket_manager=None
    )
    market_analyzer = MarketStatisticsAnalyzer(market_data)
    parameter_optimizer = ParameterOptimizer(strategy_engine)
    
    awf_analyzer = AdaptiveWalkForwardAnalyzer(
        strategy_engine=strategy_engine,
        parameter_optimizer=parameter_optimizer,
        market_analyzer=market_analyzer
    )
    
    # Generate strategy
    strategy_proposer = StrategyProposer(llm_service, market_data)
    strategies = strategy_proposer.propose_strategies(
        count=1,
        symbols=["SPY"],
        market_regime=MarketRegime.RANGING,
        use_walk_forward=False,
        optimize_parameters=False
    )
    
    if not strategies:
        logger.error("Failed to generate strategy")
        return False
    
    strategy = strategies[0]
    
    # Get template
    from src.strategy.strategy_templates import StrategyTemplateLibrary
    template_lib = StrategyTemplateLibrary()
    templates = template_lib.get_templates_for_regime(MarketRegime.RANGING)
    template = templates[0] if templates else None
    
    if not template:
        logger.error("No template found")
        return False
    
    # Run with stricter parameter variance threshold
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)
    
    try:
        results = awf_analyzer.analyze(
            template=template,
            strategy=strategy,
            start=start_date,
            end=end_date,
            window_size_days=240,
            step_size_days=60,
            min_test_sharpe=0.3,
            max_param_variance=0.2,  # Stricter threshold
            max_degradation_slope=-0.1
        )
        
        logger.info(f"Parameter stability score: {results.parameter_stability_score:.2f}")
        logger.info(f"Is stable (max variance 0.2): {results.is_stable}")
        
        # If parameters vary significantly, should be marked as unstable
        if results.parameter_variance:
            max_variance = max(results.parameter_variance.values())
            logger.info(f"Max parameter variance: {max_variance:.2f}")
            
            if max_variance > 0.2:
                assert not results.is_stable, "Should be marked as unstable with high variance"
                logger.info("✓ High parameter variance correctly detected")
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return False


def test_degradation_detection():
    """Test that performance degradation is detected."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: Performance Degradation Detection")
    logger.info("=" * 80)
    
    # Initialize services
    from src.api.etoro_client import EToroAPIClient
    from src.core.config import get_config
    from src.models.enums import TradingMode
    
    try:
        config_manager = get_config()
        credentials = config_manager.load_credentials(TradingMode.DEMO)
        etoro_client = EToroAPIClient(
            public_key=credentials['public_key'],
            user_key=credentials['user_key'],
            mode=TradingMode.DEMO
        )
    except Exception as e:
        logger.warning(f"Could not initialize eToro client: {e}")
        from unittest.mock import Mock
        etoro_client = Mock()
    
    market_data = MarketDataManager(etoro_client)
    llm_service = LLMService()
    strategy_engine = StrategyEngine(
        llm_service=llm_service,
        market_data=market_data,
        websocket_manager=None
    )
    market_analyzer = MarketStatisticsAnalyzer(market_data)
    parameter_optimizer = ParameterOptimizer(strategy_engine)
    
    awf_analyzer = AdaptiveWalkForwardAnalyzer(
        strategy_engine=strategy_engine,
        parameter_optimizer=parameter_optimizer,
        market_analyzer=market_analyzer
    )
    
    # Generate strategy
    strategy_proposer = StrategyProposer(llm_service, market_data)
    strategies = strategy_proposer.propose_strategies(
        count=1,
        symbols=["SPY"],
        market_regime=MarketRegime.TRENDING_UP,  # Try momentum strategy
        use_walk_forward=False,
        optimize_parameters=False
    )
    
    if not strategies:
        logger.error("Failed to generate strategy")
        return False
    
    strategy = strategies[0]
    
    # Get template
    from src.strategy.strategy_templates import StrategyTemplateLibrary
    template_lib = StrategyTemplateLibrary()
    templates = template_lib.get_templates_for_regime(MarketRegime.TRENDING_UP)
    template = templates[0] if templates else None
    
    if not template:
        logger.error("No template found")
        return False
    
    # Run analysis
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)
    
    try:
        results = awf_analyzer.analyze(
            template=template,
            strategy=strategy,
            start=start_date,
            end=end_date,
            window_size_days=240,
            step_size_days=60,
            min_test_sharpe=0.3,
            max_param_variance=0.5,
            max_degradation_slope=-0.05  # Stricter degradation threshold
        )
        
        logger.info(f"Performance trend: {results.performance_trend}")
        logger.info(f"Trend slope: {results.trend_slope:.3f}")
        logger.info(f"Is degrading: {results.is_degrading}")
        
        # Check if degradation is properly detected
        if results.trend_slope < -0.05:
            assert results.is_degrading, "Should be marked as degrading with negative slope"
            logger.info("✓ Performance degradation correctly detected")
        else:
            logger.info("✓ No significant degradation detected")
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    logger.info("\n" + "=" * 80)
    logger.info("ADAPTIVE WALK-FORWARD ANALYSIS TEST SUITE")
    logger.info("=" * 80)
    
    # Test 1: Basic adaptive walk-forward
    success1 = test_adaptive_walk_forward_basic()
    
    # Test 2: Parameter stability detection
    if success1:
        success2 = test_parameter_stability_detection()
    else:
        success2 = False
    
    # Test 3: Degradation detection
    if success2:
        success3 = test_degradation_detection()
    else:
        success3 = False
    
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Basic Adaptive Walk-Forward: {'PASS' if success1 else 'FAIL'}")
    logger.info(f"Parameter Stability Detection: {'PASS' if success2 else 'FAIL'}")
    logger.info(f"Degradation Detection: {'PASS' if success3 else 'FAIL'}")
    logger.info("=" * 80)
    
    if success1 and success2 and success3:
        logger.info("\n✓ All tests passed!")
    else:
        logger.error("\n✗ Some tests failed")
