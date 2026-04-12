"""
Dashboard widget endpoints for AlphaCent Trading Platform.

Provides lightweight endpoints for bottom-zone widgets:
- Top Movers (gainers/losers by daily P&L %)
- Recent Signals (last N signals with conviction)
- Strategy Alerts (lifecycle events)

Validates: Requirements 25.2, 25.6
"""

import logging
import math
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from src.models.enums import TradingMode, StrategyStatus
from src.api.dependencies import get_current_user, get_db_session
from src.models.orm import (
    PositionORM,
    StrategyORM,
    ConvictionScoreLogORM,
    StrategyProposalORM,
    StrategyRetirementORM,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _safe_float(value) -> float:
    """Sanitize a numeric value for JSON serialization."""
    if value is None:
        return 0.0
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return 0.0
        return round(f, 4)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class MoverEntry(BaseModel):
    symbol: str
    current_price: float
    entry_price: float
    pnl_pct: float
    invested_amount: Optional[float] = None
    side: Optional[str] = None


class TopMoversResponse(BaseModel):
    gainers: List[MoverEntry]
    losers: List[MoverEntry]


class SignalEntry(BaseModel):
    id: int
    symbol: str
    strategy_name: Optional[str] = None
    conviction_score: float
    direction: str
    signal_type: str
    timestamp: str


class RecentSignalsResponse(BaseModel):
    signals: List[SignalEntry]
    total: int


class AlertEntry(BaseModel):
    id: int
    event_type: str
    strategy_name: Optional[str] = None
    symbol: Optional[str] = None
    detail: str
    timestamp: str


class StrategyAlertsResponse(BaseModel):
    alerts: List[AlertEntry]
    total: int


# ---------------------------------------------------------------------------
# GET /dashboard/top-movers
# ---------------------------------------------------------------------------

@router.get("/top-movers", response_model=TopMoversResponse)
async def get_top_movers(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Top 5 gainers + top 5 losers from open positions by unrealised P&L %.

    Validates: Requirement 25.2
    """
    positions = db.query(PositionORM).filter(
        PositionORM.closed_at.is_(None),
    ).all()

    scored: List[Dict[str, Any]] = []
    for p in positions:
        entry = p.entry_price or 0
        current = p.current_price or 0
        if entry <= 0:
            continue

        side_str = str(p.side).upper() if p.side else "LONG"
        if "SHORT" in side_str or "SELL" in side_str:
            pnl_pct = ((entry - current) / entry) * 100
        else:
            pnl_pct = ((current - entry) / entry) * 100

        scored.append({
            "symbol": p.symbol,
            "current_price": _safe_float(current),
            "entry_price": _safe_float(entry),
            "pnl_pct": _safe_float(pnl_pct),
            "invested_amount": _safe_float(getattr(p, "invested_amount", None)),
            "side": "SELL" if ("SHORT" in side_str or "SELL" in side_str) else "BUY",
        })

    # Sort descending for gainers, ascending for losers
    scored.sort(key=lambda x: x["pnl_pct"], reverse=True)
    gainers = [MoverEntry(**s) for s in scored[:5]]
    losers = [MoverEntry(**s) for s in scored[-5:][::-1]]  # worst 5, most negative first

    return TopMoversResponse(gainers=gainers, losers=losers)


# ---------------------------------------------------------------------------
# GET /dashboard/recent-signals
# ---------------------------------------------------------------------------

@router.get("/recent-signals", response_model=RecentSignalsResponse)
async def get_recent_signals(
    mode: TradingMode,
    limit: int = Query(5, ge=1, le=50),
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Last N signals with conviction score, direction, symbol, strategy, timestamp.

    Uses the conviction_score_logs table which records every signal evaluation.

    Validates: Requirement 25.6
    """
    logs = (
        db.query(ConvictionScoreLogORM)
        .order_by(desc(ConvictionScoreLogORM.timestamp))
        .limit(limit)
        .all()
    )

    # Bulk-fetch strategy names for the returned signals
    strategy_ids = list({l.strategy_id for l in logs if l.strategy_id})
    strategy_name_map: Dict[str, str] = {}
    if strategy_ids:
        strats = (
            db.query(StrategyORM.id, StrategyORM.name)
            .filter(StrategyORM.id.in_(strategy_ids))
            .all()
        )
        strategy_name_map = {s.id: s.name for s in strats}

    signals = []
    for l in logs:
        signals.append(SignalEntry(
            id=l.id,
            symbol=l.symbol,
            strategy_name=strategy_name_map.get(l.strategy_id),
            conviction_score=_safe_float(l.conviction_score),
            direction=l.signal_type or "ENTRY",
            signal_type=l.signal_type or "ENTRY",
            timestamp=l.timestamp.isoformat() if l.timestamp else "",
        ))

    return RecentSignalsResponse(signals=signals, total=len(signals))


# ---------------------------------------------------------------------------
# GET /dashboard/strategy-alerts
# ---------------------------------------------------------------------------

@router.get("/strategy-alerts", response_model=StrategyAlertsResponse)
async def get_strategy_alerts(
    mode: TradingMode,
    limit: int = Query(10, ge=1, le=100),
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Recent strategy lifecycle events: activations, retirements, pending closures, demotions.

    Combines data from:
    - strategy_proposals (activated=1 → activation events)
    - strategy_retirements (retirement events)
    - positions with pending_closure=True (pending closure events)
    - strategies with status changes (demotions / deactivations)

    Validates: Requirement 25.6
    """
    alerts: List[Dict[str, Any]] = []

    # 1. Recent activations from proposals
    recent_proposals = (
        db.query(StrategyProposalORM)
        .filter(StrategyProposalORM.activated == 1)
        .order_by(desc(StrategyProposalORM.proposed_at))
        .limit(limit)
        .all()
    )
    proposal_strategy_ids = [p.strategy_id for p in recent_proposals]
    proposal_name_map: Dict[str, str] = {}
    if proposal_strategy_ids:
        strats = (
            db.query(StrategyORM.id, StrategyORM.name)
            .filter(StrategyORM.id.in_(proposal_strategy_ids))
            .all()
        )
        proposal_name_map = {s.id: s.name for s in strats}

    for p in recent_proposals:
        name = proposal_name_map.get(p.strategy_id, p.strategy_id[:12])
        alerts.append({
            "id": p.id,
            "event_type": "activation",
            "strategy_name": name,
            "symbol": None,
            "detail": f"Strategy activated (regime: {p.market_regime})",
            "timestamp": p.proposed_at.isoformat() if p.proposed_at else "",
        })

    # 2. Recent retirements
    recent_retirements = (
        db.query(StrategyRetirementORM)
        .order_by(desc(StrategyRetirementORM.retired_at))
        .limit(limit)
        .all()
    )
    retirement_strategy_ids = [r.strategy_id for r in recent_retirements]
    retirement_name_map: Dict[str, str] = {}
    if retirement_strategy_ids:
        strats = (
            db.query(StrategyORM.id, StrategyORM.name)
            .filter(StrategyORM.id.in_(retirement_strategy_ids))
            .all()
        )
        retirement_name_map = {s.id: s.name for s in strats}

    for r in recent_retirements:
        name = retirement_name_map.get(r.strategy_id, r.strategy_id[:12])
        alerts.append({
            "id": r.id + 100000,  # offset to avoid id collision
            "event_type": "retirement",
            "strategy_name": name,
            "symbol": None,
            "detail": f"Retired: {r.reason}" if r.reason else "Strategy retired",
            "timestamp": r.retired_at.isoformat() if r.retired_at else "",
        })

    # 3. Pending closures (positions flagged for closure)
    pending_positions = (
        db.query(PositionORM)
        .filter(
            PositionORM.closed_at.is_(None),
            PositionORM.pending_closure == True,
        )
        .all()
    )
    for pos in pending_positions:
        alerts.append({
            "id": hash(pos.id) % 10**9,
            "event_type": "pending_closure",
            "strategy_name": None,
            "symbol": pos.symbol,
            "detail": pos.closure_reason or "Position pending closure",
            "timestamp": pos.opened_at.isoformat() if pos.opened_at else "",
        })

    # 4. Recent demotions — strategies moved to PAUSED or INVALID
    demoted = (
        db.query(StrategyORM)
        .filter(StrategyORM.status.in_([
            StrategyStatus.PAUSED.value,
            StrategyStatus.INVALID.value,
        ]))
        .order_by(desc(StrategyORM.created_at))
        .limit(limit)
        .all()
    )
    for s in demoted:
        alerts.append({
            "id": hash(s.id) % 10**9,
            "event_type": "demotion",
            "strategy_name": s.name,
            "symbol": None,
            "detail": f"Strategy status: {s.status.value if hasattr(s.status, 'value') else s.status}",
            "timestamp": s.created_at.isoformat() if s.created_at else "",
        })

    # Sort all alerts by timestamp descending, take top `limit`
    alerts.sort(key=lambda a: a["timestamp"], reverse=True)
    alerts = alerts[:limit]

    return StrategyAlertsResponse(
        alerts=[AlertEntry(**a) for a in alerts],
        total=len(alerts),
    )
