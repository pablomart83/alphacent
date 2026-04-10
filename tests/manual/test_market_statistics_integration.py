"""Test market statistics integration into strategy generation."""

import logging
from unittest.mock import Mock, patch, MagicMock
from src.strategy.strategy_proposer import StrategyProposer, MarketRegime
from src.llm.llm_service import LLMService, StrategyDefinition
from src.data.market_data_manager import MarketDataManager
from src.models.dataclasses import RiskConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_market_statistics_integration():
    """Test that market statistics are integrated into strategy generation."""
    
    # Create mocks
    llm_service = Mock(spec=LLMService)
    market_data = Mock(spec=MarketDataManager)
    
    # Mock historical data for market regime detection
    from src.models.dataclasses import MarketData
    mock_historical_data = [
        MarketData(timestamp=datetime.now() - timedelta(days=i), 
                   open=450.0, high=455.0, low=445.0, close=450.0 + i*0.5, volume=1000000)
        for i in range(90, 0, -1)
    ]
    market_data.get_historical_data = Mock(return_value=mock_historical_data)
    
    # Mock strategy generation
    mock_strategy = StrategyDefinition(
        name="Test Strategy",
        description="Test strategy with market data",
        rules={
            "entry_conditions": ["RSI_14 is below 30"],
            "exit_conditions": ["RSI_14 rises above 60"],
            "indicators": ["RSI"]
        },
        symbols=["SPY"],
        risk_params=RiskConfig(),
        reasoning="Test reasoning"
    )
    llm_service.generate_strategy.return_value = mock_strategy
    
    # Create proposer
    proposer = StrategyProposer(llm_service, market_data)
    
    # Mock market analyzer methods
    mock_symbol_stats = {
        'volatility_metrics': {
            'volatility': 0.025,
            'atr_ratio': 0.015
        },
        'trend_metrics': {
            'trend_strength': 0.65,
            'adx': 25.0
        },
        'mean_reversion_metrics': {
            'mean_reversion_score': 0.45,
            'hurst_exponent': 0.48
        },
        'price_action': {
            'current_price': 450.0,
            'support_20d': 440.0,
            'resistance_20d': 460.0
        }
    }
    
    mock_indicator_dist = {
        'RSI': {
            'mean': 52.3,
            'std': 12.5,
            'min': 25.0,
            'max': 78.0,
            'pct_oversold': 8.5,
            'pct_overbought': 6.2,
            'avg_duration_oversold': 2.3,
            'avg_duration_overbought': 1.8,
            'current_value': 45.0
        },
        'STOCH': {
            'mean': 50.0,
            'pct_oversold': 12.0,
            'pct_overbought': 10.0
        }
    }
    
    mock_market_context = {
        'vix': 18.5,
        'risk_regime': 'risk-on',
        'treasury_10y': 4.2
    }
    
    proposer.market_analyzer.analyze_symbol = Mock(return_value=mock_symbol_stats)
    proposer.market_analyzer.analyze_indicator_distributions = Mock(return_value=mock_indicator_dist)
    proposer.market_analyzer.get_market_context = Mock(return_value=mock_market_context)
    
    # Propose strategies
    logger.info("Testing strategy proposal with market statistics...")
    strategies = proposer.propose_strategies(count=1, symbols=["SPY"])
    
    # Verify strategies were generated
    assert len(strategies) > 0, "Should generate at least one strategy"
    logger.info(f"✓ Generated {len(strategies)} strategy")
    
    # Verify market analyzer was called
    assert proposer.market_analyzer.analyze_symbol.called, "Should call analyze_symbol"
    assert proposer.market_analyzer.analyze_indicator_distributions.called, "Should call analyze_indicator_distributions"
    assert proposer.market_analyzer.get_market_context.called, "Should call get_market_context"
    logger.info("✓ Market analyzer methods were called")
    
    # Verify LLM was called with prompt containing market data
    assert llm_service.generate_strategy.called, "Should call LLM generate_strategy"
    
    # Get the prompt that was passed to LLM
    call_args = llm_service.generate_strategy.call_args
    prompt = call_args[0][0]  # First positional argument
    
    # Verify market data is in the prompt
    assert "CRITICAL MARKET DATA" in prompt, "Prompt should contain market data section"
    assert "Volatility:" in prompt, "Prompt should contain volatility"
    assert "Trend strength:" in prompt, "Prompt should contain trend strength"
    assert "Mean reversion score:" in prompt, "Prompt should contain mean reversion score"
    assert "Current price:" in prompt, "Prompt should contain current price"
    assert "Support level" in prompt, "Prompt should contain support level"
    assert "Resistance level" in prompt, "Prompt should contain resistance level"
    logger.info("✓ Prompt contains market statistics")
    
    # Verify indicator distributions are in the prompt
    assert "RSI below 30 occurs" in prompt, "Prompt should contain RSI oversold percentage"
    assert "RSI above 70 occurs" in prompt, "Prompt should contain RSI overbought percentage"
    assert "Current RSI:" in prompt, "Prompt should contain current RSI value"
    logger.info("✓ Prompt contains indicator distributions")
    
    # Verify market context is in the prompt
    assert "Market Context:" in prompt, "Prompt should contain market context"
    assert "VIX" in prompt, "Prompt should contain VIX"
    assert "Risk regime:" in prompt, "Prompt should contain risk regime"
    logger.info("✓ Prompt contains market context")
    
    # Verify guidance about using realistic thresholds
    assert "Uses thresholds that actually trigger" in prompt, "Prompt should guide on realistic thresholds"
    assert "Use the distribution data" in prompt, "Prompt should instruct to use distribution data"
    logger.info("✓ Prompt contains guidance on using market data")
    
    logger.info("\n✅ All market statistics integration tests passed!")
    return True


