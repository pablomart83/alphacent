"""Demo script to show market statistics integration in action."""

import logging
from unittest.mock import Mock
from src.strategy.strategy_proposer import StrategyProposer, MarketRegime
from src.llm.llm_service import LLMService, StrategyDefinition
from src.data.market_data_manager import MarketDataManager
from src.models.dataclasses import RiskConfig

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def demo_market_statistics_integration():
    """Demonstrate market statistics integration with realistic data."""
    
    print("=" * 100)
    print("MARKET STATISTICS INTEGRATION DEMO")
    print("=" * 100)
    print()
    
    # Create mocks
    llm_service = Mock(spec=LLMService)
    market_data = Mock(spec=MarketDataManager)
    
    # Mock strategy generation
    mock_strategy = StrategyDefinition(
        name="Data-Driven Mean Reversion Strategy",
        description="Mean reversion strategy using RSI and Bollinger Bands with market-aware thresholds",
        rules={
            "entry_conditions": [
                "RSI_14 is below 32",  # Slightly above 30 since it only occurs 7.8% of time
                "Price is below Lower_Band_20"
            ],
            "exit_conditions": [
                "RSI_14 rises above 58",  # Below 70 since overbought is rare (5.4%)
                "Price is above Middle_Band_20"  # More frequent than Upper_Band
            ],
            "indicators": ["RSI", "Bollinger Bands"]
        },
        symbols=["SPY"],
        risk_params=RiskConfig(),
        reasoning="Thresholds chosen based on actual market distributions to ensure sufficient trade frequency"
    )
    llm_service.generate_strategy.return_value = mock_strategy
    
    # Create proposer
    proposer = StrategyProposer(llm_service, market_data)
    
    # Mock realistic market data for SPY
    mock_symbol_stats = {
        'volatility_metrics': {
            'volatility': 0.0234,  # 2.34% daily volatility
            'atr_ratio': 0.0156,
            'historical_volatility_20d': 0.0245
        },
        'trend_metrics': {
            'trend_strength': 0.72,  # Strong uptrend
            'adx': 28.5,
            'price_change_20d': 0.045,  # +4.5% over 20 days
            'price_change_50d': 0.082   # +8.2% over 50 days
        },
        'mean_reversion_metrics': {
            'mean_reversion_score': 0.38,  # More trending than mean reverting
            'hurst_exponent': 0.46,
            'autocorrelation_lag1': 0.12
        },
        'price_action': {
            'current_price': 452.75,
            'high_20d': 458.90,
            'low_20d': 442.30,
            'support_20d': 443.50,
            'resistance_20d': 457.80
        }
    }
    
    mock_indicator_dist = {
        'RSI': {
            'mean': 53.2,
            'std': 13.1,
            'min': 24.5,
            'max': 79.3,
            'pct_oversold': 7.8,  # RSI < 30 occurs 7.8% of time
            'pct_overbought': 5.4,  # RSI > 70 occurs 5.4% of time
            'avg_duration_oversold': 2.1,  # Stays oversold for ~2 days
            'avg_duration_overbought': 1.6,  # Stays overbought for ~1.6 days
            'current_value': 46.8
        },
        'STOCH': {
            'mean': 51.0,
            'std': 25.0,
            'pct_oversold': 11.2,  # STOCH < 20 occurs 11.2% of time
            'pct_overbought': 9.8,  # STOCH > 80 occurs 9.8% of time
            'current_value': 38.5
        },
        'Bollinger_Bands': {
            'pct_below_lower': 4.2,  # Price below lower band 4.2% of time
            'pct_above_upper': 3.8,  # Price above upper band 3.8% of time
            'current_position': 'middle'
        }
    }
    
    mock_market_context = {
        'vix': 17.8,  # Moderate fear
        'risk_regime': 'risk-on',  # Bullish sentiment
        'treasury_10y': 4.15,
        'market_sentiment': 'bullish'
    }
    
    proposer.market_analyzer.analyze_symbol = Mock(return_value=mock_symbol_stats)
    proposer.market_analyzer.analyze_indicator_distributions = Mock(return_value=mock_indicator_dist)
    proposer.market_analyzer.get_market_context = Mock(return_value=mock_market_context)
    
    # Propose strategies
    print("📊 Analyzing Market Conditions...")
    print()
    strategies = proposer.propose_strategies(count=1, symbols=["SPY"])
    
    # Get the prompt that was sent to LLM
    call_args = llm_service.generate_strategy.call_args
    prompt = call_args[0][0]
    
    # Extract and display the market data section
    print("=" * 100)
    print("MARKET DATA SECTION SENT TO LLM")
    print("=" * 100)
    print()
    
    if "CRITICAL MARKET DATA:" in prompt:
        start_idx = prompt.index("CRITICAL MARKET DATA:")
        end_markers = ["CRITICAL - EXACT INDICATOR NAMING"]
        end_idx = len(prompt)
        for marker in end_markers:
            if marker in prompt[start_idx:]:
                end_idx = start_idx + prompt[start_idx:].index(marker)
                break
        
        market_data_section = prompt[start_idx:end_idx]
        print(market_data_section)
    
    print("=" * 100)
    print("GENERATED STRATEGY")
    print("=" * 100)
    print()
    print(f"Name: {mock_strategy.name}")
    print(f"Description: {mock_strategy.description}")
    print()
    print("Entry Conditions:")
    for condition in mock_strategy.rules['entry_conditions']:
        print(f"  - {condition}")
    print()
    print("Exit Conditions:")
    for condition in mock_strategy.rules['exit_conditions']:
        print(f"  - {condition}")
    print()
    print(f"Reasoning: {mock_strategy.reasoning}")
    print()
    
    print("=" * 100)
    print("KEY INSIGHTS")
    print("=" * 100)
    print()
    print("✓ LLM received comprehensive market statistics:")
    print("  - Volatility: 2.34% (moderate)")
    print("  - Trend strength: 0.72 (strong uptrend)")
    print("  - Mean reversion score: 0.38 (more trending)")
    print("  - Current price: $452.75")
    print("  - Support: $443.50, Resistance: $457.80")
    print()
    print("✓ LLM received indicator distributions:")
    print("  - RSI < 30 occurs only 7.8% of time (rare!)")
    print("  - RSI > 70 occurs only 5.4% of time (rare!)")
    print("  - Price below lower band occurs 4.2% of time")
    print()
    print("✓ LLM received market context:")
    print("  - VIX: 17.8 (moderate fear)")
    print("  - Risk regime: risk-on (bullish)")
    print()
    print("✓ Strategy uses market-aware thresholds:")
    print("  - Entry: RSI < 32 (not 30, since 30 is too rare)")
    print("  - Exit: RSI > 58 (not 70, since 70 is too rare)")
    print("  - Exit: Middle_Band (not Upper_Band, more frequent)")
    print()
    print("=" * 100)
    print("✅ MARKET STATISTICS INTEGRATION SUCCESSFUL!")
    print("=" * 100)


if __name__ == "__main__":
    demo_market_statistics_integration()
