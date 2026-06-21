#!/usr/bin/env python3
"""Clear ONLY crypto entries from the WF caches AND the re-proposal blacklists
so the next cycle re-tests them from scratch.

Use after:
- DSL grammar changes
- Template code changes (entry/exit condition rewrites)
- WF / acceptance / cost-model changes (e.g. the 2026-06-20 per-trade cost-net
  crypto gate) — the rejection blacklist accumulated during the prior (artifact)
  regime would otherwise block the most-active crypto templates from being
  re-proposed, so clearing the WF cache alone can't force a fresh re-test.
- Crypto-relevant config changes.

Clears crypto entries from BOTH:
  - the WF result caches (.wf_validated_combos / .wf_failed_cache), and
  - the proposal blocklists (.rejection_blacklist / .zero_trade_blacklist),
    which exclude (template, symbol) combos from the proposer's scoring loop.

Preserves all stock/etf/forex/index/commodity entries.
Safe to re-run. Restart the service after running so the in-memory copies reload.

JSON shape (all four files): {"entries": [{"template": ..., "symbol": ..., ...}, ...]}
"""
import json
import sys
from pathlib import Path

# Ensure the repo root is importable regardless of invocation cwd (running
# `python scripts/foo.py` puts scripts/ on sys.path[0], not the repo root).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Authoritative crypto universe. Derive from tradeable_instruments so this never
# drifts from the live universe (the old hardcoded set still had MATIC/DOGE and was
# missing the LTC/BCH/ADA/XRP added in the 2026-06-20 universe expansion — which would
# have silently left wrong-cost WF entries for those coins behind). Falls back to a
# static set only if the import fails.
try:
    from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO
    CRYPTO_SYMBOLS = {s.upper() for s in DEMO_ALLOWED_CRYPTO}
except Exception:
    CRYPTO_SYMBOLS = {
        'BTC', 'ETH', 'SOL', 'AVAX', 'LINK', 'DOT',
        'ADA', 'XRP', 'LTC', 'BCH',
    }

FILES = [
    "config/.wf_validated_combos.json",
    "config/.wf_failed_cache.json",
    "config/.rejection_blacklist.json",
    "config/.zero_trade_blacklist.json",
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
