"""Test that market data is properly formatted in the LLM prompt."""

import logging
from unittest.mock import Mock
from src.strategy.strategy_proposer import StrategyProposer, MarketRegime
from src.llm.llm_service import LLMService, StrategyDefinition
from src.data.market_data_manager import MarketDataManager
from src.models.dataclasses import RiskConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_prompt_contains_all_market_data():
    """Test that the prompt contains all expected market data fields."""
    
    # Create mocks
    llm_service = Mock(spec=LLMService)
    market_data = Mock(spec=MarketDataManager)
    
    # Mock strategy generation
    mock_strategy = StrategyDefinition(
        name="Data-Driven Strategy",
        description="Strategy using market statistics",
        rules={
            "entry_conditions": ["RSI_14 is below 30", "Price is below Lower_Band_20"],
            "exit_conditions": ["RSI_14 rises above 60", "Price is above Middle_Band_20"],
            "indicators": ["RSI", "Bollinger Bands"]
        },
        symbols=["SPY"],
        risk_params=RiskConfig(),
        reasoning="Based on market statistics"
    )
    llm_service.generate_strategy.return_value = mock_strategy
    
    # Create proposer
    proposer = StrategyProposer(llm_service, market_data)
    
    # Mock comprehensive market data
    mock_symbol_stats = {
        'volatility_metrics': {
            'volatility': 0.0234,
            'atr_ratio': 0.0156,
            'historical_volatility_20d': 0.0245
        },
        'trend_metrics': {
            'trend_strength': 0.72,
            'adx': 28.5,
            'price_change_20d': 0.045,
            'price_change_50d': 0.082
        },
        'mean_reversion_metrics': {
            'mean_reversion_score': 0.38,
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
            'pct_oversold': 7.8,
            'pct_overbought': 5.4,
            'avg_duration_oversold': 2.1,
            'avg_duration_overbought': 1.6,
            'current_value': 46.8
        },
        'STOCH': {
            'mean': 51.0,
            'std': 25.0,
            'pct_oversold': 11.2,
            'pct_overbought': 9.8,
            'current_value': 38.5
        },
        'Bollinger_Bands': {
            'pct_below_lower': 4.2,
            'pct_above_upper': 3.8,
            'current_position': 'middle'
        }
    }
    
    mock_market_context = {
        'vix': 17.8,
        'risk_regime': 'risk-on',
        'treasury_10y': 4.15,
        'market_sentiment': 'bullish'
    }
    
    proposer.market_analyzer.analyze_symbol = Mock(return_value=mock_symbol_stats)
    proposer.market_analyzer.analyze_indicator_distributions = Mock(return_value=mock_indicator_dist)
    proposer.market_analyzer.get_market_context = Mock(return_value=mock_market_context)
    
    # Propose strategies
    logger.info("Testing comprehensive market data in prompt...")
    strategies = proposer.propose_strategies(count=1, symbols=["SPY"])
    
    # Get the prompt
    call_args = llm_service.generate_strategy.call_args
    prompt = call_args[0][0]
    
    logger.info("\n" + "="*80)
    logger.info("GENERATED PROMPT EXCERPT:")
    logger.info("="*80)
    
    # Extract and display the market data section
    if "CRITICAL MARKET DATA:" in prompt:
        start_idx = prompt.index("CRITICAL MARKET DATA:")
        # Find the end of market data section (before the next major section)
        end_markers = ["CRITICAL - EXACT INDICATOR NAMING", "Include entry/exit rules"]
        end_idx = len(prompt)
        for marker in end_markers:
            if marker in prompt[start_idx:]:
                end_idx = start_idx + prompt[start_idx:].index(marker)
                break
        
        market_data_section = prompt[start_idx:end_idx]
        logger.info(market_data_section[:1000])  # First 1000 chars
        logger.info("...")
    
    logger.info("="*80 + "\n")
    
    # Verify all key market statistics are present
    assert "Volatility: 2.3%" in prompt, "Should contain volatility percentage"
    assert "Trend strength: 0.72" in prompt, "Should contain trend strength"
    assert "Mean reversion score: 0.38" in prompt, "Should contain mean reversion score"
    assert "Current price: $452.75" in prompt, "Should contain current price"
    assert "Support level (20d): $443.50" in prompt, "Should contain support level"
    assert "Resistance level (20d): $457.80" in prompt, "Should contain resistance level"
    logger.info("✓ All price action metrics present")
    
    # Verify RSI distribution data
    assert "RSI below 30 occurs 7.8% of time" in prompt, "Should contain RSI oversold percentage"
    assert "RSI above 70 occurs 5.4% of time" in prompt, "Should contain RSI overbought percentage"
    assert "avg duration: 2.1 days" in prompt, "Should contain RSI oversold duration"
    assert "Current RSI: 46.8" in prompt, "Should contain current RSI value"
    logger.info("✓ RSI distribution data present")
    
    # Verify Stochastic distribution data
    assert "Stochastic below 20 occurs 11.2% of time" in prompt, "Should contain Stochastic oversold"
    assert "Stochastic above 80 occurs 9.8% of time" in prompt, "Should contain Stochastic overbought"
    logger.info("✓ Stochastic distribution data present")
    
    # Verify Bollinger Bands distribution data
    assert "Price below lower band occurs 4.2% of time" in prompt, "Should contain BB lower band percentage"
    assert "Price above upper band occurs 3.8% of time" in prompt, "Should contain BB upper band percentage"
    logger.info("✓ Bollinger Bands distribution data present")
    
    # Verify market context
    assert "VIX (market fear): 17.8" in prompt, "Should contain VIX"
    assert "Risk regime: risk-on" in prompt, "Should contain risk regime"
    logger.info("✓ Market context data present")
    
    # Verify guidance on using the data
    assert "Uses thresholds that actually trigger" in prompt, "Should guide on realistic thresholds"
    assert "Accounts for the current volatility level" in prompt, "Should guide on volatility"
    assert "Respects actual support/resistance levels" in prompt, "Should guide on support/resistance"
    assert "Considers the mean reversion vs trending characteristics" in prompt, "Should guide on regime"
    assert "Use the distribution data to choose realistic thresholds" in prompt, "Should guide on distributions"
    logger.info("✓ All guidance instructions present")
    
    logger.info("\n✅ Prompt contains all expected market data and guidance!")
    return True


