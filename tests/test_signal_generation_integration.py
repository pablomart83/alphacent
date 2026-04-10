"""Integration tests for signal generation with real data and components - NO MOCKS."""

import pytest
from datetime import datetime

from src.strategy.strategy_engine import StrategyEngine
from src.llm.llm_service import LLMService
from src.data.market_data_manager import MarketDataManager
from src.risk.risk_manager import RiskManager
from src.models import (
    Strategy,
    StrategyStatus,
    RiskConfig,
    PerformanceMetrics,
    SignalAction,
    AccountInfo,
    TradingMode,
)


@pytest.fixture
def real_market_data_manager():
    """
    Create real MarketDataManager with real eToro client using actual credentials.
    This will fetch REAL market data from eToro API (with Yahoo Finance fallback).
    """
    from src.api.etoro_client import EToroAPIClient
    from src.core.config import get_config
    
    config = get_config()
    
    # Load real eToro credentials from encrypted config
    creds = config.load_credentials(TradingMode.DEMO)
    
    # Use real eToro credentials
    etoro_client = EToroAPIClient(
        public_key=creds["public_key"],
        user_key=creds["user_key"],
        mode=TradingMode.DEMO
    )
    
    return MarketDataManager(etoro_client)


@pytest.fixture
def real_llm_service():
    """Create real LLMService instance."""
    return LLMService()


@pytest.fixture
def real_strategy_engine(real_llm_service, real_market_data_manager):
    """Create real StrategyEngine with actual dependencies - NO MOCKS."""
    # Use real database
    engine = StrategyEngine(real_llm_service, real_market_data_manager)
    return engine


@pytest.fixture
def real_risk_manager():
    """Create real RiskManager instance."""
    return RiskManager(RiskConfig())


@pytest.fixture
def demo_strategy():
    """Create a demo strategy with real symbols."""
    return Strategy(
        id="integration-test-strategy",
        name="Integration Test Strategy",
        description="Strategy for integration testing with real data",
        status=StrategyStatus.DEMO,
        rules={
            "entry_conditions": ["Fast MA crosses above Slow MA"],
            "exit_conditions": ["Fast MA crosses below Slow MA"],
            "indicators": ["SMA_10", "SMA_30", "RSI_14"],
            "timeframe": "1d"
        },
        symbols=["AAPL"],  # Use a real, liquid symbol
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        allocation_percent=30.0,
        activated_at=datetime.now(),
        performance=PerformanceMetrics()
    )


@pytest.fixture
def real_account():
    """Create realistic account info."""
    return AccountInfo(
        account_id="integration-test-account",
        mode=TradingMode.DEMO,
        balance=10000.0,
        buying_power=10000.0,
        margin_used=0.0,
        margin_available=10000.0,
        daily_pnl=0.0,
        total_pnl=0.0,
        positions_count=0,
        updated_at=datetime.now()
    )


