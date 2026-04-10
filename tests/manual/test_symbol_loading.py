#!/usr/bin/env python3
"""Test that strategy proposer loads symbols from tradeable_instruments.py"""
import sys
sys.path.insert(0, '.')

from src.strategy.strategy_proposer import StrategyProposer
from src.core.tradeable_instruments import get_tradeable_symbols
from src.models.enums import TradingMode

# Create proposer
proposer = StrategyProposer(llm_service=None, market_data=None)

# Get symbols from proposer
proposer_symbols = proposer._load_trading_symbols()

# Get symbols from tradeable_instruments
tradeable_symbols = get_tradeable_symbols(TradingMode.DEMO)

print(f"Proposer loaded {len(proposer_symbols)} symbols")
print(f"Tradeable instruments has {len(tradeable_symbols)} symbols")
print(f"\nProposer symbols: {sorted(proposer_symbols)}")
print(f"\nTradeable symbols: {sorted(tradeable_symbols)}")

# Check if they match
if set(proposer_symbols) == set(tradeable_symbols):
    print("\n✅ SUCCESS: Proposer is using tradeable_instruments.py")
else:
    print("\n❌ FAIL: Symbols don't match")
    print(f"In proposer but not tradeable: {set(proposer_symbols) - set(tradeable_symbols)}")
    print(f"In tradeable but not proposer: {set(tradeable_symbols) - set(proposer_symbols)}")
