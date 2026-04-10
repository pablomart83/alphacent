"""Test indicator detection and calculation from strategy.rules["indicators"]."""

import pandas as pd
from datetime import datetime, timedelta
from src.strategy.strategy_engine import StrategyEngine
from src.strategy.indicator_library import IndicatorLibrary
from src.llm.llm_service import LLMService
from src.data.market_data_manager import MarketDataManager
from src.models.dataclasses import Strategy, RiskConfig, PerformanceMetrics
from src.models.enums import StrategyStatus


def test_bollinger_bands_indicator_detection():
    """Test that Bollinger Bands indicator is properly detected and calculated."""
    
    # Create mock strategy with Bollinger Bands
    strategy = Strategy(
        id="test-bb-strategy",
        name="Bollinger Bands Test Strategy",
        description="Test strategy using Bollinger Bands",
        status=StrategyStatus.PROPOSED,
        rules={
            "indicators": ["Bollinger Bands", "RSI"],
            "entry_conditions": [
                "Price is below Lower_Band_20",
                "RSI_14 is below 30"
            ],
            "exit_conditions": [
                "Price is above Upper_Band_20",
                "RSI_14 is above 70"
            ],
            "timeframe": "1d"
        },
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    # Create test data
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    test_data = pd.DataFrame({
        'open': [100 + i * 0.5 for i in range(100)],
        'high': [102 + i * 0.5 for i in range(100)],
        'low': [98 + i * 0.5 for i in range(100)],
        'close': [100 + i * 0.5 for i in range(100)],
        'volume': [1000000] * 100
    }, index=dates)
    
    # Create indicator library
    indicator_library = IndicatorLibrary()
    
    # Create strategy engine (we'll use its new method directly)
    # Note: We need to mock LLM and market data, but we're only testing indicator calculation
    class MockLLM:
        pass
    
    class MockMarketData:
        pass
    
    engine = StrategyEngine(MockLLM(), MockMarketData())
    engine.indicator_library = indicator_library
    
    # Test the new method
    indicators = engine._calculate_indicators_from_strategy(strategy, test_data, "AAPL")
    
    # Verify Bollinger Bands keys are present
    print("\n=== Test Results ===")
    print(f"Total indicators calculated: {len(indicators)}")
    print(f"Indicator keys: {list(indicators.keys())}")
    
    # Check for Bollinger Bands keys
    bb_keys = ["Upper_Band_20", "Middle_Band_20", "Lower_Band_20"]
    for key in bb_keys:
        if key in indicators:
            print(f"✓ {key} found")
            print(f"  Sample values: {indicators[key].head(3).tolist()}")
        else:
            print(f"✗ {key} NOT FOUND")
    
    # Check for RSI
    if "RSI_14" in indicators:
        print(f"✓ RSI_14 found")
        print(f"  Sample values: {indicators['RSI_14'].head(3).tolist()}")
    else:
        print(f"✗ RSI_14 NOT FOUND")
    
    # Verify all expected keys are present
    expected_keys = ["Upper_Band_20", "Middle_Band_20", "Lower_Band_20", "RSI_14"]
    missing_keys = [k for k in expected_keys if k not in indicators]
    
    if missing_keys:
        print(f"\n❌ FAILED: Missing keys: {missing_keys}")
        return False
    else:
        print(f"\n✅ SUCCESS: All expected indicator keys are present!")
        return True


if __name__ == "__main__":
    success = test_bollinger_bands_indicator_detection()
    exit(0 if success else 1)
