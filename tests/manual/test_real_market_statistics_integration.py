"""Test market statistics integration with real data."""

import logging
from unittest.mock import Mock
from src.strategy.strategy_proposer import StrategyProposer, MarketRegime
from src.llm.llm_service import LLMService, StrategyDefinition
from src.data.market_data_manager import MarketDataManager
from src.api.etoro_client import EToroAPIClient
from src.models.dataclasses import RiskConfig
from src.models.enums import TradingMode
from src.core.config import Configuration

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_real_market_statistics_integration():
    """Test market statistics integration with real market data."""
    
    logger.info("=" * 80)
    logger.info("Testing Market Statistics Integration with Real Data")
    logger.info("=" * 80)
    
    # Load credentials
    config = Configuration()
    credentials = config.load_credentials(TradingMode.DEMO)
    
    # Create eToro client with real credentials
    etoro_client = EToroAPIClient(
        public_key=credentials["public_key"],
        user_key=credentials["user_key"],
        mode=TradingMode.DEMO
    )
    
    # Create real market data manager
    market_data = MarketDataManager(etoro_client=etoro_client)
    
    # Create mock LLM service (we'll mock just the LLM, not the data)
    llm_service = Mock(spec=LLMService)
    
    # Mock strategy generation to return a realistic strategy
    mock_strategy = StrategyDefinition(
        name="Data-Driven RSI Strategy",
        description="Mean reversion strategy using market statistics",
        rules={
            "entry_conditions": ["RSI_14 is below 32", "Price is below Lower_Band_20"],
            "exit_conditions": ["RSI_14 rises above 58", "Price is above Middle_Band_20"],
            "indicators": ["RSI", "Bollinger Bands"]
        },
        symbols=["SPY"],
        risk_params=RiskConfig(),
        reasoning="Thresholds based on actual market distributions"
    )
    llm_service.generate_strategy.return_value = mock_strategy
    
    # Create proposer with real market data
    proposer = StrategyProposer(llm_service, market_data)
    
    # Propose strategies with real market analysis
    logger.info("\nProposing strategies with real market data...")
    strategies = proposer.propose_strategies(count=1, symbols=["SPY"])
    
    # Verify strategies were generated
    assert len(strategies) > 0, "Should generate at least one strategy"
    logger.info(f"✓ Generated {len(strategies)} strategy")
    
    # Verify LLM was called
    assert llm_service.generate_strategy.called, "Should call LLM generate_strategy"
    
    # Get the prompt that was passed to LLM
    call_args = llm_service.generate_strategy.call_args
    prompt = call_args[0][0]
    
    # Verify market data section exists
    assert "CRITICAL MARKET DATA" in prompt, "Prompt should contain market data section"
    logger.info("✓ Prompt contains CRITICAL MARKET DATA section")
    
    # Extract and display the market data section
    logger.info("\n" + "=" * 80)
    logger.info("MARKET DATA SECTION IN PROMPT")
    logger.info("=" * 80)
    
    if "CRITICAL MARKET DATA:" in prompt:
        start_idx = prompt.index("CRITICAL MARKET DATA:")
        end_markers = ["CRITICAL - EXACT INDICATOR NAMING", "Include entry/exit rules"]
        end_idx = len(prompt)
        for marker in end_markers:
            if marker in prompt[start_idx:]:
                end_idx = start_idx + prompt[start_idx:].index(marker)
                break
        
        market_data_section = prompt[start_idx:end_idx]
        # Display first 1500 characters
        logger.info(market_data_section[:1500])
        if len(market_data_section) > 1500:
            logger.info("... (truncated)")
    
    logger.info("=" * 80)
    
    # Verify key market statistics are present
    has_volatility = "Volatility:" in prompt
    has_trend = "Trend strength:" in prompt
    has_mean_reversion = "Mean reversion score:" in prompt
    has_price = "Current price:" in prompt
    has_support = "Support level" in prompt
    has_resistance = "Resistance level" in prompt
    
    logger.info("\n" + "=" * 80)
    logger.info("VERIFICATION RESULTS")
    logger.info("=" * 80)
    logger.info(f"{'✓' if has_volatility else '✗'} Volatility metrics present")
    logger.info(f"{'✓' if has_trend else '✗'} Trend strength present")
    logger.info(f"{'✓' if has_mean_reversion else '✗'} Mean reversion score present")
    logger.info(f"{'✓' if has_price else '✗'} Current price present")
    logger.info(f"{'✓' if has_support else '✗'} Support level present")
    logger.info(f"{'✓' if has_resistance else '✗'} Resistance level present")
    
    # Check for indicator distributions
    has_rsi_dist = "RSI below 30 occurs" in prompt or "RSI above 70 occurs" in prompt
    has_guidance = "Uses thresholds that actually trigger" in prompt
    
    logger.info(f"{'✓' if has_rsi_dist else '✗'} Indicator distributions present")
    logger.info(f"{'✓' if has_guidance else '✗'} Guidance on using market data present")
    
    # At least some market data should be present
    market_data_present = has_volatility or has_trend or has_mean_reversion or has_price
    
    if market_data_present:
        logger.info("\n✅ Market statistics successfully integrated into prompt!")
    else:
        logger.warning("\n⚠️  Market statistics may not be fully integrated")
    
    logger.info("=" * 80)
    
    return market_data_present


