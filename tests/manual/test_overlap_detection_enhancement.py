"""
Test enhanced signal overlap detection and logging (Task 9.8.3).

Verifies:
1. Detailed overlap analysis logging (entry-only, exit-only, overlap days)
2. Enhanced conflict resolution logic (>80% reject, 50-80% warn, <50% proceed)
3. Signal quality metrics (avg spacing, holding period, frequency)
"""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from datetime import datetime, timedelta
from strategy.strategy_engine import StrategyEngine
from llm.llm_service import LLMService
from data.market_data_manager import MarketDataManager
from api.etoro_client import EToroAPIClient
from core.config import get_config
from models.dataclasses import Strategy, StrategyStatus
from models.enums import TradingMode
import logging

# Set up logging to capture output
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def initialize_services():
    """Initialize real services for testing."""
    # Initialize configuration manager
    config_manager = get_config()
    
    # Initialize eToro client
    try:
        credentials = config_manager.load_credentials(TradingMode.DEMO)
        etoro_client = EToroAPIClient(
            public_key=credentials['public_key'],
            user_key=credentials['user_key'],
            mode=TradingMode.DEMO
        )
        logger.info("✓ eToro client initialized")
    except Exception as e:
        logger.warning(f"⚠ Could not initialize eToro client: {e}")
        from unittest.mock import Mock
        etoro_client = Mock()
    
    # Initialize LLM service
    llm_service = LLMService()
    logger.info("✓ LLM service initialized")
    
    # Initialize market data manager
    market_data = MarketDataManager(etoro_client=etoro_client)
    logger.info("✓ Market data manager initialized")
    
    # Initialize strategy engine
    strategy_engine = StrategyEngine(
        llm_service=llm_service,
        market_data=market_data
    )
    logger.info("✓ Strategy engine initialized")
    
    return strategy_engine


def test_high_overlap_rejection():
    """Test that strategies with >80% overlap are rejected."""
    logger.info("\n" + "="*80)
    logger.info("TEST 1: High Overlap Rejection (>80%)")
    logger.info("="*80)
    
    engine = initialize_services()
    
    # Create strategy with nearly identical entry/exit conditions (high overlap)
    from models.dataclasses import RiskConfig
    strategy = Strategy(
        id="test-high-overlap",
        name="High Overlap Test Strategy",
        description="Strategy with >80% signal overlap",
        symbols=["SPY"],
        rules={
            "indicators": ["RSI"],
            "entry_conditions": ["RSI_14 is below 50"],  # Very common condition
            "exit_conditions": ["RSI_14 is above 50"]    # Opposite but overlaps often
        },
        status=StrategyStatus.PROPOSED,
        risk_params=RiskConfig(),
        created_at=datetime.now()
    )
    
    # Validate the strategy
    validation_result = engine.validate_strategy_rules(strategy)
    
    logger.info(f"\nValidation Result:")
    logger.info(f"  Is Valid: {validation_result.get('is_valid', validation_result.get('valid', 'N/A'))}")
    logger.info(f"  Overlap %: {validation_result.get('overlap_percentage', 'N/A')}")
    logger.info(f"  Errors: {validation_result.get('errors', [])}")
    logger.info(f"  Warnings: {validation_result.get('warnings', [])}")
    
    # Check that strategy was rejected
    overlap_pct = validation_result.get('overlap_percentage', 0)
    has_critical_error = any('CRITICAL' in str(e) for e in validation_result.get('errors', []))
    
    if overlap_pct > 80:
        logger.info(f"✅ PASS: Strategy correctly identified with {overlap_pct:.1f}% overlap")
    else:
        logger.warning(f"⚠️  Overlap was {overlap_pct:.1f}%, expected >80%")
    
    if has_critical_error:
        logger.info("✅ PASS: Strategy correctly rejected with CRITICAL error")
    else:
        logger.warning("⚠️  Expected CRITICAL error for >80% overlap")
    
    return validation_result


