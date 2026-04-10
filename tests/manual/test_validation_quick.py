"""Quick test of strategy validation with indicator parsing."""

import sys
from datetime import datetime, timedelta
from src.strategy.strategy_engine import StrategyEngine
from src.llm.llm_service import LLMService
from src.data.market_data_manager import MarketDataManager
from src.api.etoro_client import EToroAPIClient
from src.models import Strategy, StrategyStatus, RiskConfig, PerformanceMetrics
from src.core.config import get_config
from src.models.enums import TradingMode

def test_validation():
    """Test strategy validation with indicator parsing."""
    print("=" * 70)
    print("Testing Strategy Validation with Indicator Parsing")
    print("=" * 70)
    
    # Initialize components
    config = get_config()
    creds = config.load_credentials(TradingMode.DEMO)
    
    etoro_client = EToroAPIClient(
        public_key=creds["public_key"],
        user_key=creds["user_key"],
        mode=TradingMode.DEMO
    )
    
    llm_service = LLMService()
    market_data = MarketDataManager(etoro_client)
    strategy_engine = StrategyEngine(llm_service, market_data)
    
    # Create a test strategy with SMA and RSI
    test_strategy = Strategy(
        id="test-123",
        name="Test SMA RSI Strategy",
        description="Test strategy for validation",
        status=StrategyStatus.PROPOSED,
        rules={
            "entry_conditions": ["Price is above SMA_20", "RSI_14 is below 70"],
            "exit_conditions": ["Price drops below SMA_20", "RSI_14 rises above 70"],
            "indicators": ["SMA", "RSI"],
            "timeframe": "1d"
        },
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )
    
    print(f"\nValidating strategy: {test_strategy.name}")
    print(f"Symbols: {test_strategy.symbols}")
    print(f"Entry conditions: {test_strategy.rules['entry_conditions']}")
    print(f"Exit conditions: {test_strategy.rules['exit_conditions']}")
    print()
    
    # Validate
    result = strategy_engine.validate_strategy_signals(test_strategy)
    
    print("\nValidation Results:")
    print(f"  Valid: {result['is_valid']}")
    print(f"  Entry signals: {result['entry_signals']}")
    print(f"  Exit signals: {result['exit_signals']}")
    
    if result['errors']:
        print(f"  Errors: {result['errors']}")
    
    if result['warnings']:
        print(f"  Warnings: {result['warnings']}")
    
    print("\n" + "=" * 70)
    
    if result['is_valid']:
        print("✓ Validation PASSED - Strategy generates signals")
        return True
    else:
        print("✗ Validation FAILED - Strategy does not generate sufficient signals")
        return False

if __name__ == "__main__":
    try:
        success = test_validation()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
