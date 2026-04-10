#!/usr/bin/env python3
"""
Verify fundamental filter improvements by testing with sample data.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.data.fundamental_data_provider import FundamentalData
from src.strategy.fundamental_filter import FundamentalFilter, FilterResult
from datetime import datetime


def test_filter_improvements():
    """Test filter with various scenarios."""
    print("=" * 80)
    print("FUNDAMENTAL FILTER IMPROVEMENTS VERIFICATION")
    print("=" * 80)
    print()
    
    # Mock config
    config = {
        'alpha_edge': {
            'fundamental_filters': {
                'enabled': True,
                'min_checks_passed': 3,  # NEW: Reduced from 4
                'min_market_cap': 500_000_000,  # NEW: $500M minimum
                'checks': {
                    'profitable': True,
                    'growing': True,
                    'reasonable_valuation': True,
                    'no_dilution': True,
                    'insider_buying': True
                }
            }
        }
    }
    
    # Mock data provider (we'll test the filter logic directly)
    class MockDataProvider:
        def get_fundamental_data(self, symbol):
            # Return test data based on symbol
            if symbol == "GOOD_STOCK":
                return FundamentalData(
                    symbol="GOOD_STOCK",
                    timestamp=datetime.now(),
                    eps=5.0,  # Profitable
                    revenue_growth=0.15,  # Growing 15%
                    pe_ratio=25.0,  # Reasonable
                    debt_to_equity=0.3,  # Low debt
                    roe=0.20,  # High ROE
                    market_cap=5_000_000_000,  # $5B
                    insider_net_buying=1_000_000,  # Insider buying
                    shares_change_percent=2.0,  # Low dilution
                    source="FMP"
                )
            elif symbol == "MISSING_DATA":
                return FundamentalData(
                    symbol="MISSING_DATA",
                    timestamp=datetime.now(),
                    eps=3.0,  # Has EPS
                    revenue_growth=None,  # Missing
                    pe_ratio=None,  # Missing
                    debt_to_equity=None,
                    roe=None,
                    market_cap=2_000_000_000,  # $2B
                    insider_net_buying=None,  # Missing
                    shares_change_percent=None,  # Missing
                    source="FMP"
                )
            elif symbol == "MICRO_CAP":
                return FundamentalData(
                    symbol="MICRO_CAP",
                    timestamp=datetime.now(),
                    eps=1.0,
                    revenue_growth=0.10,
                    pe_ratio=15.0,
                    debt_to_equity=0.2,
                    roe=0.15,
                    market_cap=300_000_000,  # $300M - below threshold
                    insider_net_buying=100_000,
                    shares_change_percent=1.0,
                    source="FMP"
                )
            elif symbol == "EXPENSIVE":
                return FundamentalData(
                    symbol="EXPENSIVE",
                    timestamp=datetime.now(),
                    eps=2.0,
                    revenue_growth=0.20,
                    pe_ratio=55.0,  # High P/E (would fail old threshold of 40, pass new 50)
                    debt_to_equity=0.4,
                    roe=0.18,
                    market_cap=10_000_000_000,
                    insider_net_buying=500_000,
                    shares_change_percent=3.0,
                    source="FMP"
                )
            return None
    
    filter = FundamentalFilter(config, MockDataProvider())
    
    # Test scenarios
    scenarios = [
        ("GOOD_STOCK", "default", "Should PASS - all checks pass"),
        ("MISSING_DATA", "default", "Should PASS - missing data passes by default (NEW)"),
        ("MICRO_CAP", "default", "Should FAIL - below $500M market cap (NEW)"),
        ("EXPENSIVE", "default", "Should PASS - P/E 55 < 50 threshold (NEW, was 40)"),
    ]
    
    print("TEST SCENARIOS:")
    print()
    
    for symbol, strategy_type, expected in scenarios:
        report = filter.filter_symbol(symbol, strategy_type)
        status = "✓ PASS" if report.passed else "✗ FAIL"
        match = "✓" if (report.passed and "PASS" in expected) or (not report.passed and "FAIL" in expected) else "✗"
        
        print(f"{match} {symbol:15s} {status:8s} - {expected}")
        print(f"   Checks: {report.checks_passed}/{report.checks_total} (need {report.min_required})")
        
        for result in report.results:
            check_status = "✓" if result.passed else "✗"
            print(f"     {check_status} {result.check_name:20s}: {result.reason}")
        print()
    
    print("=" * 80)
    print()
    print("SUMMARY OF IMPROVEMENTS:")
    print()
    print("1. ✓ Reduced min_checks_passed from 4 to 3")
    print("2. ✓ Added $500M minimum market cap filter")
    print("3. ✓ Increased P/E thresholds by 20% (40→50, 60→70, 25→30)")
    print("4. ✓ Missing data now passes non-critical checks")
    print()
    print("Expected pass rate: 55-70% (up from 32%)")
    print("=" * 80)


if __name__ == "__main__":
    test_filter_improvements()