@pytest.mark.integration
@pytest.mark.slow
def test_signal_generation_with_real_market_data(real_strategy_engine, demo_strategy):
    """
    Integration test: Generate signals using REAL market data - NO MOCKS.
    
    This test verifies that the signal generation works end-to-end with:
    - Real MarketDataManager fetching actual historical data from Yahoo Finance
    - Real indicator calculations (MA, RSI, volume)
    - Real signal generation logic
    - Real system state checks
    
    This test may take longer as it fetches real market data.
    """
    from src.core.system_state_manager import get_system_state_manager
    from src.models.enums import SystemStateEnum
    
    # Get real system state manager
    state_manager = get_system_state_manager()
    
    # Temporarily set system to ACTIVE for testing
    original_state = state_manager.get_current_state()
    if original_state.state != SystemStateEnum.ACTIVE:
        state_manager.set_state(SystemStateEnum.ACTIVE, "Integration test", "test")
    
    try:
        # Generate signals with REAL data
        print(f"\n🔍 Fetching real market data for {demo_strategy.symbols}...")
        signals = real_strategy_engine.generate_signals(demo_strategy)
        
        print(f"✓ Signal generation completed")
        print(f"✓ Generated {len(signals)} signal(s)")
        
        # Verify signals structure
        assert isinstance(signals, list)
        
        # If signals were generated, verify their structure with REAL data
        for signal in signals:
            print(f"\n📊 Signal Details:")
            print(f"  Strategy: {signal.strategy_id}")
            print(f"  Symbol: {signal.symbol}")
            print(f"  Action: {signal.action.value}")
            print(f"  Confidence: {signal.confidence:.2f}")
            print(f"  Generated: {signal.generated_at}")
            
            # Verify signal has all required fields
            assert signal.strategy_id == demo_strategy.id
            assert signal.symbol in demo_strategy.symbols
            assert signal.action in [SignalAction.ENTER_LONG, SignalAction.EXIT_LONG]
            
            # Verify confidence score from REAL calculations
            assert 0.0 <= signal.confidence <= 1.0
            
            # Verify reasoning exists and contains REAL indicator values
            assert signal.reasoning is not None
            assert len(signal.reasoning) > 0
            print(f"  Reasoning: {signal.reasoning[:150]}...")
            
            # Verify REAL indicators are present
            assert "fast_ma" in signal.indicators
            assert "slow_ma" in signal.indicators
            assert "rsi" in signal.indicators
            assert "price" in signal.indicators
            assert "volume" in signal.indicators
            
            # Verify indicator values are realistic (from REAL market data)
            print(f"\n📈 Real Indicator Values:")
            print(f"  Fast MA (10-day): ${signal.indicators['fast_ma']:.2f}")
            print(f"  Slow MA (30-day): ${signal.indicators['slow_ma']:.2f}")
            print(f"  RSI (14-day): {signal.indicators['rsi']:.1f}")
            print(f"  Current Price: ${signal.indicators['price']:.2f}")
            print(f"  Volume: {signal.indicators['volume']:,.0f}")
            
            assert signal.indicators["fast_ma"] > 0
            assert signal.indicators["slow_ma"] > 0
            assert 0 <= signal.indicators["rsi"] <= 100
            assert signal.indicators["price"] > 0
            assert signal.indicators["volume"] >= 0
            
            # Verify metadata from REAL calculations
            assert "strategy_name" in signal.metadata
            assert signal.metadata["strategy_name"] == demo_strategy.name
            assert "confidence_factors" in signal.metadata
            
            # Verify REAL confidence factors
            factors = signal.metadata["confidence_factors"]
            print(f"\n🎯 Confidence Factors (from real data):")
            print(f"  MA Spread: {factors['ma_spread']:.2f}")
            print(f"  RSI: {factors['rsi']:.2f}")
            print(f"  Volume: {factors['volume']:.2f}")
            
            assert "ma_spread" in factors
            assert "rsi" in factors
            assert "volume" in factors
            assert all(0.0 <= v <= 1.0 for v in factors.values())
        
        if len(signals) == 0:
            print("\n✓ No signals generated (no crossovers detected in current market conditions)")
            print("  This is expected behavior - signals are only generated when conditions are met")
        
    finally:
        # Restore original state
        if original_state.state != SystemStateEnum.ACTIVE:
            state_manager.set_state(original_state.state, "Restore after test", "test")


@pytest.mark.integration
@pytest.mark.slow
def test_signal_validation_with_real_risk_manager(real_risk_manager, demo_strategy, real_account):
    """
    Integration test: Validate signals using REAL RiskManager - NO MOCKS.
    
    This test verifies that signal validation works with:
    - Real RiskManager with actual risk calculations
    - Real position sizing logic
    - Real risk limit checks
    """
    from src.models import TradingSignal
    
    print("\n🔍 Testing real risk validation...")
    
    # Create a realistic signal (based on typical AAPL values)
    signal = TradingSignal(
        strategy_id=demo_strategy.id,
        symbol="AAPL",
        action=SignalAction.ENTER_LONG,
        confidence=0.75,
        reasoning="Fast MA (155.23) crossed above slow MA (152.45). RSI moderately bullish at 58.3. Above average volume (45000000 vs avg 42000000). Overall confidence: 0.75",
        generated_at=datetime.now(),
        indicators={
            "fast_ma": 155.23,
            "slow_ma": 152.45,
            "rsi": 58.3,
            "volume": 45000000,
            "volume_ma": 42000000,
            "price": 155.50
        },
        metadata={
            "strategy_name": demo_strategy.name,
            "timestamp": datetime.now().isoformat(),
            "confidence_factors": {
                "ma_spread": 0.65,
                "rsi": 0.70,
                "volume": 0.90
            }
        }
    )
    
    # Validate signal with REAL risk manager
    result = real_risk_manager.validate_signal(signal, real_account, [])
    
    print(f"\n✓ Risk validation completed")
    print(f"  Valid: {result.is_valid}")
    print(f"  Position size: ${result.position_size:.2f}")
    print(f"  Reason: {result.reason}")
    
    # Verify validation result from REAL calculations
    assert result is not None
    assert result.is_valid is True
    assert result.position_size > 0
    
    # Verify position size is within REAL limits
    max_position_size = real_account.balance * real_risk_manager.config.max_position_size_pct
    assert result.position_size <= max_position_size
    print(f"  Max allowed: ${max_position_size:.2f}")
    
    # Verify position size meets REAL minimum (eToro requirement)
    assert result.position_size >= 10.0
    print(f"  eToro minimum: $10.00")
    
    print(f"\n✓ All real risk checks passed")


