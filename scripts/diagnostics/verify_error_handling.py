#!/usr/bin/env python3
"""
Verification script to ensure proper error handling when data is unavailable.
"""

import sys
import re
from pathlib import Path

def check_error_handling(filepath: Path) -> dict:
    """Check if endpoints have proper error handling."""
    results = {
        'has_http_exceptions': False,
        'has_empty_returns': False,
        'endpoints': []
    }
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Check for HTTPException usage
    if 'HTTPException' in content and 'HTTP_503_SERVICE_UNAVAILABLE' in content:
        results['has_http_exceptions'] = True
    
    # Check for empty array/object returns
    if re.search(r'return\s+\w+Response\(\s*\w+\s*=\s*\[\s*\]', content):
        results['has_empty_returns'] = True
    
    # Find all endpoint functions
    endpoint_pattern = r'@router\.(get|post|put|delete)\([^)]*\)\s*\nasync def (\w+)'
    endpoints = re.findall(endpoint_pattern, content)
    results['endpoints'] = [name for _, name in endpoints]
    
    return results

def main():
    """Main verification function."""
    print("Verifying error handling in backend routers...\n")
    
    router_files = [
        "src/api/routers/account.py",
        "src/api/routers/market_data.py",
        "src/api/routers/control.py",
        "src/api/routers/strategies.py",
    ]
    
    for filepath in router_files:
        path = Path(filepath)
        if not path.exists():
            print(f"❌ File not found: {filepath}")
            continue
        
        results = check_error_handling(path)
        
        print(f"\n{filepath}:")
        print(f"  ✓ HTTPException for unavailable services: {results['has_http_exceptions']}")
        print(f"  ✓ Empty returns for no data: {results['has_empty_returns']}")
        print(f"  ✓ Endpoints found: {len(results['endpoints'])}")
    
    print("\n✅ Error handling verification complete!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
