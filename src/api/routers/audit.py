"""
Audit log endpoints for AlphaCent Trading Platform.

Provides filterable, paginated audit log, trade lifecycle detail,
and CSV export from existing signal, order, position, and strategy tables.

Validates: Requirements 21.1, 21.2, 21.3, 21.4, 21.8, 21.9, 21.10
"""

import csv
import io
import logging
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from src.api.dependencies import get_current_user, get_db_session

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Response Models
# ============================================================================

class AuditLogEntry(BaseModel):
    """Single audit log entry."""
    id: str
    timestamp: str
    event_type: str
    symbol: Optional[str] = None
    strategy_name: Optional[str] = None
    severity: str = "info"
    description: str
    metadata: Optional[dict] = None


class AuditLogResponse(BaseModel):
    """Paginated audit log response."""
    entries: list[AuditLogEntry] = []
    total: int = 0
    offset: int = 0
    limit: int = 100


class TradeLifecycleStep(BaseModel):
    """A single step in a trade lifecycle."""
    step: str
    timestamp: Optional[str] = None
    details: dict = {}


class TradeLifecycleData(BaseModel):
    """Full trade lifecycle chain."""
    trade_id: str
    symbol: Optional[str] = None
    strategy_name: Optional[str] = None
    steps: list[TradeLifecycleStep] = []


# ============================================================================
# Helper: Build unified audit entries from existing tables
# ============================================================================

