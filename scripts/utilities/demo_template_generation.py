"""Demo script showing template-based strategy generation with market statistics."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import Mock
from src.strategy.strategy_proposer import StrategyProposer, MarketRegime
from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.api.etoro_client import EToroAPIClient


def main():
    """Demonstrate template-based strategy generation."""
    print("\n" + "="*80)
    print("DEMO: Template-Based Strategy Generation with Market Statistics")
    print("="*80)
    
    # Initialize components
    print("\n1. Initializing components...")
    mock_etoro = Mock(spec=EToroAPIClient)
    market_data = MarketDataManager(mock_etoro)
    llm_service = LLMService()
    proposer = StrategyProposer(llm_service, market_data)
    print("   ✓ StrategyProposer initialized with template library")
    
    # Show available templates
    print("\n2. Available strategy templates:")
    all_templates = proposer.template_library.get_all_templates()
    print(f"   Total templates: {len(all_templates)}")
    
    regime_coverage = proposer.template_library.get_regime_coverage()
    for regime, count in regime_coverage.items():
        print(f"   - {regime.value}: {count} templates")
    
    # Generate strategies for RANGING market
    print("\n3. Generating strategies for RANGING market...")
    print("   (Using market statistics to customize parameters)")
    
    symbols = ["SPY", "QQQ"]
    strategies = proposer.generate_strategies_from_templates(
        count=5,
        symbols=symbols,
        market_regime=MarketRegime.RANGING
    )
    
    print(f"\n   Generated {len(strategies)} strategies:")
    
    for i, strategy in enumerate(strategies, 1):
        print(f"\n   {i}. {strategy.name}")
        print(f"      Type: {strategy.metadata.get('template_type', 'N/A')}")
        print(f"      Indicators: {', '.join(strategy.rules.get('indicators', []))}")
        
        # Show customized parameters
        params = strategy.metadata.get('customized_parameters', {})
        if params:
            print(f"      Parameters:")
            for key, value in params.items():
                print(f"        - {key}: {value}")
        
        # Show entry/exit conditions
        entry = strategy.rules.get('entry_conditions', [])
        exit_conds = strategy.rules.get('exit_conditions', [])
        
        if entry:
            print(f"      Entry: {entry[0]}")
        if exit_conds:
            print(f"      Exit: {exit_conds[0]}")
    
    # Show how parameters were customized
    print("\n4. Parameter Customization Example:")
    print("   Template: RSI Mean Reversion")
    print("   Default parameters: RSI oversold=30, overbought=70")
    print("   ")
    print("   Market analysis:")
    print("   - RSI < 30 occurs 0% of time (too rare)")
    print("   - RSI > 70 occurs 13% of time (common)")
    print("   ")
    print("   Customized parameters:")
    print("   - RSI oversold=35 (relaxed to get more signals)")
    print("   - RSI overbought=75 (tightened because common)")
    
    # Compare with LLM-based generation
    print("\n5. Comparison: Template-based vs LLM-based")
    print("   ")
    print("   Template-based generation:")
    print("   ✓ Fast (no LLM API calls)")
    print("   ✓ Reliable (no LLM errors)")
    print("   ✓ Data-driven (uses real market statistics)")
    print("   ✓ Consistent (same template → similar strategies)")
    print("   ✗ Less creative (limited to templates)")
    print("   ")
    print("   LLM-based generation:")
    print("   ✓ Creative (can generate novel strategies)")
    print("   ✓ Flexible (can adapt to any market condition)")
    print("   ✗ Slower (requires LLM API calls)")
    print("   ✗ Less reliable (LLM can make mistakes)")
    print("   ✗ Expensive (API costs)")
    
    print("\n" + "="*80)
    print("✅ DEMO COMPLETE")
    print("="*80)
    print("\nKey Takeaways:")
    print("1. Template-based generation is fast and reliable")
    print("2. Market statistics customize parameters to current conditions")
    print("3. Multi-source data (Yahoo Finance, Alpha Vantage, FRED) provides comprehensive analysis")
    print("4. Parameter variations ensure strategy diversity")
    print("5. No LLM required - system can run autonomously")
    print("="*80)


if __name__ == "__main__":
    main()
