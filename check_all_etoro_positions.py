#!/usr/bin/env python3
"""Check ALL positions on eToro to see what symbols we have"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.models.enums import TradingMode

config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)
etoro_client = EToroAPIClient(
    public_key=credentials["public_key"],
    user_key=credentials["user_key"],
    mode=TradingMode.DEMO,
)

print("=== Fetching ALL positions from eToro ===")
positions = etoro_client.get_positions()
print(f"Total positions: {len(positions)}\n")

# Show all positions with their symbols
for p in positions:
    print(f"Symbol: {p.symbol:20s} | ID: {p.etoro_position_id} | {p.side.value:5s} | qty={p.quantity:10.2f} | entry=${p.entry_price:8.2f} | pnl=${p.unrealized_pnl:8.2f}")

# Check for variations of GE and PLTR
print("\n=== Searching for GE-like symbols ===")
ge_like = [p for p in positions if 'GE' in p.symbol.upper()]
for p in ge_like:
    print(f"Found: {p.symbol} | ID: {p.etoro_position_id}")

print("\n=== Searching for PLTR-like symbols ===")
pltr_like = [p for p in positions if 'PLTR' in p.symbol.upper() or 'PALANTIR' in p.symbol.upper()]
for p in pltr_like:
    print(f"Found: {p.symbol} | ID: {p.etoro_position_id}")
