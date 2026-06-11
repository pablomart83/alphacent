"""Canonical position-close primitives (A1 — close-path unification).

Every code path that marks a position closed has historically re-implemented two
rules, and the divergence caused real-money incidents (2026-06-11: a demo-scoped
`POST /positions/sync` closed the LIVE AMD+PANW because its "no longer on eToro →
close" query had no account_type filter; the live pass then re-entered → duplicate
real position). The rules:

  1. ACCOUNT SCOPING. eToro reuses numeric position IDs across the demo and live
     accounts, and each eToro client is mode-scoped. A close decision for account X
     must only ever touch positions of account X. Comparing DB positions of account X
     against account Y's eToro response is the incident.

  2. NEVER CLOSE ON AN EMPTY/PARTIAL eToro RESPONSE. A transient API blip returning
     `[]` must not wholesale-close the book. Only the monitoring sync's
     consecutive-miss guard may close on absence, and only after repeated non-empty
     misses.

This module is the single source of truth for both. Route every close through
`finalize_position_close` (enforces rule 1 defensively) and resolve "which DB
positions are gone from eToro" through `positions_absent_from_etoro` (enforces
rule 2). Closing a position in the DB is never harmless — it can spawn a real
re-entry order — so these guards are mandatory, not advisory.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable, List, Optional

logger = logging.getLogger(__name__)


class AccountScopeViolation(Exception):
    """Raised/flagged when a close would act on a position of the wrong account."""


def finalize_position_close(
    position_orm,
    *,
    reason: str = "position_closed",
    expected_account_type: Optional[str] = None,
    log_journal: bool = True,
) -> bool:
    """Mark a position closed: set closed_at, compute realized P&L, journal the exit.

    Rule 1 enforcement: when `expected_account_type` is provided, the position's
    own account_type MUST match. On mismatch we log CRITICAL and return False
    WITHOUT touching the row — a cross-account close is refused, not performed.

    Realized P&L is computed from the actual price move (entry vs current) using the
    canonical dollar field (invested_amount), falling back to the last unrealized
    value only when cost basis is unavailable. Behaviour preserved from the original
    account.py `_finalize_position_close`.

    Returns True if the position was finalized, False if refused.
    """
    pos_acct = getattr(position_orm, "account_type", None) or "demo"
    if expected_account_type is not None and pos_acct != expected_account_type:
        logger.critical(
            "[A1] REFUSED cross-account close: position %s (%s) is account_type=%s "
            "but caller expected %s — not closing (reason=%r). This guard prevents "
            "the 2026-06-11 cross-account close incident.",
            getattr(position_orm, "id", "?"),
            getattr(position_orm, "symbol", "?"),
            pos_acct,
            expected_account_type,
            reason,
        )
        return False

    position_orm.closed_at = datetime.now()

    entry = position_orm.entry_price or 0
    current = position_orm.current_price or entry
    invested = (
        getattr(position_orm, "invested_amount", None)
        or getattr(position_orm, "quantity", 0)
        or 0
    )
    if entry > 0 and invested > 0:
        side_str = str(position_orm.side).upper() if position_orm.side else "LONG"
        if "SHORT" in side_str or "SELL" in side_str:
            calculated_pnl = invested * (entry - current) / entry
        else:
            calculated_pnl = invested * (current - entry) / entry
        position_orm.realized_pnl = (position_orm.realized_pnl or 0) + calculated_pnl
    else:
        position_orm.realized_pnl = (position_orm.realized_pnl or 0) + (
            position_orm.unrealized_pnl or 0
        )
    position_orm.unrealized_pnl = 0.0
    position_orm.pending_closure = False
    if reason and not getattr(position_orm, "closure_reason", None):
        position_orm.closure_reason = reason

    if log_journal:
        try:
            from src.analytics.trade_journal import TradeJournal
            from src.models.database import get_database

            journal = TradeJournal(get_database())
            journal.log_exit(
                trade_id=str(position_orm.id),
                exit_time=position_orm.closed_at,
                exit_price=position_orm.current_price,
                exit_reason=reason,
                symbol=position_orm.symbol,
            )
        except Exception as e:  # journaling must never block the close
            logger.debug(
                "Could not log exit to trade journal for %s: %s",
                getattr(position_orm, "symbol", "?"),
                e,
            )
    return True


def positions_absent_from_etoro(
    session,
    account_type: str,
    etoro_position_ids: Iterable,
    *,
    allow_empty: bool = False,
) -> List:
    """Return open DB positions of `account_type` whose etoro_position_id is NOT in
    the given eToro id set — the canonical "no longer on eToro → candidate to close"
    query.

    Rule 1: scoped to `account_type`.
    Rule 2: if `etoro_position_ids` is empty, returns [] (refuses to treat an
    empty/transient eToro response as "everything is gone"), unless `allow_empty`
    is explicitly set by a caller that has its own absence guard (e.g. the
    monitoring consecutive-miss path).
    """
    id_set = {str(x) for x in etoro_position_ids if x is not None}
    if not id_set and not allow_empty:
        logger.warning(
            "[A1] positions_absent_from_etoro called with EMPTY eToro id set for "
            "account_type=%s — refusing to flag any position as absent (transient "
            "API/auth blip guard).",
            account_type,
        )
        return []

    from src.models.orm import PositionORM

    open_positions = (
        session.query(PositionORM)
        .filter(
            PositionORM.closed_at.is_(None),
            PositionORM.account_type == account_type,
        )
        .all()
    )
    return [
        p
        for p in open_positions
        if p.etoro_position_id and str(p.etoro_position_id) not in id_set
    ]
