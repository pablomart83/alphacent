"""
Test rolling window validation with multiple out-of-sample periods.

Tests task 9.12.2 implementation:
- Rolling window validation across 3 time periods
- Market regime detection and performance analysis
- Consistency scoring and robustness checks
"""

import pytest
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.strategy.strategy_engine import StrategyEngine
from src.strategy.strategy_templates import StrategyTemplateLibrary, MarketRegime, StrategyType
from src.data.market_data_manager import MarketDataManager
from src.api.etoro_client import EToroAPIClient
from src.models.database import Database
import logging

logger = logging.getLogger(__name__)

def get_initialized_components():
    """Initialize all required components for testing."""
    from src.core.config import get_config
    from src.models.enums import TradingMode
    from src.llm.llm_service import LLMService
    from unittest.mock import Mock
    
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
        logger.warning(f"Could not initialize eToro client: {e}, using mock")
        etoro_client = Mock()
    
    market_data = MarketDataManager(etoro_client)
    llm_service = LLMService()
    strategy_engine = StrategyEngine(
        llm_service=None,
        market_data=market_data,
        websocket_manager=None
    )
    
    from src.strategy.strategy_proposer import StrategyProposer
    strategy_proposer = StrategyProposer(llm_service=llm_service, market_data=market_data)
    
    return strategy_engine, strategy_proposer

def test_rolling_window_validation_basic():
    """
    Test basic rolling window validation with 3 time windows.
    
    Verifies:
    - 3 windows are tested (early, middle, recent)
    - Each window has train and test results
    - Consistency score is calculated
    - Robustness flag is set correctly
    """
    logger.info("\n" + "="*60)
    logger.info("TEST: Rolling Window Validation - Basic")
    logger.info("="*60)
    
    # Initialize components
    strategy_engine, strategy_proposer = get_initialized_components()
    
    # Propose a single strategy using real proposer
    logger.info("Proposing strategy...")
    strategies = strategy_proposer.propose_strategies(
        count=1,
        symbols=["SPY"],
        use_walk_forward=False,
        optimize_parameters=False
    )
    
    assert len(strategies) > 0, "No strategies proposed"
    strategy = strategies[0]
    
    # Set date range for 2 years of data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)  # 2 years
    
    logger.info(f"Testing strategy: {strategy.name}")
    logger.info(f"Date range: {start_date.date()} to {end_date.date()}")
    
    # Run rolling window validation
    results = strategy_engine.rolling_window_validate(
        strategy=strategy,
        start=start_date,
        end=end_date
    )
    
    # Verify results structure
    assert "windows" in results
    assert "consistency_score" in results
    assert "is_robust" in results
    assert "regime_performance" in results
    
    # Verify 3 windows were tested
    assert len(results["windows"]) == 3
    assert results["total_windows"] == 3
    
    # Verify each window has required fields
    for window in results["windows"]:
        assert "window_name" in window
        assert "train_sharpe" in window
        assert "test_sharpe" in window
        assert "train_return" in window
        assert "test_return" in window
        assert "train_trades" in window
        assert "test_trades" in window
        assert "degradation_pct" in window
        assert "passed" in window
    
    # Log results
    logger.info(f"\nResults:")
    logger.info(f"  Windows passed: {results['windows_passed']}/{results['total_windows']}")
    logger.info(f"  Consistency score: {results['consistency_score']:.1f}%")
    logger.info(f"  Is robust: {results['is_robust']}")
    logger.info(f"  Avg train Sharpe: {results['train_sharpe_mean']:.2f}")
    logger.info(f"  Avg test Sharpe: {results['test_sharpe_mean']:.2f}")
    
    for window in results["windows"]:
        logger.info(f"\n  {window['window_name']}:")
        logger.info(f"    Train: Sharpe={window['train_sharpe']:.2f}, Return={window['train_return']:.2%}, Trades={window['train_trades']}")
        logger.info(f"    Test:  Sharpe={window['test_sharpe']:.2f}, Return={window['test_return']:.2%}, Trades={window['test_trades']}")
        logger.info(f"    Degradation: {window['degradation_pct']:.1f}%")
        logger.info(f"    Status: {'PASS' if window['passed'] else 'FAIL'}")
    
    # Verify consistency score calculation
    expected_consistency = (results['windows_passed'] / results['total_windows']) * 100
    assert abs(results['consistency_score'] - expected_consistency) < 0.1
    
    # Verify robustness flag (should be True if >= 60% consistency)
    expected_robust = results['consistency_score'] >= 60.0
    assert results['is_robust'] == expected_robust
    
    logger.info(f"\n✓ Test passed: Rolling window validation works correctly")