def test_prompt_adapts_to_market_conditions():
    """Test that prompt guidance adapts based on actual market statistics."""
    
    # Create mocks
    llm_service = Mock(spec=LLMService)
    market_data = Mock(spec=MarketDataManager)
    
    mock_strategy = StrategyDefinition(
        name="Adaptive Strategy",
        description="Strategy adapted to market conditions",
        rules={
            "entry_conditions": ["RSI_14 is below 35"],
            "exit_conditions": ["RSI_14 rises above 65"],
            "indicators": ["RSI"]
        },
        symbols=["SPY"],
        risk_params=RiskConfig(),
        reasoning="Adapted thresholds"
    )
    llm_service.generate_strategy.return_value = mock_strategy
    
    # Create proposer
    proposer = StrategyProposer(llm_service, market_data)
    
    # Test Case 1: High volatility market
    logger.info("\nTest Case 1: High Volatility Market")
    high_vol_stats = {
        'volatility_metrics': {'volatility': 0.045},  # 4.5% volatility (high)
        'trend_metrics': {'trend_strength': 0.3},
        'mean_reversion_metrics': {'mean_reversion_score': 0.7},
        'price_action': {'current_price': 450.0, 'support_20d': 430.0, 'resistance_20d': 470.0}
    }
    
    proposer.market_analyzer.analyze_symbol = Mock(return_value=high_vol_stats)
    proposer.market_analyzer.analyze_indicator_distributions = Mock(return_value={})
    proposer.market_analyzer.get_market_context = Mock(return_value={'vix': 28.0, 'risk_regime': 'risk-off'})
    
    strategies = proposer.propose_strategies(count=1, symbols=["SPY"])
    prompt = llm_service.generate_strategy.call_args[0][0]
    
    assert "Volatility: 4.5%" in prompt, "Should show high volatility"
    assert "VIX (market fear): 28.0" in prompt, "Should show elevated VIX"
    assert "Risk regime: risk-off" in prompt, "Should show risk-off regime"
    logger.info("✓ High volatility conditions reflected in prompt")
    
    # Test Case 2: Strong trending market
    logger.info("\nTest Case 2: Strong Trending Market")
    trending_stats = {
        'volatility_metrics': {'volatility': 0.018},  # 1.8% volatility (low)
        'trend_metrics': {'trend_strength': 0.85},  # Strong trend
        'mean_reversion_metrics': {'mean_reversion_score': 0.2},  # Low mean reversion
        'price_action': {'current_price': 480.0, 'support_20d': 465.0, 'resistance_20d': 495.0}
    }
    
    proposer.market_analyzer.analyze_symbol = Mock(return_value=trending_stats)
    proposer.market_analyzer.analyze_indicator_distributions = Mock(return_value={})
    proposer.market_analyzer.get_market_context = Mock(return_value={'vix': 14.0, 'risk_regime': 'risk-on'})
    
    strategies = proposer.propose_strategies(count=1, symbols=["SPY"])
    prompt = llm_service.generate_strategy.call_args[0][0]
    
    assert "Volatility: 1.8%" in prompt, "Should show low volatility"
    assert "Trend strength: 0.85" in prompt, "Should show strong trend"
    assert "Mean reversion score: 0.20" in prompt, "Should show low mean reversion"
    logger.info("✓ Strong trending conditions reflected in prompt")
    
    # Test Case 3: Rare indicator conditions
    logger.info("\nTest Case 3: Rare Indicator Conditions")
    rare_conditions_dist = {
        'RSI': {
            'mean': 55.0,
            'pct_oversold': 2.1,  # Very rare
            'pct_overbought': 1.8,  # Very rare
            'avg_duration_oversold': 0.8,
            'avg_duration_overbought': 0.6,
            'current_value': 58.0
        }
    }
    
    proposer.market_analyzer.analyze_symbol = Mock(return_value=high_vol_stats)
    proposer.market_analyzer.analyze_indicator_distributions = Mock(return_value=rare_conditions_dist)
    proposer.market_analyzer.get_market_context = Mock(return_value={})
    
    strategies = proposer.propose_strategies(count=1, symbols=["SPY"])
    prompt = llm_service.generate_strategy.call_args[0][0]
    
    assert "RSI below 30 occurs 2.1% of time" in prompt, "Should show rare oversold condition"
    assert "RSI above 70 occurs 1.8% of time" in prompt, "Should show rare overbought condition"
    assert "If RSI < 30 only occurs 5% of the time" in prompt, "Should warn about rare conditions"
    logger.info("✓ Rare indicator conditions reflected with warning")
    
    logger.info("\n✅ Prompt adapts correctly to different market conditions!")
    return True


if __name__ == "__main__":
    print("=" * 80)
    print("Testing Market Data Content in LLM Prompts")
    print("=" * 80)
    
    try:
        test_prompt_contains_all_market_data()
        print()
        test_prompt_adapts_to_market_conditions()
        
        print("\n" + "=" * 80)
        print("✅ ALL PROMPT CONTENT TESTS PASSED!")
        print("=" * 80)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise
