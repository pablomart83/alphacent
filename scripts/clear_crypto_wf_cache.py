#!/usr/bin/env python3
"""Clear ONLY crypto entries from WF caches so next cycle re-tests them.

Use after:
- DSL grammar changes
- Template code changes (entry/exit condition rewrites)
- Crypto-relevant config changes (though the schema-version mechanism in
  _apply_wf_schema_version_check should also handle config changes)

Preserves stock/etf/forex/index/commodity cache entries.
Safe to re-run.

JSON shape (as of 2026-05-02):
    {
      "entries": [
        {"template": "Crypto Weekly Trend Follow", "symbol": "BTC", "result": [...], "cached_at": ...},
        ...
      ]
    }

History: the previous version of this script looked up `entry["key"][1]` which
didn't match the real layout (template/symbol are top-level fields, not a key
array). The script ran but always removed 0 entries, silently. Fixed 2026-05-02.
"""
import json
from pathlib import Path

CRYPTO_SYMBOLS = {
    'BTC', 'ETH', 'SOL', 'AVAX', 'LINK', 'DOT',
    'ADA', 'XRP', 'MATIC', 'DOGE',
}

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

    kept, removed = [], []
    for e in entries:
        sym = (e.get("symbol") or "").upper()
        # Legacy fallback: some old entries may still carry a key tuple.
        if not sym:
            key = e.get("key", [None, None])
            if isinstance(key, (list, tuple)) and len(key) > 1:
                sym = (key[1] or "").upper()
        if sym in CRYPTO_SYMBOLS:
            removed.append(e)
        else:
            kept.append(e)

    data["entries"] = kept

    with open(p, "w") as f:
        json.dump(data, f, indent=2)

    print(
        f"{path}: removed {len(removed)} crypto entries, kept {len(kept)} non-crypto "
        f"(was {original_count} total)"
    )


if __name__ == "__main__":
    for f in FILES:
        clear_crypto(f)
    print("Done. Next cycle will re-test all crypto combos.")
