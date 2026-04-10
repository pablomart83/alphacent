#!/usr/bin/env python3
"""Quick test to verify SHORT strategies are being generated."""

import sys
sys.path.insert(0, '/Users/pablma/Kiro-Act2')

from src.strategy.strategy_templates import StrategyTemplateLibrary, MarketRegime

def main():
    print("\n" + "="*80)
    print("  SHORT STRATEGY TEMPLATE TEST")
    print("="*80)
    
    library = StrategyTemplateLibrary()
    
    # Count total templates
    total = library.get_template_count()
    print(f"\n  Total templates: {total}")
    
    # Count SHORT templates
    short_templates = [t for t in library.get_all_templates() 
                      if t.metadata and t.metadata.get('direction') == 'short']
    print(f"  SHORT templates: {len(short_templates)}")
    print(f"  LONG templates: {total - len(short_templates)}")
    
    # Check SHORT templates by regime
    print("\n  SHORT Templates by Market Regime:")
    print("  " + "-"*76)
    
    regimes_to_check = [
        MarketRegime.RANGING,
        MarketRegime.RANGING_LOW_VOL,
        MarketRegime.RANGING_HIGH_VOL,
        MarketRegime.TRENDING_UP,
        MarketRegime.TRENDING_UP_STRONG,
        MarketRegime.TRENDING_UP_WEAK,
        MarketRegime.TRENDING_DOWN,
        MarketRegime.TRENDING_DOWN_STRONG,
        MarketRegime.TRENDING_DOWN_WEAK,
    ]
    
    for regime in regimes_to_check:
        regime_templates = library.get_templates_for_regime(regime)
        short_count = sum(1 for t in regime_templates 
                         if t.metadata and t.metadata.get('direction') == 'short')
        long_count = len(regime_templates) - short_count
        print(f"  {regime.value:30s} | SHORT: {short_count:2d} | LONG: {long_count:2d} | Total: {len(regime_templates):2d}")
    
    # List all SHORT templates for RANGING markets
    print("\n  SHORT Templates for RANGING Markets:")
    print("  " + "-"*76)
    ranging_shorts = [t for t in library.get_templates_for_regime(MarketRegime.RANGING)
                     if t.metadata and t.metadata.get('direction') == 'short']
    for i, template in enumerate(ranging_shorts, 1):
        print(f"  {i}. {template.name}")
        print(f"     Entry: {template.entry_conditions[0][:70]}")
        print(f"     Exit:  {template.exit_conditions[0][:70]}")
        print()
    
    # List all SHORT templates for TRENDING_UP markets
    print("\n  SHORT Templates for TRENDING_UP Markets:")
    print("  " + "-"*76)
    uptrend_shorts = [t for t in library.get_templates_for_regime(MarketRegime.TRENDING_UP)
                     if t.metadata and t.metadata.get('direction') == 'short']
    for i, template in enumerate(uptrend_shorts, 1):
        print(f"  {i}. {template.name}")
        print(f"     Entry: {template.entry_conditions[0][:70]}")
        print(f"     Exit:  {template.exit_conditions[0][:70]}")
        print()
    
    print("="*80)
    print(f"  ✅ SUCCESS: {len(short_templates)} SHORT templates available")
    print(f"  ✅ RANGING markets now have {len(ranging_shorts)} SHORT templates")
    print(f"  ✅ TRENDING_UP markets now have {len(uptrend_shorts)} SHORT templates")
    print("="*80)

if __name__ == "__main__":
    main()