def test_market_statistics_with_multiple_symbols():
    """Test that market statistics work with multiple symbols."""
    
    # Create mocks
    llm_service = Mock(spec=LLMService)
    market_data = Mock(spec=MarketDataManager)
    
    # Mock strategy generation
    mock_strategy = StrategyDefinition(
        name="Multi-Symbol Strategy",
        description="Test strategy with multiple symbols",
        rules={
            "entry_conditions": ["RSI_14 is below 30"],
            "exit_conditions": ["RSI_14 rises above 60"],
            "indicators": ["RSI"]
        },
        symbols=["SPY", "QQQ"],
        risk_params=RiskConfig(),
        reasoning="Test reasoning"
    )
    llm_service.generate_strategy.return_value = mock_strategy
    
    # Create proposer
    proposer = StrategyProposer(llm_service, market_data)
    
    # Mock market analyzer to return different stats for each symbol
    def mock_analyze_symbol(symbol, period_days=90):
        return {
            'volatility_metrics': {'volatility': 0.02 if symbol == "SPY" else 0.03},
            'trend_metrics': {'trend_strength': 0.6 if symbol == "SPY" else 0.7},
            'mean_reversion_metrics': {'mean_reversion_score': 0.5},
            'price_action': {
                'current_price': 450.0 if symbol == "SPY" else 380.0,
                'support_20d': 440.0 if symbol == "SPY" else 370.0,
                'resistance_20d': 460.0 if symbol == "SPY" else 390.0
            }
        }
    
    def mock_analyze_distributions(symbol, period_days=90):
        return {
            'RSI': {
                'mean': 52.0,
                'pct_oversold': 8.0,
                'pct_overbought': 6.0,
                'avg_duration_oversold': 2.0,
                'avg_duration_overbought': 1.5,
                'current_value': 45.0
            }
        }
    
    proposer.market_analyzer.analyze_symbol = Mock(side_effect=mock_analyze_symbol)
    proposer.market_analyzer.analyze_indicator_distributions = Mock(side_effect=mock_analyze_distributions)
    proposer.market_analyzer.get_market_context = Mock(return_value={'vix': 18.0, 'risk_regime': 'risk-on'})
    
    # Propose strategies with multiple symbols
    logger.info("Testing strategy proposal with multiple symbols...")
    strategies = proposer.propose_strategies(count=1, symbols=["SPY", "QQQ"])
    
    # Verify strategies were generated
    assert len(strategies) > 0, "Should generate at least one strategy"
    logger.info(f"✓ Generated {len(strategies)} strategy")
    
    # Verify market analyzer was called for each symbol
    assert proposer.market_analyzer.analyze_symbol.call_count == 2, "Should analyze both symbols"
    logger.info("✓ Market analyzer called for both symbols")
    
    # Get the prompt
    call_args = llm_service.generate_strategy.call_args
    prompt = call_args[0][0]
    
    # Verify both symbols are in the prompt
    assert "SPY Market Statistics:" in prompt, "Prompt should contain SPY statistics"
    assert "QQQ Market Statistics:" in prompt, "Prompt should contain QQQ statistics"
    logger.info("✓ Prompt contains statistics for both symbols")
    
    logger.info("\n✅ Multi-symbol market statistics test passed!")
    return True


def test_market_statistics_error_handling():
    """Test that strategy generation continues even if market statistics fail."""
    
    # Create mocks
    llm_service = Mock(spec=LLMService)
    market_data = Mock(spec=MarketDataManager)
    
    # Mock strategy generation
    mock_strategy = StrategyDefinition(
        name="Fallback Strategy",
        description="Strategy generated despite market data errors",
        rules={
            "entry_conditions": ["RSI_14 is below 30"],
            "exit_conditions": ["RSI_14 rises above 60"],
            "indicators": ["RSI"]
        },
        symbols=["SPY"],
        risk_params=RiskConfig(),
        reasoning="Test reasoning"
    )
    llm_service.generate_strategy.return_value = mock_strategy
    
    # Create proposer
    proposer = StrategyProposer(llm_service, market_data)
    
    # Mock market analyzer to raise exceptions
    proposer.market_analyzer.analyze_symbol = Mock(side_effect=Exception("API error"))
    proposer.market_analyzer.analyze_indicator_distributions = Mock(side_effect=Exception("API error"))
    proposer.market_analyzer.get_market_context = Mock(side_effect=Exception("API error"))
    
    # Propose strategies - should not crash
    logger.info("Testing strategy proposal with market statistics errors...")
    strategies = proposer.propose_strategies(count=1, symbols=["SPY"])
    
    # Verify strategies were still generated
    assert len(strategies) > 0, "Should generate strategies even with market data errors"
    logger.info(f"✓ Generated {len(strategies)} strategy despite errors")
    
    # Verify LLM was still called (without market data)
    assert llm_service.generate_strategy.called, "Should still call LLM"
    logger.info("✓ Strategy generation continued despite market data errors")
    
    logger.info("\n✅ Error handling test passed!")
    return True


if __name__ == "__main__":
    print("=" * 80)
    print("Testing Market Statistics Integration")
    print("=" * 80)
    
    try:
        test_market_statistics_integration()
        print()
        test_market_statistics_with_multiple_symbols()
        print()
        test_market_statistics_error_handling()
        
        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED!")
        print("=" * 80)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise
