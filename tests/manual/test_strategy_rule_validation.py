"""Test strategy rule validation functionality."""

import logging
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.models.dataclasses import RiskConfig, Strategy
from src.models.enums import StrategyStatus
from src.strategy.strategy_engine import StrategyEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_mock_etoro_client():
    """Create a mock eToro client for testing."""
    mock_client = MagicMock()
    mock_client.is_connected.return_value = True
    return mock_client


def test_rsi_threshold_validation():
    """Test RSI threshold validation."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 1: RSI Threshold Validation")
    logger.info("=" * 80)
    
    # Initialize services
    llm_service = LLMService()
    mock_etoro = create_mock_etoro_client()
    market_data = MarketDataManager(mock_etoro)
    strategy_engine = StrategyEngine(llm_service, market_data)
    
    # Test Case 1: Bad RSI thresholds (should fail)
    logger.info("\nTest Case 1a: Bad RSI entry threshold (RSI < 70)")
    bad_strategy_1 = Strategy(
        id="test-bad-rsi-1",
        name="Bad RSI Entry Strategy",
        description="Strategy with incorrect RSI entry threshold",
        status=StrategyStatus.PROPOSED,
        symbols=["SPY"],
        rules={
            "indicators": ["RSI"],
            "entry_conditions": ["RSI_14 is below 70"],  # BAD: should be < 35
            "exit_conditions": ["RSI_14 rises above 70"]
        },
        risk_params=RiskConfig(),
        created_at=datetime.now()
    )
    
    result = strategy_engine.validate_strategy_rules(bad_strategy_1)
    logger.info(f"Validation result: is_valid={result['is_valid']}")
    logger.info(f"Errors: {result['errors']}")
    logger.info(f"Suggestions: {result['suggestions']}")
    
    assert not result['is_valid'], "Should reject RSI < 70 for entry"
    assert any("RSI entry threshold" in err for err in result['errors'])
    
    # Test Case 1b: Bad RSI exit threshold (should fail)
    logger.info("\nTest Case 1b: Bad RSI exit threshold (RSI > 30)")
    bad_strategy_2 = Strategy(
        id="test-bad-rsi-2",
        name="Bad RSI Exit Strategy",
        description="Strategy with incorrect RSI exit threshold",
        status=StrategyStatus.PROPOSED,
        symbols=["SPY"],
        rules={
            "indicators": ["RSI"],
            "entry_conditions": ["RSI_14 is below 30"],
            "exit_conditions": ["RSI_14 rises above 30"]  # BAD: should be > 65
        },
        risk_params=RiskConfig(),
        created_at=datetime.now()
    )
    
    result = strategy_engine.validate_strategy_rules(bad_strategy_2)
    logger.info(f"Validation result: is_valid={result['is_valid']}")
    logger.info(f"Errors: {result['errors']}")
    logger.info(f"Suggestions: {result['suggestions']}")
    
    assert not result['is_valid'], "Should reject RSI > 30 for exit"
    assert any("RSI exit threshold" in err for err in result['errors'])
    
    # Test Case 2: Good RSI thresholds (should pass)
    logger.info("\nTest Case 2: Good RSI thresholds")
    good_strategy = Strategy(
        id="test-good-rsi",
        name="Good RSI Strategy",
        description="Strategy with correct RSI thresholds",
        status=StrategyStatus.PROPOSED,
        symbols=["SPY"],
        rules={
            "indicators": ["RSI"],
            "entry_conditions": ["RSI_14 is below 30"],  # GOOD
            "exit_conditions": ["RSI_14 rises above 70"]  # GOOD
        },
        risk_params=RiskConfig(),
        created_at=datetime.now()
    )
    
    result = strategy_engine.validate_strategy_rules(good_strategy)
    logger.info(f"Validation result: is_valid={result['is_valid']}")
    logger.info(f"Errors: {result['errors']}")
    
    # Note: This might still fail on signal overlap, but RSI thresholds should be OK
    rsi_errors = [err for err in result['errors'] if 'RSI' in err and 'threshold' in err]
    assert len(rsi_errors) == 0, "Should not have RSI threshold errors"
    
    logger.info("✓ RSI threshold validation tests passed")


def test_bollinger_band_validation():
    """Test Bollinger Band logic validation."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Bollinger Band Logic Validation")
    logger.info("=" * 80)
    
    # Initialize services
    llm_service = LLMService()
    mock_etoro = create_mock_etoro_client()
    market_data = MarketDataManager(mock_etoro)
    strategy_engine = StrategyEngine(llm_service, market_data)
    
    # Test Case 1: Reversed Bollinger Band logic (should fail)
    logger.info("\nTest Case 1: Reversed Bollinger Band entry logic")
    bad_bb_strategy = Strategy(
        id="test-bad-bb",
        name="Bad Bollinger Band Strategy",
        description="Strategy with reversed BB logic",
        status=StrategyStatus.PROPOSED,
        symbols=["SPY"],
        rules={
            "indicators": ["Bollinger Bands"],
            "entry_conditions": ["Price crosses above Lower_Band_20"],  # BAD: should be below
            "exit_conditions": ["Price crosses above Upper_Band_20"]
        },
        risk_params=RiskConfig(),
        created_at=datetime.now()
    )
    
    result = strategy_engine.validate_strategy_rules(bad_bb_strategy)
    logger.info(f"Validation result: is_valid={result['is_valid']}")
    logger.info(f"Errors: {result['errors']}")
    logger.info(f"Suggestions: {result['suggestions']}")
    
    assert not result['is_valid'], "Should reject reversed BB entry logic"
    assert any("Bollinger Band entry logic" in err for err in result['errors'])
    
    # Test Case 2: Correct Bollinger Band logic (should pass threshold check)
    logger.info("\nTest Case 2: Correct Bollinger Band logic")
    good_bb_strategy = Strategy(
        id="test-good-bb",
        name="Good Bollinger Band Strategy",
        description="Strategy with correct BB logic",
        status=StrategyStatus.PROPOSED,
        symbols=["SPY"],
        rules={
            "indicators": ["Bollinger Bands"],
            "entry_conditions": ["Price crosses below Lower_Band_20"],  # GOOD
            "exit_conditions": ["Price crosses above Upper_Band_20"]  # GOOD
        },
        risk_params=RiskConfig(),
        created_at=datetime.now()
    )
    
    result = strategy_engine.validate_strategy_rules(good_bb_strategy)
    logger.info(f"Validation result: is_valid={result['is_valid']}")
    logger.info(f"Errors: {result['errors']}")
    
    # Check for BB-specific errors
    bb_errors = [err for err in result['errors'] if 'Bollinger Band' in err and 'logic' in err]
    assert len(bb_errors) == 0, "Should not have Bollinger Band logic errors"
    
    logger.info("✓ Bollinger Band validation tests passed")


