"""Verification script for Task 9.7.1: Indicator Detection and Calculation Fix."""

import pandas as pd
from datetime import datetime
from src.strategy.strategy_engine import StrategyEngine
from src.strategy.indicator_library import IndicatorLibrary
from src.models.dataclasses import Strategy, RiskConfig, PerformanceMetrics
from src.models.enums import StrategyStatus
from unittest.mock import Mock


def verify_task_9_7_1():
    """
    Verify that Task 9.7.1 is complete:
    - Strategy with "Bollinger Bands" in rules["indicators"] 
    - All 3 band keys are calculated and available
    - Strategy with "MACD" gets all 3 components
    - Strategy with "Support/Resistance" gets both keys
    - Strategy with "Stochastic Oscillator" gets the key
    """
    
    print("="*70)
    print("TASK 9.7.1 VERIFICATION")
    print("="*70)
    print("\nTask: Fix Indicator Detection and Calculation in Strategy Engine")
    print("\nAcceptance Criteria:")
    print("  ✓ Strategy referencing 'Bollinger Bands' has all 3 band keys available")
    print("  ✓ Strategy referencing 'MACD' has all 3 components available")
    print("  ✓ Strategy referencing 'Support/Resistance' has both keys available")
    print("  ✓ Strategy referencing 'Stochastic Oscillator' has the key available")
    print("\n" + "="*70)
    
    # Create test data
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    test_data = pd.DataFrame({
        'open': [100 + i * 0.5 for i in range(100)],
        'high': [102 + i * 0.5 for i in range(100)],
        'low': [98 + i * 0.5 for i in range(100)],
        'close': [100 + i * 0.5 for i in range(100)],
        'volume': [1000000] * 100
    }, index=dates)
    
    # Create mocks
    mock_llm = Mock()
    mock_market_data = Mock()
    
    # Create strategy engine
    engine = StrategyEngine(mock_llm, mock_market_data)
    
    # Test 1: Bollinger Bands
    print("\n[Test 1] Bollinger Bands Indicator Detection")
    print("-" * 70)
    
    strategy_bb = Strategy(
        id="test-bb",
        name="BB Test",
        description="Test",
        status=StrategyStatus.PROPOSED,
        rules={
            "indicators": ["Bollinger Bands"],
            "entry_conditions": [],
            "exit_conditions": [],
            "timeframe": "1d"
        },
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    indicators_bb = engine._calculate_indicators_from_strategy(strategy_bb, test_data, "AAPL")
    
    bb_keys = ["Upper_Band_20", "Middle_Band_20", "Lower_Band_20"]
    bb_success = all(key in indicators_bb for key in bb_keys)
    
    print(f"  Indicators calculated: {list(indicators_bb.keys())}")
    print(f"  Expected keys: {bb_keys}")
    print(f"  Result: {'✅ PASS' if bb_success else '❌ FAIL'}")
    
    # Test 2: MACD
    print("\n[Test 2] MACD Indicator Detection")
    print("-" * 70)
    
    strategy_macd = Strategy(
        id="test-macd",
        name="MACD Test",
        description="Test",
        status=StrategyStatus.PROPOSED,
        rules={
            "indicators": ["MACD"],
            "entry_conditions": [],
            "exit_conditions": [],
            "timeframe": "1d"
        },
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    indicators_macd = engine._calculate_indicators_from_strategy(strategy_macd, test_data, "AAPL")
    
    macd_keys = ["MACD_12_26_9", "MACD_12_26_9_SIGNAL", "MACD_12_26_9_HIST"]
    macd_success = all(key in indicators_macd for key in macd_keys)
    
    print(f"  Indicators calculated: {list(indicators_macd.keys())}")
    print(f"  Expected keys: {macd_keys}")
    print(f"  Result: {'✅ PASS' if macd_success else '❌ FAIL'}")
    
    # Test 3: Support/Resistance
    print("\n[Test 3] Support/Resistance Indicator Detection")
    print("-" * 70)
    
    strategy_sr = Strategy(
        id="test-sr",
        name="SR Test",
        description="Test",
        status=StrategyStatus.PROPOSED,
        rules={
            "indicators": ["Support/Resistance"],
            "entry_conditions": [],
            "exit_conditions": [],
            "timeframe": "1d"
        },
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    indicators_sr = engine._calculate_indicators_from_strategy(strategy_sr, test_data, "AAPL")
    
    sr_keys = ["Support", "Resistance"]
    sr_success = all(key in indicators_sr for key in sr_keys)
    
    print(f"  Indicators calculated: {list(indicators_sr.keys())}")
    print(f"  Expected keys: {sr_keys}")
    print(f"  Result: {'✅ PASS' if sr_success else '❌ FAIL'}")
    
    # Test 4: Stochastic Oscillator
    print("\n[Test 4] Stochastic Oscillator Indicator Detection")
    print("-" * 70)
    
    strategy_stoch = Strategy(
        id="test-stoch",
        name="Stoch Test",
        description="Test",
        status=StrategyStatus.PROPOSED,
        rules={
            "indicators": ["Stochastic Oscillator"],
            "entry_conditions": [],
            "exit_conditions": [],
            "timeframe": "1d"
        },
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    indicators_stoch = engine._calculate_indicators_from_strategy(strategy_stoch, test_data, "AAPL")
    
    stoch_keys = ["STOCH_14"]
    stoch_success = all(key in indicators_stoch for key in stoch_keys)
    
    print(f"  Indicators calculated: {list(indicators_stoch.keys())}")
    print(f"  Expected keys: {stoch_keys}")
    print(f"  Result: {'✅ PASS' if stoch_success else '❌ FAIL'}")
    
    # Test 5: Multiple indicators
    print("\n[Test 5] Multiple Indicators Detection")
    print("-" * 70)
    
    strategy_multi = Strategy(
        id="test-multi",
        name="Multi Test",
        description="Test",
        status=StrategyStatus.PROPOSED,
        rules={
            "indicators": ["Bollinger Bands", "RSI", "MACD"],
            "entry_conditions": [],
            "exit_conditions": [],
            "timeframe": "1d"
        },
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    indicators_multi = engine._calculate_indicators_from_strategy(strategy_multi, test_data, "AAPL")
    
    multi_keys = ["Upper_Band_20", "Middle_Band_20", "Lower_Band_20", "RSI_14", 
                  "MACD_12_26_9", "MACD_12_26_9_SIGNAL", "MACD_12_26_9_HIST"]
    multi_success = all(key in indicators_multi for key in multi_keys)
    
    print(f"  Indicators calculated: {list(indicators_multi.keys())}")
    print(f"  Expected keys: {multi_keys}")
    print(f"  Result: {'✅ PASS' if multi_success else '❌ FAIL'}")
    
    # Final result
    print("\n" + "="*70)
    print("FINAL RESULT")
    print("="*70)
    
    all_success = bb_success and macd_success and sr_success and stoch_success and multi_success
    
    if all_success:
        print("\n✅ ALL TESTS PASSED - TASK 9.7.1 COMPLETE!")
        print("\nSummary:")
        print("  ✓ Bollinger Bands → 3 keys (Upper_Band_20, Middle_Band_20, Lower_Band_20)")
        print("  ✓ MACD → 3 keys (MACD_12_26_9, MACD_12_26_9_SIGNAL, MACD_12_26_9_HIST)")
        print("  ✓ Support/Resistance → 2 keys (Support, Resistance)")
        print("  ✓ Stochastic Oscillator → 1 key (STOCH_14)")
        print("  ✓ Multiple indicators work together")
        return True
    else:
        print("\n❌ SOME TESTS FAILED")
        return False


if __name__ == "__main__":
    success = verify_task_9_7_1()
    exit(0 if success else 1)
