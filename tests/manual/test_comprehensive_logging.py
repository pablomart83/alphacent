"""
Test comprehensive indicator calculation logging in StrategyEngine.

This test verifies that:
1. strategy.rules["indicators"] list is logged
2. Each indicator being calculated is logged
3. Keys returned by each indicator are logged
4. Final indicators dict keys are logged
5. Missing indicators referenced in rules are logged with detailed error messages
"""

import sys
import os
import logging
from datetime import datetime, timedelta
from io import StringIO

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.strategy.strategy_engine import StrategyEngine
from src.llm.llm_service import LLMService
from src.data.market_data_manager import MarketDataManager
from src.models.dataclasses import Strategy
from src.models.enums import StrategyStatus, TradingMode

# Configure logging to capture log output
log_capture = StringIO()
handler = logging.StreamHandler(log_capture)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(levelname)s - %(message)s')
handler.setFormatter(formatter)

# Get the logger used by StrategyEngine
logger = logging.getLogger('strategy.strategy_engine')
logger.addHandler(handler)
logger.setLevel(logging.INFO)


def test_indicator_calculation_logging():
    """Test that indicator calculation is logged comprehensively."""
    print("\n" + "=" * 80)
    print("TEST: Comprehensive Indicator Calculation Logging")
    print("=" * 80)
    
    # Initialize services
    llm_service = LLMService()
    market_data = MarketDataManager()
    strategy_engine = StrategyEngine(llm_service, market_data)
    
    # Create a test strategy with multiple indicators
    strategy = Strategy(
        name="Test Logging Strategy",
        description="Strategy to test comprehensive logging",
        symbols=["AAPL"],
        rules={
            "indicators": ["RSI", "Bollinger Bands", "MACD", "Support/Resistance"],
            "entry_conditions": [
                "RSI_14 < 30",
                "Close price below Lower_Band_20"
            ],
            "exit_conditions": [
                "RSI_14 > 70",
                "Close price above Upper_Band_20"
            ]
        },
        status=StrategyStatus.PROPOSED,
        mode=TradingMode.DEMO
    )
    
    # Clear log capture
    log_capture.truncate(0)
    log_capture.seek(0)
    
    # Run validation which will trigger indicator calculation
    print("\nRunning strategy validation to trigger indicator calculation...")
    result = strategy_engine.validate_strategy_signals(strategy)
    
    # Get captured logs
    log_output = log_capture.getvalue()
    
    print("\n" + "=" * 80)
    print("CAPTURED LOG OUTPUT:")
    print("=" * 80)
    print(log_output)
    print("=" * 80)
    
    # Verify logging requirements
    print("\n" + "=" * 80)
    print("VERIFICATION RESULTS:")
    print("=" * 80)
    
    checks = {
        "1. Strategy indicators list logged": "Strategy rules['indicators'] list:" in log_output,
        "2. Indicator calculation start logged": "INDICATOR CALCULATION START" in log_output,
        "3. Processing individual indicators": "Processing indicator:" in log_output,
        "4. Method and parameters logged": "Method:" in log_output and "Parameters:" in log_output,
        "5. Keys returned logged": "Keys returned:" in log_output or "Key returned:" in log_output,
        "6. Calculation complete logged": "INDICATOR CALCULATION COMPLETE" in log_output,
        "7. Final indicator keys logged": "Final indicator keys available:" in log_output,
        "8. Total indicators count logged": "Total indicators calculated:" in log_output,
    }
    
    all_passed = True
    for check_name, passed in checks.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {check_name}")
        if not passed:
            all_passed = False
    
    print("=" * 80)
    
    if all_passed:
        print("\n✓ All logging checks PASSED!")
    else:
        print("\n✗ Some logging checks FAILED!")
    
    return all_passed


def test_missing_indicator_logging():
    """Test that missing indicator references are logged with detailed errors."""
    print("\n" + "=" * 80)
    print("TEST: Missing Indicator Reference Logging")
    print("=" * 80)
    
    # Initialize services
    llm_service = LLMService()
    market_data = MarketDataManager()
    strategy_engine = StrategyEngine(llm_service, market_data)
    
    # Create a strategy that references indicators not in the calculation list
    # This will cause the LLM to generate code referencing indicators that don't exist
    strategy = Strategy(
        name="Test Missing Indicator Strategy",
        description="Strategy to test missing indicator error logging",
        symbols=["AAPL"],
        rules={
            "indicators": ["RSI"],  # Only RSI calculated
            "entry_conditions": [
                "RSI_14 < 30 and MACD_12_26_9 > 0"  # MACD not in indicators list!
            ],
            "exit_conditions": [
                "RSI_14 > 70"
            ]
        },
        status=StrategyStatus.PROPOSED,
        mode=TradingMode.DEMO
    )
    
    # Clear log capture
    log_capture.truncate(0)
    log_capture.seek(0)
    
    # Run validation
    print("\nRunning strategy validation with missing indicator reference...")
    result = strategy_engine.validate_strategy_signals(strategy)
    
    # Get captured logs
    log_output = log_capture.getvalue()
    
    print("\n" + "=" * 80)
    print("CAPTURED LOG OUTPUT (ERROR SECTION):")
    print("=" * 80)
    # Print only ERROR lines
    for line in log_output.split('\n'):
        if 'ERROR' in line or 'INDICATOR REFERENCE ERROR' in line or 'SUGGESTION' in line:
            print(line)
    print("=" * 80)
    
    # Verify error logging requirements
    print("\n" + "=" * 80)
    print("VERIFICATION RESULTS:")
    print("=" * 80)
    
    checks = {
        "1. Indicator reference error logged": "INDICATOR REFERENCE ERROR" in log_output,
        "2. Rule text logged": "Rule text:" in log_output,
        "3. Generated code logged": "Generated code:" in log_output,
        "4. Missing indicators logged": "Missing indicators:" in log_output,
        "5. Available indicators logged": "Available indicators:" in log_output,
        "6. Suggestion for fix logged": "SUGGESTION FOR FIX:" in log_output,
    }
    
    all_passed = True
    for check_name, passed in checks.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {check_name}")
        if not passed:
            all_passed = False
    
    print("=" * 80)
    
    if all_passed:
        print("\n✓ All error logging checks PASSED!")
    else:
        print("\n✗ Some error logging checks FAILED!")
    
    return all_passed


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("COMPREHENSIVE LOGGING TEST SUITE")
    print("=" * 80)
    
    test1_passed = test_indicator_calculation_logging()
    test2_passed = test_missing_indicator_logging()
    
    print("\n" + "=" * 80)
    print("FINAL RESULTS:")
    print("=" * 80)
    print(f"Test 1 (Indicator Calculation Logging): {'✓ PASS' if test1_passed else '✗ FAIL'}")
    print(f"Test 2 (Missing Indicator Error Logging): {'✓ PASS' if test2_passed else '✗ FAIL'}")
    print("=" * 80)
    
    if test1_passed and test2_passed:
        print("\n✓✓✓ ALL TESTS PASSED! ✓✓✓")
        sys.exit(0)
    else:
        print("\n✗✗✗ SOME TESTS FAILED! ✗✗✗")
        sys.exit(1)
