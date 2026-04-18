#!/usr/bin/env python3
"""
Sprint 6.1 — Add Performance Indexes

Adds indexes to the most-queried columns in the positions, orders, and
historical_price_cache tables. These are full table scans on every monitoring
cycle (every 5 seconds) with 780K+ rows.

Run on EC2:
    cd /home/ubuntu/alphacent
    python3 migrations/add_performance_indexes.py

Uses CONCURRENTLY so the table stays readable during index creation.
Safe to run multiple times — all statements use IF NOT EXISTS.
"""

import logging
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

INDEXES = [
    # positions — queried by strategy_id, closed_at, pending_closure on every monitoring cycle
    (
        "idx_positions_strategy_id",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_positions_strategy_id ON positions(strategy_id)",
    ),
    (
        "idx_positions_closed_at",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_positions_closed_at ON positions(closed_at)",
    ),
    (
        "idx_positions_pending_closure",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_positions_pending_closure "
        "ON positions(pending_closure) WHERE pending_closure = true",
    ),
    # orders — queried by status and strategy_id in signal coordination
    (
        "idx_orders_status",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_orders_status ON orders(status)",
    ),
    (
        "idx_orders_strategy_id",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_orders_strategy_id ON orders(strategy_id)",
    ),
    # historical_price_cache — queried by symbol + date on every price lookup
    (
        "idx_historical_price_cache_symbol_date",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_historical_price_cache_symbol_date "
        "ON historical_price_cache(symbol, date DESC)",
    ),
]


def run():
    from src.models.database import get_database
    db = get_database()

    # CONCURRENTLY requires autocommit — use raw psycopg2 connection
    engine = db.engine
    raw_conn = engine.raw_connection()
    raw_conn.set_isolation_level(0)  # AUTOCOMMIT
    cursor = raw_conn.cursor()

    for name, sql in INDEXES:
        logger.info(f"Creating index: {name} ...")
        try:
            cursor.execute(sql)
            logger.info(f"  ✓ {name}")
        except Exception as e:
            logger.warning(f"  ✗ {name}: {e}")

    cursor.close()
    raw_conn.close()
    logger.info("Done.")


if __name__ == "__main__":
    run()
