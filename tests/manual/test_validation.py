#!/usr/bin/env python3
"""Test symbol validation."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.tradeable_instruments import is_tradeable, get_blocked_reason, get_tradeable_symbols
from src.models.enums import TradingMode

symbols_to_test = ["GE", "GOLD", "AAPL", "SPY", "BTC"]

print("Testing symbol validation:")
print("=" * 60)

for symbol in symbols_to_test:
    tradeable = is_tradeable(symbol, TradingMode.DEMO)
    reason = get_blocked_reason(symbol, TradingMode.DEMO)
    print(f"{symbol:10} | Tradeable: {tradeable:5} | Reason: {reason or 'OK'}")

print("\n" + "=" * 60)
all_symbols = get_tradeable_symbols(TradingMode.DEMO)
print(f"Total tradeable symbols: {len(all_symbols)}")
print(f"GE in list: {'GE' in all_symbols}")
print(f"GOLD in list: {'GOLD' in all_symbols}")
