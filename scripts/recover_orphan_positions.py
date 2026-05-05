"""Recover orphan positions whose strategy_id was set to 'etoro_position'
because the originating order was incorrectly marked CANCELLED/FAILED
before eToro executed it at market open.

Background
----------
On 2026-05-04 21:52 UTC a stale-order cleanup sweep called cancel_order()
on six PENDING orders (XLK, SOXL, SMH, TQQQ) that had been submitted
21:42-21:46 UTC and were legitimately queued for the 2026-05-05 09:30 ET
market open.  eToro returned 404 on the cancel endpoint (the orders were
queued, not cancellable).  Our code mis-interpreted cancel-404 as
"order gone" and transitioned the local rows to CANCELLED/FAILED.

At 13:30:03-13:30:06 UTC on 2026-05-05 eToro executed those queued orders.
The next monitoring_service sync tick found 4 new positions with no
matching DB row and created them with the default fallback
strategy_id='etoro_position'.  Those positions are now invisible to:
  - TSL cycle (no strategy_id → no risk_params lookup → no trail)
  - loser-pair penalty (no template_name in metadata)
  - conviction validation loop (no conviction_score, no template)
  - per-strategy concentration caps
  - strategy retirement cleanup
  - trade journal closed-trade attribution

This script re-links each orphan to its originating order and backfills
the trade_journal entry with the signal-time metadata.

Matching algorithm (per orphan position)
-----------------------------------------
1. orders table: (symbol, submitted_at within ±24h of position.opened_at,
   status IN (CANCELLED, FAILED), order_metadata IS NOT NULL).
   If multiple matches, pick the one whose etoro_order_id is numerically
   closest to the position's etoro_position_id (eToro position IDs often
   derive from order IDs on fill).

2. Fallback: conviction_score_logs by (symbol, timestamp within 6h before
   position.opened_at).  Used only when no order match exists.

For each matched orphan:
  - UPDATE positions.strategy_id = <real_strategy_id>
  - UPDATE positions.stop_loss, take_profit from strategy.risk_params
    if currently NULL
  - UPDATE trade_journal entry with conviction_score, template_name,
    market_regime from order.order_metadata
  - Append reconciliation marker to trade_journal.trade_metadata:
    {"orphan_recovery_source": "sync_path_relink_2026_05_06"}

Usage
-----
    # Dry-run (default) — prints planned changes, no DB writes:
    venv/bin/python3 scripts/recover_orphan_positions.py

    # Apply changes:
    venv/bin/python3 scripts/recover_orphan_positions.py --apply

    # Verify specific known orphans:
    venv/bin/python3 scripts/recover_orphan_positions.py --verify

Idempotent: only touches rows where strategy_id = 'etoro_position', so
re-running after a partial apply is safe.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Known orphans from the 2026-05-05 incident — used by --verify mode.
KNOWN_ORPHANS = [
    {"symbol": "SOXL", "etoro_position_id": "3509139906"},
    {"symbol": "SMH",  "etoro_position_id": "3509138740"},
    {"symbol": "TQQQ", "etoro_position_id": "3509138333"},
    {"symbol": "XLK",  "etoro_position_id": "3509137957"},
]

RECOVERY_SOURCE_KEY = "orphan_recovery_source"
RECOVERY_SOURCE_VAL = "sync_path_relink_2026_05_06"


def _numeric_distance(a: Optional[str], b: Optional[str]) -> float:
    """Return absolute numeric distance between two ID strings.

    eToro position IDs often derive from order IDs on fill, so the
    numerically-closest order is the best match when multiple candidates
    exist.  Returns float('inf') if either value is non-numeric.
    """
    try:
        return abs(int(a) - int(b))
    except (TypeError, ValueError):
        return float("inf")


def _pick_best_order(candidates, position_etoro_id: Optional[str]):
    """From a list of order ORM rows, return the one whose etoro_order_id
    is numerically closest to position_etoro_id.  Falls back to the most
    recently submitted order if no numeric comparison is possible.
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    # Sort by numeric distance to position's eToro ID, then by recency.
    def sort_key(o):
        dist = _numeric_distance(o.etoro_order_id, position_etoro_id)
        # Negate submitted_at for secondary sort (most recent first).
        ts = o.submitted_at or datetime.min
        return (dist, -ts.timestamp() if hasattr(ts, "timestamp") else 0)

    return sorted(candidates, key=sort_key)[0]


