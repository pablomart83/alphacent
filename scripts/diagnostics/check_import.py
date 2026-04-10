#!/usr/bin/env python3
"""Check what's actually being imported."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import src.core.tradeable_instruments as ti

print(f"Module file: {ti.__file__}")
print(f"\nModule attributes:")
for attr in dir(ti):
    if not attr.startswith('_'):
        val = getattr(ti, attr)
        if isinstance(val, list):
            print(f"  {attr}: {len(val)} items")
            if attr == "DEMO_ALL_TRADEABLE":
                print(f"    Contents: {val}")
        else:
            print(f"  {attr}: {type(val).__name__}")
