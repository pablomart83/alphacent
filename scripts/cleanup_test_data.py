"""
Database cleanup script for Task 6.2: Clean Up Test Data and Stale Positions.

Removes test artifacts and stale data from the database:
1. Remove fake test positions (strategy_1, strategy_2, strategy_3)
2. Remove old manual/vibe_coding orders
3. Retire all BACKTESTED strategies
4. Validate DEMO strategies have proper rules/indicators
5. Clean up orphaned data (positions/orders without valid strategies)
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.database import get_database
from src.models.enums import StrategyStatus
from src.models.orm import (
    OrderORM,
    PositionORM,
    StrategyORM,
    StrategyRetirementORM,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def cleanup_test_positions(session) -> int:
    """Remove fake test positions (strategy_1, strategy_2, strategy_3)."""
    fake_strategy_ids = ["strategy_1", "strategy_2", "strategy_3"]
    deleted = (
        session.query(PositionORM)
        .filter(PositionORM.strategy_id.in_(fake_strategy_ids))
        .delete(synchronize_session="fetch")
    )
    logger.info(f"Removed {deleted} fake test positions (strategy_1/2/3)")
    return deleted


def cleanup_orphaned_positions(session) -> int:
    """Remove positions whose strategy_id doesn't exist in strategies table.
    
    Note: Positions synced from eToro (etoro_position) may reappear if the
    backend is running, since it re-syncs real broker positions periodically.
    """
    from sqlalchemy import not_, select

    subq = select(StrategyORM.id)
    orphaned = (
        session.query(PositionORM)
        .filter(not_(PositionORM.strategy_id.in_(subq)))
        .all()
    )
    count = 0
    for pos in orphaned:
        logger.info(
            f"  Removing orphaned position: id={pos.id}, "
            f"strategy_id={pos.strategy_id}, symbol={pos.symbol}"
        )
        session.delete(pos)
        count += 1
    logger.info(f"Removed {count} orphaned positions")
    return count


def cleanup_stale_orders(session) -> int:
    """Remove old manual and vibe_coding orders that are no longer relevant."""
    stale_strategy_ids = ["manual", "manual_vibe_coding"]
    deleted = (
        session.query(OrderORM)
        .filter(OrderORM.strategy_id.in_(stale_strategy_ids))
        .delete(synchronize_session="fetch")
    )
    logger.info(f"Removed {deleted} stale manual/vibe_coding orders")
    return deleted


def cleanup_orphaned_orders(session) -> int:
    """Remove orders whose strategy_id doesn't exist in strategies table."""
    from sqlalchemy import not_, select

    subq = select(StrategyORM.id)
    orphaned = (
        session.query(OrderORM)
        .filter(not_(OrderORM.strategy_id.in_(subq)))
        .all()
    )
    count = 0
    for order in orphaned:
        logger.info(
            f"  Removing orphaned order: id={order.id}, "
            f"strategy_id={order.strategy_id}, symbol={order.symbol}"
        )
        session.delete(order)
        count += 1
    logger.info(f"Removed {count} orphaned orders")
    return count


def retire_backtested_strategies(session) -> int:
    """Retire all BACKTESTED strategies and record retirements."""
    backtested = (
        session.query(StrategyORM)
        .filter(StrategyORM.status == StrategyStatus.BACKTESTED)
        .all()
    )
    now = datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    count = 0
    for strategy in backtested:
        strategy.status = StrategyStatus.RETIRED
        strategy.retired_at = now

        # Record retirement
        perf = strategy.performance or {}
        if isinstance(perf, str):
            perf = json.loads(perf)

        retirement = StrategyRetirementORM(
            strategy_id=strategy.id,
            retired_at=now,
            reason="Bulk cleanup: BACKTESTED strategy never activated",
            final_sharpe=perf.get("sharpe_ratio"),
            final_return=perf.get("total_return"),
        )
        session.add(retirement)
        count += 1

    logger.info(f"Retired {count} BACKTESTED strategies")
    return count


