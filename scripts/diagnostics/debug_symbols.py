#!/usr/bin/env python3
"""Debug symbol lists."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.tradeable_instruments import (
    DEMO_ALLOWED_STOCKS,
    DEMO_ALLOWED_COMMODITIES,
    DEMO_ALL_TRADEABLE,
    get_tradeable_symbols
)
from src.models.enums import TradingMode

print("DEMO_ALLOWED_STOCKS:")
print(DEMO_ALLOWED_STOCKS)
print(f"\nTotal: {len(DEMO_ALLOWED_STOCKS)}")
print(f"GE in DEMO_ALLOWED_STOCKS: {'GE' in DEMO_ALLOWED_STOCKS}")

print("\n" + "=" * 60)
print("DEMO_ALLOWED_COMMODITIES:")
print(DEMO_ALLOWED_COMMODITIES)
print(f"\nTotal: {len(DEMO_ALLOWED_COMMODITIES)}")
print(f"GOLD in DEMO_ALLOWED_COMMODITIES: {'GOLD' in DEMO_ALLOWED_COMMODITIES}")

print("\n" + "=" * 60)
print("DEMO_ALL_TRADEABLE:")
print(DEMO_ALL_TRADEABLE)
print(f"\nTotal: {len(DEMO_ALL_TRADEABLE)}")
print(f"GE in DEMO_ALL_TRADEABLE: {'GE' in DEMO_ALL_TRADEABLE}")
print(f"GOLD in DEMO_ALL_TRADEABLE: {'GOLD' in DEMO_ALL_TRADEABLE}")

print("\n" + "=" * 60)
runtime_symbols = get_tradeable_symbols(TradingMode.DEMO)
print(f"get_tradeable_symbols(DEMO) returns {len(runtime_symbols)} symbols:")
print(runtime_symbols)
print(f"\nGE in runtime: {'GE' in runtime_symbols}")
print(f"GOLD in runtime: {'GOLD' in runtime_symbols}")
