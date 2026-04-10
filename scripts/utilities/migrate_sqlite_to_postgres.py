#!/usr/bin/env python3
"""
Migrate data from SQLite to PostgreSQL.

Usage:
    python scripts/utilities/migrate_sqlite_to_postgres.py

Prerequisites:
    - PostgreSQL running locally with 'alphacent' database created
    - psycopg2-binary installed in venv
    - SQLite database at alphacent.db

This script:
1. Reads all data from SQLite
2. Creates schema in PostgreSQL (via SQLAlchemy ORM)
3. Copies all rows table by table
4. Verifies row counts match
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

SQLITE_URL = "sqlite:///alphacent.db"
POSTGRES_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/alphacent")


def migrate():
    logger.info(f"Source: {SQLITE_URL}")
    logger.info(f"Target: {POSTGRES_URL}")

    # Connect to both
    sqlite_engine = create_engine(SQLITE_URL)
    pg_engine = create_engine(POSTGRES_URL)

    # Create schema in PostgreSQL from ORM models
    from src.models.orm import Base
    from src.analytics.trade_journal import TradeJournalEntryORM  # noqa: F401 — registers the model
    from src.strategy.performance_tracker import StrategyPerformanceHistoryORM  # noqa: F401
    from src.strategy.correlation_analyzer import StrategyCorrelationHistoryORM  # noqa: F401
    from src.strategy.performance_degradation_monitor import PerformanceDegradationHistoryORM  # noqa: F401
    
    logger.info("Creating PostgreSQL schema from ORM models...")
    Base.metadata.create_all(bind=pg_engine)
    logger.info("Schema created.")

    # Get table names from SQLite
    sqlite_inspector = inspect(sqlite_engine)
    tables = sqlite_inspector.get_table_names()
    logger.info(f"Found {len(tables)} tables in SQLite: {tables}")

    # Migrate each table
    SqliteSession = sessionmaker(bind=sqlite_engine)
    PgSession = sessionmaker(bind=pg_engine)

    total_rows = 0
    for table_name in tables:
        # Skip SQLite internal tables
        if table_name.startswith('sqlite_') or table_name.startswith('_'):
            continue

        # Check if table exists in PostgreSQL
        pg_inspector = inspect(pg_engine)
        if table_name not in pg_inspector.get_table_names():
            logger.warning(f"  Table '{table_name}' not in PostgreSQL schema, skipping")
            continue

        # Read all rows from SQLite
        with sqlite_engine.connect() as src_conn:
            rows = src_conn.execute(text(f"SELECT * FROM {table_name}")).fetchall()
            if not rows:
                logger.info(f"  {table_name}: 0 rows (empty)")
                continue

            # Get column names
            columns = [col["name"] for col in sqlite_inspector.get_columns(table_name)]
            pg_columns = [col["name"] for col in pg_inspector.get_columns(table_name)]
            
            # Only use columns that exist in both
            common_columns = [c for c in columns if c in pg_columns]
            if not common_columns:
                logger.warning(f"  {table_name}: no common columns, skipping")
                continue

        # Clear target table first
        with pg_engine.connect() as pg_conn:
            pg_conn.execute(text(f"DELETE FROM {table_name}"))
            pg_conn.commit()

        # Insert in batches
        batch_size = 500
        col_list = ", ".join(common_columns)
        param_list = ", ".join([f":{c}" for c in common_columns])
        insert_sql = text(f"INSERT INTO {table_name} ({col_list}) VALUES ({param_list})")

        # Detect boolean columns in PostgreSQL (SQLite stores them as 0/1 integers)
        pg_col_types = {col["name"]: str(col["type"]) for col in pg_inspector.get_columns(table_name)}
        bool_columns = {c for c in common_columns if 'BOOLEAN' in pg_col_types.get(c, '').upper()}

        inserted = 0
        with pg_engine.connect() as pg_conn:
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                row_dicts = []
                for row in batch:
                    row_dict = {}
                    for col in common_columns:
                        idx = columns.index(col)
                        val = row[idx]
                        # Cast 0/1 integers to Python booleans for PostgreSQL Boolean columns
                        if col in bool_columns and isinstance(val, int):
                            val = bool(val)
                        row_dict[col] = val
                    row_dicts.append(row_dict)
                
                pg_conn.execute(insert_sql, row_dicts)
                inserted += len(batch)
            pg_conn.commit()

        # Reset sequences for tables with auto-increment IDs
        if 'id' in common_columns:
            try:
                with pg_engine.connect() as pg_conn:
                    pg_conn.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM {table_name}), 0) + 1, false)"
                    ))
                    pg_conn.commit()
            except Exception:
                pass  # Table might not have a sequence

        logger.info(f"  {table_name}: {inserted} rows migrated")
        total_rows += inserted

    # Verify
    logger.info(f"\nMigration complete: {total_rows} total rows across {len(tables)} tables")
    logger.info("\nVerification:")
    with sqlite_engine.connect() as src, pg_engine.connect() as dst:
        for table_name in tables:
            if table_name.startswith('sqlite_') or table_name.startswith('_'):
                continue
            pg_inspector = inspect(pg_engine)
            if table_name not in pg_inspector.get_table_names():
                continue
            src_count = src.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            dst_count = dst.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
            status = "✓" if src_count == dst_count else "✗ MISMATCH"
            logger.info(f"  {table_name}: SQLite={src_count}, PostgreSQL={dst_count} {status}")


if __name__ == "__main__":
    migrate()
