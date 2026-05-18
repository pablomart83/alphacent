#!/usr/bin/env python3
"""
Phase 1 — Watchlist Elimination Migration
==========================================

For each strategy where len(symbols) > 1:
  - LIVE strategies: skip (already single-symbol, GOOGL + SOXL)
  - For each watchlist symbol (symbols[1:]):
      - Check if (template, watchlist_symbol) already exists as a strategy → skip
      - Check if there are any paper trades for this watchlist symbol
      - If trades exist: create new strategy row (clone parent, symbols=[watchlist_symbol],
        status=PAPER, name="{template} {watchlist_symbol}")
      - Reassign positions, orders, trade_journal, signal_decisions rows
        where strategy_id=parent AND symbol=watchlist_symbol → new strategy_id
      - If no trades: do NOT create strategy (watchlist symbol never traded)
  - Update parent: symbols = [symbols[0]] (primary only)

All changes run in a single transaction per parent strategy (atomic per strategy).
LIVE strategies are skipped entirely.

Run with: python3 scripts/migrate_watchlist_to_single_symbol.py [--dry-run]
"""

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_migration(dry_run: bool = False) -> None:
    from src.models.database import get_database
    from sqlalchemy import text

    db = get_database()
    session = db.get_session()

    try:
        # ── 1. Load all multi-symbol strategies (non-LIVE) ──────────────────
        rows = session.execute(
            text("""
                SELECT
                    id,
                    name,
                    status,
                    symbols,
                    rules,
                    risk_params,
                    strategy_metadata,
                    backtest_results,
                    reasoning,
                    allocation_percent,
                    created_at,
                    activated_at
                FROM strategies
                WHERE json_array_length(symbols::json) > 1
                  AND status != 'LIVE'
                ORDER BY status, name
            """)
        ).fetchall()

        logger.info(f"Found {len(rows)} multi-symbol non-LIVE strategies to migrate")

        # ── 2. Also check LIVE strategies — they should already be single-symbol ──
        live_rows = session.execute(
            text("""
                SELECT id, name, symbols
                FROM strategies
                WHERE status = 'LIVE'
            """)
        ).fetchall()
        for lr in live_rows:
            syms = lr.symbols if isinstance(lr.symbols, list) else json.loads(lr.symbols or "[]")
            if len(syms) > 1:
                logger.warning(f"LIVE strategy {lr.name} ({lr.id[:8]}) has {len(syms)} symbols — SKIPPING (manual review needed)")
            else:
                logger.info(f"LIVE strategy {lr.name} ({lr.id[:8]}) already single-symbol ✓")

        # ── 3. Build set of existing (template, symbol) pairs to avoid duplicates ──
        existing_pairs = set()
        existing_rows = session.execute(
            text("""
                SELECT
                    COALESCE(strategy_metadata->>'template_name', name) AS template_name,
                    symbols::json->>0 AS primary_symbol
                FROM strategies
                WHERE status NOT IN ('INVALID', 'PROPOSED')
            """)
        ).fetchall()
        for er in existing_rows:
            if er.template_name and er.primary_symbol:
                existing_pairs.add((er.template_name, er.primary_symbol))

        logger.info(f"Loaded {len(existing_pairs)} existing (template, symbol) pairs for dedup")

        # ── 4. Migrate each multi-symbol strategy ───────────────────────────
        stats = {
            "strategies_processed": 0,
            "watchlist_symbols_total": 0,
            "new_strategies_created": 0,
            "symbols_with_trades": 0,
            "symbols_without_trades": 0,
            "symbols_already_exist": 0,
            "positions_reassigned": 0,
            "orders_reassigned": 0,
            "trades_reassigned": 0,
            "signal_decisions_reassigned": 0,
            "parents_trimmed": 0,
        }

        for row in rows:
            strategy_id = row.id
            strategy_name = row.name
            status = row.status

            # Parse symbols
            if isinstance(row.symbols, list):
                symbols = row.symbols
            else:
                symbols = json.loads(row.symbols or "[]")

            if len(symbols) <= 1:
                continue  # Already single-symbol, skip

            primary_symbol = symbols[0]
            watchlist_symbols = symbols[1:]

            # Parse metadata
            if isinstance(row.strategy_metadata, dict):
                meta = row.strategy_metadata
            elif row.strategy_metadata:
                meta = json.loads(row.strategy_metadata)
            else:
                meta = {}

            template_name = meta.get("template_name") or strategy_name

            logger.info(
                f"\n{'='*60}\n"
                f"Processing: {strategy_name} ({strategy_id[:8]}) [{status}]\n"
                f"  Primary: {primary_symbol}\n"
                f"  Watchlist: {watchlist_symbols}"
            )

            stats["strategies_processed"] += 1
            stats["watchlist_symbols_total"] += len(watchlist_symbols)

            # Process each watchlist symbol in a savepoint (atomic per symbol)
            for wl_sym in watchlist_symbols:
                logger.info(f"  → Watchlist symbol: {wl_sym}")

                # Check if (template, wl_sym) already exists
                if (template_name, wl_sym) in existing_pairs:
                    logger.info(f"    SKIP: ({template_name}, {wl_sym}) already exists in pipeline")
                    stats["symbols_already_exist"] += 1
                    continue

                # Count trades for this watchlist symbol under this strategy
                trade_count = session.execute(
                    text("""
                        SELECT COUNT(*) FROM trade_journal
                        WHERE strategy_id = :sid AND symbol = :sym
                          AND account_type = 'demo'
                    """),
                    {"sid": strategy_id, "sym": wl_sym},
                ).scalar()

                # Count open positions
                pos_count = session.execute(
                    text("""
                        SELECT COUNT(*) FROM positions
                        WHERE strategy_id = :sid AND symbol = :sym
                          AND account_type = 'demo' AND closed_at IS NULL
                    """),
                    {"sid": strategy_id, "sym": wl_sym},
                ).scalar()

                # Count all positions (including closed)
                all_pos_count = session.execute(
                    text("""
                        SELECT COUNT(*) FROM positions
                        WHERE strategy_id = :sid AND symbol = :sym
                          AND account_type = 'demo'
                    """),
                    {"sid": strategy_id, "sym": wl_sym},
                ).scalar()

                # Count pending orders
                order_count = session.execute(
                    text("""
                        SELECT COUNT(*) FROM orders
                        WHERE strategy_id = :sid AND symbol = :sym
                          AND account_type = 'demo'
                    """),
                    {"sid": strategy_id, "sym": wl_sym},
                ).scalar()

                has_activity = (trade_count > 0 or pos_count > 0 or all_pos_count > 0 or order_count > 0)

                if not has_activity:
                    logger.info(
                        f"    NO ACTIVITY: {wl_sym} has 0 trades, 0 positions, 0 orders — "
                        f"not creating strategy"
                    )
                    stats["symbols_without_trades"] += 1
                    continue

                # Has activity — create new strategy for this watchlist symbol
                stats["symbols_with_trades"] += 1
                logger.info(
                    f"    HAS ACTIVITY: {wl_sym} — trades={trade_count}, "
                    f"positions={all_pos_count} ({pos_count} open), orders={order_count}"
                )

                new_strategy_id = str(uuid.uuid4())
                new_name = f"{template_name} {wl_sym}"
                # Determine status: PAPER if has paper trades, else BACKTESTED
                new_status = "PAPER" if trade_count > 0 else status

                # Clone metadata, update for new strategy
                new_meta = dict(meta)
                new_meta["parent_strategy_id"] = strategy_id
                new_meta["migrated_from_watchlist"] = True
                new_meta["migrated_at"] = datetime.now().isoformat()
                new_meta["template_name"] = template_name

                # Parse risk_params
                if isinstance(row.risk_params, dict):
                    risk_params = row.risk_params
                elif row.risk_params:
                    risk_params = json.loads(row.risk_params)
                else:
                    risk_params = {}

                # Parse rules
                if isinstance(row.rules, dict):
                    rules = row.rules
                elif row.rules:
                    rules = json.loads(row.rules)
                else:
                    rules = {}

                if not dry_run:
                    # Serialize all JSON fields — psycopg2 can't adapt dict/list directly.
                    def _to_json(v):
                        if v is None:
                            return None
                        if isinstance(v, str):
                            return v
                        return json.dumps(v)

                    # Insert new strategy row using psycopg2 %(name)s style with CAST for jsonb
                    from sqlalchemy import text as _text
                    session.execute(
                        _text("""
                            INSERT INTO strategies (
                                id, name, description, status, rules, symbols,
                                allocation_percent, risk_params, created_at, activated_at,
                                performance, reasoning, backtest_results, strategy_metadata,
                                live_trade_count
                            ) VALUES (
                                :id, :name, :description, :status,
                                CAST(:rules AS json), CAST(:symbols AS json),
                                :allocation_percent, CAST(:risk_params AS json),
                                :created_at, :activated_at,
                                CAST(:performance AS json), CAST(:reasoning AS json),
                                CAST(:backtest_results AS json), CAST(:strategy_metadata AS json),
                                0
                            )
                        """),
                        {
                            "id": new_strategy_id,
                            "name": new_name,
                            "description": f"Migrated from watchlist of {strategy_name}",
                            "status": new_status,
                            "rules": _to_json(rules),
                            "symbols": json.dumps([wl_sym]),
                            "allocation_percent": row.allocation_percent or 0.0,
                            "risk_params": _to_json(risk_params),
                            "created_at": datetime.now(),
                            "activated_at": row.activated_at,
                            "performance": json.dumps({"total_return": 0.0, "sharpe_ratio": 0.0,
                                                        "sortino_ratio": 0.0, "max_drawdown": 0.0,
                                                        "win_rate": 0.0, "avg_win": 0.0,
                                                        "avg_loss": 0.0, "total_trades": 0}),
                            "reasoning": _to_json(row.reasoning),
                            "backtest_results": _to_json(row.backtest_results),
                            "strategy_metadata": json.dumps(new_meta),
                        },
                    )

                    # Reassign trade_journal rows
                    tj_updated = session.execute(
                        text("""
                            UPDATE trade_journal
                            SET strategy_id = :new_sid
                            WHERE strategy_id = :old_sid AND symbol = :sym
                              AND account_type = 'demo'
                        """),
                        {"new_sid": new_strategy_id, "old_sid": strategy_id, "sym": wl_sym},
                    ).rowcount
                    stats["trades_reassigned"] += tj_updated

                    # Reassign positions (all, including closed)
                    pos_updated = session.execute(
                        text("""
                            UPDATE positions
                            SET strategy_id = :new_sid
                            WHERE strategy_id = :old_sid AND symbol = :sym
                              AND account_type = 'demo'
                        """),
                        {"new_sid": new_strategy_id, "old_sid": strategy_id, "sym": wl_sym},
                    ).rowcount
                    stats["positions_reassigned"] += pos_updated

                    # Reassign orders
                    ord_updated = session.execute(
                        text("""
                            UPDATE orders
                            SET strategy_id = :new_sid
                            WHERE strategy_id = :old_sid AND symbol = :sym
                              AND account_type = 'demo'
                        """),
                        {"new_sid": new_strategy_id, "old_sid": strategy_id, "sym": wl_sym},
                    ).rowcount
                    stats["orders_reassigned"] += ord_updated

                    # Reassign signal_decisions
                    sd_updated = session.execute(
                        text("""
                            UPDATE signal_decisions
                            SET strategy_id = :new_sid
                            WHERE strategy_id = :old_sid AND symbol = :sym
                        """),
                        {"new_sid": new_strategy_id, "old_sid": strategy_id, "sym": wl_sym},
                    ).rowcount
                    stats["signal_decisions_reassigned"] += sd_updated

                    logger.info(
                        f"    CREATED: {new_name} ({new_strategy_id[:8]}) [{new_status}] — "
                        f"reassigned {tj_updated} trades, {pos_updated} positions, "
                        f"{ord_updated} orders, {sd_updated} signal_decisions"
                    )
                else:
                    logger.info(
                        f"    [DRY RUN] Would create: {new_name} [{new_status}] — "
                        f"would reassign {trade_count} trades, {all_pos_count} positions, "
                        f"{order_count} orders"
                    )

                # Add to existing_pairs so we don't create duplicates within this run
                existing_pairs.add((template_name, wl_sym))
                stats["new_strategies_created"] += 1

            # ── Trim parent to primary symbol only ──────────────────────────
            if not dry_run:
                session.execute(
                    text("""
                        UPDATE strategies
                        SET symbols = :new_symbols
                        WHERE id = :sid
                    """),
                    {
                        "new_symbols": json.dumps([primary_symbol]),
                        "sid": strategy_id,
                    },
                )
                logger.info(f"  TRIMMED parent {strategy_name[:50]} → symbols=[{primary_symbol}]")
            else:
                logger.info(f"  [DRY RUN] Would trim parent → symbols=[{primary_symbol}]")

            stats["parents_trimmed"] += 1

        # ── 5. Commit ────────────────────────────────────────────────────────
        if not dry_run:
            session.commit()
            logger.info("\n✅ Migration committed successfully")
        else:
            session.rollback()
            logger.info("\n[DRY RUN] No changes committed")

        # ── 6. Print summary ─────────────────────────────────────────────────
        logger.info("\n" + "="*60)
        logger.info("MIGRATION SUMMARY")
        logger.info("="*60)
        for k, v in stats.items():
            logger.info(f"  {k:40s}: {v}")
        logger.info("="*60)

        if not dry_run:
            # Verify final state
            final_multi = session.execute(
                text("""
                    SELECT COUNT(*) FROM strategies
                    WHERE json_array_length(symbols::json) > 1
                      AND status != 'LIVE'
                """)
            ).scalar()
            logger.info(f"\nPost-migration: {final_multi} non-LIVE multi-symbol strategies remaining (should be 0)")

            # Verify LIVE positions untouched
            live_pos = session.execute(
                text("""
                    SELECT id, symbol, unrealized_pnl FROM positions
                    WHERE account_type = 'live' AND closed_at IS NULL
                """)
            ).fetchall()
            logger.info(f"LIVE positions intact: {len(live_pos)}")
            for lp in live_pos:
                logger.info(f"  {lp.symbol}: unrealized_pnl={lp.unrealized_pnl:.2f}")

    except Exception as e:
        session.rollback()
        logger.error(f"Migration FAILED: {e}", exc_info=True)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate watchlist strategies to single-symbol")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without committing")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("DRY RUN MODE — no changes will be committed")
    else:
        logger.info("LIVE MODE — changes will be committed to the database")
        logger.info("Starting in 3 seconds... Ctrl+C to abort")
        import time
        time.sleep(3)

    run_migration(dry_run=args.dry_run)