def test_moderate_overlap_warning():
    """Test that strategies with 50-80% overlap get warnings but proceed."""
    logger.info("\n" + "="*80)
    logger.info("TEST 2: Moderate Overlap Warning (50-80%)")
    logger.info("="*80)
    
    engine = initialize_services()
    
    # Create strategy with moderate overlap
    from models.dataclasses import RiskConfig
    strategy = Strategy(
        id="test-moderate-overlap",
        name="Moderate Overlap Test Strategy",
        description="Strategy with 50-80% signal overlap",
        symbols=["SPY"],
        rules={
            "indicators": ["RSI"],
            "entry_conditions": ["RSI_14 is below 45"],
            "exit_conditions": ["RSI_14 is above 55"]  # Some overlap expected
        },
        status=StrategyStatus.PROPOSED,
        risk_params=RiskConfig(),
        created_at=datetime.now()
    )
    
    # Validate the strategy
    validation_result = engine.validate_strategy_rules(strategy)
    
    logger.info(f"\nValidation Result:")
    logger.info(f"  Is Valid: {validation_result.get('is_valid', validation_result.get('valid', 'N/A'))}")
    logger.info(f"  Overlap %: {validation_result.get('overlap_percentage', 'N/A')}")
    logger.info(f"  Errors: {validation_result.get('errors', [])}")
    logger.info(f"  Warnings: {validation_result.get('warnings', [])}")
    
    overlap_pct = validation_result.get('overlap_percentage', 0)
    has_warning = any('WARNING' in str(w) for w in validation_result.get('warnings', []))
    has_critical_error = any('CRITICAL' in str(e) for e in validation_result.get('errors', []))
    
    if 50 <= overlap_pct <= 80:
        logger.info(f"✅ PASS: Moderate overlap detected ({overlap_pct:.1f}%)")
    else:
        logger.warning(f"⚠️  Overlap was {overlap_pct:.1f}%, expected 50-80%")
    
    if has_warning and not has_critical_error:
        logger.info("✅ PASS: Strategy has warning but not rejected")
    else:
        logger.warning("⚠️  Expected warning without critical error")
    
    return validation_result


def test_low_overlap_proceed():
    """Test that strategies with <50% overlap proceed normally."""
    logger.info("\n" + "="*80)
    logger.info("TEST 3: Low Overlap Proceed (<50%)")
    logger.info("="*80)
    
    engine = initialize_services()
    
    # Create strategy with low overlap (good thresholds)
    from models.dataclasses import RiskConfig
    strategy = Strategy(
        id="test-low-overlap",
        name="Low Overlap Test Strategy",
        description="Strategy with <50% signal overlap",
        symbols=["SPY"],
        rules={
            "indicators": ["RSI"],
            "entry_conditions": ["RSI_14 is below 30"],  # Oversold
            "exit_conditions": ["RSI_14 is above 70"]    # Overbought - distinct
        },
        status=StrategyStatus.PROPOSED,
        risk_params=RiskConfig(),
        created_at=datetime.now()
    )
    
    # Validate the strategy
    validation_result = engine.validate_strategy_rules(strategy)
    
    logger.info(f"\nValidation Result:")
    logger.info(f"  Is Valid: {validation_result.get('is_valid', validation_result.get('valid', 'N/A'))}")
    logger.info(f"  Overlap %: {validation_result.get('overlap_percentage', 'N/A')}")
    logger.info(f"  Entry-only %: {validation_result.get('entry_only_percentage', 'N/A')}")
    logger.info(f"  Exit-only %: {validation_result.get('exit_only_percentage', 'N/A')}")
    logger.info(f"  Errors: {validation_result.get('errors', [])}")
    logger.info(f"  Warnings: {validation_result.get('warnings', [])}")
    
    overlap_pct = validation_result.get('overlap_percentage', 0)
    has_overlap_error = any('overlap' in str(e).lower() for e in validation_result.get('errors', []))
    
    if overlap_pct < 50:
        logger.info(f"✅ PASS: Low overlap detected ({overlap_pct:.1f}%)")
    else:
        logger.warning(f"⚠️  Overlap was {overlap_pct:.1f}%, expected <50%")
    
    if not has_overlap_error:
        logger.info("✅ PASS: No overlap-related errors")
    else:
        logger.warning("⚠️  Unexpected overlap error for <50% overlap")
    
    return validation_result


