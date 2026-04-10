"""Verify Strategy Template Library integrates with existing system."""

from src.strategy.strategy_templates import StrategyTemplateLibrary
from src.strategy.strategy_proposer import MarketRegime
from src.strategy.indicator_library import IndicatorLibrary


def verify_indicator_compatibility():
    """Verify that all template indicators are available in IndicatorLibrary."""
    print("=" * 80)
    print("VERIFYING INDICATOR COMPATIBILITY")
    print("=" * 80)
    print()
    
    library = StrategyTemplateLibrary()
    indicator_lib = IndicatorLibrary()
    
    # Get all unique indicators from templates
    all_indicators = set()
    for template in library.get_all_templates():
        all_indicators.update(template.required_indicators)
    
    print(f"Total unique indicators across all templates: {len(all_indicators)}")
    print()
    
    # Map template indicator names to IndicatorLibrary indicator names
    # Template uses standardized keys like "RSI_14", "SMA_20"
    # IndicatorLibrary.calculate() accepts names like "RSI", "SMA" and returns standardized keys
    indicator_name_map = {
        "RSI": "RSI",
        "SMA": "SMA",
        "EMA": "EMA",
        "MACD": "MACD",
        "ATR": "ATR",
        "STOCH": "STOCH",
        "Lower": "BBANDS",  # Bollinger Bands
        "Middle": "BBANDS",
        "Upper": "BBANDS",
        "Support": "SUPPORT_RESISTANCE",
        "Resistance": "SUPPORT_RESISTANCE",
    }
    
    # Check which indicators are available
    available_indicators = []
    missing_indicators = []
    
    available_indicator_names = indicator_lib.list_indicators()
    
    for indicator in sorted(all_indicators):
        # Extract base name from standardized key
        # e.g., "RSI_14" -> "RSI", "Lower_Band_20" -> "Lower"
        if "_" in indicator:
            base_name = indicator.split("_")[0]
        else:
            base_name = indicator
        
        # Map to IndicatorLibrary name
        lib_name = indicator_name_map.get(base_name)
        
        if lib_name and lib_name in available_indicator_names:
            available_indicators.append(indicator)
            print(f"✅ {indicator} - Available via IndicatorLibrary.calculate('{lib_name}')")
        else:
            missing_indicators.append(indicator)
            if lib_name:
                print(f"❌ {indicator} - Indicator '{lib_name}' not found in library")
            else:
                print(f"⚠️  {indicator} - Unknown indicator type '{base_name}'")
    
    print()
    print(f"Available: {len(available_indicators)}/{len(all_indicators)}")
    print(f"Missing: {len(missing_indicators)}/{len(all_indicators)}")
    print()
    
    if missing_indicators:
        print("Missing indicators:")
        for indicator in missing_indicators:
            print(f"  • {indicator}")
        print()
        print("Available indicators in library:")
        for ind in available_indicator_names:
            print(f"  • {ind}")
        print()
        return False
    else:
        print("✅ All template indicators are available in IndicatorLibrary!")
        print()
        return True


def verify_market_regime_compatibility():
    """Verify that MarketRegime enum is compatible."""
    print("=" * 80)
    print("VERIFYING MARKET REGIME COMPATIBILITY")
    print("=" * 80)
    print()
    
    library = StrategyTemplateLibrary()
    
    # Check all regimes used in templates
    regimes_used = set()
    for template in library.get_all_templates():
        regimes_used.update(template.market_regimes)
    
    print(f"Market regimes used in templates: {len(regimes_used)}")
    for regime in regimes_used:
        print(f"  • {regime.value}")
    
    print()
    print("Available MarketRegime values:")
    for regime in MarketRegime:
        print(f"  • {regime.value}")
    
    print()
    
    # Check if all used regimes are valid
    all_valid = all(regime in MarketRegime for regime in regimes_used)
    
    if all_valid:
        print("✅ All template regimes are valid MarketRegime values!")
        print()
        return True
    else:
        print("❌ Some template regimes are not valid MarketRegime values!")
        print()
        return False


def verify_template_structure():
    """Verify that templates have the correct structure for strategy generation."""
    print("=" * 80)
    print("VERIFYING TEMPLATE STRUCTURE")
    print("=" * 80)
    print()
    
    library = StrategyTemplateLibrary()
    
    all_valid = True
    for template in library.get_all_templates():
        print(f"Checking: {template.name}")
        
        # Check required fields
        checks = [
            (template.name, "name"),
            (template.description, "description"),
            (template.strategy_type, "strategy_type"),
            (len(template.market_regimes) > 0, "market_regimes"),
            (len(template.entry_conditions) > 0, "entry_conditions"),
            (len(template.exit_conditions) > 0, "exit_conditions"),
            (len(template.required_indicators) > 0, "required_indicators"),
            (len(template.default_parameters) > 0, "default_parameters"),
            (template.expected_trade_frequency, "expected_trade_frequency"),
            (template.expected_holding_period, "expected_holding_period"),
            (template.risk_reward_ratio > 0, "risk_reward_ratio"),
        ]
        
        template_valid = True
        for check, field_name in checks:
            if not check:
                print(f"  ❌ Missing or invalid: {field_name}")
                template_valid = False
                all_valid = False
        
        if template_valid:
            print(f"  ✅ All fields valid")
        
        print()
    
    if all_valid:
        print("✅ All templates have correct structure!")
        print()
        return True
    else:
        print("❌ Some templates have structural issues!")
        print()
        return False


def main():
    """Run all verification checks."""
    print()
    print("=" * 80)
    print("STRATEGY TEMPLATE LIBRARY INTEGRATION VERIFICATION")
    print("=" * 80)
    print()
    
    results = []
    
    # Run checks
    results.append(("Indicator Compatibility", verify_indicator_compatibility()))
    results.append(("Market Regime Compatibility", verify_market_regime_compatibility()))
    results.append(("Template Structure", verify_template_structure()))
    
    # Summary
    print("=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    print()
    
    all_passed = True
    for check_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{check_name}: {status}")
        if not passed:
            all_passed = False
    
    print()
    
    if all_passed:
        print("🎉 ALL VERIFICATION CHECKS PASSED!")
        print()
        print("The Strategy Template Library is fully compatible with the existing system.")
        print("Ready for integration with StrategyProposer in Task 9.10.2.")
    else:
        print("⚠️  SOME VERIFICATION CHECKS FAILED!")
        print()
        print("Please review the issues above before proceeding to Task 9.10.2.")
    
    print()
    print("=" * 80)
    
    return all_passed


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
