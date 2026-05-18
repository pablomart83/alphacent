#!/usr/bin/env python3
"""
Fix open positions that are misattributed after watchlist migration.

These are positions in a non-primary symbol sitting under a parent strategy
whose symbols=[primary_symbol]. The migration skipped creating new strategies
for these because they had no closed trades (no P&L in trade_journal) — only
open positions.

For each such position:
  1. Check if a strategy for (template, position_symbol) already exists
     → if yes, reassign the position to it
  2. If not, create a new PAPER strategy (clone of parent, symbols=[position_symbol])
     and reassign the position + any related orders/signal_decisions

Run with: python3 scripts/fix_open_position_orphans.py [--dry-run]
"""

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


def run_fix(dry_run: bool = False) -> None:
    from src.models.database import get_database
    from sqlalchemy import text

    db = get_database()
    session = db.get_session()

    try:
        # Find all open positions where position.symbol != strategy.symbols[0]
        orphans = session.execute(text("""
            SELECT
                s.id                                                    AS strategy_id,
                s.name                                                  AS strategy_name,
                s.symbols::json->>0                                     AS primary_symbol,
                s.rules,
                s.risk_params,
                s.strategy_metadata,
                s.backtest_results,
                s.reasoning,
                s.allocation_percent,
                s.activated_at,
                COALESCE(s.strategy_metadata->>'template_name', s.name) AS template_name,
                p.id                                                    AS position_id,
                p.symbol                                                AS position_symbol,
                p.unrealized_pnl
            FROM strategies s
            JOIN positions p ON p.strategy_id = s.id
            WHERE p.account_type = 'demo'
              AND p.closed_at IS NULL
              AND s.status = 'PAPER'
              AND p.symbol != s.symbols::json->>0
            ORDER BY s.name, p.symbol
        """)).fetchall()

        logger.info(f"Found {len(orphans)} misattributed open positions")

        # Build existing (template, symbol) → strategy_id map
        existing = session.execute(text("""
            SELECT
                COALESCE(strategy_metadata->>'template_name', name) AS template_name,
                symbols::json->>0                                    AS primary_symbol,
                id
            FROM strategies
            WHERE status NOT IN ('INVALID', 'PROPOSED', 'RETIRED')
        """)).fetchall()
        existing_map = {}  # (template_name, symbol) -> strategy_id
        for r in existing:
            if r.template_name and r.primary_symbol:
                existing_map[(r.template_name, r.primary_symbol)] = r.id

        stats = {"positions_reassigned": 0, "strategies_created": 0,
                 "orders_reassigned": 0, "signal_decisions_reassigned": 0}

        def _to_json(v):
            if v is None:
                return None
            if isinstance(v, str):
                return v
            return json.dumps(v)

        for row in orphans:
            template_name = row.template_name
            pos_sym = row.position_symbol
            key = (template_name, pos_sym)

            logger.info(f"\n  Position {row.position_id} | {pos_sym} | under '{row.strategy_name}' (primary={row.primary_symbol})")

            # Does a strategy for (template, pos_sym) already exist?
            target_strategy_id = existing_map.get(key)

            if target_strategy_id:
                logger.info(f"    → Existing strategy found for ({template_name}, {pos_sym}): {target_strategy_id[:8]}")
            else:
                # Create new strategy
                new_id = str(uuid.uuid4())
                new_name = f"{template_name} {pos_sym}"

                meta = row.strategy_metadata if isinstance(row.strategy_metadata, dict) else (json.loads(row.strategy_metadata) if row.strategy_metadata else {})
                new_meta = dict(meta)
                new_meta["parent_strategy_id"] = row.strategy_id
                new_meta["migrated_from_watchlist"] = True
                new_meta["migrated_at"] = datetime.now().isoformat()
                new_meta["template_name"] = template_name

                rules = row.rules if isinstance(row.rules, dict) else (json.loads(row.rules) if row.rules else {})
                risk_params = row.risk_params if isinstance(row.risk_params, dict) else (json.loads(row.risk_params) if row.risk_params else {})

                logger.info(f"    → Creating new strategy: {new_name} ({new_id[:8]})")

                if not dry_run:
                    session.execute(text("""
                        INSERT INTO strategies (
                            id, name, description, status, rules, symbols,
                            allocation_percent, risk_params, created_at, activated_at,
                            performance, reasoning, backtest_results, strategy_metadata,
                            live_trade_count
                        ) VALUES (
                            :id, :name, :description, 'PAPER',
                            CAST(:rules AS json), CAST(:symbols AS json),
                            :allocation_percent, CAST(:risk_params AS json),
                            :created_at, :activated_at,
                            CAST(:performance AS json), CAST(:reasoning AS json),
                            CAST(:backtest_results AS json), CAST(:strategy_metadata AS json),
                            0
                        )
                    """), {
                        "id": new_id,
                        "name": new_name,
                        "description": f"Created for open position in {pos_sym} (watchlist migration fix)",
                        "rules": _to_json(rules),
                        "symbols": json.dumps([pos_sym]),
                        "allocation_percent": row.allocation_percent or 0.0,
                        "risk_params": _to_json(risk_params),
                        "created_at": datetime.now(),
                        "activated_at": row.activated_at,
                        "performance": json.dumps({"total_return": 0.0, "sharpe_ratio": 0.0,
                                                    "sortino_ratio": 0.0, "max_drawdown": 0.0,
                                                    "win_rate": 0.0, "avg_win": 0.0,
                                                    "avg_loss": 0.0, "total_trades": 0}),
                        "reasoning": _to_json(row.reasoning),
                        "backtest_results": _to_json(row.backtrack_results if hasattr(row, 'backtrack_results') else row.backtest_results),
                        "strategy_metadata": json.dumps(new_meta),
                    })
                    stats["strategies_created"] += 1

                target_strategy_id = new_id
                existing_map[key] = new_id  # prevent duplicates within this run

            # Reassign the position
            if not dry_run:
                session.execute(text("""
                    UPDATE positions SET strategy_id = :new_sid
                    WHERE id = :pos_id
                """), {"new_sid": target_strategy_id, "pos_id": row.position_id})
                stats["positions_reassigned"] += 1

                # Reassign any open orders for this position's symbol under the old strategy
                ord_count = session.execute(text("""
                    UPDATE orders SET strategy_id = :new_sid
                    WHERE strategy_id = :old_sid AND symbol = :sym
                      AND account_type = 'demo' AND status = 'PENDING'
                """), {"new_sid": target_strategy_id, "old_sid": row.strategy_id, "sym": pos_sym}).rowcount
                stats["orders_reassigned"] += ord_count

                # Reassign signal_decisions for this symbol under the old strategy
                sd_count = session.execute(text("""
                    UPDATE signal_decisions SET strategy_id = :new_sid
                    WHERE strategy_id = :old_sid AND symbol = :sym
                """), {"new_sid": target_strategy_id, "old_sid": row.strategy_id, "sym": pos_sym}).rowcount
                stats["signal_decisions_reassigned"] += sd_count

                logger.info(f"    → Reassigned position + {ord_count} orders + {sd_count} signal_decisions")
            else:
                logger.info(f"    [DRY RUN] Would reassign position {row.position_id} → {target_strategy_id[:8] if target_strategy_id else 'NEW'}")

        if not dry_run:
            session.commit()
            logger.info("\n✅ Fix committed")

            # Verify
            remaining = session.execute(text("""
                SELECT COUNT(*) FROM strategies s
                JOIN positions p ON p.strategy_id = s.id
                WHERE p.account_type = 'demo' AND p.closed_at IS NULL
                  AND s.status = 'PAPER'
                  AND p.symbol != s.symbols::json->>0
            """)).scalar()
            logger.info(f"Remaining misattributed positions: {remaining} (should be 0)")

            live_pos = session.execute(text("""
                SELECT symbol, unrealized_pnl FROM positions
                WHERE account_type = 'live' AND closed_at IS NULL
            """)).fetchall()
            logger.info(f"LIVE positions intact: {len(live_pos)}")
            for lp in live_pos:
                logger.info(f"  {lp.symbol}: {lp.unrealized_pnl:.2f}")
        else:
            session.rollback()
            logger.info("\n[DRY RUN] No changes committed")

        logger.info("\n" + "="*50)
        logger.info("SUMMARY")
        for k, v in stats.items():
            logger.info(f"  {k}: {v}")

    except Exception as e:
        session.rollback()
        logger.error(f"Fix FAILED: {e}", exc_info=True)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.dry_run:
        logger.info("LIVE MODE — starting in 3s")
        import time; time.sleep(3)
    run_fix(dry_run=args.dry_run)
