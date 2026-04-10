"""
Test additional LLM prompt enhancements.

This test verifies the additional enhancements:
1. Guidance on avoiding contradictory conditions
2. Crossover detection examples
3. Realistic expectations guidance
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from strategy.strategy_proposer import StrategyProposer, MarketRegime
from llm.llm_service import LLMService
from data.market_data_manager import MarketDataManager
from api.etoro_client import EToroAPIClient
from unittest.mock import Mock


def create_test_proposer():
    """Create a StrategyProposer instance for testing."""
    llm_service = LLMService()
    mock_etoro = Mock(spec=EToroAPIClient)
    market_data = MarketDataManager(mock_etoro)
    return StrategyProposer(llm_service, market_data)


def test_contradictory_conditions_guidance():
    """Test that prompt includes guidance on avoiding contradictory conditions."""
    proposer = create_test_proposer()
    
    prompt = proposer._create_proposal_prompt(
        regime=MarketRegime.RANGING,
        available_indicators=["RSI", "Bollinger Bands", "SMA"],
        symbols=["SPY"],
        strategy_number=1,
        total_strategies=6
    )
    
    # Verify contradictory conditions guidance
    assert 'CRITICAL - AVOID CONTRADICTORY CONDITIONS:' in prompt, "Missing contradictory conditions section"
    assert 'BAD: Entry uses "RSI_14 is below 30" AND "RSI_14 is above 70"' in prompt, "Missing impossible condition example"
    assert 'GOOD: Entry uses "RSI_14 is below 30" AND "Price is below Lower_Band_20"' in prompt, "Missing good combination example"
    
    print("✅ Prompt contains contradictory conditions guidance")


def test_crossover_detection_guidance():
    """Test that prompt includes crossover detection guidance."""
    proposer = create_test_proposer()
    
    prompt = proposer._create_proposal_prompt(
        regime=MarketRegime.RANGING,
        available_indicators=["RSI", "Bollinger Bands", "MACD"],
        symbols=["SPY"],
        strategy_number=1,
        total_strategies=6
    )
    
    # Verify crossover detection guidance
    assert 'CRITICAL - CROSSOVER DETECTION:' in prompt, "Missing crossover detection section"
    assert 'MACD_12_26_9 crosses above MACD_12_26_9_SIGNAL' in prompt, "Missing MACD crossover example"
    assert 'Price crosses above SMA_20' in prompt, "Missing price crossover example"
    assert 'WRONG: "MACD_12_26_9 is above MACD_12_26_9_SIGNAL" (this is a state, not a crossover)' in prompt, "Missing crossover warning"
    
    print("✅ Prompt contains crossover detection guidance")


def test_realistic_expectations_guidance():
    """Test that prompt includes realistic expectations guidance."""
    proposer = create_test_proposer()
    
    prompt = proposer._create_proposal_prompt(
        regime=MarketRegime.RANGING,
        available_indicators=["RSI", "Bollinger Bands", "SMA"],
        symbols=["SPY"],
        strategy_number=1,
        total_strategies=6
    )
    
    # Verify realistic expectations guidance
    assert 'CRITICAL - REALISTIC EXPECTATIONS:' in prompt, "Missing realistic expectations section"
    assert 'Win rate: 40-60%' in prompt, "Missing win rate guidance"
    assert 'Trade frequency: 1-5 trades per month' in prompt, "Missing trade frequency guidance"
    assert 'Sharpe ratio: 1.0-2.0 is excellent' in prompt, "Missing Sharpe ratio guidance"
    assert 'Max drawdown: 10-20% is acceptable' in prompt, "Missing drawdown guidance"
    assert 'REALISTIC trading opportunities' in prompt, "Missing realistic opportunities emphasis"
    
    print("✅ Prompt contains realistic expectations guidance")


def test_llm_service_crossover_examples():
    """Test that LLMService interpret_trading_rule includes crossover examples."""
    llm_service = LLMService()
    
    # Create a mock context
    context = {
        "available_indicators": ["RSI", "MACD", "SMA"],
        "data_columns": ["open", "high", "low", "close", "volume"]
    }
    
    # We can't actually call the LLM, but we can verify the prompt would be correct
    # by checking the method exists and has the right structure
    assert hasattr(llm_service, 'interpret_trading_rule'), "Missing interpret_trading_rule method"
    
    # Read the source to verify crossover examples are in the prompt
    import inspect
    source = inspect.getsource(llm_service.interpret_trading_rule)
    
    assert 'For crossovers: detect when indicator crosses above/below another' in source, "Missing crossover rule"
    assert 'Bullish crossover:' in source, "Missing bullish crossover example"
    assert 'Bearish crossover:' in source, "Missing bearish crossover example"
    assert 'MACD crosses above signal line' in source, "Missing MACD crossover example"
    assert 'Price crosses below lower Bollinger Band' in source, "Missing price crossover example"
    
    print("✅ LLMService contains crossover detection examples")


def test_enhanced_prompt_completeness():
    """Test that all enhancements are present together."""
    proposer = create_test_proposer()
    
    prompt = proposer._create_proposal_prompt(
        regime=MarketRegime.TRENDING_UP,
        available_indicators=["RSI", "Bollinger Bands", "SMA", "MACD", "ATR"],
        symbols=["SPY", "QQQ", "DIA"],
        strategy_number=3,
        total_strategies=6
    )
    
    # Verify all major sections are present
    sections = [
        'CRITICAL - EXACT INDICATOR NAMING CONVENTION:',
        'CRITICAL - PROPER THRESHOLD EXAMPLES:',
        'CRITICAL - ENTRY/EXIT PAIRING RULES:',
        'ANTI-PATTERNS - NEVER USE THESE:',
        'EXAMPLE OF GOOD STRATEGY:',
        'CRITICAL - AVOID CONTRADICTORY CONDITIONS:',
        'CRITICAL - CROSSOVER DETECTION:',
        'CRITICAL - REALISTIC EXPECTATIONS:'
    ]
    
    for section in sections:
        assert section in prompt, f"Missing section: {section}"
    
    print("✅ All enhancement sections present in prompt")


def test_prompt_length_reasonable():
    """Test that enhanced prompt is not excessively long."""
    proposer = create_test_proposer()
    
    prompt = proposer._create_proposal_prompt(
        regime=MarketRegime.RANGING,
        available_indicators=["RSI", "Bollinger Bands", "SMA"],
        symbols=["SPY"],
        strategy_number=1,
        total_strategies=6
    )
    
    # Prompt should be comprehensive but not excessive
    # Typical LLM context limits are 4096-8192 tokens
    # Rough estimate: 1 token ≈ 4 characters
    # So 8000 characters ≈ 2000 tokens (reasonable)
    prompt_length = len(prompt)
    
    assert prompt_length < 12000, f"Prompt too long: {prompt_length} characters (should be < 12000)"
    assert prompt_length > 3000, f"Prompt too short: {prompt_length} characters (should be > 3000)"
    
    print(f"✅ Prompt length reasonable: {prompt_length} characters (~{prompt_length // 4} tokens)")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("Testing Additional LLM Prompt Enhancements")
    print("="*70 + "\n")
    
    test_contradictory_conditions_guidance()
    test_crossover_detection_guidance()
    test_realistic_expectations_guidance()
    test_llm_service_crossover_examples()
    test_enhanced_prompt_completeness()
    test_prompt_length_reasonable()
    
    print("\n" + "="*70)
    print("✅ ALL ADDITIONAL ENHANCEMENTS VERIFIED!")
    print("="*70 + "\n")
    
    print("Summary of Enhancements:")
    print("  1. ✅ Contradictory conditions guidance (avoid impossible combinations)")
    print("  2. ✅ Crossover detection examples (proper shift() usage)")
    print("  3. ✅ Realistic expectations (win rate, trade frequency, Sharpe)")
    print("  4. ✅ Enhanced LLMService rule interpretation (crossover support)")
    print("  5. ✅ All sections integrated without excessive length")
    print()
