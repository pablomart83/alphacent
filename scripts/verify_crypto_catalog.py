#!/usr/bin/env python3
"""Read-only diagnostic: list crypto templates surviving the catalog cost-style
policy (2026-06-20 crypto revamp). Confirms the filter kept the trend/momentum/
breakout set and dropped mean-reversion/intraday — and didn't over-cull.

Run on EC2 via the venv:
    /home/ubuntu/alphacent/venv/bin/python3 scripts/verify_crypto_catalog.py
"""
import os, sys
_S = os.path.dirname(os.path.abspath(__file__))
_W = os.path.dirname(_S)
if _W not in sys.path:
    sys.path.insert(0, _W)

from src.strategy.template_catalog import load_catalog

ts = load_catalog()
crypto = [t for t in ts if (t.metadata or {}).get("crypto_optimized") is True]
print(f"Total templates loaded: {len(ts)}")
print(f"Crypto templates surviving cost-style policy: {len(crypto)}")
print("-" * 78)
by_style = {}
for t in sorted(crypto, key=lambda x: (str(x.strategy_type), x.name)):
    st = t.strategy_type.value if hasattr(t.strategy_type, "value") else str(t.strategy_type)
    iv = (t.metadata or {}).get("interval", "?")
    by_style[st] = by_style.get(st, 0) + 1
    print(f"  {st:16} {str(iv):4} {t.expected_holding_period:22} {t.name}")
print("-" * 78)
print("By style:", by_style)