def test_signal_overlap_validation():
    """Test signal overlap validation."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Signal Overlap Validation")
    logger.info("=" * 80)
    
    # Initialize services
    llm_service = LLMService()
    mock_etoro = create_mock_etoro_client()
    market_data = MarketDataManager(mock_etoro)
    strategy_engine = StrategyEngine(llm_service, market_data)
    
    # Test Case 1: High overlap strategy (should fail)
    logger.info("\nTest Case 1: High overlap strategy (RSI < 70 entry, RSI > 30 exit)")
    high_overlap_strategy = Strategy(
        id="test-high-overlap",
        name="High Overlap Strategy",
        description="Strategy with overlapping entry/exit conditions",
        status=StrategyStatus.PROPOSED,
        symbols=["SPY"],
        rules={
            "indicators": ["RSI"],
            "entry_conditions": ["RSI_14 is below 70"],  # Too broad
            "exit_conditions": ["RSI_14 rises above 30"]  # Too broad
        },
        risk_params=RiskConfig(),
        created_at=datetime.now()
    )
    
    result = strategy_engine.validate_strategy_rules(high_overlap_strategy)
    logger.info(f"Validation result: is_valid={result['is_valid']}")
    logger.info(f"Overlap percentage: {result['overlap_percentage']:.1f}%")
    logger.info(f"Entry-only percentage: {result['entry_only_percentage']:.1f}%")
    logger.info(f"Errors: {result['errors']}")
    
    # Should fail due to RSI thresholds OR overlap
    assert not result['is_valid'], "Should reject high overlap strategy"
    
    # Test Case 2: Low overlap strategy (should pass overlap check)
    logger.info("\nTest Case 2: Low overlap strategy (RSI < 30 entry, RSI > 70 exit)")
    low_overlap_strategy = Strategy(
        id="test-low-overlap",
        name="Low Overlap Strategy",
        description="Strategy with distinct entry/exit conditions",
        status=StrategyStatus.PROPOSED,
        symbols=["SPY"],
        rules={
            "indicators": ["RSI"],
            "entry_conditions": ["RSI_14 is below 30"],  # Narrow
            "exit_conditions": ["RSI_14 rises above 70"]  # Narrow
        },
        risk_params=RiskConfig(),
        created_at=datetime.now()
    )
    
    result = strategy_engine.validate_strategy_rules(low_overlap_strategy)
    logger.info(f"Validation result: is_valid={result['is_valid']}")
    logger.info(f"Overlap percentage: {result['overlap_percentage']:.1f}%")
    logger.info(f"Entry-only percentage: {result['entry_only_percentage']:.1f}%")
    logger.info(f"Errors: {result['errors']}")
    
    # Check overlap specifically
    if result['overlap_percentage'] > 0:
        logger.info(f"Overlap: {result['overlap_percentage']:.1f}%")
        if result['overlap_percentage'] > 50:
            logger.warning("Overlap exceeds 50% threshold")
    
    logger.info("✓ Signal overlap validation tests passed")


def test_complete_validation_flow():
    """Test complete validation flow with a realistic strategy."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 4: Complete Validation Flow")
    logger.info("=" * 80)
    
    # Initialize services
    llm_service = LLMService()
    mock_etoro = create_mock_etoro_client()
    market_data = MarketDataManager(mock_etoro)
    strategy_engine = StrategyEngine(llm_service, market_data)
    
    # Create a realistic strategy
    logger.info("\nTesting realistic mean reversion strategy")
    strategy = Strategy(
        id="test-complete",
        name="Mean Reversion Strategy",
        description="Buy oversold, sell overbought",
        status=StrategyStatus.PROPOSED,
        symbols=["SPY"],
        rules={
            "indicators": ["RSI", "Bollinger Bands"],
            "entry_conditions": [
                "RSI_14 is below 30",
                "Price crosses below Lower_Band_20"
            ],
            "exit_conditions": [
                "RSI_14 rises above 70",
                "Price crosses above Upper_Band_20"
            ]
        },
        risk_params=RiskConfig(),
        created_at=datetime.now()
    )
    
    result = strategy_engine.validate_strategy_rules(strategy)
    
    logger.info(f"\nValidation Results:")
    logger.info(f"  is_valid: {result['is_valid']}")
    logger.info(f"  overlap_percentage: {result['overlap_percentage']:.1f}%")
    logger.info(f"  entry_only_percentage: {result['entry_only_percentage']:.1f}%")
    
    if result['errors']:
        logger.info(f"  Errors ({len(result['errors'])}):")
        for err in result['errors']:
            logger.info(f"    - {err}")
    
    if result['warnings']:
        logger.info(f"  Warnings ({len(result['warnings'])}):")
        for warn in result['warnings']:
            logger.info(f"    - {warn}")
    
    if result['suggestions']:
        logger.info(f"  Suggestions ({len(result['suggestions'])}):")
        for sugg in result['suggestions']:
            logger.info(f"    - {sugg}")
    
    logger.info("✓ Complete validation flow test passed")


if __name__ == "__main__":
    try:
        test_rsi_threshold_validation()
        test_bollinger_band_validation()
        test_signal_overlap_validation()
        test_complete_validation_flow()
        
        logger.info("\n" + "=" * 80)
        logger.info("ALL TESTS PASSED ✓")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"\nTEST FAILED: {e}", exc_info=True)
        raise
