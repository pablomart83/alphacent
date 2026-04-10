"""Database initialization and connection management."""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .orm import Base

logger = logging.getLogger(__name__)


def _get_database_url(db_path: str = "alphacent.db") -> str:
    """Get database URL from environment or use PostgreSQL default.
    
    To fall back to SQLite, set:
        export DATABASE_URL=sqlite:///alphacent.db
    """
    return os.environ.get("DATABASE_URL", "postgresql://localhost/alphacent")


class Database:
    """Database connection manager. Supports PostgreSQL and SQLite."""

    def __init__(self, db_path: str = "alphacent.db"):
        """Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file (ignored if DATABASE_URL is set)
        """
        self.db_path = db_path
        self.database_url = _get_database_url(db_path)
        self.is_postgres = self.database_url.startswith("postgresql")
        
        if self.is_postgres:
            # Register psycopg2 adapters for numpy types.
            # psycopg2 doesn't know how to serialize np.float64, np.int64, etc.
            # Without this, they render as 'np.float64(1.0)' in SQL — which PostgreSQL
            # interprets as a schema reference and crashes.
            try:
                import numpy as np
                import psycopg2.extensions
                psycopg2.extensions.register_adapter(np.float64, lambda v: psycopg2.extensions.AsIs(float(v)))
                psycopg2.extensions.register_adapter(np.float32, lambda v: psycopg2.extensions.AsIs(float(v)))
                psycopg2.extensions.register_adapter(np.int64, lambda v: psycopg2.extensions.AsIs(int(v)))
                psycopg2.extensions.register_adapter(np.int32, lambda v: psycopg2.extensions.AsIs(int(v)))
                psycopg2.extensions.register_adapter(np.bool_, lambda v: psycopg2.extensions.AsIs(bool(v)))
                logger.info("Registered psycopg2 adapters for numpy types")
            except ImportError:
                pass
            
            self.engine = create_engine(
                self.database_url,
                echo=False,
                pool_size=20,
                max_overflow=10,
                pool_pre_ping=False,  # Skip per-connection health check (saves ~1ms per query)
                pool_recycle=1800,
                pool_timeout=10,
                # Use prepared statements and keep connections warm
                connect_args={
                    "options": "-c statement_timeout=120000 -c idle_in_transaction_session_timeout=300000"
                },
            )
            logger.info(f"Using PostgreSQL: {self.database_url.split('@')[-1] if '@' in self.database_url else self.database_url}")
        else:
            self.engine = create_engine(
                self.database_url,
                echo=False,
                pool_size=10,
                max_overflow=5,
                pool_pre_ping=True,
                pool_recycle=1800,
                pool_timeout=10,
                connect_args={"timeout": 30}
            )
            # SQLite PRAGMAs for WAL mode
            from sqlalchemy import event
            @event.listens_for(self.engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=60000")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA cache_size=-64000")
                cursor.execute("PRAGMA wal_autocheckpoint=1000")
                cursor.close()
            logger.info(f"Using SQLite: {db_path}")
        
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self._initialized = False

    def initialize(self) -> None:
        """Initialize database schema (create tables)."""
        if self._initialized:
            logger.info("Database already initialized")
            return

        logger.info(f"Initializing database at {self.database_url.split('@')[-1] if '@' in self.database_url else self.db_path}")
        Base.metadata.create_all(bind=self.engine)
        if not self.is_postgres:
            self._ensure_schema_updates()
        self._initialized = True
        logger.info("Database initialized successfully")

    def _ensure_schema_updates(self) -> None:
        """Apply incremental schema updates for columns added after initial creation.

        SQLite's CREATE TABLE IF NOT EXISTS won't add new columns to existing tables,
        so we handle that here with ALTER TABLE ADD COLUMN (idempotent via column check).
        """
        from sqlalchemy import text, inspect

        inspector = inspect(self.engine)
        migrations = [
            # (table, column, sql_type, default)
            ("positions", "close_order_id", "VARCHAR", None),
            ("positions", "close_attempts", "INTEGER DEFAULT 0", None),
            ("fundamental_data_cache", "dividend_yield", "FLOAT", None),
            ("fundamental_data_cache", "earnings_surprise", "FLOAT", None),
            ("account_info", "equity", "FLOAT DEFAULT 0.0", None),
            ("positions", "invested_amount", "FLOAT", None),
            ("historical_price_cache", "interval", "VARCHAR DEFAULT '1d'", None),
            ("trade_journal", "side", "VARCHAR", None),
            ("orders", "order_action", "VARCHAR", None),
        ]

        with self.engine.connect() as conn:
            for table, column, sql_type, _default in migrations:
                existing = [c["name"] for c in inspector.get_columns(table)]
                if column not in existing:
                    try:
                        conn.execute(text(
                            f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"
                        ))
                        conn.commit()
                        logger.info(f"Added column {table}.{column}")
                    except Exception as e:
                        logger.debug(f"Column {table}.{column} may already exist: {e}")

            # Create unique index for (symbol, date, interval) if it doesn't exist
            # This replaces the old (symbol, date) constraint for intraday support
            try:
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_hist_symbol_date_interval "
                    "ON historical_price_cache (symbol, date, interval)"
                ))
                conn.commit()
                logger.debug("Ensured unique index ix_hist_symbol_date_interval exists")
            except Exception as e:
                logger.debug(f"Index ix_hist_symbol_date_interval may already exist: {e}")

            # Migrate historical_price_cache: replace old UNIQUE(symbol, date) with
            # UNIQUE(symbol, date, interval) to support 1h bars alongside 1d bars.
            # SQLite can't ALTER constraints, so we recreate the table.
            try:
                # Check if old constraint still exists by looking at table DDL
                ddl_row = conn.execute(text(
                    "SELECT sql FROM sqlite_master WHERE tbl_name = 'historical_price_cache' AND type = 'table'"
                )).fetchone()
                if ddl_row and 'uq_historical_symbol_date' in ddl_row[0] and 'interval' not in ddl_row[0].split('UNIQUE')[1].split(')')[0]:
                    logger.info("Migrating historical_price_cache: replacing UNIQUE(symbol, date) with UNIQUE(symbol, date, interval)")
                    conn.execute(text("ALTER TABLE historical_price_cache RENAME TO _hpc_old"))
                    conn.execute(text("""
                        CREATE TABLE historical_price_cache (
                            id INTEGER NOT NULL PRIMARY KEY,
                            symbol VARCHAR NOT NULL,
                            date DATETIME NOT NULL,
                            interval VARCHAR NOT NULL DEFAULT '1d',
                            open FLOAT NOT NULL,
                            high FLOAT NOT NULL,
                            low FLOAT NOT NULL,
                            close FLOAT NOT NULL,
                            volume FLOAT NOT NULL DEFAULT 0.0,
                            source VARCHAR NOT NULL,
                            fetched_at DATETIME NOT NULL,
                            CONSTRAINT uq_historical_symbol_date_interval UNIQUE (symbol, date, interval)
                        )
                    """))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_historical_price_cache_symbol ON historical_price_cache (symbol)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_historical_price_cache_date ON historical_price_cache (date)"))
                    conn.execute(text("""
                        INSERT INTO historical_price_cache (id, symbol, date, interval, open, high, low, close, volume, source, fetched_at)
                        SELECT id, symbol, date, COALESCE(interval, '1d'), open, high, low, close, volume, source, fetched_at
                        FROM _hpc_old
                    """))
                    conn.execute(text("DROP TABLE _hpc_old"))
                    conn.commit()
                    logger.info("Migration complete: historical_price_cache now supports multi-interval data")
            except Exception as e:
                logger.warning(f"historical_price_cache migration failed (may already be done): {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass

    def get_session(self) -> Session:
        """Get a new database session.
        
        Returns:
            SQLAlchemy session
        """
        return self.SessionLocal()

    def close(self) -> None:
        """Close database connection."""
        self.engine.dispose()
        logger.info("Database connection closed")


# Global database instance
_db_instance: Optional[Database] = None


def get_database(db_path: str = "alphacent.db") -> Database:
    """Get or create global database instance.
    
    Uses DATABASE_URL env var for PostgreSQL, falls back to SQLite at db_path.
        
    Returns:
        Database instance
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path)
        _db_instance.initialize()
    return _db_instance


def init_database(db_path: str = "alphacent.db") -> None:
    """Initialize database with schema.
    
    Args:
        db_path: Path to SQLite database file
    """
    db = get_database(db_path)
    db.initialize()


def cleanup_stale_data(config: dict = None) -> Dict[str, int]:
    """Clean up stale data from the database based on retention policies.
    
    Retention policies (configurable via config):
    - Historical prices: Keep max 2000 days per symbol
    - Filter logs: Keep 90 days
    - Retired strategies: Purge backtest results for strategies retired >90 days
    
    Args:
        config: Optional config dict with data_management.retention settings
        
    Returns:
        Dict with counts of deleted records per category
    """
    from datetime import datetime, timedelta
    
    # Default retention periods
    retention = {
        'historical_prices_days': 2000,
        'filter_logs_days': 90,
        'retired_strategy_days': 90,
    }
    
    # Override from config if provided
    if config:
        dm_config = config.get('data_management', {}).get('retention', {})
        retention['historical_prices_days'] = dm_config.get('historical_prices_days', 2000)
        retention['filter_logs_days'] = dm_config.get('filter_logs_days', 90)
        retention['retired_strategy_days'] = dm_config.get('retired_strategy_days', 90)
    
    db = get_database()
    session = db.get_session()
    results = {
        'historical_prices_deleted': 0,
        'fundamental_filter_logs_deleted': 0,
        'ml_filter_logs_deleted': 0,
        'conviction_logs_deleted': 0,
    }
    
    try:
        now = datetime.now()
        
        # 1. Historical prices: delete bars older than retention period per symbol
        try:
            from .orm import HistoricalPriceCacheORM
            cutoff = now - timedelta(days=retention['historical_prices_days'])
            deleted = session.query(HistoricalPriceCacheORM).filter(
                HistoricalPriceCacheORM.date < cutoff
            ).delete(synchronize_session=False)
            results['historical_prices_deleted'] = deleted
        except Exception as e:
            logger.warning(f"Error cleaning historical prices: {e}")
        
        # 2. Filter logs: delete entries older than retention period
        try:
            from .orm import FundamentalFilterLogORM
            cutoff = now - timedelta(days=retention['filter_logs_days'])
            deleted = session.query(FundamentalFilterLogORM).filter(
                FundamentalFilterLogORM.timestamp < cutoff
            ).delete(synchronize_session=False)
            results['fundamental_filter_logs_deleted'] = deleted
        except Exception as e:
            logger.warning(f"Error cleaning fundamental filter logs: {e}")
        
        try:
            from .orm import MLFilterLogORM
            cutoff = now - timedelta(days=retention['filter_logs_days'])
            deleted = session.query(MLFilterLogORM).filter(
                MLFilterLogORM.timestamp < cutoff
            ).delete(synchronize_session=False)
            results['ml_filter_logs_deleted'] = deleted
        except Exception as e:
            logger.warning(f"Error cleaning ML filter logs: {e}")
        
        try:
            from .orm import ConvictionScoreLogORM
            cutoff = now - timedelta(days=retention['filter_logs_days'])
            deleted = session.query(ConvictionScoreLogORM).filter(
                ConvictionScoreLogORM.timestamp < cutoff
            ).delete(synchronize_session=False)
            results['conviction_logs_deleted'] = deleted
        except Exception as e:
            logger.warning(f"Error cleaning conviction score logs: {e}")
        
        session.commit()
        
        total = sum(results.values())
        if total > 0:
            logger.info(f"Data cleanup complete: {total} records deleted ({results})")
        else:
            logger.debug("Data cleanup: no stale records found")
        
        return results
        
    except Exception as e:
        logger.error(f"Error during data cleanup: {e}")
        session.rollback()
        return results
    finally:
        session.close()

def cleanup_removed_symbols(removed_symbols: list) -> Dict[str, int]:
    """Remove all data for symbols that have been removed from the tradeable instruments list.

    Cleans up data across all tables that reference the removed symbols.
    For strategies, handles the JSON symbols field specially:
    - Strategies that ONLY reference removed symbols are retired
    - Strategies that reference removed symbols among others have those symbols removed from the list

    This function is idempotent — safe to run multiple times.

    Args:
        removed_symbols: List of symbol strings to remove (e.g., ["SQ", "DE"])

    Returns:
        Dict with counts of deleted/modified records per table
    """
    from datetime import datetime

    if not removed_symbols:
        logger.info("No symbols to remove")
        return {}

    db = get_database()
    session = db.get_session()
    results = {}

    logger.info(f"Cleaning up data for removed symbols: {removed_symbols}")

    try:
        # Tables with a simple 'symbol' column — bulk delete
        simple_tables = [
            ("historical_price_cache", "HistoricalPriceCacheORM"),
            ("fundamental_data_cache", "FundamentalDataORM"),
            ("data_quality_reports", "DataQualityReportORM"),
            ("earnings_history", "EarningsHistoryORM"),
            ("fundamental_filter_logs", "FundamentalFilterLogORM"),
            ("ml_filter_logs", "MLFilterLogORM"),
            ("conviction_score_logs", "ConvictionScoreLogORM"),
            ("rejected_signals", "RejectedSignalORM"),
            ("signal_decision_log", "SignalDecisionLogORM"),
            ("trading_signals", "TradingSignalORM"),
            ("market_data", "MarketDataORM"),
            ("orders", "OrderORM"),
            ("positions", "PositionORM"),
        ]

        for table_name, orm_name in simple_tables:
            try:
                # Import ORM models inside function to avoid circular imports
                from . import orm as orm_module
                OrmClass = getattr(orm_module, orm_name)
                deleted = session.query(OrmClass).filter(
                    OrmClass.symbol.in_(removed_symbols)
                ).delete(synchronize_session=False)
                results[table_name] = deleted
                if deleted > 0:
                    logger.info(f"Deleted {deleted} records from {table_name} for symbols {removed_symbols}")
            except Exception as e:
                logger.warning(f"Error cleaning {table_name}: {e}")
                results[table_name] = 0

        # Handle strategies specially — symbols is a JSON list
        try:
            from .orm import StrategyORM
            from .enums import StrategyStatus

            strategies_retired = 0
            strategies_updated = 0

            # Find all strategies that reference any removed symbol
            all_strategies = session.query(StrategyORM).all()
            for strategy in all_strategies:
                symbols = strategy.symbols or []
                if not isinstance(symbols, list):
                    continue

                # Check if any removed symbol is in this strategy's symbol list
                overlap = [s for s in symbols if s in removed_symbols]
                if not overlap:
                    continue

                remaining = [s for s in symbols if s not in removed_symbols]

                if not remaining:
                    # Strategy ONLY references removed symbols — retire it
                    if strategy.status != StrategyStatus.RETIRED:
                        strategy.status = StrategyStatus.RETIRED
                        strategy.retired_at = datetime.now()
                        strategies_retired += 1
                        logger.info(
                            f"Retired strategy {strategy.id} ({strategy.name}) — "
                            f"all symbols removed: {overlap}"
                        )
                else:
                    # Remove the symbols from the list
                    strategy.symbols = remaining
                    strategies_updated += 1
                    logger.info(
                        f"Updated strategy {strategy.id} ({strategy.name}) — "
                        f"removed symbols {overlap}, remaining: {remaining}"
                    )

            results['strategies_retired'] = strategies_retired
            results['strategies_updated'] = strategies_updated

        except Exception as e:
            logger.warning(f"Error cleaning strategies: {e}")
            results['strategies_retired'] = 0
            results['strategies_updated'] = 0

        session.commit()

        total = sum(results.values())
        logger.info(f"Symbol cleanup complete for {removed_symbols}: {total} total changes ({results})")

        return results

    except Exception as e:
        logger.error(f"Error during symbol cleanup: {e}")
        session.rollback()
        return results
    finally:
        session.close()


async def warm_new_symbols_cache(new_symbols: list) -> Dict[str, Any]:
    """Warm the database cache for newly added symbols.

    Fetches and caches fundamental data (via FMP) and historical price data
    for each new symbol so they're ready for the next autonomous cycle.

    Args:
        new_symbols: List of symbol strings to warm cache for

    Returns:
        Dict with results: symbols_warmed, symbols_failed, details
    """
    from typing import Any

    if not new_symbols:
        logger.info("No new symbols to warm cache for")
        return {"symbols_warmed": [], "symbols_failed": [], "details": {}}

    logger.info(f"Warming cache for {len(new_symbols)} new symbols: {new_symbols}")

    warmed = []
    failed = []
    details = {}

    # Warm fundamental data via FundamentalDataProvider
    try:
        from src.data.fundamental_data_provider import FundamentalDataProvider
        fdp = FundamentalDataProvider()

        for symbol in new_symbols:
            try:
                data = await fdp.get_fundamental_data(symbol, use_cache=False)
                if data:
                    details[symbol] = {"fundamentals": "cached"}
                    logger.info(f"Warmed fundamental data for {symbol}")
                else:
                    details[symbol] = {"fundamentals": "no_data"}
                    logger.warning(f"No fundamental data available for {symbol}")
            except Exception as e:
                details.setdefault(symbol, {})["fundamentals"] = f"error: {e}"
                logger.warning(f"Failed to warm fundamental data for {symbol}: {e}")
    except Exception as e:
        logger.warning(f"Could not initialize FundamentalDataProvider: {e}")

    # Warm historical price data via MarketDataManager
    try:
        from src.data.market_data_manager import MarketDataManager
        mdm = MarketDataManager()

        for symbol in new_symbols:
            try:
                df = await mdm.get_historical_data(symbol, days=1825)
                if df is not None and len(df) > 0:
                    details.setdefault(symbol, {})["historical_prices"] = f"{len(df)} bars cached"
                    warmed.append(symbol)
                    logger.info(f"Warmed historical prices for {symbol}: {len(df)} bars")
                else:
                    details.setdefault(symbol, {})["historical_prices"] = "no_data"
                    if symbol not in failed:
                        failed.append(symbol)
                    logger.warning(f"No historical price data for {symbol}")
            except Exception as e:
                details.setdefault(symbol, {})["historical_prices"] = f"error: {e}"
                if symbol not in failed:
                    failed.append(symbol)
                logger.warning(f"Failed to warm historical prices for {symbol}: {e}")
    except Exception as e:
        logger.warning(f"Could not initialize MarketDataManager: {e}")
        for symbol in new_symbols:
            if symbol not in warmed and symbol not in failed:
                failed.append(symbol)

    # Symbols that got fundamentals but not prices still count as partially warmed
    for symbol in new_symbols:
        if symbol not in warmed and symbol not in failed:
            failed.append(symbol)

    result = {
        "symbols_warmed": warmed,
        "symbols_failed": failed,
        "details": details,
    }

    logger.info(
        f"Cache warming complete: {len(warmed)} warmed, {len(failed)} failed "
        f"out of {len(new_symbols)} symbols"
    )

    return result

