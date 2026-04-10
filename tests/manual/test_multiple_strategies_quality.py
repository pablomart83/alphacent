"""
Test multiple strategy generations to measure improvement.
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
        match = re.search(r'RSI_\d+\s+(?:is\s+)?(?:below|<)\s+(\d+)', condition, re.IGNORECASE)
        if match:
            thresholds.append(('below', int(match.group(1))))
        
        match = re.search(r'RSI_\d+\s+(?:rises\s+)?(?:above|>)\s+(\d+)', condition, re.IGNORECASE)
        if match:
            thresholds.append(('above', int(match.group(1))))
    
    return thresholds


print("\n" + "="*70)
print("TESTING MULTIPLE STRATEGIES WITH ENHANCED PROMPTS")
print("="*70 + "\n")

# Create components
llm_service = LLMService()
mock_etoro = Mock(spec=EToroAPIClient)
market_data = MarketDataManager(mock_etoro)
proposer = StrategyProposer(llm_service, market_data)

print("Generating 3 strategies for RANGING market...")
print("(This will take 2-3 minutes as the LLM generates each strategy)\n")

results = []

try:
    strategies = proposer.propose_strategies(
        count=3,
        symbols=["SPY", "QQQ"],
        market_regime=MarketRegime.RANGING
    )
    
    print(f"✅ Generated {len(strategies)} strategies\n")
    
    for i, strategy in enumerate(strategies, 1):
        print(f"\n{'='*70}")
        print(f"STRATEGY {i}: {strategy.name}")
        print(f"{'='*70}\n")
        
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
        
        # Analyze
        result = {
            'name': strategy.name,
            'proper_rsi_entry': False,
            'proper_rsi_exit': False,
            'bad_rsi_entry': False,
            'bad_rsi_exit': False,
            'uses_bollinger': 'Bollinger Bands' in indicators,
            'issues': []
        }
        
        # Check RSI thresholds
        entry_rsi = extract_rsi_thresholds(entry_conditions)
        for direction, threshold in entry_rsi:
            if direction == 'below':
                if threshold <= 35:
                    result['proper_rsi_entry'] = True
                    print(f"\n✅ Entry RSI threshold: {threshold} (GOOD)")
                elif threshold >= 70:
                    result['bad_rsi_entry'] = True
                    result['issues'].append(f"Entry RSI >= 70: {threshold}")
                    print(f"\n❌ Entry RSI threshold: {threshold} (BAD - too high)")
                else:
                    print(f"\n⚠️  Entry RSI threshold: {threshold} (ACCEPTABLE)")
        
        exit_rsi = extract_rsi_thresholds(exit_conditions)
        for direction, threshold in exit_rsi:
            if direction == 'above':
                if threshold >= 65:
                    result['proper_rsi_exit'] = True
                    print(f"✅ Exit RSI threshold: {threshold} (GOOD)")
                elif threshold <= 30:
                    result['bad_rsi_exit'] = True
                    result['issues'].append(f"Exit RSI <= 30: {threshold}")
                    print(f"❌ Exit RSI threshold: {threshold} (BAD - too low)")
                else:
                    print(f"⚠️  Exit RSI threshold: {threshold} (ACCEPTABLE)")
        
        # Check for bad patterns
        all_text = ' '.join(entry_conditions + exit_conditions).lower()
        if 'below 70' in all_text or '< 70' in all_text:
            if not any('below 30' in c.lower() or '< 30' in c for c in entry_conditions):
                result['issues'].append("Uses 'below 70' pattern")
                print("❌ Uses 'below 70' pattern (too common)")
        
        if 'above 30' in all_text or '> 30' in all_text:
            if not any('above 70' in c.lower() or '> 70' in c for c in exit_conditions):
                result['issues'].append("Uses 'above 30' pattern")
                print("❌ Uses 'above 30' pattern (too common)")
        
        results.append(result)
    
    # Summary
    print(f"\n\n{'='*70}")
    print("SUMMARY OF RESULTS")
    print(f"{'='*70}\n")
    
    total = len(results)
    proper_entry = sum(1 for r in results if r['proper_rsi_entry'])
    proper_exit = sum(1 for r in results if r['proper_rsi_exit'])
    bad_entry = sum(1 for r in results if r['bad_rsi_entry'])
    bad_exit = sum(1 for r in results if r['bad_rsi_exit'])
    clean = sum(1 for r in results if not r['issues'])
    
    print(f"Total strategies: {total}")
    print(f"Strategies with proper RSI entry (≤ 35): {proper_entry}/{total} ({proper_entry/total*100:.0f}%)")
    print(f"Strategies with proper RSI exit (≥ 65): {proper_exit}/{total} ({proper_exit/total*100:.0f}%)")
    print(f"Strategies with BAD RSI entry (≥ 70): {bad_entry}/{total} ({bad_entry/total*100:.0f}%)")
    print(f"Strategies with BAD RSI exit (≤ 30): {bad_exit}/{total} ({bad_exit/total*100:.0f}%)")
    print(f"Strategies with NO issues: {clean}/{total} ({clean/total*100:.0f}%)")
    
    print(f"\n{'='*70}")
    print("COMPARISON TO BASELINE (from Task 9.6)")
    print(f"{'='*70}\n")
    print("BEFORE Enhanced Prompts (Task 9.6):")
    print("  - ~30% had indicator naming errors")
    print("  - ~40% validation pass rate")
    print("  - Strategies generated 0-1 trades per 90 days")
    print("  - Many used RSI < 70 for entry (too common)")
    print()
    print("AFTER Enhanced Prompts (Task 9.8.2 + Additional):")
    print(f"  - {proper_entry}/{total} ({proper_entry/total*100:.0f}%) use proper RSI entry thresholds")
    print(f"  - {proper_exit}/{total} ({proper_exit/total*100:.0f}%) use proper RSI exit thresholds")
    print(f"  - {bad_entry}/{total} ({bad_entry/total*100:.0f}%) use bad RSI entry thresholds")
    print(f"  - {clean}/{total} ({clean/total*100:.0f}%) have no issues")
    print()
    
    if bad_entry == 0 and bad_exit == 0:
        print("🎉 EXCELLENT! No strategies use the bad patterns we warned against!")
        print("   Enhanced prompts are successfully preventing common mistakes.")
    elif bad_entry + bad_exit <= 1:
        print("✅ GOOD! Very few strategies use bad patterns.")
        print("   Enhanced prompts are working well.")
    else:
        print("⚠️  Some strategies still use bad patterns.")
        print("   Enhanced prompts may need further refinement.")
    
    print()

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
