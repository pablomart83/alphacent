"""Intel page API — /intel/*

Endpoints:
  POST /intel/run?lookback_days=N   — trigger analysis run
  GET  /intel/runs                  — run history
  GET  /intel/findings              — findings with filters
  GET  /intel/findings/{id}         — single finding
  POST /intel/findings/{id}/dismiss — dismiss with reason
  POST /intel/findings/{id}/resolve — mark resolved
  GET  /intel/summary               — counts for nav badge
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from src.api.dependencies import get_current_user, get_db_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intel", tags=["intel"])


# ── Request / Response models ─────────────────────────────────────────────────

class DismissBody(BaseModel):
    reason: str = ""


class RunResponse(BaseModel):
    run_id: str
    findings_created: int
    findings_updated: int
    findings_count: int
    duration_s: float


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_finding(row) -> dict:
    import json
    # context_links: PostgreSQL JSON columns come back already parsed as list/dict
    # Only call json.loads if it's a string (e.g. SQLite)
    cl = row[9]
    if isinstance(cl, str):
        try:
            cl = json.loads(cl)
        except Exception:
            cl = []
    elif cl is None:
        cl = []
    return {
        "id": row[0],
        "check_id": row[1],
        "key": row[2],
        "category": row[3],
        "severity": row[4],
        "title": row[5],
        "detail": row[6],
        "evidence": row[7],
        "recommended_action": row[8],
        "context_links": cl,
        "ask_kiro_prompt": row[10],
        "first_seen": row[11].isoformat() + "Z" if row[11] else None,
        "last_seen": row[12].isoformat() + "Z" if row[12] else None,
        "occurrence_count": row[13],
        "lookback_days": row[14],
        "status": row[15],
        "dismissed_reason": row[16],
        "resolved_at": row[17].isoformat() + "Z" if row[17] else None,
        "created_at": row[18].isoformat() + "Z" if row[18] else None,
        "updated_at": row[19].isoformat() + "Z" if row[19] else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/run", response_model=RunResponse)
async def run_analysis(
    lookback_days: int = Query(default=7, ge=1, le=90),
    username: str = Depends(get_current_user),
):
    """Trigger a full analysis run. Runs synchronously (5-15s). Returns summary."""
    from src.models.database import get_database
    from src.analytics.intel_log_reader import IntelLogReader
    from src.analytics.intel_analyst import IntelAnalyst

    db = get_database()
    log_reader = IntelLogReader()
    analyst = IntelAnalyst(db, log_reader)

    try:
        result = analyst.run(lookback_days=lookback_days)
        return RunResponse(**result)
    except Exception as exc:
        logger.error(f"Intel run failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/runs")
async def get_runs(
    limit: int = Query(default=20, ge=1, le=100),
    username: str = Depends(get_current_user),
    db=Depends(get_db_session),
):
    """List recent analysis runs."""
    rows = db.execute(text(
        "SELECT id, started_at, completed_at, lookback_days, findings_created, "
        "findings_updated, findings_total, duration_s, error, status "
        "FROM intel_runs ORDER BY started_at DESC LIMIT :limit"
    ), {"limit": limit}).fetchall()

    return [
        {
            "id": r[0],
            "started_at": r[1].isoformat() + "Z" if r[1] else None,
            "completed_at": r[2].isoformat() + "Z" if r[2] else None,
            "lookback_days": r[3],
            "findings_created": r[4],
            "findings_updated": r[5],
            "findings_total": r[6],
            "duration_s": r[7],
            "error": r[8],
            "status": r[9],
        }
        for r in rows
    ]


@router.get("/findings")
async def get_findings(
    status: Optional[str] = Query(default="open"),
    category: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=500),
    username: str = Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Get findings with optional filters."""
    conditions = []
    params: dict = {"limit": limit}

    if status and status != "all":
        conditions.append("status = :status")
        params["status"] = status

    if category:
        conditions.append("category = :category")
        params["category"] = category

    if severity:
        conditions.append("severity = :severity")
        params["severity"] = severity

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    rows = db.execute(text(
        f"SELECT id, check_id, key, category, severity, title, detail, evidence, "
        f"recommended_action, context_links, ask_kiro_prompt, first_seen, last_seen, "
        f"occurrence_count, lookback_days, status, dismissed_reason, resolved_at, "
        f"created_at, updated_at "
        f"FROM system_findings {where} "
        f"ORDER BY "
        f"  CASE severity WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END, "
        f"  last_seen DESC "
        f"LIMIT :limit"
    ), params).fetchall()

    return [_row_to_finding(r) for r in rows]


@router.get("/findings/{finding_id}")
async def get_finding(
    finding_id: str,
    username: str = Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Get single finding with full detail."""
    row = db.execute(text(
        "SELECT id, check_id, key, category, severity, title, detail, evidence, "
        "recommended_action, context_links, ask_kiro_prompt, first_seen, last_seen, "
        "occurrence_count, lookback_days, status, dismissed_reason, resolved_at, "
        "created_at, updated_at "
        "FROM system_findings WHERE id = :id"
    ), {"id": finding_id}).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Finding not found")

    return _row_to_finding(row)


@router.post("/findings/{finding_id}/dismiss")
async def dismiss_finding(
    finding_id: str,
    body: DismissBody,
    username: str = Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Dismiss a finding with a reason."""
    result = db.execute(text(
        "UPDATE system_findings SET status='dismissed', dismissed_reason=:reason, "
        "updated_at=NOW() WHERE id=:id AND status='open'"
    ), {"id": finding_id, "reason": body.reason})
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Finding not found or already dismissed")

    return {"success": True, "message": "Finding dismissed"}


@router.post("/findings/{finding_id}/resolve")
async def resolve_finding(
    finding_id: str,
    username: str = Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Mark a finding as resolved."""
    result = db.execute(text(
        "UPDATE system_findings SET status='resolved', resolved_at=NOW(), "
        "updated_at=NOW() WHERE id=:id AND status IN ('open','dismissed')"
    ), {"id": finding_id})
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Finding not found or already resolved")

    return {"success": True, "message": "Finding resolved"}


@router.get("/summary")
async def get_summary(
    username: str = Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Summary counts for nav badge and top tiles."""
    counts = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE severity='P0' AND status='open') as p0_open,
            COUNT(*) FILTER (WHERE severity='P1' AND status='open') as p1_open,
            COUNT(*) FILTER (WHERE severity='P2' AND status='open') as p2_open,
            COUNT(*) FILTER (WHERE severity='opportunity' AND status='open') as opp_open,
            COUNT(*) FILTER (WHERE status='resolved' AND resolved_at > NOW() - INTERVAL '7 days') as resolved_week
        FROM system_findings
    """)).fetchone()

    last_run = db.execute(text(
        "SELECT started_at, duration_s, findings_total FROM intel_runs "
        "WHERE status='complete' ORDER BY started_at DESC LIMIT 1"
    )).fetchone()

    return {
        "p0_open": counts[0] or 0,
        "p1_open": counts[1] or 0,
        "p2_open": counts[2] or 0,
        "opportunities_open": counts[3] or 0,
        "resolved_this_week": counts[4] or 0,
        "last_run_at": last_run[0].isoformat() + "Z" if last_run and last_run[0] else None,
        "last_run_duration_s": last_run[1] if last_run else None,
        "last_run_findings": last_run[2] if last_run else None,
    }