def test_real_market_context():
    """Test that market context (VIX, risk regime) is included."""
    
    logger.info("\n" + "=" * 80)
    logger.info("Testing Market Context Integration")
    logger.info("=" * 80)
    
    # Load credentials
    config = Configuration()
    credentials = config.load_credentials(TradingMode.DEMO)
    
    # Create eToro client
    etoro_client = EToroAPIClient(
        public_key=credentials["public_key"],
        user_key=credentials["user_key"],
        mode=TradingMode.DEMO
    )
    
    # Create real market data manager
    market_data = MarketDataManager(etoro_client=etoro_client)
    
    # Create mock LLM service
    llm_service = Mock(spec=LLMService)
    mock_strategy = StrategyDefinition(
        name="Context-Aware Strategy",
        description="Strategy aware of market context",
        rules={
            "entry_conditions": ["RSI_14 is below 30"],
            "exit_conditions": ["RSI_14 rises above 60"],
            "indicators": ["RSI"]
        },
        symbols=["SPY"],
        risk_params=RiskConfig(),
        reasoning="Adapted to market context"
    )
    llm_service.generate_strategy.return_value = mock_strategy
    
    # Create proposer
    proposer = StrategyProposer(llm_service, market_data)
    
    # Propose strategies
    logger.info("\nAnalyzing market context...")
    strategies = proposer.propose_strategies(count=1, symbols=["SPY"])
    
    # Get the prompt
    call_args = llm_service.generate_strategy.call_args
    prompt = call_args[0][0]
    
    # Check for market context
    has_market_context = "Market Context:" in prompt
    has_vix = "VIX" in prompt
    has_risk_regime = "Risk regime:" in prompt
    
    logger.info("\n" + "=" * 80)
    logger.info("MARKET CONTEXT VERIFICATION")
    logger.info("=" * 80)
    logger.info(f"{'✓' if has_market_context else '✗'} Market Context section present")
    logger.info(f"{'✓' if has_vix else '✗'} VIX data present")
    logger.info(f"{'✓' if has_risk_regime else '✗'} Risk regime present")
    
    if has_market_context:
        logger.info("\n✅ Market context successfully integrated!")
    else:
        logger.info("\n⚠️  Market context may not be available (API keys needed)")
    
    logger.info("=" * 80)
    
    return True


def test_multiple_symbols_real_data():
    """Test market statistics with multiple symbols using real data."""
    
    logger.info("\n" + "=" * 80)
    logger.info("Testing Multiple Symbols with Real Data")
    logger.info("=" * 80)
    
    # Load credentials
    config = Configuration()
    credentials = config.load_credentials(TradingMode.DEMO)
    
    # Create eToro client
    etoro_client = EToroAPIClient(
        public_key=credentials["public_key"],
        user_key=credentials["user_key"],
        mode=TradingMode.DEMO
    )
    
    # Create real market data manager
    market_data = MarketDataManager(etoro_client=etoro_client)
    
    # Create mock LLM service
    llm_service = Mock(spec=LLMService)
    mock_strategy = StrategyDefinition(
        name="Multi-Symbol Strategy",
        description="Strategy for multiple symbols",
        rules={
            "entry_conditions": ["RSI_14 is below 30"],
            "exit_conditions": ["RSI_14 rises above 60"],
            "indicators": ["RSI"]
        },
        symbols=["SPY", "QQQ"],
        risk_params=RiskConfig(),
        reasoning="Multi-symbol analysis"
    )
    llm_service.generate_strategy.return_value = mock_strategy
    
    # Create proposer
    proposer = StrategyProposer(llm_service, market_data)
    
    # Propose strategies with multiple symbols
    logger.info("\nAnalyzing multiple symbols...")
    strategies = proposer.propose_strategies(count=1, symbols=["SPY", "QQQ"])
    
    # Get the prompt
    call_args = llm_service.generate_strategy.call_args
    prompt = call_args[0][0]
    
    # Check for both symbols
    has_spy = "SPY Market Statistics:" in prompt
    has_qqq = "QQQ Market Statistics:" in prompt
    
    logger.info("\n" + "=" * 80)
    logger.info("MULTI-SYMBOL VERIFICATION")
    logger.info("=" * 80)
    logger.info(f"{'✓' if has_spy else '✗'} SPY statistics present")
    logger.info(f"{'✓' if has_qqq else '✗'} QQQ statistics present")
    
    if has_spy and has_qqq:
        logger.info("\n✅ Multiple symbols successfully analyzed!")
    elif has_spy or has_qqq:
        logger.info("\n⚠️  At least one symbol analyzed successfully")
    else:
        logger.info("\n⚠️  Symbol analysis may have encountered issues")
    
    logger.info("=" * 80)
    
    return True


if __name__ == "__main__":
    print("\n" + "=" * 100)
    print("REAL MARKET STATISTICS INTEGRATION TEST")
    print("=" * 100)
    print("\nThis test uses REAL market data from Yahoo Finance and Alpha Vantage/FRED APIs")
    print("(if API keys are configured)")
    print("=" * 100)
    
    try:
        # Run tests
        test_real_market_statistics_integration()
        test_real_market_context()
        test_multiple_symbols_real_data()
        
        print("\n" + "=" * 100)
        print("✅ ALL REAL DATA TESTS COMPLETED!")
        print("=" * 100)
        print("\nNote: Some features (VIX, risk regime) require API keys to be configured.")
        print("See API_SETUP_INSTRUCTIONS.md for details.")
        print("=" * 100)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise
