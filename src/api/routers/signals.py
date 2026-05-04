"""
Signal activity endpoints for AlphaCent Trading Platform.

Provides endpoints for viewing recent signal decisions (accepted/rejected).

2026-05-04 — Unified funnel migration
=====================================
This router previously read from `signal_decision_log` (SignalDecisionLogORM),
which was a legacy table written only by `trading_scheduler._log_signal_decision`.
The rest of the system (proposer, walk-forward, activation, ex-post veto, order
executor) wrote to `signal_decisions` (SignalDecisionORM) — the canonical
funnel. Two tables, no join, frontend confused.

Now reads exclusively from `signal_decisions`, filtering to the stages that
represent "a signal was generated and a decision was made":
    gate_blocked    — rejected at coordination/risk (the vast majority of
                      the legacy REJECTED rows)
    order_submitted — signal passed validation, order sent to eToro
    order_filled    — optional upstream read for full lifecycle

The response shape is unchanged so frontend widgets keep working. The
translation layer below maps unified-table columns to the legacy response
fields (signal_id, side, signal_type, etc.).
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from src.models.enums import TradingMode
from src.api.dependencies import get_current_user, get_db_session
from src.models.orm import SignalDecisionORM

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signals", tags=["signals"])


class SignalDecisionResponse(BaseModel):
    """Single signal decision entry."""
    id: int
    signal_id: str
    strategy_id: str
    symbol: str
    side: str
    signal_type: str
    decision: str
    rejection_reason: Optional[str] = None
    created_at: str
    metadata: Optional[Dict[str, Any]] = None


class RejectionBreakdown(BaseModel):
    """Breakdown of rejection reasons."""
    reason: str
    count: int
    percentage: float


class SignalSummaryStats(BaseModel):
    """Summary statistics for signal decisions."""
    total: int
    accepted: int
    rejected: int
    acceptance_rate: float
    rejection_reasons: List[RejectionBreakdown]


class RecentSignalsResponse(BaseModel):
    """Response for recent signals endpoint."""
    signals: List[SignalDecisionResponse]
    summary: SignalSummaryStats


@router.get("/recent", response_model=RecentSignalsResponse)
async def get_recent_signals(
    mode: TradingMode = Query(TradingMode.DEMO),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_db_session),
    _user: str = Depends(get_current_user),
):
    """
    Get recent signal decisions with summary statistics.

    Returns the last N signal decisions (accepted and rejected) along with
    aggregate stats like acceptance rate and rejection reason breakdown.

    2026-05-04: Migrated from `signal_decision_log` to the canonical
    `signal_decisions` funnel. Scoped to the stages that represent the
    "signal was generated → decision was made" boundary:
        - gate_blocked (rejection at coordination/risk)
        - order_submitted (signal passed validation to eToro)
        - order_filled (optional upstream lifecycle)
    Upstream stages (proposed, wf_*, activated, signal_emitted) are a
    different question — "did we propose / validate / activate", not
    "did we decide on a signal". Keep them out of this endpoint so the
    rejection-reason breakdown stays focused.
    """
    try:
        # Stages that represent a signal→decision pair. Keep this tight so
        # the acceptance-rate denominator is meaningful (total emitted
        # signals that reached a decision, not total proposals in a cycle).
        DECISION_STAGES = ("gate_blocked", "order_submitted", "order_filled")

        recent = (
            session.query(SignalDecisionORM)
            .filter(SignalDecisionORM.stage.in_(DECISION_STAGES))
            .order_by(desc(SignalDecisionORM.timestamp))
            .limit(limit)
            .all()
        )

        signals = [_row_to_response(r) for r in recent]

        # Compute summary stats over the fetched window
        total = len(signals)
        accepted = sum(1 for s in signals if s.decision == "ACCEPTED")
        rejected = total - accepted
        acceptance_rate = (accepted / total * 100) if total > 0 else 0.0

        # Rejection reason breakdown
        reason_counts: Dict[str, int] = defaultdict(int)
        for s in signals:
            if s.decision == "REJECTED" and s.rejection_reason:
                reason_key = _categorize_rejection(s.rejection_reason)
                reason_counts[reason_key] += 1

        rejection_reasons = [
            RejectionBreakdown(
                reason=reason,
                count=count,
                percentage=(count / rejected * 100) if rejected > 0 else 0.0,
            )
            for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1])
        ]

        summary = SignalSummaryStats(
            total=total,
            accepted=accepted,
            rejected=rejected,
            acceptance_rate=round(acceptance_rate, 1),
            rejection_reasons=rejection_reasons,
        )

        return RecentSignalsResponse(signals=signals, summary=summary)

    except Exception as e:
        logger.error(f"Error fetching recent signals: {e}", exc_info=True)
        return RecentSignalsResponse(
            signals=[],
            summary=SignalSummaryStats(
                total=0, accepted=0, rejected=0,
                acceptance_rate=0.0, rejection_reasons=[],
            ),
        )


def _row_to_response(row: SignalDecisionORM) -> "SignalDecisionResponse":
    """Translate a unified-funnel row to the legacy SignalDecisionResponse schema.

    Frontend widgets (SignalStatsWidget, CycleIntelligencePanel, etc.) were
    built around the legacy `signal_decision_log.to_dict()` output, so we
    preserve that contract here rather than churning 6 UI components.
    """
    meta = row.decision_metadata or {}

    # Derive side (BUY/SELL) from direction or action in metadata
    action_val = meta.get("action", "")
    if row.direction == "long" or "LONG" in action_val or "BUY" in action_val:
        side = "BUY"
    elif row.direction == "short" or "SHORT" in action_val or "SELL" in action_val:
        side = "SELL"
    else:
        side = "BUY"  # default — entries dominate the funnel

    # Derive signal_type from action
    if "EXIT" in action_val or "EXIT_" in action_val:
        signal_type = "EXIT"
    else:
        signal_type = "ENTRY"

    # Decision enum: unified-table uses lower-case, legacy UI expects upper
    if row.stage in ("order_submitted", "order_filled"):
        decision = "ACCEPTED"
    else:
        decision = "REJECTED"

    return SignalDecisionResponse(
        id=row.id,
        signal_id=f"sd-{row.id}",  # synthetic — the legacy signal_id was opaque
        strategy_id=row.strategy_id or "",
        symbol=row.symbol or "",
        side=side,
        signal_type=signal_type,
        decision=decision,
        rejection_reason=row.reason,
        created_at=(row.timestamp.isoformat() if row.timestamp else ""),
        metadata={
            **meta,
            "template_name": row.template_name,
            "cycle_id": row.cycle_id,
            "score": row.score,
            "stage": row.stage,  # exposes the unified taxonomy to the UI
        },
    )


def _categorize_rejection(reason: str) -> str:
    """Map a verbose rejection reason to a short category label."""
    reason_lower = reason.lower()
    if "duplicate" in reason_lower or "existing" in reason_lower:
        return "Duplicate Position"
    if "portfolio balance" in reason_lower or "sector" in reason_lower or "directional" in reason_lower:
        return "Portfolio Balance"
    if "risk" in reason_lower or "exposure" in reason_lower or "position size" in reason_lower:
        return "Risk Limit"
    if "correlation" in reason_lower:
        return "Correlated Symbol"
    if "symbol limit" in reason_lower:
        return "Symbol Limit"
    if "pending" in reason_lower:
        return "Pending Order Exists"
    if "confidence" in reason_lower or "conviction" in reason_lower:
        return "Low Confidence"
    return "Other"
