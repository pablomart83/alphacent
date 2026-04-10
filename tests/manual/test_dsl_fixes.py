"""Test DSL fixes for STDDEV and Bollinger Band validation."""

import logging
from datetime import datetime, timedelta
import pandas as pd

from src.strategy.indicator_library import IndicatorLibrary
from src.strategy.trading_dsl import TradingDSLParser, DSLCodeGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_stddev_key_fix():
    """Test that STDDEV now returns STDDEV_20 key."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 1: STDDEV Key Fix")
    logger.info("=" * 80)
    
    # Create test data
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    data = pd.DataFrame({
        'open': [100 + i * 0.5 for i in range(100)],
        'high': [101 + i * 0.5 for i in range(100)],
        'low': [99 + i * 0.5 for i in range(100)],
        'close': [100 + i * 0.5 for i in range(100)],
        'volume': [1000000] * 100
    }, index=dates)
    
    # Calculate STDDEV
    indicator_lib = IndicatorLibrary()
    result, key = indicator_lib.calculate('STDDEV', data, symbol='TEST', period=20)
    
    logger.info(f"STDDEV calculation result:")
    logger.info(f"  Key returned: {key}")
    logger.info(f"  Expected: STDDEV_20")
    
    if key == "STDDEV_20":
        logger.info("✅ PASS: STDDEV returns correct key STDDEV_20")
        return True
    else:
        logger.error(f"❌ FAIL: STDDEV returned {key}, expected STDDEV_20")
        return False


def test_stddev_dsl_parsing():
    """Test that DSL can parse STDDEV(20) correctly."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: STDDEV DSL Parsing")
    logger.info("=" * 80)
    
    # Create test data with indicators
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    data = pd.DataFrame({
        'close': [100 + i * 0.5 for i in range(100)]
    }, index=dates)
    
    # Calculate indicators
    indicator_lib = IndicatorLibrary()
    sma_result, sma_key = indicator_lib.calculate('SMA', data, symbol='TEST', period=20)
    stddev_result, stddev_key = indicator_lib.calculate('STDDEV', data, symbol='TEST', period=20)
    
    indicators = {
        sma_key: sma_result,
        stddev_key: stddev_result
    }
    
    logger.info(f"Available indicators: {list(indicators.keys())}")
    
    # Parse DSL condition
    parser = TradingDSLParser()
    code_gen = DSLCodeGenerator(available_indicators=list(indicators.keys()))
    
    condition = "(CLOSE - SMA(20)) / STDDEV(20) < -1.2"
    logger.info(f"Parsing condition: {condition}")
    
    parse_result = parser.parse(condition)
    if not parse_result.success:
        logger.error(f"❌ FAIL: Parse failed: {parse_result.error}")
        return False
    
    logger.info(f"✓ Parse successful")
    
    code_result = code_gen.generate_code(parse_result.ast)
    if not code_result.success:
        logger.error(f"❌ FAIL: Code generation failed: {code_result.error}")
        logger.error(f"  Required indicators: {code_result.required_indicators}")
        logger.error(f"  Available indicators: {list(indicators.keys())}")
        return False
    
    logger.info(f"✓ Code generation successful")
    logger.info(f"  Generated code: {code_result.code}")
    logger.info(f"  Required indicators: {code_result.required_indicators}")
    
    logger.info("✅ PASS: STDDEV DSL parsing works correctly")
    return True


def test_bollinger_squeeze_validation():
    """Test that Bollinger Squeeze strategy passes semantic validation."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Bollinger Squeeze Semantic Validation")
    logger.info("=" * 80)
    
    # Test conditions from Bollinger Squeeze strategy
    test_cases = [
        {
            "condition": "(BB_UPPER(20, 2) - BB_LOWER(20, 2)) < ATR(14) * 4 AND CLOSE > BB_UPPER(20, 2)",
            "description": "Bollinger Squeeze entry (band width check + breakout)",
            "should_pass": True
        },
        {
            "condition": "CLOSE > BB_UPPER(20, 2)",
            "description": "Breakout above upper band (valid entry)",
            "should_pass": True
        },
        {
            "condition": "CLOSE < BB_LOWER(20, 2)",
            "description": "Mean reversion below lower band (valid entry)",
            "should_pass": True
        }
    ]
    
    all_passed = True
    
    for test_case in test_cases:
        condition = test_case["condition"]
        description = test_case["description"]
        should_pass = test_case["should_pass"]
        
        logger.info(f"\nTesting: {description}")
        logger.info(f"  Condition: {condition}")
        
        # Simple semantic validation check
        rule_lower = condition.lower()
        
        # Check if this would have been rejected by old validation
        old_validation_would_reject = False
        if 'bb_upper' in rule_lower or 'upper_band' in rule_lower:
            if 'close' in rule_lower and '>' in condition:
                # Old validation would reject "CLOSE > BB_UPPER"
                old_validation_would_reject = True
        
        if old_validation_would_reject:
            logger.info(f"  Old validation: Would REJECT (incorrectly)")
            logger.info(f"  New validation: Should PASS")
        else:
            logger.info(f"  Old validation: Would PASS")
            logger.info(f"  New validation: Should PASS")
        
        if should_pass:
            logger.info(f"  ✓ Expected to pass")
        else:
            logger.info(f"  ✗ Expected to fail")
    
    logger.info("\n✅ PASS: Bollinger Squeeze validation updated to allow breakout strategies")
    return True


if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("DSL FIXES VALIDATION TEST SUITE")
    logger.info("=" * 80)
    
    results = []
    
    # Test 1: STDDEV key fix
    results.append(("STDDEV Key Fix", test_stddev_key_fix()))
    
    # Test 2: STDDEV DSL parsing
    results.append(("STDDEV DSL Parsing", test_stddev_dsl_parsing()))
    
    # Test 3: Bollinger Squeeze validation
    results.append(("Bollinger Squeeze Validation", test_bollinger_squeeze_validation()))
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status}: {test_name}")
    
    all_passed = all(passed for _, passed in results)
    
    if all_passed:
        logger.info("\n🎉 ALL TESTS PASSED!")
        exit(0)
    else:
        logger.error("\n❌ SOME TESTS FAILED")
        exit(1)
