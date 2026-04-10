"""Demonstration of Strategy Template Library."""

from src.strategy.strategy_proposer import MarketRegime
from src.strategy.strategy_templates import StrategyTemplateLibrary, StrategyType


def main():
    """Demonstrate the Strategy Template Library."""
    print("=" * 80)
    print("STRATEGY TEMPLATE LIBRARY DEMONSTRATION")
    print("=" * 80)
    print()
    
    # Initialize library
    library = StrategyTemplateLibrary()
    
    # Show overview
    print(f"📚 Total Templates: {library.get_template_count()}")
    print()
    
    # Show regime coverage
    print("🌍 Market Regime Coverage:")
    coverage = library.get_regime_coverage()
    for regime, count in coverage.items():
        print(f"  • {regime.value}: {count} templates")
    print()
    
    # Show templates by type
    print("📊 Templates by Strategy Type:")
    for strategy_type in StrategyType:
        templates = library.get_templates_by_type(strategy_type)
        print(f"  • {strategy_type.value}: {len(templates)} templates")
    print()
    
    # Show all templates
    print("=" * 80)
    print("ALL STRATEGY TEMPLATES")
    print("=" * 80)
    print()
    
    for i, template in enumerate(library.get_all_templates(), 1):
        print(f"{i}. {template.name}")
        print(f"   Type: {template.strategy_type.value}")
        print(f"   Description: {template.description}")
        print(f"   Market Regimes: {', '.join(r.value for r in template.market_regimes)}")
        print(f"   Required Indicators: {', '.join(template.required_indicators)}")
        print(f"   Trade Frequency: {template.expected_trade_frequency}")
        print(f"   Holding Period: {template.expected_holding_period}")
        print(f"   Risk/Reward: {template.risk_reward_ratio}")
        print()
        
        # Show entry conditions
        print("   Entry Conditions:")
        for condition in template.entry_conditions:
            print(f"     • {condition}")
        print()
        
        # Show exit conditions
        print("   Exit Conditions:")
        for condition in template.exit_conditions:
            print(f"     • {condition}")
        print()
        
        # Show default parameters
        print("   Default Parameters:")
        for param, value in template.default_parameters.items():
            print(f"     • {param}: {value}")
        print()
        print("-" * 80)
        print()
    
    # Show templates for specific regimes
    print("=" * 80)
    print("TEMPLATES BY MARKET REGIME")
    print("=" * 80)
    print()
    
    for regime in MarketRegime:
        templates = library.get_templates_for_regime(regime)
        print(f"📈 {regime.value.upper()} Market ({len(templates)} templates):")
        for template in templates:
            print(f"  • {template.name} ({template.strategy_type.value})")
        print()
    
    # Show detailed example: RSI Mean Reversion
    print("=" * 80)
    print("DETAILED EXAMPLE: RSI Mean Reversion Template")
    print("=" * 80)
    print()
    
    rsi_template = library.get_template_by_name("RSI Mean Reversion")
    if rsi_template:
        print(f"Name: {rsi_template.name}")
        print(f"Type: {rsi_template.strategy_type.value}")
        print(f"Description: {rsi_template.description}")
        print()
        print("Market Suitability:")
        for regime in rsi_template.market_regimes:
            print(f"  ✓ {regime.value}")
        print()
        print("Trading Logic:")
        print("  Entry:")
        for condition in rsi_template.entry_conditions:
            print(f"    → {condition}")
        print("  Exit:")
        for condition in rsi_template.exit_conditions:
            print(f"    → {condition}")
        print()
        print("Required Indicators:")
        for indicator in rsi_template.required_indicators:
            print(f"  • {indicator}")
        print()
        print("Default Parameters:")
        for param, value in rsi_template.default_parameters.items():
            print(f"  • {param}: {value}")
        print()
        print(f"Expected Performance:")
        print(f"  • Trade Frequency: {rsi_template.expected_trade_frequency}")
        print(f"  • Holding Period: {rsi_template.expected_holding_period}")
        print(f"  • Risk/Reward Ratio: {rsi_template.risk_reward_ratio}")
    
    print()
    print("=" * 80)
    print("DEMONSTRATION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
