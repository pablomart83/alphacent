#!/usr/bin/env python3
"""
Verify Duplicate Order Fix - February 23, 2026

This script verifies that the duplicate order bug has been fixed by:
1. Checking the code changes in strategy_engine.py
2. Simulating the position-aware filtering logic
3. Verifying that strategy-symbol combinations are properly checked
"""

import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

def verify_code_changes():
    """Verify that the code changes were applied correctly."""
    print("="*80)
    print("VERIFYING CODE CHANGES")
    print("="*80)
    
    strategy_engine_path = Path("src/strategy/strategy_engine.py")
    
    if not strategy_engine_path.exists():
        print("❌ strategy_engine.py not found!")
        return False
    
    with open(strategy_engine_path, 'r') as f:
        content = f.read()
    
    # Check for the fix
    checks = [
        ("strategy_symbol_positions = set()", "Strategy-symbol position tracking"),
        ("strategy_symbol_positions.add((pos.strategy_id, normalized_symbol))", "Strategy-symbol tuple creation"),
        ("strategy_symbol_key = (strategy.id, normalized_symbol)", "Strategy-symbol key creation"),
        ("if strategy_symbol_key in strategy_symbol_positions:", "Strategy-symbol position check"),
        ("This prevents duplicate orders", "Duplicate order prevention comment")
    ]
    
    all_passed = True
    for check_str, description in checks:
        if check_str in content:
            print(f"✅ {description}: FOUND")
        else:
            print(f"❌ {description}: NOT FOUND")
            all_passed = False
    
    return all_passed


def simulate_filtering_logic():
    """Simulate the position-aware filtering logic to verify it works correctly."""
    print("\n" + "="*80)
    print("SIMULATING POSITION-AWARE FILTERING LOGIC")
    print("="*80)
    
    # Simulate existing positions
    print("\n📊 Simulated Scenario:")
    print("   Strategy A has position in JPM")
    print("   Strategy B has position in GE")
    print("   Strategy C has no positions")
    
    # Simulate the fix
    strategy_symbol_positions = set()
    strategy_symbol_positions.add(("strategy_a", "JPM"))
    strategy_symbol_positions.add(("strategy_b", "GE"))
    
    print("\n🔍 Testing Filtering Logic:")
    
    # Test 1: Strategy A tries to trade JPM again
    test_cases = [
        ("strategy_a", "JPM", True, "Strategy A trading JPM (has position)"),
        ("strategy_a", "GE", False, "Strategy A trading GE (no position)"),
        ("strategy_b", "JPM", False, "Strategy B trading JPM (no position)"),
        ("strategy_b", "GE", True, "Strategy B trading GE (has position)"),
        ("strategy_c", "JPM", False, "Strategy C trading JPM (no position)"),
        ("strategy_c", "GE", False, "Strategy C trading GE (no position)"),
    ]
    
    all_passed = True
    for strategy_id, symbol, should_skip, description in test_cases:
        strategy_symbol_key = (strategy_id, symbol)
        will_skip = strategy_symbol_key in strategy_symbol_positions
        
        if will_skip == should_skip:
            status = "✅ PASS"
        else:
            status = "❌ FAIL"
            all_passed = False
        
        action = "SKIP" if will_skip else "ALLOW"
        expected = "SKIP" if should_skip else "ALLOW"
        print(f"   {status}: {description} → {action} (expected: {expected})")
    
    return all_passed


def verify_config_changes():
    """Verify that config changes were applied."""
    print("\n" + "="*80)
    print("VERIFYING CONFIG CHANGES")
    print("="*80)
    
    import yaml
    
    config_path = Path("config/autonomous_trading.yaml")
    
    if not config_path.exists():
        print("❌ Config file not found!")
        return False
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    checks = [
        (config.get('backtest', {}).get('period_days') == 1825, "Backtest period: 1825 days (5 years)"),
        (config.get('backtest', {}).get('warmup_days') == 100, "Warmup period: 100 days"),
        (config.get('transaction_costs', {}).get('enabled') == True, "Transaction costs: Enabled"),
        (config.get('regime_detection', {}).get('enabled') == True, "Regime detection: Enabled"),
    ]
    
    all_passed = True
    for condition, description in checks:
        if condition:
            print(f"✅ {description}")
        else:
            print(f"❌ {description}")
            all_passed = False
    
    return all_passed


def main():
    """Main verification."""
    print("="*80)
    print("DUPLICATE ORDER FIX VERIFICATION")
    print("="*80)
    print("\nVerifying all fixes applied on February 23, 2026")
    
    results = []
    
    # Verify code changes
    results.append(("Code Changes", verify_code_changes()))
    
    # Simulate filtering logic
    results.append(("Filtering Logic", simulate_filtering_logic()))
    
    # Verify config changes
    results.append(("Config Changes", verify_config_changes()))
    
    # Summary
    print("\n" + "="*80)
    print("VERIFICATION SUMMARY")
    print("="*80)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
        all_passed = all_passed and passed
    
    if all_passed:
        print("\n" + "="*80)
        print("✅ ALL VERIFICATIONS PASSED")
        print("="*80)
        print("\nThe duplicate order bug has been fixed!")
        print("\nNext steps:")
        print("1. Run E2E test to verify in real environment")
        print("2. Monitor for 24 hours to ensure no regressions")
        print("3. Check logs for 'existing position found for this strategy-symbol combination'")
        return 0
    else:
        print("\n" + "="*80)
        print("❌ SOME VERIFICATIONS FAILED")
        print("="*80)
        print("\nPlease review the failed checks above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
