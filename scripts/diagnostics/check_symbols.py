#!/usr/bin/env python3
"""Quick check of tradeable symbols."""

# Directly check the lists without imports
DEMO_ALLOWED_STOCKS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "NFLX",
    "AMD", "INTC", "CSCO", "ADBE", "ORCL", "CRM",
    "JPM", "V", "MA", "PYPL", "COIN",
    "WMT", "DIS", "BA", "JNJ", "PG", "UNH", "KO", "PEP", "MCD",
    "NKE", "COST", "HD", "LOW", "TGT", "SBUX", "GE",
    "UBER", "ABNB", "SNAP", "PLTR",
    "BABA",
]

DEMO_ALLOWED_COMMODITIES = [
    "GOLD", "SILVER", "OIL", "COPPER",
]

DEMO_ALL_TRADEABLE = DEMO_ALLOWED_STOCKS + DEMO_ALLOWED_COMMODITIES

print(f"GE in DEMO_ALLOWED_STOCKS: {'GE' in DEMO_ALLOWED_STOCKS}")
print(f"GOLD in DEMO_ALLOWED_COMMODITIES: {'GOLD' in DEMO_ALLOWED_COMMODITIES}")
print(f"GE in DEMO_ALL_TRADEABLE: {'GE' in DEMO_ALL_TRADEABLE}")
print(f"GOLD in DEMO_ALL_TRADEABLE: {'GOLD' in DEMO_ALL_TRADEABLE}")
print(f"\nTotal tradeable: {len(DEMO_ALL_TRADEABLE)}")
