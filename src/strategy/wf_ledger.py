"""Durable walk-forward (WF) validation ledger.

This module is the persistence/recovery layer for the WF test Sharpe at the
(template_name, symbol) level. It exists so a pair whose WF edge was established
(it passed walk-forward at some point) keeps that fact permanently — even after
the BACKTESTED TTL deletes every strategy version that carried the WF Sharpe in
its `strategy_metadata` JSON.

Background
----------
The graduation gate divides paper Sharpe by WF Sharpe (the qualification ratio).
WF Sharpe lives in `strategies.strategy_metadata` JSON, which dies with the row
when a stale version is TTL-deleted. The gate's `best_wf_by_template` fallback
recovers it from surviving sibling versions, but goes to 0 when *all* surviving
versions of a template lack `wf_test_sharpe` simultaneously (WF-carrying versions
deleted, re-proposed versions not yet re-validated). The gate then fail-closes a
pair whose WF edge WAS established. This is the same class of bug as the
trade-history loss (commit `1a373bd`): metadata not surviving version deletion.

The `wf_validation_ledger` table (see `WfValidationLedgerORM`) persists the WF
Sharpe per (template, symbol), is upserted on every WF pass, and is never pruned.

Public API
----------
- ``record_wf_validation(template, symbol, wf_test_sharpe, ...)`` — fire-and-forget
  upsert on a single pass. Never raises (matches `decision_log.record_decision`).
- ``load_wf_ledger(session)`` — bulk-load {(template, symbol): wf_test_sharpe} for
  the graduation gate's recovery path.
- ``backfill_from_current_state()`` — seed the ledger from currently-surviving
  `strategies` rows so established pairs are covered immediately (idempotent).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def _log_write_failure(op: str, exc: Exception) -> None:
    # Ledger writes are best-effort analytics — a failure must never break the
    # caller (proposer hot loop / graduation queue). Surface at debug only.
    logger.debug(f"wf_ledger.{op} write failed (non-fatal): {exc}")


def record_wf_validation(
    template_name: Optional[str],
    symbol: Optional[str],
    wf_test_sharpe: Optional[float],
    *,
    wf_test_trades: Optional[int] = None,
    source: str = "proposer",
) -> None:
    """Upsert a durable WF-validation record for (template_name, symbol).

    Fire-and-forget: never raises. Only records positive test Sharpes (a
    non-positive WF Sharpe is not an established edge and would not help the
    qualification-ratio recovery anyway). On an existing row, updates the
    latest Sharpe/trades, bumps `last_validated_at` + `validation_count`, and
    grows `best_wf_test_sharpe` (max ever).
    """
    if not template_name or not symbol or wf_test_sharpe is None:
        return
    try:
        sharpe = float(wf_test_sharpe)
    except (TypeError, ValueError):
        return
    if not (sharpe > 0):  # also rejects NaN
        return

    try:
        from src.models.database import get_database
        from src.models.orm import WfValidationLedgerORM

        db = get_database()
        with db.session_scope() as session:
            now = datetime.now()
            row = (
                session.query(WfValidationLedgerORM)
                .filter_by(template_name=template_name, symbol=symbol)
                .first()
            )
            if row is None:
                session.add(
                    WfValidationLedgerORM(
                        template_name=template_name,
                        symbol=symbol,
                        wf_test_sharpe=sharpe,
                        wf_test_trades=wf_test_trades,
                        best_wf_test_sharpe=sharpe,
                        first_validated_at=now,
                        last_validated_at=now,
                        validation_count=1,
                        source=source,
                    )
                )
            else:
                row.wf_test_sharpe = sharpe
                if wf_test_trades is not None:
                    row.wf_test_trades = wf_test_trades
                if row.best_wf_test_sharpe is None or sharpe > row.best_wf_test_sharpe:
                    row.best_wf_test_sharpe = sharpe
                row.last_validated_at = now
                row.validation_count = (row.validation_count or 0) + 1
                row.source = source
    except Exception as e:
        _log_write_failure("record_wf_validation", e)


def load_wf_ledger(session) -> Dict[Tuple[str, str], float]:
    """Return {(template_name, symbol): wf_test_sharpe} for graduation recovery.

    Reads the durable ledger on the caller's session (so it shares the same
    transaction as the rest of the graduation query). Returns an empty dict on
    any error so the gate degrades to its prior behaviour rather than breaking.
    """
    out: Dict[Tuple[str, str], float] = {}
    try:
        from sqlalchemy import text as _text

        rows = session.execute(
            _text(
                """
                SELECT template_name, symbol, wf_test_sharpe
                FROM wf_validation_ledger
                WHERE wf_test_sharpe > 0
                """
            )
        ).fetchall()
        for r in rows:
            if r.template_name and r.symbol and r.wf_test_sharpe:
                out[(r.template_name, r.symbol)] = float(r.wf_test_sharpe)
    except Exception as e:
        # The gate calls this inside a try and tolerates an empty result.
        logger.debug(f"wf_ledger.load_wf_ledger failed (non-fatal): {e}")
        try:
            session.rollback()
        except Exception:
            pass
    return out


def backfill_from_current_state() -> Dict[str, int]:
    """Seed the ledger from currently-surviving `strategies` rows.

    For every surviving strategy (any status) that carries a positive WF test
    Sharpe in its metadata, record a ledger entry for each of its symbols. This
    makes already-established pairs covered immediately without waiting for a
    re-validation cycle. Idempotent: re-running updates `last_validated_at` and
    `validation_count` but does not create duplicates (uniqueness on
    (template_name, symbol)). The most-recently-created strategy version wins the
    `wf_test_sharpe` value (processed last).

    Returns a stats dict: {"strategies_scanned", "pairs_recorded"}.
    """
    stats = {"strategies_scanned": 0, "pairs_recorded": 0}
    try:
        from sqlalchemy import text as _text

        from src.models.database import get_database

        db = get_database()
        with db.session_scope() as session:
            # Pull (template, symbol, wf_sharpe, wf_trades) per surviving version,
            # symbols unnested, ordered oldest→newest so the newest validation is
            # applied last and wins. Uses the same WF-key COALESCE as the gate.
            rows = session.execute(
                _text(
                    """
                    SELECT
                        COALESCE(
                            s.strategy_metadata->>'template_name',
                            REGEXP_REPLACE(s.name, ' V[0-9]+$', '')
                        )                                               AS template_name,
                        sym.symbol                                      AS symbol,
                        COALESCE(
                            (s.strategy_metadata->>'wf_test_sharpe')::float,
                            (s.strategy_metadata->>'wf_sharpe')::float,
                            (s.strategy_metadata->>'walk_forward_sharpe')::float
                        )                                               AS wf_sharpe,
                        (s.strategy_metadata->>'wf_test_trades')::int   AS wf_trades,
                        s.created_at                                    AS created_at
                    FROM strategies s
                    CROSS JOIN LATERAL jsonb_array_elements_text(
                        CASE WHEN jsonb_typeof(s.symbols::jsonb) = 'array'
                             THEN s.symbols::jsonb ELSE '[]'::jsonb END
                    ) AS sym(symbol)
                    WHERE s.strategy_metadata IS NOT NULL
                    ORDER BY s.created_at ASC NULLS FIRST
                    """
                )
            ).fetchall()

            from src.models.orm import WfValidationLedgerORM

            # Cache existing rows to avoid a query per pair.
            existing = {
                (r.template_name, r.symbol): r
                for r in session.query(WfValidationLedgerORM).all()
            }
            now = datetime.now()
            for r in rows:
                stats["strategies_scanned"] += 1
                tmpl = r.template_name
                sym = r.symbol
                sharpe = r.wf_sharpe
                if not tmpl or not sym or sharpe is None:
                    continue
                try:
                    sharpe = float(sharpe)
                except (TypeError, ValueError):
                    continue
                if not (sharpe > 0):
                    continue
                trades = int(r.wf_trades) if r.wf_trades is not None else None
                key = (tmpl, sym)
                row = existing.get(key)
                if row is None:
                    row = WfValidationLedgerORM(
                        template_name=tmpl,
                        symbol=sym,
                        wf_test_sharpe=sharpe,
                        wf_test_trades=trades,
                        best_wf_test_sharpe=sharpe,
                        first_validated_at=now,
                        last_validated_at=now,
                        validation_count=1,
                        source="backfill_strategies",
                    )
                    session.add(row)
                    existing[key] = row
                    stats["pairs_recorded"] += 1
                else:
                    # Newest version processed last wins the current value.
                    row.wf_test_sharpe = sharpe
                    if trades is not None:
                        row.wf_test_trades = trades
                    if row.best_wf_test_sharpe is None or sharpe > row.best_wf_test_sharpe:
                        row.best_wf_test_sharpe = sharpe
                    row.last_validated_at = now
                    row.source = "backfill_strategies"
    except Exception as e:
        logger.error(f"wf_ledger.backfill_from_current_state failed: {e}", exc_info=True)
    return stats
