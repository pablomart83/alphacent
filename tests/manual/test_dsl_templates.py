"""Test that strategy templates use valid DSL syntax."""

import sys
sys.path.insert(0, '/Users/kuro/code/alphacent')

from src.strategy.strategy_templates import StrategyTemplateLibrary
from src.strategy.trading_dsl import TradingDSLParser


def test_all_templates_use_valid_dsl():
    """Verify all strategy templates use valid DSL syntax."""
    print("\n" + "="*80)
    print("Testing Strategy Templates DSL Syntax")
    print("="*80)
    
    library = StrategyTemplateLibrary()
    parser = TradingDSLParser()
    
    all_templates = library.get_all_templates()
    print(f"\nTotal templates: {len(all_templates)}")
    
    all_valid = True
    
    for template in all_templates:
        print(f"\n{'='*80}")
        print(f"Template: {template.name}")
        print(f"Type: {template.strategy_type.value}")
        print(f"Regimes: {[r.value for r in template.market_regimes]}")
        
        # Test entry conditions
        print(f"\nEntry Conditions ({len(template.entry_conditions)}):")
        for i, condition in enumerate(template.entry_conditions, 1):
            print(f"  {i}. {condition}")
            result = parser.parse(condition)
            if result.success:
                print(f"     ✅ Valid DSL syntax")
            else:
                print(f"     ❌ INVALID: {result.error}")
                all_valid = False
        
        # Test exit conditions
        print(f"\nExit Conditions ({len(template.exit_conditions)}):")
        for i, condition in enumerate(template.exit_conditions, 1):
            print(f"  {i}. {condition}")
            result = parser.parse(condition)
            if result.success:
                print(f"     ✅ Valid DSL syntax")
            else:
                print(f"     ❌ INVALID: {result.error}")
                all_valid = False
    
    print(f"\n{'='*80}")
    if all_valid:
        print("✅ ALL TEMPLATES USE VALID DSL SYNTAX")
    else:
        print("❌ SOME TEMPLATES HAVE INVALID DSL SYNTAX")
    print("="*80)
    
    return all_valid


def test_specific_dsl_examples():
    """Test the specific DSL examples from the task."""
    print("\n" + "="*80)
    print("Testing Specific DSL Examples from Task")
    print("="*80)
    
    parser = TradingDSLParser()
    
    examples = [
        ("RSI Mean Reversion Entry", "RSI(14) < 30"),
        ("RSI Mean Reversion Exit", "RSI(14) > 70"),
        ("Bollinger Band Bounce Entry", "CLOSE < BB_LOWER(20, 2)"),
        ("Bollinger Band Bounce Exit", "CLOSE > BB_UPPER(20, 2)"),
        ("SMA Crossover Entry", "SMA(20) CROSSES_ABOVE SMA(50)"),
        ("SMA Crossover Exit", "SMA(20) CROSSES_BELOW SMA(50)"),
        ("MACD Momentum Entry", "MACD() CROSSES_ABOVE MACD_SIGNAL()"),
        ("MACD Momentum Exit", "MACD() CROSSES_BELOW MACD_SIGNAL()"),
    ]
    
    all_valid = True
    
    for name, rule in examples:
        print(f"\n{name}:")
        print(f"  Rule: {rule}")
        result = parser.parse(rule)
        if result.success:
            print(f"  ✅ Valid DSL syntax")
        else:
            print(f"  ❌ INVALID: {result.error}")
            all_valid = False
    
    print(f"\n{'='*80}")
    if all_valid:
        print("✅ ALL EXAMPLES USE VALID DSL SYNTAX")
    else:
        print("❌ SOME EXAMPLES HAVE INVALID DSL SYNTAX")
    print("="*80)
    
    return all_valid


if __name__ == "__main__":
    # Test all templates
    templates_valid = test_all_templates_use_valid_dsl()
    
    # Test specific examples
    examples_valid = test_specific_dsl_examples()
    
    # Overall result
    print("\n" + "="*80)
    print("OVERALL RESULT")
    print("="*80)
    if templates_valid and examples_valid:
        print("✅ Task 9.11.4.4 Complete: All templates use valid DSL syntax")
        sys.exit(0)
    else:
        print("❌ Task 9.11.4.4 Failed: Some templates have invalid DSL syntax")
        sys.exit(1)
