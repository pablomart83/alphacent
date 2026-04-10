"""
Test enhanced LLM strategy generation prompts.

This test verifies that the updated prompts include:
1. Specific threshold examples (RSI < 30 for entry, > 70 for exit)
2. Bollinger Band examples (Lower_Band_20 for entry, Upper_Band_20 for exit)
3. Entry/exit pairing rules
4. Anti-patterns to avoid
5. Example of good strategy
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
    
    # Mock the EToroAPIClient
    mock_etoro = Mock(spec=EToroAPIClient)
    market_data = MarketDataManager(mock_etoro)
    
    return StrategyProposer(llm_service, market_data)


def test_prompt_contains_threshold_examples():
    """Test that prompt includes specific RSI threshold examples."""
    proposer = create_test_proposer()
    
    # Generate prompt
    prompt = proposer._create_proposal_prompt(
        regime=MarketRegime.RANGING,
        available_indicators=["RSI", "Bollinger Bands", "SMA"],
        symbols=["SPY"],
        strategy_number=1,
        total_strategies=6
    )
    
    # Verify RSI threshold examples
    assert 'RSI_14 is below 30' in prompt, "Missing RSI oversold entry example"
    assert 'RSI_14 rises above 70' in prompt, "Missing RSI overbought exit example"
    assert 'NOT below 70!' in prompt, "Missing warning about wrong RSI entry threshold"
    assert 'NOT above 30!' in prompt, "Missing warning about wrong RSI exit threshold"
    
    print("✅ Prompt contains proper RSI threshold examples")


def test_prompt_contains_bollinger_examples():
    """Test that prompt includes Bollinger Band examples."""
    proposer = create_test_proposer()
    
    prompt = proposer._create_proposal_prompt(
        regime=MarketRegime.RANGING,
        available_indicators=["RSI", "Bollinger Bands", "SMA"],
        symbols=["SPY"],
        strategy_number=1,
        total_strategies=6
    )
    
    # Verify Bollinger Band examples
    assert 'Price crosses below Lower_Band_20' in prompt, "Missing Bollinger lower band entry"
    assert 'Price crosses above Upper_Band_20' in prompt, "Missing Bollinger upper band exit"
    assert 'Price crosses above Middle_Band_20' in prompt, "Missing Bollinger middle band alternative"
    
    print("✅ Prompt contains proper Bollinger Band examples")


def test_prompt_contains_pairing_rules():
    """Test that prompt includes entry/exit pairing rules."""
    proposer = create_test_proposer()
    
    prompt = proposer._create_proposal_prompt(
        regime=MarketRegime.RANGING,
        available_indicators=["RSI", "Bollinger Bands", "SMA"],
        symbols=["SPY"],
        strategy_number=1,
        total_strategies=6
    )
    
    # Verify pairing rules
    assert 'If entry uses RSI < 30' in prompt, "Missing RSI pairing rule"
    assert 'exit MUST use RSI > 70' in prompt, "Missing RSI exit requirement"
    assert 'If entry uses Lower_Band_20' in prompt, "Missing Bollinger pairing rule"
    assert 'exit MUST use Upper_Band_20 or Middle_Band_20' in prompt, "Missing Bollinger exit requirement"
    assert 'Entry and exit conditions MUST be OPPOSITE' in prompt, "Missing opposite condition rule"
    
    print("✅ Prompt contains entry/exit pairing rules")


def test_prompt_contains_anti_patterns():
    """Test that prompt includes anti-patterns to avoid."""
    proposer = create_test_proposer()
    
    prompt = proposer._create_proposal_prompt(
        regime=MarketRegime.RANGING,
        available_indicators=["RSI", "Bollinger Bands", "SMA"],
        symbols=["SPY"],
        strategy_number=1,
        total_strategies=6
    )
    
    # Verify anti-patterns
    assert 'ANTI-PATTERNS - NEVER USE THESE:' in prompt, "Missing anti-patterns section"
    assert 'NEVER use "RSI_14 is below 70" for entry' in prompt, "Missing RSI < 70 anti-pattern"
    assert 'NEVER use "RSI_14 rises above 30" for exit' in prompt, "Missing RSI > 30 anti-pattern"
    assert 'NEVER use same threshold for entry and exit' in prompt, "Missing same threshold anti-pattern"
    assert 'NEVER use overlapping conditions' in prompt, "Missing overlapping conditions anti-pattern"
    
    print("✅ Prompt contains anti-patterns to avoid")


def test_prompt_contains_good_example():
    """Test that prompt includes example of good strategy."""
    proposer = create_test_proposer()
    
    prompt = proposer._create_proposal_prompt(
        regime=MarketRegime.RANGING,
        available_indicators=["RSI", "Bollinger Bands", "SMA"],
        symbols=["SPY"],
        strategy_number=1,
        total_strategies=6
    )
    
    # Verify good example
    assert 'EXAMPLE OF GOOD STRATEGY:' in prompt, "Missing good example section"
    assert '"name": "RSI Bollinger Mean Reversion"' in prompt, "Missing example strategy name"
    assert '"entry_conditions": [' in prompt, "Missing entry conditions in example"
    assert '"exit_conditions": [' in prompt, "Missing exit conditions in example"
    
    print("✅ Prompt contains example of good strategy")


def test_prompt_structure_for_all_regimes():
    """Test that enhanced prompts work for all market regimes."""
    proposer = create_test_proposer()
    
    regimes = [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN, MarketRegime.RANGING]
    
    for regime in regimes:
        prompt = proposer._create_proposal_prompt(
            regime=regime,
            available_indicators=["RSI", "Bollinger Bands", "SMA", "MACD"],
            symbols=["SPY", "QQQ"],
            strategy_number=3,
            total_strategies=6
        )
        
        # Verify all key sections present
        assert 'CRITICAL - PROPER THRESHOLD EXAMPLES:' in prompt
        assert 'CRITICAL - ENTRY/EXIT PAIRING RULES:' in prompt
        assert 'ANTI-PATTERNS - NEVER USE THESE:' in prompt
        assert 'EXAMPLE OF GOOD STRATEGY:' in prompt
        
        print(f"✅ Enhanced prompt structure verified for {regime.value}")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("Testing Enhanced LLM Strategy Generation Prompts")
    print("="*70 + "\n")
    
    test_prompt_contains_threshold_examples()
    test_prompt_contains_bollinger_examples()
    test_prompt_contains_pairing_rules()
    test_prompt_contains_anti_patterns()
    test_prompt_contains_good_example()
    test_prompt_structure_for_all_regimes()
    
    print("\n" + "="*70)
    print("✅ ALL TESTS PASSED - Enhanced prompts verified!")
    print("="*70 + "\n")