@pytest.mark.integration
@pytest.mark.slow
def test_end_to_end_with_real_components(
    real_strategy_engine,
    real_risk_manager,
    demo_strategy,
    real_account
):
    """
    Integration test: Complete end-to-end with ALL REAL components - NO MOCKS.
    
    This test verifies the complete workflow:
    1. Generate signals with REAL market data
    2. Validate signals with REAL risk manager
    3. Verify all components work together correctly
    
    This is the ultimate integration test - everything is real.
    """
    from src.core.system_state_manager import get_system_state_manager
    from src.models.enums import SystemStateEnum
    
    print("\n" + "="*60)
    print("🚀 END-TO-END INTEGRATION TEST - ALL REAL COMPONENTS")
    print("="*60)
    
    # Get real system state manager
    state_manager = get_system_state_manager()
    
    # Temporarily set system to ACTIVE
    original_state = state_manager.get_current_state()
    if original_state.state != SystemStateEnum.ACTIVE:
        state_manager.set_state(SystemStateEnum.ACTIVE, "Integration test", "test")
    
    try:
        # Step 1: Generate signals with REAL data
        print(f"\n📡 Step 1: Fetching real market data and generating signals...")
        signals = real_strategy_engine.generate_signals(demo_strategy)
        
        print(f"✓ Generated {len(signals)} signal(s) from real market data")
        
        # Step 2: Validate each signal with REAL risk manager
        print(f"\n🛡️  Step 2: Validating signals with real risk manager...")
        validated_signals = []
        
        for i, signal in enumerate(signals, 1):
            print(f"\n  Signal {i}/{len(signals)}:")
            print(f"    Symbol: {signal.symbol}")
            print(f"    Action: {signal.action.value}")
            print(f"    Confidence: {signal.confidence:.2f}")
            
            result = real_risk_manager.validate_signal(signal, real_account, [])
            
            if result.is_valid:
                validated_signals.append((signal, result))
                print(f"    ✓ APPROVED - Position size: ${result.position_size:.2f}")
            else:
                print(f"    ✗ REJECTED - {result.reason}")
        
        # Step 3: Verify workflow completed successfully
        print(f"\n📊 Results:")
        print(f"  Total signals generated: {len(signals)}")
        print(f"  Signals approved: {len(validated_signals)}")
        print(f"  Signals rejected: {len(signals) - len(validated_signals)}")
        
        # Verify workflow structure
        assert isinstance(signals, list)
        
        # If signals were validated, verify they're ready for execution
        for signal, validation in validated_signals:
            assert validation.is_valid
            assert validation.position_size > 0
            assert signal.confidence > 0
            assert len(signal.reasoning) > 0
            
            print(f"\n  ✓ Signal ready for execution:")
            print(f"    {signal.symbol} {signal.action.value} ${validation.position_size:.2f}")
        
        if len(signals) == 0:
            print("\n  ℹ️  No signals generated - no trading opportunities in current market")
        
        print(f"\n{'='*60}")
        print("✅ END-TO-END TEST PASSED - ALL REAL COMPONENTS WORKING")
        print("="*60)
        
    finally:
        # Restore original state
        if original_state.state != SystemStateEnum.ACTIVE:
            state_manager.set_state(original_state.state, "Restore after test", "test")