def validate_demo_strategies(session) -> dict:
    """Validate that all DEMO strategies have proper rules and indicators."""
    demo_strategies = (
        session.query(StrategyORM)
        .filter(StrategyORM.status == StrategyStatus.DEMO)
        .all()
    )
    results = {"total": len(demo_strategies), "valid": 0, "invalid": []}

    for strategy in demo_strategies:
        rules = strategy.rules
        if isinstance(rules, str):
            rules = json.loads(rules)

        symbols = strategy.symbols
        if isinstance(symbols, str):
            symbols = json.loads(symbols)

        has_entry = bool(rules.get("entry_conditions"))
        has_exit = bool(rules.get("exit_conditions"))
        has_indicators = bool(rules.get("indicators"))
        has_symbols = bool(symbols)

        if has_entry and has_exit and has_indicators and has_symbols:
            results["valid"] += 1
        else:
            results["invalid"].append(
                {
                    "id": strategy.id,
                    "name": strategy.name,
                    "has_entry": has_entry,
                    "has_exit": has_exit,
                    "has_indicators": has_indicators,
                    "has_symbols": has_symbols,
                }
            )

    logger.info(
        f"DEMO strategy validation: {results['valid']}/{results['total']} valid"
    )
    for inv in results["invalid"]:
        logger.warning(f"  Invalid DEMO strategy: {inv['name']} ({inv['id']})")

    return results


def run_cleanup():
    """Execute the full database cleanup."""
    logger.info("=" * 60)
    logger.info("Starting database cleanup (Task 6.2)")
    logger.info("=" * 60)

    db = get_database()
    session = db.get_session()

    try:
        # Pre-cleanup stats
        logger.info("\n--- Pre-cleanup stats ---")
        pos_count = session.query(PositionORM).count()
        order_count = session.query(OrderORM).count()
        strat_counts = {}
        for s in session.query(StrategyORM).all():
            status = s.status.value if hasattr(s.status, "value") else str(s.status)
            strat_counts[status] = strat_counts.get(status, 0) + 1
        logger.info(f"Positions: {pos_count}")
        logger.info(f"Orders: {order_count}")
        logger.info(f"Strategies by status: {strat_counts}")

        # Step 1: Remove fake test positions
        logger.info("\n--- Step 1: Remove fake test positions ---")
        cleanup_test_positions(session)

        # Step 2: Remove orphaned positions
        logger.info("\n--- Step 2: Remove orphaned positions ---")
        cleanup_orphaned_positions(session)

        # Step 3: Remove stale manual/vibe_coding orders
        logger.info("\n--- Step 3: Remove stale orders ---")
        cleanup_stale_orders(session)

        # Step 4: Remove orphaned orders
        logger.info("\n--- Step 4: Remove orphaned orders ---")
        cleanup_orphaned_orders(session)

        # Step 5: Retire BACKTESTED strategies
        logger.info("\n--- Step 5: Retire BACKTESTED strategies ---")
        retire_backtested_strategies(session)

        # Step 6: Validate DEMO strategies
        logger.info("\n--- Step 6: Validate DEMO strategies ---")
        validation = validate_demo_strategies(session)

        # Commit all changes
        session.commit()
        logger.info("\nAll changes committed successfully.")

        # Post-cleanup stats
        logger.info("\n--- Post-cleanup stats ---")
        pos_count = session.query(PositionORM).count()
        order_count = session.query(OrderORM).count()
        strat_counts = {}
        for s in session.query(StrategyORM).all():
            status = s.status.value if hasattr(s.status, "value") else str(s.status)
            strat_counts[status] = strat_counts.get(status, 0) + 1
        logger.info(f"Positions: {pos_count}")
        logger.info(f"Orders: {order_count}")
        logger.info(f"Strategies by status: {strat_counts}")
        logger.info(
            f"DEMO strategies valid: {validation['valid']}/{validation['total']}"
        )

        logger.info("\n" + "=" * 60)
        logger.info("Database cleanup complete!")
        logger.info("=" * 60)
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Cleanup failed: {e}", exc_info=True)
        return False
    finally:
        session.close()


if __name__ == "__main__":
    success = run_cleanup()
    sys.exit(0 if success else 1)
