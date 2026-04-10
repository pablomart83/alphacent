"""
Signal activity endpoints for AlphaCent Trading Platform.

Provides endpoints for viewing recent signal decisions (accepted/rejected).
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
from src.models.orm import SignalDecisionLogORM

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
    """
    try:
        # Fetch recent signal decisions ordered by most recent first
        recent = (
            session.query(SignalDecisionLogORM)
            .order_by(desc(SignalDecisionLogORM.created_at))
            .limit(limit)
            .all()
        )

        signals = [SignalDecisionResponse(**s.to_dict()) for s in recent]

        # Compute summary stats over the fetched window
        total = len(signals)
        accepted = sum(1 for s in signals if s.decision == "ACCEPTED")
        rejected = total - accepted
        acceptance_rate = (accepted / total * 100) if total > 0 else 0.0

        # Rejection reason breakdown
        reason_counts: Dict[str, int] = defaultdict(int)
        for s in signals:
            if s.decision == "REJECTED" and s.rejection_reason:
                # Normalise to a short category
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
