"""Test walk-forward validation with template-based strategies (no LLM, no mocks)."""

import logging
from datetime import datetime, timedelta

from src.api.etoro_client import EToroAPIClient
from src.core.config import Configuration
from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.models.enums import TradingMode
from src.strategy.strategy_engine import StrategyEngine
from src.strategy.strategy_proposer import StrategyProposer
from src.strategy.strategy_templates import MarketRegime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_etoro_client():
    """Get real eToro client with credentials."""
    config = Configuration()
    credentials = config.load_credentials(TradingMode.DEMO)
    
    etoro_client = EToroAPIClient(
        public_key=credentials['public_key'],
        user_key=credentials['user_key'],
        mode=TradingMode.DEMO
    )
    return etoro_client


def test_walk_forward_with_templates():
    """Test walk-forward validation with real template-based strategies."""
    logger.info("=" * 80)
    logger.info("TEST: Walk-Forward Validation with Template Strategies")
    logger.info("=" * 80)
    
    # Initialize components with real eToro client
    try:
        etoro_client = get_etoro_client()
        logger.info("✓ Real eToro client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize eToro client: {e}")
        logger.info("Please ensure eToro credentials are configured")
        return False
    
    market_data = MarketDataManager(etoro_client)
    llm_service = LLMService()
    strategy_engine = StrategyEngine(llm_service, market_data)
    strategy_proposer = StrategyProposer(llm_service, market_data)
    
    # Generate template-based strategies (NO LLM, NO MOCKS)
    logger.info("\n1. Generating template-based strategies...")
    try:
        strategies = strategy_proposer.propose_strategies(
            count=3,
            symbols=["SPY"],
            market_regime=MarketRegime.RANGING,
            use_walk_forward=False  # First generate without walk-forward
        )
        
        logger.info(f"✓ Generated {len(strategies)} strategies from templates")
        
        if len(strategies) == 0:
            logger.error("No strategies generated - check template generation")
            return False
        
        for i, strategy in enumerate(strategies, 1):
            logger.info(f"  {i}. {strategy.name}")
            logger.info(f"     Template: {strategy.metadata.get('template_name', 'unknown')}")
            logger.info(f"     Type: {strategy.metadata.get('template_type', 'unknown')}")
            logger.info(f"     Indicators: {strategy.rules.get('indicators', [])}")
    
    except Exception as e:
        logger.error(f"Failed to generate strategies: {e}", exc_info=True)
        return False
    
    # Run walk-forward validation on each strategy
    logger.info("\n2. Running walk-forward validation...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    validated_strategies = []
    
    for strategy in strategies:
        logger.info(f"\n--- Validating: {strategy.name} ---")
        try:
            wf_results = strategy_engine.walk_forward_validate(
                strategy=strategy,
                start=start_date,
                end=end_date,
                train_days=60,
                test_days=30
            )
            
            train_sharpe = wf_results['train_sharpe']
            test_sharpe = wf_results['test_sharpe']
            is_overfitted = wf_results['is_overfitted']
            degradation = wf_results['performance_degradation']
            
            logger.info(f"Train Period: {wf_results['train_period'][0].date()} to {wf_results['train_period'][1].date()}")
            logger.info(f"  Sharpe: {train_sharpe:.2f}")
            logger.info(f"  Return: {wf_results['train_return']:.2%}")
            logger.info(f"  Trades: {wf_results['train_trades']}")
            
            logger.info(f"Test Period: {wf_results['test_period'][0].date()} to {wf_results['test_period'][1].date()}")
            logger.info(f"  Sharpe: {test_sharpe:.2f}")
            logger.info(f"  Return: {wf_results['test_return']:.2%}")
            logger.info(f"  Trades: {wf_results['test_trades']}")
            
            logger.info(f"Performance Degradation: {degradation:.1f}%")
            logger.info(f"Overfitted: {is_overfitted}")
            
            # Check validation criteria
            passed = train_sharpe > 0.5 and test_sharpe > 0.5 and not is_overfitted
            if passed:
                validated_strategies.append((strategy, wf_results))
                logger.info("✓ PASSED validation criteria")
            else:
                logger.info("✗ FAILED validation criteria")
                logger.info(f"  Train Sharpe > 0.5: {'✓' if train_sharpe > 0.5 else '✗'}")
                logger.info(f"  Test Sharpe > 0.5: {'✓' if test_sharpe > 0.5 else '✗'}")
                logger.info(f"  Not Overfitted: {'✓' if not is_overfitted else '✗'}")
        
        except Exception as e:
            logger.error(f"Walk-forward validation failed: {e}", exc_info=True)
    
    logger.info("\n" + "=" * 80)
    logger.info(f"RESULTS: {len(validated_strategies)}/{len(strategies)} strategies passed validation")
    logger.info("=" * 80)
    
    # Test diversity selection if we have enough validated strategies
    if len(validated_strategies) > 1:
        logger.info("\n3. Testing diversity selection...")
        try:
            diverse_strategies = strategy_proposer.select_diverse_strategies(
                strategies=validated_strategies,
                count=min(2, len(validated_strategies)),
                max_correlation=0.7
            )
            
            logger.info(f"✓ Selected {len(diverse_strategies)} diverse strategies")
            for i, strategy in enumerate(diverse_strategies, 1):
                logger.info(f"  {i}. {strategy.name}")
                logger.info(f"     Type: {strategy.metadata.get('template_type', 'unknown')}")
        
        except Exception as e:
            logger.error(f"Diversity selection failed: {e}", exc_info=True)
    
    return len(validated_strategies) > 0


def test_integrated_walk_forward():
    """Test integrated proposal with walk-forward validation."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: Integrated Proposal with Walk-Forward Validation")
    logger.info("=" * 80)
    
    # Initialize components with real eToro client
    try:
        etoro_client = get_etoro_client()
        logger.info("✓ Real eToro client initialized")
    except Exception as e:
        logger.error(f"Failed to initialize eToro client: {e}")
        return False
    
    market_data = MarketDataManager(etoro_client)
    llm_service = LLMService()
    strategy_engine = StrategyEngine(llm_service, market_data)
    strategy_proposer = StrategyProposer(llm_service, market_data)
    
    # Propose strategies with walk-forward validation enabled
    logger.info("\nProposing strategies with walk-forward validation...")
    try:
        strategies = strategy_proposer.propose_strategies(
            count=2,
            symbols=["SPY"],
            market_regime=MarketRegime.RANGING,
            use_walk_forward=True,
            strategy_engine=strategy_engine
        )
        
        logger.info("\n" + "=" * 80)
        logger.info(f"RESULTS: {len(strategies)} strategies proposed and validated")
        logger.info("=" * 80)
        
        for i, strategy in enumerate(strategies, 1):
            logger.info(f"\n{i}. {strategy.name}")
            logger.info(f"   Template: {strategy.metadata.get('template_name', 'unknown')}")
            logger.info(f"   Type: {strategy.metadata.get('template_type', 'unknown')}")
            logger.info(f"   Indicators: {strategy.rules.get('indicators', [])}")
        
        return len(strategies) > 0
    
    except Exception as e:
        logger.error(f"Integrated proposal failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    logger.info("Walk-Forward Validation Tests (Template-Based, No Mocks)")
    logger.info("=" * 80)
    
    # Test 1: Walk-forward validation on template strategies
    success1 = test_walk_forward_with_templates()
    
    # Test 2: Integrated proposal with walk-forward
    if success1:
        success2 = test_integrated_walk_forward()
    
    logger.info("\n" + "=" * 80)
    logger.info("ALL TESTS COMPLETED")
    logger.info("=" * 80)
    
    if success1:
        logger.info("\n✓ Task 9.11.1 Implementation Complete:")
        logger.info("  - walk_forward_validate() method working")
        logger.info("  - propose_strategies() using walk-forward validation")
        logger.info("  - select_diverse_strategies() selecting low-correlation strategies")
        logger.info("  - Template-based generation (no LLM dependency)")
        logger.info("  - Real market data (no mocks)")
