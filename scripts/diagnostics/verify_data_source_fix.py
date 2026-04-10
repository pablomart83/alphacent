#!/usr/bin/env python3
"""
Verification script for data source consistency fix.

This script checks that all market data fetches use Yahoo Finance consistently.
"""

import re
from pathlib import Path
from typing import List, Tuple


def check_file_for_prefer_yahoo(file_path: Path) -> List[Tuple[int, str, bool]]:
    """
    Check a Python file for get_historical_data calls and verify prefer_yahoo usage.
    
    Returns:
        List of (line_number, line_content, has_prefer_yahoo)
    """
    results = []
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines, 1):
        if 'get_historical_data(' in line:
            # Check if this call or the next few lines have prefer_yahoo
            has_prefer_yahoo = False
            context_lines = lines[i-1:min(i+5, len(lines))]
            context = ''.join(context_lines)
            
            if 'prefer_yahoo=True' in context:
                has_prefer_yahoo = True
            
            results.append((i, line.strip(), has_prefer_yahoo))
    
    return results


def main():
    """Main verification function."""
    print("=" * 80)
    print("Data Source Consistency Verification")
    print("=" * 80)
    print()
    
    # Files to check
    files_to_check = [
        'src/strategy/strategy_engine.py',
        'src/strategy/market_analyzer.py',
        'src/strategy/strategy_proposer.py',
    ]
    
    all_passed = True
    total_calls = 0
    yahoo_calls = 0
    
    for file_path_str in files_to_check:
        file_path = Path(file_path_str)
        
        if not file_path.exists():
            print(f"❌ File not found: {file_path}")
            all_passed = False
            continue
        
        print(f"Checking: {file_path}")
        print("-" * 80)
        
        results = check_file_for_prefer_yahoo(file_path)
        
        if not results:
            print("  ✓ No get_historical_data calls found")
            print()
            continue
        
        for line_num, line_content, has_prefer_yahoo in results:
            total_calls += 1
            
            if has_prefer_yahoo:
                yahoo_calls += 1
                print(f"  ✓ Line {line_num}: Uses prefer_yahoo=True")
            else:
                print(f"  ❌ Line {line_num}: Missing prefer_yahoo=True")
                print(f"     {line_content}")
                all_passed = False
        
        print()
    
    # Summary
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"Total get_historical_data calls: {total_calls}")
    print(f"Calls with prefer_yahoo=True: {yahoo_calls}")
    print(f"Calls missing prefer_yahoo: {total_calls - yahoo_calls}")
    print()
    
    if all_passed and total_calls > 0:
        print("✅ All checks passed! Data source is consistent.")
        print()
        print("Next steps:")
        print("1. Restart the backend: uvicorn src.api.main:app --reload")
        print("2. Trigger autonomous cycle: POST /strategies/autonomous/cycle")
        print("3. Monitor logs: tail -f backend.log | grep 'Yahoo Finance'")
        return 0
    elif total_calls == 0:
        print("⚠️  No get_historical_data calls found. This might be an issue.")
        return 1
    else:
        print("❌ Some checks failed. Please review the issues above.")
        print()
        print("To fix:")
        print("1. Add 'prefer_yahoo=True' to all get_historical_data calls")
        print("2. Run this script again to verify")
        return 1


if __name__ == '__main__':
    exit(main())