def _build_audit_entries(
    session: Session,
    event_types: Optional[List[str]],
    symbol: Optional[str],
    severity: Optional[str],
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    search: Optional[str],
) -> list[AuditLogEntry]:
    """
    Query the unified decision funnel, orders, positions, strategies,
    strategy_retirements, and rejected_signals tables and compose a
    unified list of AuditLogEntry objects.

    2026-05-04: Signal events read from `signal_decisions` (unified funnel),
    filtered to the decision-representing stages (gate_blocked /
    order_submitted / order_filled). Legacy `signal_decision_log` reads
    have been removed.
    """
    from src.models.orm import (
        SignalDecisionORM, OrderORM, PositionORM,
        StrategyORM, StrategyRetirementORM, RejectedSignalORM,
    )

    entries: list[AuditLogEntry] = []
    want_all = event_types is None or len(event_types) == 0

    # --- Signal decision events ---
    # Scope to decision-boundary stages so the audit log doesn't get flooded
    # with proposer/WF upstream rows (which would drown out operational signal
    # events in the user-facing audit log).
    if want_all or "signal" in event_types:
        DECISION_STAGES = ("gate_blocked", "order_submitted", "order_filled")
        q = session.query(SignalDecisionORM).filter(
            SignalDecisionORM.stage.in_(DECISION_STAGES)
        )
        if start_date:
            q = q.filter(SignalDecisionORM.timestamp >= start_date)
        if end_date:
            q = q.filter(SignalDecisionORM.timestamp <= end_date)
        if symbol:
            q = q.filter(SignalDecisionORM.symbol == symbol)
        for row in q.order_by(SignalDecisionORM.timestamp.desc()).limit(500).all():
            # Map unified decision to legacy ACCEPTED/REJECTED for the audit
            # feed, preserving the existing description format.
            accepted = row.stage in ("order_submitted", "order_filled")
            sev = "info" if accepted else "warning"
            if severity and sev != severity:
                continue
            # Derive side from direction
            _side = "BUY" if row.direction == "long" else "SELL" if row.direction == "short" else ""
            _decision_label = "ACCEPTED" if accepted else "REJECTED"
            desc = f"Signal {_decision_label}: {row.symbol or ''} {_side}".strip()
            if row.reason:
                desc += f" — {row.reason}"
            if search and search.lower() not in desc.lower():
                continue
            entries.append(AuditLogEntry(
                id=f"sig-{row.id}",
                timestamp=row.timestamp.isoformat() if row.timestamp else "",
                event_type="signal",
                symbol=row.symbol,
                strategy_name=row.template_name or row.strategy_id,
                severity=sev,
                description=desc,
                metadata=row.decision_metadata,
            ))

    # --- Order events ---
    if want_all or "order" in event_types:
        q = session.query(OrderORM)
        if start_date:
            q = q.filter(OrderORM.submitted_at >= start_date)
        if end_date:
            q = q.filter(OrderORM.submitted_at <= end_date)
        if symbol:
            q = q.filter(OrderORM.symbol == symbol)
        for row in q.order_by(OrderORM.submitted_at.desc()).limit(500).all():
            status_val = row.status.value if row.status else str(row.status)
            sev = "info"
            if status_val in ("CANCELLED", "REJECTED", "FAILED"):
                sev = "warning"
            if severity and sev != severity:
                continue
            side_val = row.side.value if row.side else str(row.side)
            desc = f"Order {status_val}: {row.symbol} {side_val} qty={row.quantity}"
            if row.filled_price:
                desc += f" filled@{row.filled_price}"
            if search and search.lower() not in desc.lower():
                continue
            entries.append(AuditLogEntry(
                id=f"ord-{row.id}",
                timestamp=(row.filled_at or row.submitted_at or datetime.now()).isoformat(),
                event_type="order",
                symbol=row.symbol,
                strategy_name=row.strategy_id,
                severity=sev,
                description=desc,
                metadata={"slippage": row.slippage, "fill_time_seconds": row.fill_time_seconds},
            ))

    # --- Position events ---
    if want_all or "position" in event_types:
        q = session.query(PositionORM)
        if start_date:
            q = q.filter(PositionORM.opened_at >= start_date)
        if end_date:
            q = q.filter(PositionORM.opened_at <= end_date)
        if symbol:
            q = q.filter(PositionORM.symbol == symbol)
        for row in q.order_by(PositionORM.opened_at.desc()).limit(500).all():
            sev = "info"
            if severity and sev != severity:
                continue
            side_val = row.side.value if row.side else str(row.side)
            desc = f"Position opened: {row.symbol} {side_val} entry@{row.entry_price}"
            if row.closed_at:
                desc = f"Position closed: {row.symbol} {side_val} PnL={row.realized_pnl:.2f}"
                sev = "info" if row.realized_pnl >= 0 else "warning"
            if search and search.lower() not in desc.lower():
                continue
            ts = (row.closed_at or row.opened_at or datetime.now()).isoformat()
            entries.append(AuditLogEntry(
                id=f"pos-{row.id}",
                timestamp=ts,
                event_type="position",
                symbol=row.symbol,
                strategy_name=row.strategy_id,
                severity=sev,
                description=desc,
            ))

    # --- Strategy lifecycle events ---
    if want_all or "strategy" in event_types:
        q = session.query(StrategyORM)
        if start_date:
            q = q.filter(StrategyORM.created_at >= start_date)
        if end_date:
            q = q.filter(StrategyORM.created_at <= end_date)
        for row in q.order_by(StrategyORM.created_at.desc()).limit(300).all():
            sev = "info"
            status_val = row.status.value if row.status else str(row.status)
            desc = f"Strategy {status_val}: {row.name}"
            if severity and sev != severity:
                continue
            if search and search.lower() not in desc.lower():
                continue
            entries.append(AuditLogEntry(
                id=f"strat-{row.id}",
                timestamp=(row.activated_at or row.created_at or datetime.now()).isoformat(),
                event_type="strategy",
                symbol=None,
                strategy_name=row.name,
                severity=sev,
                description=desc,
            ))

        # Retirements
        rq = session.query(StrategyRetirementORM)
        if start_date:
            rq = rq.filter(StrategyRetirementORM.retired_at >= start_date)
        if end_date:
            rq = rq.filter(StrategyRetirementORM.retired_at <= end_date)
        for row in rq.order_by(StrategyRetirementORM.retired_at.desc()).limit(200).all():
            desc = f"Strategy retired: {row.strategy_id} — {row.reason}"
            if search and search.lower() not in desc.lower():
                continue
            entries.append(AuditLogEntry(
                id=f"retire-{row.id}",
                timestamp=row.retired_at.isoformat() if row.retired_at else "",
                event_type="strategy",
                strategy_name=row.strategy_id,
                severity="warning",
                description=desc,
                metadata={"final_sharpe": row.final_sharpe, "final_return": row.final_return},
            ))

    # --- Rejected signals ---
    if want_all or "rejection" in event_types:
        q = session.query(RejectedSignalORM)
        if start_date:
            q = q.filter(RejectedSignalORM.timestamp >= start_date)
        if end_date:
            q = q.filter(RejectedSignalORM.timestamp <= end_date)
        if symbol:
            q = q.filter(RejectedSignalORM.symbol == symbol)
        for row in q.order_by(RejectedSignalORM.timestamp.desc()).limit(300).all():
            desc = f"Signal rejected: {row.symbol} {row.signal_type} — {row.rejection_reason}"
            if search and search.lower() not in desc.lower():
                continue
            entries.append(AuditLogEntry(
                id=f"rej-{row.id}",
                timestamp=row.timestamp.isoformat() if row.timestamp else "",
                event_type="rejection",
                symbol=row.symbol,
                strategy_name=row.strategy_id,
                severity="warning",
                description=desc,
            ))

    # Sort all entries by timestamp descending
    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return entries


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/log", response_model=AuditLogResponse)
async def get_audit_log(
    event_types: Optional[str] = Query(None, description="Comma-separated event types: signal,order,position,strategy,rejection"),
    symbol: Optional[str] = Query(None),
    severity: Optional[str] = Query(None, description="info, warning, or error"),
    start_date: Optional[str] = Query(None, description="ISO date string"),
    end_date: Optional[str] = Query(None, description="ISO date string"),
    search: Optional[str] = Query(None, description="Full-text search term"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    session: Session = Depends(get_db_session),
    _user: str = Depends(get_current_user),
):
    """
    Get filterable, paginated audit log.

    Composes entries from signal_decisions (unified funnel), orders,
    positions, strategies, strategy_retirements, and rejected_signals
    tables.

    Validates: Requirements 21.1, 21.2, 21.3, 21.4, 21.10
    """
    parsed_types = [t.strip() for t in event_types.split(",")] if event_types else None
    parsed_start = datetime.fromisoformat(start_date) if start_date else datetime.now() - timedelta(days=90)
    parsed_end = datetime.fromisoformat(end_date) if end_date else None

    entries = _build_audit_entries(
        session=session,
        event_types=parsed_types,
        symbol=symbol,
        severity=severity,
        start_date=parsed_start,
        end_date=parsed_end,
        search=search,
    )

    total = len(entries)
    page = entries[offset: offset + limit]

    return AuditLogResponse(entries=page, total=total, offset=offset, limit=limit)


@router.get("/trade-lifecycle/{trade_id}", response_model=TradeLifecycleData)
async def get_trade_lifecycle(
    trade_id: str,
    session: Session = Depends(get_db_session),
    _user: str = Depends(get_current_user),
):
    """
    Get full trade lifecycle chain for a given trade (order or position ID).

    Traces: signal → risk validation → order → fill → position → trailing stops → close.

    Validates: Requirements 21.4, 21.9
    """
    from src.models.orm import (
        SignalDecisionORM, OrderORM, PositionORM, StrategyORM,
    )

    result = TradeLifecycleData(trade_id=trade_id)
    steps: list[TradeLifecycleStep] = []

    # Try to find the order first
    order = session.query(OrderORM).filter(OrderORM.id == trade_id).first()
    position = None

    if not order:
        # Maybe trade_id is a position ID
        position = session.query(PositionORM).filter(PositionORM.id == trade_id).first()
        if position:
            # Find the order that opened this position
            order = session.query(OrderORM).filter(
                OrderORM.strategy_id == position.strategy_id,
                OrderORM.symbol == position.symbol,
            ).order_by(OrderORM.submitted_at.asc()).first()

    if not order and not position:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

    symbol = order.symbol if order else (position.symbol if position else None)
    strategy_id = order.strategy_id if order else (position.strategy_id if position else None)
    result.symbol = symbol

    # Get strategy name
    if strategy_id:
        strat = session.query(StrategyORM).filter(StrategyORM.id == strategy_id).first()
        if strat:
            result.strategy_name = strat.name

    # Step 1: Signal — read from unified funnel, decision-boundary stages only
    if strategy_id and symbol:
        DECISION_STAGES = ("gate_blocked", "order_submitted", "order_filled")
        sig = session.query(SignalDecisionORM).filter(
            SignalDecisionORM.strategy_id == strategy_id,
            SignalDecisionORM.symbol == symbol,
            SignalDecisionORM.stage.in_(DECISION_STAGES),
        ).order_by(SignalDecisionORM.timestamp.desc()).first()
        if sig:
            accepted = sig.stage in ("order_submitted", "order_filled")
            meta = sig.decision_metadata or {}
            _side = "BUY" if sig.direction == "long" else "SELL" if sig.direction == "short" else None
            steps.append(TradeLifecycleStep(
                step="signal",
                timestamp=sig.timestamp.isoformat() if sig.timestamp else None,
                details={
                    "decision": "ACCEPTED" if accepted else "REJECTED",
                    "stage": sig.stage,
                    "signal_type": "EXIT" if "EXIT" in str(meta.get("action", "")) else "ENTRY",
                    "side": _side,
                    "conviction": meta.get("conviction_score") or sig.score,
                    "reason": sig.reason,
                },
            ))

    # Step 2: Order
    if order:
        side_val = order.side.value if order.side else str(order.side)
        status_val = order.status.value if order.status else str(order.status)
        steps.append(TradeLifecycleStep(
            step="order",
            timestamp=(order.submitted_at or datetime.now()).isoformat(),
            details={
                "side": side_val,
                "quantity": order.quantity,
                "expected_price": order.expected_price,
                "status": status_val,
            },
        ))

        # Step 3: Fill
        if order.filled_at:
            steps.append(TradeLifecycleStep(
                step="fill",
                timestamp=order.filled_at.isoformat(),
                details={
                    "fill_price": order.filled_price,
                    "slippage": order.slippage,
                    "fill_time_seconds": order.fill_time_seconds,
                },
            ))

    # Step 4: Position
    if not position and order:
        position = session.query(PositionORM).filter(
            PositionORM.strategy_id == order.strategy_id,
            PositionORM.symbol == order.symbol,
        ).order_by(PositionORM.opened_at.desc()).first()

    if position:
        steps.append(TradeLifecycleStep(
            step="position",
            timestamp=position.opened_at.isoformat() if position.opened_at else None,
            details={
                "entry_price": position.entry_price,
                "stop_loss": position.stop_loss,
                "take_profit": position.take_profit,
                "quantity": position.quantity,
            },
        ))

        # Step 5: Partial exits / trailing stops
        if position.partial_exits:
            for pe in position.partial_exits:
                steps.append(TradeLifecycleStep(
                    step="trailing_stop",
                    timestamp=pe.get("timestamp") or pe.get("date"),
                    details=pe,
                ))

        # Step 6: Close
        if position.closed_at:
            steps.append(TradeLifecycleStep(
                step="close",
                timestamp=position.closed_at.isoformat(),
                details={
                    "realized_pnl": position.realized_pnl,
                    "closure_reason": position.closure_reason,
                },
            ))

    result.steps = steps
    return result


@router.get("/export")
async def export_audit_log(
    event_types: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    session: Session = Depends(get_db_session),
    _user: str = Depends(get_current_user),
):
    """
    Export filtered audit log entries as CSV.

    Filename: AlphaCent_AuditLog_{start}_{end}.csv

    Validates: Requirements 21.8
    """
    parsed_types = [t.strip() for t in event_types.split(",")] if event_types else None
    parsed_start = datetime.fromisoformat(start_date) if start_date else datetime.now() - timedelta(days=90)
    parsed_end = datetime.fromisoformat(end_date) if end_date else None

    entries = _build_audit_entries(
        session=session,
        event_types=parsed_types,
        symbol=symbol,
        severity=severity,
        start_date=parsed_start,
        end_date=parsed_end,
        search=search,
    )

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "event_type", "symbol", "strategy_name", "severity", "description"])
    for entry in entries:
        writer.writerow([
            entry.timestamp,
            entry.event_type,
            entry.symbol or "",
            entry.strategy_name or "",
            entry.severity,
            entry.description,
        ])

    csv_content = output.getvalue()
    output.close()

    start_str = parsed_start.strftime("%Y-%m-%d") if parsed_start else "all"
    end_str = parsed_end.strftime("%Y-%m-%d") if parsed_end else datetime.now().strftime("%Y-%m-%d")
    filename = f"AlphaCent_AuditLog_{start_str}_{end_str}.csv"

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
