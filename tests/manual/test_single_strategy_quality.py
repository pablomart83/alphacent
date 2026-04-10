"""
Quick test of single strategy generation with enhanced prompts.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from strategy.strategy_proposer import StrategyProposer, MarketRegime
from llm.llm_service import LLMService
from data.market_data_manager import MarketDataManager
from api.etoro_client import EToroAPIClient
from unittest.mock import Mock
import re


def extract_rsi_thresholds(conditions):
    """Extract RSI thresholds from conditions."""
    thresholds = []
    for condition in conditions:
        # Match patterns like "RSI_14 is below 30" or "RSI_14 < 30"
        match = re.search(r'RSI_\d+\s+(?:is\s+)?(?:below|<)\s+(\d+)', condition, re.IGNORECASE)
        if match:
            thresholds.append(('below', int(match.group(1))))
        
        # Match patterns like "RSI_14 rises above 70" or "RSI_14 > 70"
        match = re.search(r'RSI_\d+\s+(?:rises\s+)?(?:above|>)\s+(\d+)', condition, re.IGNORECASE)
        if match:
            thresholds.append(('above', int(match.group(1))))
    
    return thresholds


print("\n" + "="*70)
print("QUICK TEST: Single Strategy Generation with Enhanced Prompts")
print("="*70 + "\n")

# Create components
llm_service = LLMService()
mock_etoro = Mock(spec=EToroAPIClient)
market_data = MarketDataManager(mock_etoro)
proposer = StrategyProposer(llm_service, market_data)

print("Generating 1 strategy for RANGING market...")
print("(This will take 30-60 seconds as the LLM generates the strategy)\n")

try:
    strategies = proposer.propose_strategies(
        count=1,
        symbols=["SPY"],
        market_regime=MarketRegime.RANGING
    )
    
    if not strategies:
        print("❌ No strategies generated")
        sys.exit(1)
    
    strategy = strategies[0]
    
    print(f"✅ Generated strategy: {strategy.name}\n")
    print(f"Description: {strategy.description}\n")
    
    entry_conditions = strategy.rules.get('entry_conditions', [])
    exit_conditions = strategy.rules.get('exit_conditions', [])
    indicators = strategy.rules.get('indicators', [])
    
    print("Entry Conditions:")
    for cond in entry_conditions:
        print(f"  - {cond}")
    
    print("\nExit Conditions:")
    for cond in exit_conditions:
        print(f"  - {cond}")
    
    print(f"\nIndicators: {', '.join(indicators)}")
    
    # Analyze quality
    print("\n" + "="*70)
    print("QUALITY ANALYSIS")
    print("="*70 + "\n")
    
    issues = []
    
    # Check RSI thresholds
    entry_rsi = extract_rsi_thresholds(entry_conditions)
    for direction, threshold in entry_rsi:
        if direction == 'below':
            if threshold > 35:
                issues.append(f"❌ Entry RSI threshold too high: {threshold} (should be ≤ 35)")
                print(f"❌ Entry RSI threshold: {threshold} (TOO HIGH - should be ≤ 35)")
            else:
                print(f"✅ Entry RSI threshold: {threshold} (GOOD)")
    
    exit_rsi = extract_rsi_thresholds(exit_conditions)
    for direction, threshold in exit_rsi:
        if direction == 'above':
            if threshold < 65:
                issues.append(f"❌ Exit RSI threshold too low: {threshold} (should be ≥ 65)")
                print(f"❌ Exit RSI threshold: {threshold} (TOO LOW - should be ≥ 65)")
            else:
                print(f"✅ Exit RSI threshold: {threshold} (GOOD)")
    
    # Check for Bollinger Bands
    if 'Bollinger Bands' in indicators:
        has_lower_band = any('Lower_Band' in c or 'lower band' in c.lower() for c in entry_conditions)
        has_upper_band = any('Upper_Band' in c or 'upper band' in c.lower() for c in exit_conditions)
        
        if has_lower_band:
            print("✅ Uses Lower Bollinger Band for entry (mean reversion)")
        if has_upper_band:
            print("✅ Uses Upper Bollinger Band for exit (mean reversion)")
    
    # Check for contradictions
    all_conditions = entry_conditions + exit_conditions
    has_below_30 = any('below 30' in c.lower() or '< 30' in c for c in all_conditions)
    has_above_70 = any('above 70' in c.lower() or '> 70' in c for c in all_conditions)
    has_below_70 = any('below 70' in c.lower() or '< 70' in c for c in all_conditions)
    has_above_30 = any('above 30' in c.lower() or '> 30' in c for c in all_conditions)
    
    if has_below_70 and not has_below_30:
        issues.append("❌ Uses 'below 70' threshold (too common)")
        print("❌ Uses 'below 70' threshold (TOO COMMON - should use < 30)")
    
    if has_above_30 and not has_above_70:
        issues.append("❌ Uses 'above 30' threshold (too common)")
        print("❌ Uses 'above 30' threshold (TOO COMMON - should use > 70)")
    
    # Summary
    print("\n" + "="*70)
    print("RESULT")
    print("="*70 + "\n")
    
    if not issues:
        print("✅ EXCELLENT! Strategy follows all enhanced prompt guidelines:")
        print("   - Proper RSI thresholds (< 35 for entry, > 65 for exit)")
        print("   - No contradictory conditions")
        print("   - Proper indicator usage")
        print("\n🎉 Enhanced prompts are working as intended!")
    else:
        print(f"⚠️  Strategy has {len(issues)} issue(s):")
        for issue in issues:
            print(f"   {issue}")
        print("\n💡 Enhanced prompts may need further refinement.")
    
    print()

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
