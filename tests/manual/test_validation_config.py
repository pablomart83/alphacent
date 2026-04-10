"""
Quick test to verify validation config loading works correctly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.llm.llm_service import LLMService
from src.data.market_data_manager import MarketDataManager
from src.strategy.strategy_engine import StrategyEngine
from src.api.etoro_client import EToroAPIClient
from src.models.enums import TradingMode
from src.core.config import get_config

def test_validation_config_loading():
    """Test that validation config is loaded correctly."""
    print("=" * 80)
    print("Testing Validation Config Loading")
    print("=" * 80)
    
    # Initialize components
    print("\n1. Initializing components...")
    llm_service = LLMService()
    
    try:
        config_manager = get_config()
        credentials = config_manager.load_credentials(TradingMode.DEMO)
        etoro_client = EToroAPIClient(
            public_key=credentials['public_key'],
            user_key=credentials['user_key'],
            mode=TradingMode.DEMO
        )
    except Exception as e:
        print(f"   Warning: Could not initialize eToro client: {e}")
        from unittest.mock import Mock
        etoro_client = Mock()
    
    market_data = MarketDataManager(etoro_client=etoro_client)
    
    # Initialize strategy engine (this should load config)
    print("\n2. Initializing StrategyEngine (loads validation config)...")
    strategy_engine = StrategyEngine(
        llm_service=llm_service,
        market_data=market_data
    )
    
    # Check validation config
    print("\n3. Checking loaded validation config...")
    validation_config = strategy_engine.validation_config
    
    print(f"\n   Validation Config Keys: {list(validation_config.keys())}")
    
    # Check RSI config
    rsi_config = validation_config.get("rsi", {})
    print(f"\n   RSI Config:")
    print(f"      entry_max: {rsi_config.get('entry_max')} (expected: 55)")
    print(f"      exit_min: {rsi_config.get('exit_min')} (expected: 55)")
    
    # Check Stochastic config
    stoch_config = validation_config.get("stochastic", {})
    print(f"\n   Stochastic Config:")
    print(f"      entry_max: {stoch_config.get('entry_max')} (expected: 30)")
    print(f"      exit_min: {stoch_config.get('exit_min')} (expected: 70)")
    
    # Check entry opportunities config
    entry_config = validation_config.get("entry_opportunities", {})
    print(f"\n   Entry Opportunities Config:")
    print(f"      min_entry_pct: {entry_config.get('min_entry_pct')} (expected: 10)")
    print(f"      min_trades_per_month: {entry_config.get('min_trades_per_month')} (expected: 1)")
    
    # Check signal overlap config
    overlap_config = validation_config.get("signal_overlap", {})
    print(f"\n   Signal Overlap Config:")
    print(f"      max_overlap_pct: {overlap_config.get('max_overlap_pct')} (expected: 50)")
    
    # Verify values
    print("\n4. Verifying values...")
    assert rsi_config.get('entry_max') == 55, "RSI entry_max should be 55"
    assert rsi_config.get('exit_min') == 55, "RSI exit_min should be 55"
    assert stoch_config.get('entry_max') == 30, "Stochastic entry_max should be 30"
    assert stoch_config.get('exit_min') == 70, "Stochastic exit_min should be 70"
    assert entry_config.get('min_entry_pct') == 10, "min_entry_pct should be 10"
    assert overlap_config.get('max_overlap_pct') == 50, "max_overlap_pct should be 50"
    
    print("\n" + "=" * 80)
    print("✅ All validation config values loaded correctly!")
    print("=" * 80)
    
    return True

if __name__ == "__main__":
    try:
        success = test_validation_config_loading()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
