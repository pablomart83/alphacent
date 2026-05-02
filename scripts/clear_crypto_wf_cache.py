#!/usr/bin/env python3
"""Clear ONLY crypto entries from WF caches so next cycle re-tests them with new thresholds.

Preserves stock/etf/forex/index/commodity cache entries.
Safe to re-run.
"""
import json
from pathlib import Path

CRYPTO_SYMBOLS = {'BTC', 'ETH', 'SOL', 'AVAX', 'LINK', 'DOT', 'ADA', 'XRP', 'MATIC', 'DOGE'}

FILES = [
    "config/.wf_validated_combos.json",
    "config/.wf_failed_cache.json",
]


def clear_crypto(path: str) -> None:
    p = Path(path)
    if not p.exists():
        print(f"{path}: not found — skipping")
        return

    with open(p) as f:
        data = json.load(f)

    entries = data.get("entries", [])
    original_count = len(entries)

    # Entry format: {"key": [template, symbol], "result": ..., "timestamp": ...}
    kept = []
    removed = []
    for e in entries:
        key = e.get("key", [None, None])
        symbol = (key[1] if len(key) > 1 else "") or ""
        if symbol.upper() in CRYPTO_SYMBOLS:
            removed.append(e)
        else:
            kept.append(e)

    data["entries"] = kept

    with open(p, "w") as f:
        json.dump(data, f, indent=2)

    print(f"{path}: removed {len(removed)} crypto entries, kept {len(kept)} non-crypto "
          f"(was {original_count} total)")


if __name__ == "__main__":
    for f in FILES:
        clear_crypto(f)
    print("Done. Next cycle will re-test all crypto combos under the new thresholds.")