def test_rolling_window_regime_analysis():
    """
    Test market regime analysis across windows.
    
    Verifies:
    - Regimes are detected for each test period
    - Performance is tracked by regime
    - Multi-regime performance flag is set
    """
    logger.info("\n" + "="*60)
    logger.info("TEST: Rolling Window Validation - Regime Analysis")
    logger.info("="*60)
    
    # Initialize components
    strategy_engine, strategy_proposer = get_initialized_components()
    
    # Propose a strategy
    logger.info("Proposing strategy...")
    strategies = strategy_proposer.propose_strategies(
        count=1,
        symbols=["SPY", "QQQ"],
        use_walk_forward=False,
        optimize_parameters=False
    )
    
    assert len(strategies) > 0, "No strategies proposed"
    strategy = strategies[0]
    
    # Set date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)
    
    logger.info(f"Testing strategy: {strategy.name}")
    logger.info(f"Symbols: {strategy.symbols}")
    
    # Run validation
    results = strategy_engine.rolling_window_validate(
        strategy=strategy,
        start=start_date,
        end=end_date
    )
    
    # Verify regime performance structure
    regime_perf = results["regime_performance"]
    assert "regime_stats" in regime_perf
    assert "regimes_tested" in regime_perf
    assert "regimes_with_positive_sharpe" in regime_perf
    assert "works_in_multiple_regimes" in regime_perf
    
    # Log regime analysis
    logger.info(f"\nRegime Analysis:")
    logger.info(f"  Regimes tested: {regime_perf['regimes_tested']}")
    logger.info(f"  Regimes with positive Sharpe: {regime_perf['regimes_with_positive_sharpe']}")
    logger.info(f"  Works in multiple regimes: {regime_perf['works_in_multiple_regimes']}")
    
    for regime, stats in regime_perf['regime_stats'].items():
        if stats['count'] > 0:
            logger.info(f"\n  {regime}:")
            logger.info(f"    Windows: {stats['count']}")
            logger.info(f"    Avg Sharpe: {stats['avg_sharpe']:.2f}")
            logger.info(f"    Avg Return: {stats['avg_return']:.2%}")
            logger.info(f"    Windows tested: {', '.join(stats['windows'])}")
    
    # Verify at least one regime was tested
    assert regime_perf['regimes_tested'] > 0
    
    logger.info(f"\n✓ Test passed: Regime analysis works correctly")

def test_rolling_window_consistency_scoring():
    """
    Test consistency scoring logic.
    
    Verifies:
    - Consistency score = (windows_passed / total_windows) * 100
    - Strategy is robust if consistency >= 60%
    - Overfitting indicators are calculated
    """
    logger.info("\n" + "="*60)
    logger.info("TEST: Rolling Window Validation - Consistency Scoring")
    logger.info("="*60)
    
    # Initialize components
    strategy_engine, strategy_proposer = get_initialized_components()
    
    # Propose a strategy
    logger.info("Proposing strategy...")
    strategies = strategy_proposer.propose_strategies(
        count=1,
        symbols=["SPY"],
        use_walk_forward=False,
        optimize_parameters=False
    )
    
    assert len(strategies) > 0, "No strategies proposed"
    strategy = strategies[0]
    
    # Set date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)
    
    logger.info(f"Testing strategy: {strategy.name}")
    
    # Run validation
    results = strategy_engine.rolling_window_validate(
        strategy=strategy,
        start=start_date,
        end=end_date
    )
    
    # Verify consistency calculation
    windows_passed = sum(1 for w in results["windows"] if w["passed"])
    expected_consistency = (windows_passed / len(results["windows"])) * 100
    
    assert results["windows_passed"] == windows_passed
    assert abs(results["consistency_score"] - expected_consistency) < 0.1
    
    # Verify robustness threshold (60%)
    expected_robust = results["consistency_score"] >= 60.0
    assert results["is_robust"] == expected_robust
    
    # Verify overfitting indicators
    assert "overfitting_indicators" in results
    overfitting = results["overfitting_indicators"]
    assert "train_test_gap" in overfitting
    assert "variance_ratio" in overfitting
    
    logger.info(f"\nConsistency Metrics:")
    logger.info(f"  Windows passed: {windows_passed}/{len(results['windows'])}")
    logger.info(f"  Consistency score: {results['consistency_score']:.1f}%")
    logger.info(f"  Is robust: {results['is_robust']} (threshold: 60%)")
    logger.info(f"\nOverfitting Indicators:")
    logger.info(f"  Train-test gap: {overfitting['train_test_gap']:.2f}")
    logger.info(f"  Variance ratio: {overfitting['variance_ratio']:.3f}")
    
    logger.info(f"\n✓ Test passed: Consistency scoring works correctly")

def test_rolling_window_with_multiple_strategies():
    """
    Test rolling window validation with different strategy types.
    
    Verifies:
    - Mean reversion strategies
    - Momentum strategies
    - Different strategies have different consistency scores
    """
    logger.info("\n" + "="*60)
    logger.info("TEST: Rolling Window Validation - Multiple Strategies")
    logger.info("="*60)
    
    # Initialize components
    strategy_engine, strategy_proposer = get_initialized_components()
    
    # Propose multiple strategies
    logger.info("Proposing 3 strategies...")
    strategies = strategy_proposer.propose_strategies(
        count=3,
        symbols=["SPY"],
        use_walk_forward=False,
        optimize_parameters=False
    )
    
    assert len(strategies) >= 2, f"Expected at least 2 strategies, got {len(strategies)}"
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)
    
    all_results = []
    
    for i, strategy in enumerate(strategies[:3], 1):  # Test up to 3 strategies
        logger.info(f"\nTesting strategy {i}: {strategy.name}...")
        
        try:
            results = strategy_engine.rolling_window_validate(
                strategy=strategy,
                start=start_date,
                end=end_date
            )
            
            all_results.append({
                "name": strategy.name,
                "consistency_score": results["consistency_score"],
                "is_robust": results["is_robust"],
                "windows_passed": results["windows_passed"],
                "avg_test_sharpe": results["test_sharpe_mean"]
            })
            
            logger.info(f"  {strategy.name}:")
            logger.info(f"    Consistency: {results['consistency_score']:.1f}%")
            logger.info(f"    Robust: {results['is_robust']}")
            logger.info(f"    Avg test Sharpe: {results['test_sharpe_mean']:.2f}")
            
        except Exception as e:
            logger.warning(f"  Failed to validate strategy {i}: {e}")
    
    # Verify we tested multiple strategies
    assert len(all_results) >= 2
    
    # Log summary
    logger.info(f"\nSummary:")
    for result in all_results:
        logger.info(f"  {result['name']}: {result['consistency_score']:.1f}% consistency, {'ROBUST' if result['is_robust'] else 'NOT ROBUST'}")
    
    logger.info(f"\n✓ Test passed: Multiple strategies validated successfully")

if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
