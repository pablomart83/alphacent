#!/usr/bin/env python3
"""
Test new fundamental filter thresholds to project pass rate improvement.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models.database import get_database
from src.models.orm import FundamentalFilterLogORM, FundamentalDataORM
from datetime import datetime


def simulate_new_filter_logic():
    """Simulate new filter logic on historical data."""
    database = get_database()
    session = database.get_session()
    
    try:
        print("=" * 80)
        print("SIMULATING NEW FILTER THRESHOLDS")
        print("=" * 80)
        print()
        
        # Get all filter logs
        logs = session.query(FundamentalFilterLogORM).all()
        
        if not logs:
            print("No filter logs found.")
            return
        
        print(f"Analyzing {len(logs)} historical filter runs...")
        print()
        
        # Simulate new logic
        old_passed = 0
        new_passed = 0
        insufficient_data = 0
        
        for log in logs:
            # Old logic: passed if checks_passed >= 4
            if log.passed:
                old_passed += 1
            
            # New logic simulation:
            # 1. Missing data now passes (growing, valuation, dilution, insider)
            # 2. P/E thresholds increased by 20%
            # 3. Min checks reduced to 3
            # 4. NEW: Require at least 2 checks with actual data
            
            simulated_checks_passed = 0
            checks_with_data = 0
            
            # Profitable check (unchanged)
            if log.profitable is True:
                simulated_checks_passed += 1
                checks_with_data += 1
            elif log.profitable is False:
                checks_with_data += 1
            # If None, no data
            
            # Growing check (NEW: pass if None)
            if log.growing is True:
                simulated_checks_passed += 1
                checks_with_data += 1
            elif log.growing is False:
                checks_with_data += 1
            elif log.growing is None:
                simulated_checks_passed += 1  # Pass if missing
            
            # Valuation check (NEW: pass if None, higher thresholds)
            if log.valuation is True:
                simulated_checks_passed += 1
                checks_with_data += 1
            elif log.valuation is False:
                checks_with_data += 1
            elif log.valuation is None:
                simulated_checks_passed += 1  # Pass if missing
            
            # Dilution check (already passes if None)
            if log.dilution is True:
                simulated_checks_passed += 1
                checks_with_data += 1
            elif log.dilution is False:
                checks_with_data += 1
            elif log.dilution is None:
                simulated_checks_passed += 1  # Pass if missing
            
            # Insider buying check (already passes if None)
            if log.insider_buying is True:
                simulated_checks_passed += 1
                checks_with_data += 1
            elif log.insider_buying is False:
                checks_with_data += 1
            elif log.insider_buying is None:
                simulated_checks_passed += 1  # Pass if missing
            
            # NEW: Require at least 2 checks with actual data
            if checks_with_data < 2:
                insufficient_data += 1
                continue
            
            # NEW: Min checks = 3 (was 4)
            if simulated_checks_passed >= 3:
                new_passed += 1
        
        old_pass_rate = (old_passed / len(logs)) * 100
        new_pass_rate = (new_passed / len(logs)) * 100
        improvement = new_pass_rate - old_pass_rate
        
        print("RESULTS:")
        print()
        print(f"  OLD LOGIC:")
        print(f"    Passed: {old_passed}/{len(logs)} ({old_pass_rate:.1f}%)")
        print(f"    Min checks: 4/5")
        print(f"    Missing data: FAIL")
        print()
        print(f"  NEW LOGIC:")
        print(f"    Passed: {new_passed}/{len(logs)} ({new_pass_rate:.1f}%)")
        print(f"    Insufficient data: {insufficient_data} ({(insufficient_data/len(logs))*100:.1f}%)")
        print(f"    Min checks: 3/5")
        print(f"    Missing data: PASS (but need 2+ checks with data)")
        print()
        print(f"  IMPROVEMENT: +{improvement:.1f}% ({new_passed - old_passed} more symbols)")
        print()
        
        if 50 <= new_pass_rate <= 70:
            print(f"  ✓ NEW PASS RATE WITHIN TARGET (50-70%)")
        elif new_pass_rate > 70:
            print(f"  ⚠️  NEW PASS RATE TOO HIGH (>70%) - May need further tuning")
        else:
            print(f"  ⚠️  NEW PASS RATE STILL TOO LOW (<50%) - May need more loosening")
        
        print()
        print("=" * 80)
        
    finally:
        session.close()


if __name__ == "__main__":
    simulate_new_filter_logic()
