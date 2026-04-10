"""Test walk-forward validation implementation."""

import logging
from datetime import datetime, timedelta
from unittest.mock import Mock

from src.api.etoro_client import EToroAPIClient
from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.models.dataclasses import Strategy, RiskConfig, PerformanceMetrics
from src.models.enums import StrategyStatus, TradingMode
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


def test_walk_forward_validate():
    """Test walk-forward validation on a simple strategy."""
    logger.info("=" * 80)
    logger.info("TEST 1: Walk-Forward Validation on Single Strategy")
    logger.info("=" * 80)
    
    # Initialize components
    etoro_client = get_etoro_client()
    market_data = MarketDataManager(etoro_client)
    llm_service = LLMService()
    strategy_engine = StrategyEngine(llm_service, market_data)
    
    # Create a simple RSI mean reversion strategy
    strategy = Strategy(
        id="test-wf-strategy",
        name="RSI Mean Reversion Test",
        description="Simple RSI strategy for walk-forward testing",
        status=StrategyStatus.PROPOSED,
        rules={
            "indicators": ["RSI"],
            "entry_conditions": ["RSI_14 < 30"],
            "exit_conditions": ["RSI_14 > 70"]
        },
        symbols=["SPY"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    # Run walk-forward validation
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    try:
        wf_results = strategy_engine.walk_forward_validate(
            strategy=strategy,
            start=start_date,
            end=end_date,
            train_days=60,
            test_days=30
        )
        
        logger.info("\n" + "=" * 80)
        logger.info("WALK-FORWARD VALIDATION RESULTS")
        logger.info("=" * 80)
        logger.info(f"Strategy: {strategy.name}")
        logger.info(f"\nTrain Period: {wf_results['train_period'][0].date()} to {wf_results['train_period'][1].date()}")
        logger.info(f"  Sharpe Ratio: {wf_results['train_sharpe']:.2f}")
        logger.info(f"  Total Return: {wf_results['train_return']:.2%}")
        logger.info(f"  Total Trades: {wf_results['train_trades']}")
        
        logger.info(f"\nTest Period: {wf_results['test_period'][0].date()} to {wf_results['test_period'][1].date()}")
        logger.info(f"  Sharpe Ratio: {wf_results['test_sharpe']:.2f}")
        logger.info(f"  Total Return: {wf_results['test_return']:.2%}")
        logger.info(f"  Total Trades: {wf_results['test_trades']}")
        
        logger.info(f"\nPerformance Degradation: {wf_results['performance_degradation']:.1f}%")
        logger.info(f"Is Overfitted: {wf_results['is_overfitted']}")
        
        # Check validation criteria
        passed = (
            wf_results['train_sharpe'] > 0.5 and
            wf_results['test_sharpe'] > 0.5 and
            not wf_results['is_overfitted']
        )
        
        logger.info(f"\n{'✓' if passed else '✗'} Validation Criteria: {'PASSED' if passed else 'FAILED'}")
        logger.info(f"  Train Sharpe > 0.5: {'✓' if wf_results['train_sharpe'] > 0.5 else '✗'}")
        logger.info(f"  Test Sharpe > 0.5: {'✓' if wf_results['test_sharpe'] > 0.5 else '✗'}")
        logger.info(f"  Not Overfitted: {'✓' if not wf_results['is_overfitted'] else '✗'}")
        
        return wf_results
        
    except Exception as e:
        logger.error(f"Walk-forward validation failed: {e}", exc_info=True)
        return None


def test_propose_strategies_with_walk_forward():
    """Test strategy proposal with walk-forward validation."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Strategy Proposal with Walk-Forward Validation")
    logger.info("=" * 80)
    
    # Initialize components
    etoro_client = get_etoro_client()
    market_data = MarketDataManager(etoro_client)
    llm_service = LLMService()
    strategy_engine = StrategyEngine(llm_service, market_data)
    strategy_proposer = StrategyProposer(llm_service, market_data)
    
    # Propose strategies with walk-forward validation
    try:
        strategies = strategy_proposer.propose_strategies(
            count=3,
            symbols=["SPY", "QQQ"],
            market_regime=MarketRegime.RANGING,
            use_walk_forward=True,
            strategy_engine=strategy_engine
        )
        
        logger.info("\n" + "=" * 80)
        logger.info("PROPOSED STRATEGIES WITH WALK-FORWARD VALIDATION")
        logger.info("=" * 80)
        logger.info(f"Total Strategies Proposed: {len(strategies)}")
        
        for i, strategy in enumerate(strategies, 1):
            logger.info(f"\n{i}. {strategy.name}")
            logger.info(f"   Description: {strategy.description}")
            logger.info(f"   Symbols: {strategy.symbols}")
            logger.info(f"   Indicators: {strategy.rules.get('indicators', [])}")
            
            # Check if walk-forward results are stored in metadata
            if hasattr(strategy, 'metadata') and strategy.metadata:
                if 'walk_forward_results' in strategy.metadata:
                    wf = strategy.metadata['walk_forward_results']
                    logger.info(f"   Train Sharpe: {wf.get('train_sharpe', 'N/A'):.2f}")
                    logger.info(f"   Test Sharpe: {wf.get('test_sharpe', 'N/A'):.2f}")
        
        return strategies
        
    except Exception as e:
        logger.error(f"Strategy proposal with walk-forward validation failed: {e}", exc_info=True)
        return []


def test_diversity_selection():
    """Test diverse strategy selection."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Diverse Strategy Selection")
    logger.info("=" * 80)
    
    # Initialize components
    etoro_client = get_etoro_client()
    market_data = MarketDataManager(etoro_client)
    llm_service = LLMService()
    strategy_engine = StrategyEngine(llm_service, market_data)
    strategy_proposer = StrategyProposer(llm_service, market_data)
    
    # Generate more strategies than needed
    try:
        # First, generate strategies without walk-forward (faster for testing)
        all_strategies = strategy_proposer.propose_strategies(
            count=6,
            symbols=["SPY"],
            market_regime=MarketRegime.RANGING,
            use_walk_forward=False
        )
        
        logger.info(f"\nGenerated {len(all_strategies)} strategies")
        
        # Now run walk-forward validation on all
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        
        validated_strategies = []
        for strategy in all_strategies:
            try:
                wf_results = strategy_engine.walk_forward_validate(
                    strategy=strategy,
                    start=start_date,
                    end=end_date,
                    train_days=60,
                    test_days=30
                )
                
                # Only keep strategies that pass validation
                if wf_results['train_sharpe'] > 0.5 and wf_results['test_sharpe'] > 0.5:
                    validated_strategies.append((strategy, wf_results))
                    logger.info(f"✓ {strategy.name}: train={wf_results['train_sharpe']:.2f}, test={wf_results['test_sharpe']:.2f}")
                else:
                    logger.info(f"✗ {strategy.name}: train={wf_results['train_sharpe']:.2f}, test={wf_results['test_sharpe']:.2f}")
            
            except Exception as e:
                logger.warning(f"Validation failed for {strategy.name}: {e}")
        
        logger.info(f"\n{len(validated_strategies)} strategies passed validation")
        
        # Select diverse strategies
        if len(validated_strategies) > 3:
            diverse_strategies = strategy_proposer.select_diverse_strategies(
                strategies=validated_strategies,
                count=3,
                max_correlation=0.7
            )
            
            logger.info("\n" + "=" * 80)
            logger.info("SELECTED DIVERSE STRATEGIES")
            logger.info("=" * 80)
            
            for i, strategy in enumerate(diverse_strategies, 1):
                logger.info(f"\n{i}. {strategy.name}")
                logger.info(f"   Type: {strategy.metadata.get('strategy_type', 'unknown')}")
                logger.info(f"   Indicators: {strategy.rules.get('indicators', [])}")
            
            return diverse_strategies
        else:
            logger.info("Not enough validated strategies for diversity selection")
            return [s[0] for s in validated_strategies]
        
    except Exception as e:
        logger.error(f"Diversity selection test failed: {e}", exc_info=True)
        return []


if __name__ == "__main__":
    logger.info("Starting Walk-Forward Validation Tests")
    logger.info("=" * 80)
    
    # Test 1: Basic walk-forward validation
    wf_results = test_walk_forward_validate()
    
    # Test 2: Strategy proposal with walk-forward validation
    if wf_results:
        strategies = test_propose_strategies_with_walk_forward()
    
    # Test 3: Diversity selection
    # diverse_strategies = test_diversity_selection()
    
    logger.info("\n" + "=" * 80)
    logger.info("ALL TESTS COMPLETED")
    logger.info("=" * 80)