def _derive_sl_tp(strategy_orm, position_orm):
    """Return (stop_loss, take_profit) from strategy.risk_params scaled to
    the position's entry_price.  Returns (None, None) if data is missing.
    """
    if not strategy_orm or not position_orm.entry_price:
        return None, None

    risk = strategy_orm.risk_params or {}
    entry = position_orm.entry_price
    side = str(position_orm.side).upper() if position_orm.side else "LONG"
    is_long = "LONG" in side or "BUY" in side

    sl_pct = risk.get("stop_loss_pct") or risk.get("stop_loss")
    tp_pct = risk.get("take_profit_pct") or risk.get("take_profit")

    # risk_params stores percentages as fractions (0.06) or whole numbers (6).
    # Normalise: if value > 1, treat as percentage points.
    def _norm(v):
        if v is None:
            return None
        return v / 100.0 if v > 1 else v

    sl_pct = _norm(sl_pct)
    tp_pct = _norm(tp_pct)

    sl = None
    tp = None
    if sl_pct and entry:
        sl = entry * (1 - sl_pct) if is_long else entry * (1 + sl_pct)
    if tp_pct and entry:
        tp = entry * (1 + tp_pct) if is_long else entry * (1 - tp_pct)

    return sl, tp


def main(apply: bool, verify: bool) -> int:
    from src.models.database import get_database
    from src.models.orm import PositionORM, OrderORM, StrategyORM
    from src.models.enums import OrderStatus
    from src.analytics.trade_journal import TradeJournalEntryORM

    db = get_database()
    session = db.get_session()

    try:
        # ------------------------------------------------------------------ #
        # 1. Find all open orphan positions                                   #
        # ------------------------------------------------------------------ #
        orphans = (
            session.query(PositionORM)
            .filter(
                PositionORM.strategy_id == "etoro_position",
                PositionORM.closed_at.is_(None),
            )
            .all()
        )

        logger.info(f"Found {len(orphans)} open orphan positions (strategy_id='etoro_position')")

        if not orphans:
            logger.info("Nothing to recover. Exiting.")
            return 0

        matched = 0
        unmatched = 0
        updates = []

        for pos in orphans:
            logger.info(
                f"  Orphan: {pos.symbol} | pos_id={pos.id} "
                f"| etoro_pos_id={pos.etoro_position_id} "
                f"| opened_at={pos.opened_at}"
            )

            opened_at = pos.opened_at
            if opened_at and opened_at.tzinfo:
                opened_at = opened_at.replace(tzinfo=None)

            try:
                # ---------------------------------------------------------- #
                # 2a. Match via orders table                                   #
                # ---------------------------------------------------------- #
                order_match = None
                if opened_at:
                    window_lo = opened_at - timedelta(hours=24)
                    window_hi = opened_at + timedelta(hours=24)

                    candidates = (
                        session.query(OrderORM)
                        .filter(
                            OrderORM.symbol == pos.symbol,
                            OrderORM.submitted_at >= window_lo,
                            OrderORM.submitted_at <= window_hi,
                            OrderORM.status.in_([OrderStatus.CANCELLED, OrderStatus.FAILED]),
                            OrderORM.order_metadata.isnot(None),
                        )
                        .all()
                    )

                    # Filter to entry orders only (skip close/retirement orders).
                    candidates = [
                        o for o in candidates
                        if (o.order_action or "entry") in ("entry", None, "")
                    ]

                    order_match = _pick_best_order(candidates, pos.etoro_position_id)

                # ---------------------------------------------------------- #
                # 2b. Fallback: conviction_score_logs (if table exists)       #
                # ---------------------------------------------------------- #
                csl_match = None
                if order_match is None and opened_at:
                    try:
                        from sqlalchemy import text
                        window_lo_csl = opened_at - timedelta(hours=6)
                        result = session.execute(
                            text(
                                "SELECT strategy_id, conviction_score, market_regime, "
                                "       ml_confidence, timestamp "
                                "FROM conviction_score_logs "
                                "WHERE symbol = :sym "
                                "  AND timestamp >= :lo "
                                "  AND timestamp <= :hi "
                                "ORDER BY timestamp DESC "
                                "LIMIT 1"
                            ),
                            {"sym": pos.symbol, "lo": window_lo_csl, "hi": opened_at},
                        ).fetchone()
                        if result:
                            csl_match = dict(result._mapping)
                            logger.info(
                                f"    Fallback match via conviction_score_logs: "
                                f"strategy={csl_match.get('strategy_id')} "
                                f"score={csl_match.get('conviction_score')}"
                            )
                    except Exception as e:
                        logger.debug(f"    conviction_score_logs lookup failed: {e}")
                        # Roll back the failed sub-transaction so the session stays usable.
                        try:
                            session.rollback()
                        except Exception:
                            pass

                if order_match is None and csl_match is None:
                    logger.warning(
                        f"    NO MATCH for {pos.symbol} (etoro_pos_id={pos.etoro_position_id}) "
                        f"— leaving as 'etoro_position' (likely a genuine external position)"
                    )
                    unmatched += 1
                    continue

                # ---------------------------------------------------------- #
                # 3. Resolve strategy and metadata                             #
                # ---------------------------------------------------------- #
                if order_match:
                    real_strategy_id = order_match.strategy_id
                    meta = order_match.order_metadata or {}
                    match_source = f"order:{order_match.id} (etoro_order_id={order_match.etoro_order_id})"
                else:
                    real_strategy_id = csl_match.get("strategy_id", "etoro_position")
                    meta = {
                        "conviction_score": csl_match.get("conviction_score"),
                        "market_regime": csl_match.get("market_regime"),
                        "ml_confidence": csl_match.get("ml_confidence"),
                    }
                    match_source = "conviction_score_logs"

                strategy_orm = (
                    session.query(StrategyORM)
                    .filter(StrategyORM.id == real_strategy_id)
                    .first()
                )

                template_name = None
                if strategy_orm and isinstance(strategy_orm.strategy_metadata, dict):
                    template_name = (
                        strategy_orm.strategy_metadata.get("template_name")
                        or getattr(strategy_orm, "name", None)
                    )
                if not template_name and order_match:
                    template_name = meta.get("template_name")

                # Derive SL/TP from strategy risk_params if position has NULLs.
                derived_sl, derived_tp = _derive_sl_tp(strategy_orm, pos)

                # ---------------------------------------------------------- #
                # 4. Build the update record                                   #
                # ---------------------------------------------------------- #
                update = {
                    "position": pos,
                    "real_strategy_id": real_strategy_id,
                    "template_name": template_name,
                    "conviction_score": meta.get("conviction_score"),
                    "market_regime": meta.get("market_regime"),
                    "ml_confidence": meta.get("ml_confidence"),
                    "fundamentals": meta.get("fundamental_data") or meta.get("fundamentals"),
                    "derived_sl": derived_sl if pos.stop_loss is None else None,
                    "derived_tp": derived_tp if pos.take_profit is None else None,
                    "match_source": match_source,
                }
                updates.append(update)
                matched += 1

                logger.info(
                    f"    MATCH → strategy={real_strategy_id} "
                    f"template={template_name} "
                    f"conviction={meta.get('conviction_score')} "
                    f"regime={meta.get('market_regime')} "
                    f"via {match_source}"
                )
                if derived_sl and pos.stop_loss is None:
                    logger.info(f"    Will set stop_loss={derived_sl:.4f} (was NULL)")
                if derived_tp and pos.take_profit is None:
                    logger.info(f"    Will set take_profit={derived_tp:.4f} (was NULL)")

            except Exception as per_orphan_err:
                logger.error(
                    f"    Error processing orphan {pos.symbol} (pos_id={pos.id}): "
                    f"{per_orphan_err} — skipping this orphan"
                )
                try:
                    session.rollback()
                except Exception:
                    pass
                unmatched += 1

        logger.info(
            f"\nSummary: {matched} matched, {unmatched} unmatched "
            f"(unmatched = genuine external positions, left untouched)"
        )

        if not updates:
            logger.info("Nothing to apply. Exiting.")
            return 0

        if not apply:
            logger.info(
                f"\nDRY-RUN: would update {len(updates)} positions. "
                "Re-run with --apply to write."
            )
            return 0

        # ------------------------------------------------------------------ #
        # 5. Apply updates                                                     #
        # ------------------------------------------------------------------ #
        logger.info(f"\nAPPLYING updates to {len(updates)} positions...")

        for u in updates:
            pos = u["position"]

            # 5a. Re-link strategy_id on the position row.
            old_strategy_id = pos.strategy_id
            pos.strategy_id = u["real_strategy_id"]

            # 5b. Backfill SL/TP if NULL.
            if u["derived_sl"] is not None:
                pos.stop_loss = u["derived_sl"]
            if u["derived_tp"] is not None:
                pos.take_profit = u["derived_tp"]

            logger.info(
                f"  Updated position {pos.id} ({pos.symbol}): "
                f"strategy_id {old_strategy_id!r} → {pos.strategy_id!r}"
            )

            # 5c. Backfill trade_journal entry.
            try:
                tj_entry = (
                    session.query(TradeJournalEntryORM)
                    .filter(TradeJournalEntryORM.trade_id == str(pos.id))
                    .first()
                )

                recovery_meta = {
                    RECOVERY_SOURCE_KEY: RECOVERY_SOURCE_VAL,
                    "matched_via": u["match_source"],
                }
                if u["template_name"]:
                    recovery_meta["template_name"] = u["template_name"]

                if tj_entry:
                    # Update existing entry.
                    if u["conviction_score"] is not None and tj_entry.conviction_score is None:
                        tj_entry.conviction_score = u["conviction_score"]
                    if u["market_regime"] is not None and tj_entry.market_regime is None:
                        tj_entry.market_regime = u["market_regime"]
                    if u["ml_confidence"] is not None and tj_entry.ml_confidence is None:
                        tj_entry.ml_confidence = u["ml_confidence"]
                    if u["fundamentals"] is not None and tj_entry.fundamentals is None:
                        tj_entry.fundamentals = u["fundamentals"]
                    # Merge recovery marker into trade_metadata.
                    existing_meta = dict(tj_entry.trade_metadata or {})
                    existing_meta.update(recovery_meta)
                    tj_entry.trade_metadata = existing_meta
                    # Also update strategy_id on the journal row.
                    tj_entry.strategy_id = u["real_strategy_id"]
                    logger.info(
                        f"    Updated trade_journal entry for trade_id={pos.id}"
                    )
                else:
                    # No journal entry yet — create a minimal one so the
                    # conviction validation loop and loser-pair penalty can
                    # see this trade when it closes.
                    side_str = str(pos.side).upper() if pos.side else "LONG"
                    is_long = "LONG" in side_str or "BUY" in side_str
                    new_entry = TradeJournalEntryORM(
                        trade_id=str(pos.id),
                        strategy_id=u["real_strategy_id"],
                        symbol=pos.symbol,
                        side="LONG" if is_long else "SHORT",
                        entry_time=pos.opened_at or datetime.utcnow(),
                        entry_price=pos.entry_price or 0.0,
                        entry_size=pos.invested_amount or pos.quantity or 0.0,
                        entry_reason="autonomous_signal",
                        market_regime=u["market_regime"],
                        conviction_score=u["conviction_score"],
                        ml_confidence=u["ml_confidence"],
                        fundamentals=u["fundamentals"],
                        trade_metadata=recovery_meta,
                    )
                    session.add(new_entry)
                    logger.info(
                        f"    Created trade_journal entry for trade_id={pos.id}"
                    )
            except Exception as e:
                logger.warning(
                    f"    trade_journal backfill failed for {pos.symbol} "
                    f"(pos_id={pos.id}): {e} — position re-link still applied"
                )

        session.commit()
        logger.info(f"Committed {len(updates)} position updates.")

        # ------------------------------------------------------------------ #
        # 6. Post-apply verification                                           #
        # ------------------------------------------------------------------ #
        remaining = (
            session.query(PositionORM)
            .filter(
                PositionORM.strategy_id == "etoro_position",
                PositionORM.closed_at.is_(None),
            )
            .count()
        )
        logger.info(
            f"\nPost-apply: {remaining} open positions still have "
            f"strategy_id='etoro_position' (expected: genuine externals only)"
        )

        return 0

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        session.rollback()
        return 1
    finally:
        session.close()


