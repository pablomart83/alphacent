#!/usr/bin/env python3
"""Test tradeable instruments configuration"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.tradeable_instruments import (
    get_tradeable_symbols,
    is_tradeable,
    get_blocked_reason,
    get_default_watchlist
)
from src.models import TradingMode

def test_tradeable_instruments():
    print("=" * 70)
    print("Testing Tradeable Instruments Configuration")
    print("=" * 70)
    
    # Test DEMO mode
    print("\n1. DEMO Mode Tradeable Symbols:")
    demo_symbols = get_tradeable_symbols(TradingMode.DEMO)
    print(f"   Count: {len(demo_symbols)}")
    print(f"   Symbols: {', '.join(demo_symbols)}")
    
    # Test LIVE mode
    print("\n2. LIVE Mode Tradeable Symbols:")
    live_symbols = get_tradeable_symbols(TradingMode.LIVE)
    print(f"   Count: {len(live_symbols)}")
    print(f"   Symbols: {', '.join(live_symbols)}")
    
    # Test is_tradeable
    print("\n3. Testing is_tradeable():")
    test_cases = [
        ("AAPL", TradingMode.DEMO, True),
        ("BTC", TradingMode.DEMO, False),
        ("META", TradingMode.DEMO, False),
        ("NVDA", TradingMode.DEMO, False),
        ("META", TradingMode.LIVE, True),
        ("NVDA", TradingMode.LIVE, True),
    ]
    
    for symbol, mode, expected in test_cases:
        result = is_tradeable(symbol, mode)
        status = "✅" if result == expected else "❌"
        print(f"   {status} {symbol} in {mode.value}: {result} (expected {expected})")
    
    # Test get_blocked_reason
    print("\n4. Testing get_blocked_reason():")
    blocked_tests = [
        ("BTC", TradingMode.DEMO),
        ("META", TradingMode.DEMO),
        ("NVDA", TradingMode.DEMO),
        ("AAPL", TradingMode.DEMO),
    ]
    
    for symbol, mode in blocked_tests:
        reason = get_blocked_reason(symbol, mode)
        if reason:
            print(f"   ❌ {symbol}: {reason}")
        else:
            print(f"   ✅ {symbol}: Tradeable")
    
    # Test default watchlist
    print("\n5. Default Watchlists:")
    demo_watchlist = get_default_watchlist(TradingMode.DEMO)
    print(f"   DEMO: {', '.join(demo_watchlist)}")
    
    live_watchlist = get_default_watchlist(TradingMode.LIVE)
    print(f"   LIVE: {', '.join(live_watchlist)}")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    test_tradeable_instruments()
