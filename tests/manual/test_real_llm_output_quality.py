"""
Test real LLM output quality with enhanced prompts.

This test actually calls the LLM to generate strategies and validates:
1. Proper RSI thresholds (< 30 for entry, > 70 for exit)
2. Proper Bollinger Band usage
3. No contradictory conditions
4. Proper indicator naming
5. Strategy validation passes
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from strategy.strategy_proposer import StrategyProposer, MarketRegime
from strategy.strategy_engine import StrategyEngine
from llm.llm_service import LLMService
from data.market_data_manager import MarketDataManager
from api.etoro_client import EToroAPIClient
from models.database import Database
from unittest.mock import Mock
import re


def create_test_components():
    """Create test components."""
    llm_service = LLMService()
    mock_etoro = Mock(spec=EToroAPIClient)
    market_data = MarketDataManager(mock_etoro)
    proposer = StrategyProposer(llm_service, market_data)
    
    # Create strategy engine for validation
    db = Database()
    strategy_engine = StrategyEngine(db, market_data, llm_service)
    
    return proposer, strategy_engine


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


def check_bollinger_usage(conditions):
    """Check if Bollinger Bands are used correctly."""
    issues = []
    
    for condition in conditions:
        # Check for lower band usage
        if 'Lower_Band' in condition or 'lower band' in condition.lower():
            if 'above' in condition.lower() and 'entry' in str(conditions):
                issues.append(f"Entry uses 'above Lower_Band' (should be 'below'): {condition}")
        
        # Check for upper band usage
        if 'Upper_Band' in condition or 'upper band' in condition.lower():
            if 'below' in condition.lower() and 'exit' in str(conditions):
                issues.append(f"Exit uses 'below Upper_Band' (should be 'above'): {condition}")
    
    return issues


def check_contradictory_conditions(conditions):
    """Check for contradictory conditions in a single condition list."""
    issues = []
    
    # Check for RSI contradictions
    rsi_thresholds = extract_rsi_thresholds(conditions)
    if len(rsi_thresholds) >= 2:
        for i, (dir1, val1) in enumerate(rsi_thresholds):
            for dir2, val2 in rsi_thresholds[i+1:]:
                if dir1 == 'below' and dir2 == 'above':
                    if val1 < val2:
                        issues.append(f"Contradictory RSI: below {val1} AND above {val2}")
    
    return issues


def test_generate_strategies_with_enhanced_prompts():
    """Test generating actual strategies with enhanced prompts."""
    print("\n" + "="*70)
    print("TESTING REAL LLM OUTPUT WITH ENHANCED PROMPTS")
    print("="*70 + "\n")
    
    proposer, strategy_engine = create_test_components()
    
    # Test different market regimes
    regimes = [MarketRegime.RANGING, MarketRegime.TRENDING_UP]
    
    all_results = []
    
    for regime in regimes:
        print(f"\n{'='*70}")
        print(f"Testing {regime.value.upper()} Market Regime")
        print(f"{'='*70}\n")
        
        try:
            # Generate 3 strategies
            strategies = proposer.propose_strategies(
                count=3,
                symbols=["SPY", "QQQ"],
                market_regime=regime  # Fixed: use market_regime parameter
            )
            
            print(f"✅ Generated {len(strategies)} strategies for {regime.value}")
            
            for i, strategy in enumerate(strategies, 1):
                print(f"\n--- Strategy {i}: {strategy.name} ---")
                
                result = {
                    'regime': regime.value,
                    'name': strategy.name,
                    'entry_conditions': strategy.rules.get('entry_conditions', []),
                    'exit_conditions': strategy.rules.get('exit_conditions', []),
                    'indicators': strategy.rules.get('indicators', []),
                    'issues': []
                }
                
                # Check RSI thresholds in entry conditions
                entry_rsi = extract_rsi_thresholds(result['entry_conditions'])
                for direction, threshold in entry_rsi:
                    if direction == 'below':
                        if threshold > 35:
                            result['issues'].append(f"❌ Entry RSI threshold too high: {threshold} (should be < 35)")
                            print(f"  ❌ Entry RSI threshold too high: {threshold} (should be < 35)")
                        else:
                            print(f"  ✅ Entry RSI threshold good: {threshold}")
                
                # Check RSI thresholds in exit conditions
                exit_rsi = extract_rsi_thresholds(result['exit_conditions'])
                for direction, threshold in exit_rsi:
                    if direction == 'above':
                        if threshold < 65:
                            result['issues'].append(f"❌ Exit RSI threshold too low: {threshold} (should be > 65)")
                            print(f"  ❌ Exit RSI threshold too low: {threshold} (should be > 65)")
                        else:
                            print(f"  ✅ Exit RSI threshold good: {threshold}")
                
                # Check Bollinger Band usage
                bb_issues = check_bollinger_usage(result['entry_conditions'] + result['exit_conditions'])
                if bb_issues:
                    result['issues'].extend(bb_issues)
                    for issue in bb_issues:
                        print(f"  {issue}")
                elif 'Bollinger Bands' in result['indicators']:
                    print(f"  ✅ Bollinger Bands usage looks correct")
                
                # Check for contradictory conditions
                entry_contradictions = check_contradictory_conditions(result['entry_conditions'])
                if entry_contradictions:
                    result['issues'].extend([f"❌ Entry: {c}" for c in entry_contradictions])
                    for issue in entry_contradictions:
                        print(f"  ❌ Entry contradiction: {issue}")
                else:
                    print(f"  ✅ No contradictory entry conditions")
                
                exit_contradictions = check_contradictory_conditions(result['exit_conditions'])
                if exit_contradictions:
                    result['issues'].extend([f"❌ Exit: {c}" for c in exit_contradictions])
                    for issue in exit_contradictions:
                        print(f"  ❌ Exit contradiction: {issue}")
                else:
                    print(f"  ✅ No contradictory exit conditions")
                
                # Print conditions
                print(f"\n  Entry Conditions:")
                for cond in result['entry_conditions']:
                    print(f"    - {cond}")
                
                print(f"\n  Exit Conditions:")
                for cond in result['exit_conditions']:
                    print(f"    - {cond}")
                
                print(f"\n  Indicators: {', '.join(result['indicators'])}")
                
                # Try validation
                try:
                    validation_result = strategy_engine.validate_strategy_rules(strategy)
                    if validation_result['is_valid']:
                        print(f"\n  ✅ VALIDATION PASSED")
                    else:
                        print(f"\n  ❌ VALIDATION FAILED:")
                        for error in validation_result['errors']:
                            print(f"    - {error}")
                            result['issues'].append(f"Validation: {error}")
                except Exception as e:
                    print(f"\n  ⚠️  Validation error: {e}")
                    result['issues'].append(f"Validation exception: {e}")
                
                all_results.append(result)
        
        except Exception as e:
            print(f"❌ Error generating strategies for {regime.value}: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print(f"\n\n{'='*70}")
    print("SUMMARY OF RESULTS")
    print(f"{'='*70}\n")
    
    total_strategies = len(all_results)
    if total_strategies == 0:
        print("❌ No strategies were generated. Cannot calculate metrics.")
        return all_results
    
    strategies_with_issues = sum(1 for r in all_results if r['issues'])
    strategies_clean = total_strategies - strategies_with_issues
    
    print(f"Total strategies generated: {total_strategies}")
    print(f"Strategies with NO issues: {strategies_clean} ({strategies_clean/total_strategies*100:.1f}%)")
    print(f"Strategies with issues: {strategies_with_issues} ({strategies_with_issues/total_strategies*100:.1f}%)")
    
    if strategies_with_issues > 0:
        print(f"\n--- Strategies with Issues ---")
        for result in all_results:
            if result['issues']:
                print(f"\n{result['name']} ({result['regime']}):")
                for issue in result['issues']:
                    print(f"  - {issue}")
    
    # Calculate improvement metrics
    print(f"\n{'='*70}")
    print("IMPROVEMENT METRICS")
    print(f"{'='*70}\n")
    
    # Count specific improvements
    proper_rsi_entry = 0
    proper_rsi_exit = 0
    no_contradictions = 0
    
    for result in all_results:
        # Check RSI thresholds
        entry_rsi = extract_rsi_thresholds(result['entry_conditions'])
        for direction, threshold in entry_rsi:
            if direction == 'below' and threshold <= 35:
                proper_rsi_entry += 1
        
        exit_rsi = extract_rsi_thresholds(result['exit_conditions'])
        for direction, threshold in exit_rsi:
            if direction == 'above' and threshold >= 65:
                proper_rsi_exit += 1
        
        # Check contradictions
        if not check_contradictory_conditions(result['entry_conditions']) and \
           not check_contradictory_conditions(result['exit_conditions']):
            no_contradictions += 1
    
    print(f"Proper RSI entry thresholds (< 35): {proper_rsi_entry}/{total_strategies}")
    print(f"Proper RSI exit thresholds (> 65): {proper_rsi_exit}/{total_strategies}")
    print(f"No contradictory conditions: {no_contradictions}/{total_strategies} ({no_contradictions/total_strategies*100:.1f}%)")
    
    print(f"\n{'='*70}")
    print("EXPECTED IMPROVEMENTS FROM ENHANCED PROMPTS:")
    print(f"{'='*70}")
    print("Before: ~30% strategies with RSI < 70 for entry (BAD)")
    print("After:  Should be 0% with RSI < 70, most using RSI < 30-35 (GOOD)")
    print()
    print("Before: ~40% strategies with contradictory conditions")
    print("After:  Should be < 10% with contradictions")
    print()
    print("Before: ~50% validation pass rate")
    print("After:  Should be > 80% validation pass rate")
    print(f"{'='*70}\n")
    
    return all_results


if __name__ == "__main__":
    results = test_generate_strategies_with_enhanced_prompts()
    
    print("\n✅ Real LLM output quality test completed!")
    print("Review the results above to see if enhanced prompts improved strategy quality.\n")