def test_signal_quality_metrics():
    """Test that signal quality metrics are calculated and logged."""
    logger.info("\n" + "="*80)
    logger.info("TEST 4: Signal Quality Metrics")
    logger.info("="*80)
    
    engine = initialize_services()
    
    # Create strategy with good signal characteristics
    from models.dataclasses import RiskConfig
    strategy = Strategy(
        id="test-quality-metrics",
        name="Quality Metrics Test Strategy",
        description="Strategy to test quality metrics calculation",
        symbols=["SPY"],
        rules={
            "indicators": ["RSI"],
            "entry_conditions": ["RSI_14 is below 30"],
            "exit_conditions": ["RSI_14 is above 70"]
        },
        status=StrategyStatus.PROPOSED,
        risk_params=RiskConfig(),
        created_at=datetime.now()
    )
    
    # Validate the strategy
    validation_result = engine.validate_strategy_rules(strategy)
    
    logger.info(f"\nSignal Quality Metrics:")
    logger.info(f"  Avg days between entries: {validation_result.get('avg_days_between_entries', 'N/A')}")
    logger.info(f"  Signal frequency (per month): {validation_result.get('signal_frequency_per_month', 'N/A')}")
    logger.info(f"  Avg holding period (days): {validation_result.get('avg_holding_period_days', 'N/A')}")
    
    # Check that metrics were calculated
    has_spacing = validation_result.get('avg_days_between_entries') is not None
    has_frequency = validation_result.get('signal_frequency_per_month') is not None
    has_holding = validation_result.get('avg_holding_period_days') is not None
    
    if has_spacing:
        logger.info("✅ PASS: Average entry spacing calculated")
    else:
        logger.warning("⚠️  Average entry spacing not calculated")
    
    if has_frequency:
        logger.info("✅ PASS: Signal frequency calculated")
    else:
        logger.warning("⚠️  Signal frequency not calculated")
    
    if has_holding:
        logger.info("✅ PASS: Average holding period calculated")
    else:
        logger.warning("⚠️  Average holding period not calculated")
    
    return validation_result


def test_detailed_logging():
    """Test that detailed overlap analysis is logged."""
    logger.info("\n" + "="*80)
    logger.info("TEST 5: Detailed Logging Verification")
    logger.info("="*80)
    
    engine = initialize_services()
    
    from models.dataclasses import RiskConfig
    strategy = Strategy(
        id="test-detailed-logging",
        name="Logging Test Strategy",
        description="Strategy to verify detailed logging",
        symbols=["SPY"],
        rules={
            "indicators": ["RSI"],
            "entry_conditions": ["RSI_14 is below 30"],
            "exit_conditions": ["RSI_14 is above 70"]
        },
        status=StrategyStatus.PROPOSED,
        risk_params=RiskConfig(),
        created_at=datetime.now()
    )
    
    # Validate - this should trigger detailed logging
    validation_result = engine.validate_strategy_rules(strategy)
    
    # Check that all expected metrics are present
    expected_keys = [
        'overlap_percentage',
        'entry_only_percentage',
        'exit_only_percentage',
        'avg_days_between_entries',
        'signal_frequency_per_month',
        'avg_holding_period_days'
    ]
    
    logger.info(f"\nChecking for expected metrics in validation result:")
    for key in expected_keys:
        if key in validation_result:
            logger.info(f"  ✅ {key}: {validation_result[key]}")
        else:
            logger.warning(f"  ⚠️  {key}: MISSING")
    
    all_present = all(key in validation_result for key in expected_keys)
    
    if all_present:
        logger.info("\n✅ PASS: All expected metrics present in validation result")
    else:
        logger.warning("\n⚠️  Some metrics missing from validation result")
    
    return validation_result


if __name__ == "__main__":
    logger.info("="*80)
    logger.info("TASK 9.8.3: Enhanced Signal Overlap Detection and Logging Tests")
    logger.info("="*80)
    
    try:
        # Run all tests
        result1 = test_high_overlap_rejection()
        result2 = test_moderate_overlap_warning()
        result3 = test_low_overlap_proceed()
        result4 = test_signal_quality_metrics()
        result5 = test_detailed_logging()
        
        logger.info("\n" + "="*80)
        logger.info("TEST SUMMARY")
        logger.info("="*80)
        logger.info("All tests completed. Review logs above for detailed results.")
        logger.info("Expected behaviors:")
        logger.info("  1. >80% overlap → REJECTED with CRITICAL error")
        logger.info("  2. 50-80% overlap → WARNING but proceed")
        logger.info("  3. <50% overlap → Proceed normally")
        logger.info("  4. Signal quality metrics calculated")
        logger.info("  5. Detailed logging with entry-only, exit-only, overlap days")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
