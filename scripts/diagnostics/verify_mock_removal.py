#!/usr/bin/env python3
"""
Verification script to ensure mock data has been removed from backend endpoints.
"""

import sys
import re
from pathlib import Path

def check_file_for_mock_data(filepath: Path) -> list[str]:
    """Check a file for mock data patterns."""
    issues = []
    
    with open(filepath, 'r') as f:
        content = f.read()
        lines = content.split('\n')
    
    # Patterns that indicate mock data
    mock_patterns = [
        (r'mock_\w+\s*=\s*\[', 'Mock data array assignment'),
        (r'mock_\w+\s*=\s*{', 'Mock data dict assignment'),
        (r'return\s+\w*[Mm]ock\w*Response\(', 'Returning mock response directly'),
        (r'# For now, return mock data', 'Comment indicating mock data'),
        (r'MockPortfolio', 'Mock portfolio class usage'),
    ]
    
    for i, line in enumerate(lines, 1):
        for pattern, description in mock_patterns:
            if re.search(pattern, line):
                issues.append(f"Line {i}: {description} - {line.strip()}")
    
    return issues

def main():
    """Main verification function."""
    print("Verifying mock data removal from backend routers...\n")
    
    router_files = [
        "src/api/routers/account.py",
        "src/api/routers/market_data.py",
        "src/api/routers/control.py",
        "src/api/routers/strategies.py",
        "src/api/routers/orders.py",
    ]
    
    all_issues = {}
    
    for filepath in router_files:
        path = Path(filepath)
        if not path.exists():
            print(f"❌ File not found: {filepath}")
            continue
        
        issues = check_file_for_mock_data(path)
        if issues:
            all_issues[filepath] = issues
    
    # Report results
    if all_issues:
        print("❌ Found potential mock data in the following files:\n")
        for filepath, issues in all_issues.items():
            print(f"\n{filepath}:")
            for issue in issues:
                print(f"  - {issue}")
        print("\n⚠️  Please review these findings.")
        return 1
    else:
        print("✅ No mock data patterns found in backend routers!")
        print("\nVerified files:")
        for filepath in router_files:
            if Path(filepath).exists():
                print(f"  ✓ {filepath}")
        return 0

if __name__ == "__main__":
    sys.exit(main())
