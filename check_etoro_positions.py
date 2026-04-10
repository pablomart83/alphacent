#!/usr/bin/env python3
"""Check what positions eToro actually has"""
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

print("=== Fetching positions from eToro ===")
positions = etoro_client.get_positions()
print(f"Total positions: {len(positions)}")

# Filter for GE and PLTR
ge_positions = [p for p in positions if p.symbol == 'GE']
pltr_positions = [p for p in positions if p.symbol == 'PLTR']

print(f"\n=== GE Positions on eToro ({len(ge_positions)}) ===")
for p in ge_positions:
    print(f"ID: {p.etoro_position_id} | {p.side.value} | qty={p.quantity} | entry=${p.entry_price} | current=${p.current_price} | pnl=${p.unrealized_pnl}")

print(f"\n=== PLTR Positions on eToro ({len(pltr_positions)}) ===")
for p in pltr_positions:
    print(f"ID: {p.etoro_position_id} | {p.side.value} | qty={p.quantity} | entry=${p.entry_price} | current=${p.current_price} | pnl=${p.unrealized_pnl}")
