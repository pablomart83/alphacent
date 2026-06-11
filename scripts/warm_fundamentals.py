#!/usr/bin/env python3
"""Drain the FMP fundamental-warm backlog (one-off).

Repeatedly runs FMPCacheWarmer.warm_all_symbols (30 stale symbols/run) until
nothing fresh is left to fetch, so the System-tab coverage gauge clears 80%
after the SKIP_FUNDAMENTALS fix (2026-06-11). Uses config_loader so the real
FMP key (api_keys.yaml overlay) is present — run_cache_warming() reads raw
yaml and would get the secrets-manager placeholder.

Run ON EC2:
    cd /home/ubuntu/alphacent && set -a && . ./.env.production && set +a && \
        venv/bin/python3 scripts/warm_fundamentals.py
"""
from __future__ import annotations
import sys
sys.path.insert(0, ".")


def main() -> int:
    from src.core.config_loader import load_config
    from src.data.fmp_cache_warmer import FMPCacheWarmer

    cfg = load_config()
    warmer = FMPCacheWarmer(cfg)
    for i in range(6):
        stats = warmer.warm_all_symbols()
        fetched = stats.get("fundamentals_fetched", 0)
        cached = stats.get("fundamentals_cached", 0)
        failed = stats.get("fundamentals_failed", 0)
        print(f"[warm] pass {i+1}: fetched={fetched} cached={cached} failed={failed}")
        if fetched == 0:
            print("[warm] no more stale symbols to fetch — done")
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