def verify_known_orphans() -> int:
    """Print DB state for the 4 known 2026-05-05 orphans."""
    from src.models.database import get_database
    from src.models.orm import PositionORM, OrderORM
    from src.models.enums import OrderStatus

    db = get_database()
    session = db.get_session()
    try:
        logger.info("=== Verifying known 2026-05-05 orphans ===\n")
        for spec in KNOWN_ORPHANS:
            pos = (
                session.query(PositionORM)
                .filter(PositionORM.etoro_position_id == spec["etoro_position_id"])
                .first()
            )
            if not pos:
                logger.warning(
                    f"  {spec['symbol']} (etoro_pos_id={spec['etoro_position_id']}): "
                    f"NOT FOUND in positions table"
                )
                continue

            logger.info(
                f"  {spec['symbol']} | pos_id={pos.id} "
                f"| strategy_id={pos.strategy_id!r} "
                f"| opened_at={pos.opened_at} "
                f"| closed_at={pos.closed_at} "
                f"| sl={pos.stop_loss} tp={pos.take_profit}"
            )

            # Show candidate orders.
            opened_at = pos.opened_at
            if opened_at and opened_at.tzinfo:
                opened_at = opened_at.replace(tzinfo=None)
            if opened_at:
                window_lo = opened_at - timedelta(hours=24)
                window_hi = opened_at + timedelta(hours=24)
                candidates = (
                    session.query(OrderORM)
                    .filter(
                        OrderORM.symbol == pos.symbol,
                        OrderORM.submitted_at >= window_lo,
                        OrderORM.submitted_at <= window_hi,
                        OrderORM.status.in_([OrderStatus.CANCELLED, OrderStatus.FAILED]),
                        OrderORM.order_metadata.isnot(None),
                    )
                    .all()
                )
                if candidates:
                    for o in candidates:
                        dist = _numeric_distance(o.etoro_order_id, pos.etoro_position_id)
                        logger.info(
                            f"    Candidate order: id={o.id} "
                            f"etoro_order_id={o.etoro_order_id} "
                            f"strategy={o.strategy_id} "
                            f"status={o.status} "
                            f"submitted={o.submitted_at} "
                            f"numeric_dist={dist} "
                            f"meta_keys={list((o.order_metadata or {}).keys())}"
                        )
                else:
                    logger.warning(
                        f"    No CANCELLED/FAILED orders with metadata found "
                        f"within ±24h for {spec['symbol']}"
                    )
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to DB (default is dry-run)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Print DB state for the 4 known 2026-05-05 orphans and exit",
    )
    args = parser.parse_args()

    if args.verify:
        sys.exit(verify_known_orphans())
    else:
        sys.exit(main(apply=args.apply, verify=args.verify))
