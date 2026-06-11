#!/usr/bin/env python3
"""Report the FMP fundamental-coverage gap (read-only diagnostic).

Lists applicable stock symbols (DEMO universe minus SKIP_FUNDAMENTALS) that
have NO fresh (≤7d) row in fundamental_data_cache — i.e. the symbols dragging
the System-tab "FMP cache warm" coverage gauge below 80%.

Run ON EC2:
    cd /home/ubuntu/alphacent && set -a && . ./.env.production && set +a && \
        venv/bin/python3 scripts/fund_gap.py
"""
from __future__ import annotations
import sys
from datetime import datetime, timedelta
sys.path.insert(0, ".")


def main() -> int:
    from src.core.tradeable_instruments import get_tradeable_symbols
    from src.models.enums import TradingMode
    from src.data.fmp_cache_warmer import FMPCacheWarmer
    from src.models.database import get_database
    from src.models.orm import FundamentalDataORM

    syms = [s for s in get_tradeable_symbols(TradingMode.DEMO)
            if s not in FMPCacheWarmer.SKIP_FUNDAMENTALS]
    db = get_database()
    ses = db.get_session()
    try:
        cut = datetime.now() - timedelta(days=7)
        fresh = {r[0] for r in ses.query(FundamentalDataORM.symbol)
                 .filter(FundamentalDataORM.fetched_at >= cut).all()}
        anyrow = {r[0] for r in ses.query(FundamentalDataORM.symbol).distinct().all()}
    finally:
        ses.close()

    fresh_app = [s for s in syms if s in fresh]
    missing = [s for s in syms if s not in fresh]
    never = [s for s in missing if s not in anyrow]
    stale = [s for s in missing if s in anyrow]
    dotted = [s for s in missing if '.' in s]

    print(f"total_applicable={len(syms)} fresh={len(fresh_app)} "
          f"coverage_pct={round(len(fresh_app)/len(syms)*100,1) if syms else 0}")
    print(f"missing={len(missing)} (never_fetched={len(never)} stale={len(stale)} non_us_dotted={len(dotted)})")
    print("NEVER:", " ".join(sorted(never)))
    print("STALE:", " ".join(sorted(stale)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
