"""Simple test for walk-forward validation using template strategies."""

import logging
from datetime import datetime, timedelta
from unittest.mock import Mock

from src.api.etoro_client import EToroAPIClient
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
    """Get eToro client (real or mock)."""
    try:
        from src.api.etoro_client import EToroAPIClient
        etoro_client = EToroAPIClient(mode=TradingMode.DEMO)
        return etoro_client
    except Exception as e:
        logger.warning(f"Failed to create real eToro client: {e}, using mock")
        return Mock(spec=EToroAPIClient)


def test_walk_forward_with_templates():
    """Test walk-forward validation with template-based strategies."""
    logger.info("=" * 80)
    logger.info("TEST: Walk-Forward Validation with Template Strategies")
    logger.info("=" * 80)
    
    # Initialize components
    etoro_client = get_etoro_client()
    market_data = MarketDataManager(etoro_client)
    llm_service = LLMService()
    strategy_engine = StrategyEngine(llm_service, market_data)
    strategy_proposer = StrategyProposer(llm_service, market_data)
    
    # Generate template-based strategies (no LLM, guaranteed to work)
    logger.info("\n1. Generating template-based strategies...")
    strategies = strategy_proposer.propose_strategies(
        count=3,
        symbols=["SPY"],
        market_regime=MarketRegime.RANGING,
        use_walk_forward=False  # First generate without walk-forward
    )
    
    logger.info(f"Generated {len(strategies)} strategies")
    for i, strategy in enumerate(strategies, 1):
        logger.info(f"  {i}. {strategy.name}")
        logger.info(f"     Indicators: {strategy.rules.get('indicators', [])}")
        logger.info(f"     Entry: {strategy.rules.get('entry_conditions', [])}")
        logger.info(f"     Exit: {strategy.rules.get('exit_conditions', [])}")
    
    # Run walk-forward validation on each strategy
    logger.info("\n2. Running walk-forward validation...")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    validated_count = 0
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
            
            logger.info(f"Train Sharpe: {train_sharpe:.2f}")
            logger.info(f"Test Sharpe: {test_sharpe:.2f}")
            logger.info(f"Degradation: {degradation:.1f}%")
            logger.info(f"Overfitted: {is_overfitted}")
            
            # Check validation criteria
            passed = train_sharpe > 0.5 and test_sharpe > 0.5 and not is_overfitted
            if passed:
                validated_count += 1
                logger.info("✓ PASSED validation criteria")
            else:
                logger.info("✗ FAILED validation criteria")
        
        except Exception as e:
            logger.error(f"Walk-forward validation failed: {e}")
    
    logger.info("\n" + "=" * 80)
    logger.info(f"RESULTS: {validated_count}/{len(strategies)} strategies passed validation")
    logger.info("=" * 80)
    
    return validated_count > 0


def test_propose_with_walk_forward():
    """Test integrated proposal with walk-forward validation."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: Integrated Proposal with Walk-Forward Validation")
    logger.info("=" * 80)
    
    # Initialize components
    etoro_client = get_etoro_client()
    market_data = MarketDataManager(etoro_client)
    llm_service = LLMService()
    strategy_engine = StrategyEngine(llm_service, market_data)
    strategy_proposer = StrategyProposer(llm_service, market_data)
    
    # Propose strategies with walk-forward validation enabled
    logger.info("\nProposing strategies with walk-forward validation...")
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
        logger.info(f"   Indicators: {strategy.rules.get('indicators', [])}")
        logger.info(f"   Type: {strategy.metadata.get('strategy_type', 'unknown')}")
    
    return len(strategies) > 0


if __name__ == "__main__":
    logger.info("Starting Walk-Forward Validation Tests (Template-Based)")
    logger.info("=" * 80)
    
    # Test 1: Walk-forward validation on template strategies
    success1 = test_walk_forward_with_templates()
    
    # Test 2: Integrated proposal with walk-forward
    if success1:
        success2 = test_propose_with_walk_forward()
    
    logger.info("\n" + "=" * 80)
    logger.info("ALL TESTS COMPLETED")
    logger.info("=" * 80)
