"""
Live trading endpoints — Phase 2B.

Provides summary, positions, orders, divergence, and management endpoints
for the live Agent Portfolio account.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user, get_db_session
from src.models.orm import PositionORM, OrderORM, LiveStrategyORM, GraduationApprovalORM, StrategyORM
from src.models.enums import StrategyStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/live", tags=["live"])


# ── Summary ───────────────────────────────────────────────────────────────────

@router.get("/summary")
async def get_live_summary(
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Live account summary: balance, P&L, positions, deployed capital.
    Reads from DB (kept fresh by MonitoringService live sync).
    """
    from src.models.orm import AccountInfoORM, EquitySnapshotORM
    from sqlalchemy import func

    # Account info — live row
    account = db.query(AccountInfoORM).filter_by(account_id="live_account_001").first()
    if not account:
        # Try by mode
        account = db.query(AccountInfoORM).filter(
            AccountInfoORM.mode.in_(["LIVE", "live"])
        ).first()

    balance = float(account.balance) if account else 0.0
    equity = float(account.equity) if account else 0.0
    daily_pnl = float(account.daily_pnl) if account else 0.0

    # Open live positions
    open_positions = db.query(PositionORM).filter(
        PositionORM.closed_at.is_(None),
        PositionORM.account_type == "live",
    ).all()

    unrealized_pnl = sum(float(p.unrealized_pnl or 0) for p in open_positions)
    deployed_capital = sum(float(p.invested_amount or 0) for p in open_positions)

    # Active live authorizations
    active_live = db.query(LiveStrategyORM).filter(
        LiveStrategyORM.retired_at.is_(None)
    ).count()

    # Live equity snapshots for today's P&L
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday_snap = (
        db.query(EquitySnapshotORM)
        .filter(
            EquitySnapshotORM.account_type == "live",
            EquitySnapshotORM.snapshot_type == "daily",
            EquitySnapshotORM.date < today,
        )
        .order_by(EquitySnapshotORM.date.desc())
        .first()
    )
    prev_equity = float(yesterday_snap.equity) if yesterday_snap else equity
    today_pnl = equity - prev_equity if prev_equity > 0 else 0.0

    # Mirror ratio from config
    mirror_ratio = 0.10
    try:
        import yaml
        from pathlib import Path
        cfg = yaml.safe_load(Path("config/autonomous_trading.yaml").read_text()) or {}
        mirror_ratio = float(cfg.get("live_trading", {}).get("mirror_ratio", 0.10))
    except Exception:
        pass

    return {
        "virtual_balance": balance,
        "virtual_equity": equity,
        "real_equity": round(equity * mirror_ratio, 2),
        "mirror_ratio": mirror_ratio,
        "unrealized_pnl_virtual": round(unrealized_pnl, 2),
        "unrealized_pnl_real": round(unrealized_pnl * mirror_ratio, 2),
        "today_pnl_virtual": round(today_pnl, 2),
        "today_pnl_real": round(today_pnl * mirror_ratio, 2),
        "open_positions": len(open_positions),
        "deployed_capital_virtual": round(deployed_capital, 2),
        "deployed_capital_real": round(deployed_capital * mirror_ratio, 2),
        "deployed_pct": round(deployed_capital / balance * 100, 1) if balance > 0 else 0.0,
        "active_live_authorizations": active_live,
        "live_enabled": _get_live_enabled(),
    }


def _get_live_enabled() -> bool:
    try:
        import yaml
        from pathlib import Path
        cfg = yaml.safe_load(Path("config/autonomous_trading.yaml").read_text()) or {}
        return bool(cfg.get("live_trading", {}).get("enabled", False))
    except Exception:
        return False


# ── Divergence ────────────────────────────────────────────────────────────────

@router.get("/divergence")
async def get_live_divergence(
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Per live_strategies row: paper Sharpe vs live Sharpe from trade_journal.
    Divergence = live_sharpe / paper_sharpe × 100%.
    Flags strategies where live is underperforming paper by >50%.
    """
    from sqlalchemy import text

    live_rows = db.query(LiveStrategyORM).filter(
        LiveStrategyORM.retired_at.is_(None)
    ).all()

    if not live_rows:
        return {"divergence": [], "count": 0}

    strategy_ids = [ls.strategy_id for ls in live_rows]

    # Single bulk query: aggregate stats for all live strategies by account_type.
    # Replaces 2×N individual queries (one paper + one live per strategy).
    bulk_stats = db.execute(
        text("""
            SELECT
                strategy_id,
                symbol,
                account_type,
                COUNT(*) AS trades,
                ROUND(CASE WHEN STDDEV(pnl) > 0
                     THEN (AVG(pnl) / STDDEV(pnl)) * SQRT(252) ELSE 0
                END::numeric, 3) AS sharpe,
                ROUND(100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0)::numeric, 1) AS win_rate,
                ROUND(COALESCE(SUM(pnl), 0)::numeric, 2) AS total_pnl
            FROM trade_journal
            WHERE strategy_id = ANY(:sids)
              AND pnl IS NOT NULL
              AND account_type IN ('demo', 'live')
            GROUP BY strategy_id, symbol, account_type
        """),
        {"sids": strategy_ids},
    ).fetchall()

    # Index by (strategy_id, account_type) for O(1) lookup
    stats_map: dict = {}
    for row in bulk_stats:
        stats_map[(row.strategy_id, row.account_type)] = row

    results = []
    for ls in live_rows:
        paper = stats_map.get((ls.strategy_id, 'demo'))
        live_stats = stats_map.get((ls.strategy_id, 'live'))

        paper_sharpe = float(paper.sharpe) if paper and paper.sharpe is not None else None
        live_sharpe = float(live_stats.sharpe) if live_stats and live_stats.sharpe is not None else None
        divergence_pct = None
        if paper_sharpe and paper_sharpe > 0 and live_sharpe is not None:
            divergence_pct = round(live_sharpe / paper_sharpe * 100, 1)

        results.append({
            "id": ls.id,
            "strategy_id": ls.strategy_id,
            "template_name": ls.template_name,
            "symbol": ls.symbol,
            "activated_at": ls.activated_at.isoformat() if ls.activated_at else None,
            "position_size": ls.position_size,
            "sl_pct": ls.sl_pct,
            "tp_pct": ls.tp_pct,
            "conviction_min": ls.conviction_min,
            "paper_trades": int(paper.trades) if paper else 0,
            "paper_sharpe": paper_sharpe,
            "paper_win_rate": float(paper.win_rate) if paper and paper.win_rate is not None else None,
            "paper_pnl": float(paper.total_pnl) if paper and paper.total_pnl is not None else None,
            "live_trades": int(live_stats.trades) if live_stats else 0,
            "live_sharpe": live_sharpe,
            "live_win_rate": float(live_stats.win_rate) if live_stats and live_stats.win_rate is not None else None,
            "live_pnl": float(live_stats.total_pnl) if live_stats and live_stats.total_pnl is not None else None,
            "divergence_pct": divergence_pct,
            "divergence_flag": divergence_pct is not None and divergence_pct < 50,
        })

    results.sort(key=lambda x: (x["divergence_flag"] is True, -(x["divergence_pct"] or 999)), reverse=True)
    return {"divergence": results, "count": len(results)}



# ── Live strategy parameter update ───────────────────────────────────────────

class UpdateLiveStrategyBody(BaseModel):
    position_size: Optional[float] = None
    sl_pct: Optional[float] = None
    tp_pct: Optional[float] = None
    conviction_min: Optional[int] = None


@router.patch("/strategies/{live_id}")
async def update_live_strategy(
    live_id: int,
    body: UpdateLiveStrategyBody,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Update CIO-controlled parameters on an active live authorization.
    Only non-None fields are updated. Takes effect on the next signal cycle.
    """
    ls = db.query(LiveStrategyORM).filter_by(id=live_id).first()
    if not ls:
        raise HTTPException(status_code=404, detail=f"Live strategy {live_id} not found")
    if ls.retired_at is not None:
        raise HTTPException(status_code=400, detail="Cannot update a retired live strategy")

    changes = []
    if body.position_size is not None:
        if body.position_size <= 0:
            raise HTTPException(status_code=422, detail="position_size must be > 0")
        ls.position_size = body.position_size
        changes.append(f"position_size={body.position_size:.0f}")
    if body.sl_pct is not None:
        if not (0 < body.sl_pct < 1):
            raise HTTPException(status_code=422, detail="sl_pct must be between 0 and 1 (e.g. 0.06 = 6%)")
        ls.sl_pct = body.sl_pct
        changes.append(f"sl_pct={body.sl_pct:.3f}")
    if body.tp_pct is not None:
        if not (0 < body.tp_pct < 2):
            raise HTTPException(status_code=422, detail="tp_pct must be between 0 and 2 (e.g. 0.15 = 15%)")
        ls.tp_pct = body.tp_pct
        changes.append(f"tp_pct={body.tp_pct:.3f}")
    if body.conviction_min is not None:
        if not (50 <= body.conviction_min <= 100):
            raise HTTPException(status_code=422, detail="conviction_min must be 50–100")
        ls.conviction_min = body.conviction_min
        changes.append(f"conviction_min={body.conviction_min}")

    if not changes:
        return {"success": True, "message": "No changes", "live_id": live_id}

    db.commit()
    logger.info(
        f"User {username} updated live strategy {live_id} "
        f"({ls.template_name} / {ls.symbol}): {', '.join(changes)}"
    )
    return {
        "success": True,
        "message": f"Updated {', '.join(changes)}",
        "live_id": live_id,
        "position_size": ls.position_size,
        "sl_pct": ls.sl_pct,
        "tp_pct": ls.tp_pct,
        "conviction_min": ls.conviction_min,
    }


# ── Live strategy management ──────────────────────────────────────────────────

@router.post("/strategies/{live_id}/retire")
async def retire_live_strategy(
    live_id: int,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Retire a live authorization — stops live fills for this (strategy, symbol) pair
    AND flags any open live position for that strategy for closure.

    Sets retired_at = NOW(); the strategy continues paper-trading on DEMO. Open
    live positions are flagged (pending_closure = True) — the live MonitoringService
    pending-closure pass submits the close orders on its next 60s cycle. Retiring is
    an explicit CIO action, so flagging the real-money position for closure is the
    intended behaviour (a retired strategy should not keep holding real capital).
    """
    ls = db.query(LiveStrategyORM).filter_by(id=live_id).first()
    if not ls:
        raise HTTPException(status_code=404, detail=f"Live strategy {live_id} not found")
    if ls.retired_at is not None:
        raise HTTPException(status_code=400, detail="Already retired")

    ls.retired_at = datetime.now()

    # Revert the strategy's lifecycle status LIVE → PAPER so the live book is not
    # overstated. A live_strategies row with retired_at set is excluded from the
    # live pass (get_all_live_approvals filters retired_at IS NULL), but the
    # strategies.status field was previously left at 'LIVE' forever — so any UI or
    # query that counts status='LIVE' (the live book) over-reported retired pairs
    # (confirmed 2026-06-16: 15 status='LIVE' rows vs 10 active live_strategies).
    # PAPER is the documented post-retire state ("the strategy continues
    # paper-trading on DEMO"): it re-enters the DEMO loop for data collection and
    # can only return to live via an explicit CIO graduate action. Scoped to the
    # exact strategy_id; only flip when currently LIVE (idempotent / safe).
    status_reverted = False
    strat_orm = db.query(StrategyORM).filter_by(id=ls.strategy_id).first()
    if strat_orm is not None and strat_orm.status == StrategyStatus.LIVE:
        strat_orm.status = StrategyStatus.PAPER
        status_reverted = True

    # Flag any OPEN LIVE position for this strategy for closure. Scoped to
    # account_type='live' so a paper/demo position for the same strategy is never
    # touched, and to closed_at IS NULL / not-already-pending so it is idempotent.
    open_live_positions = db.query(PositionORM).filter(
        PositionORM.strategy_id == ls.strategy_id,
        PositionORM.account_type == 'live',
        PositionORM.closed_at.is_(None),
        PositionORM.pending_closure == False,  # noqa: E712 — SQLAlchemy boolean filter
    ).all()
    flagged = 0
    for _pos in open_live_positions:
        _pos.pending_closure = True
        _pos.closure_reason = (
            f"Live strategy retired by {username} "
            f"({ls.template_name} / {ls.symbol}) — flagged for closure on retire"
        )
        flagged += 1

    db.commit()

    if flagged:
        logger.warning(
            f"User {username} retired live strategy {live_id} "
            f"({ls.template_name} / {ls.symbol}) and flagged {flagged} open live "
            f"position(s) for closure — pending-closure pass will submit close order(s)"
            f"{' [status LIVE→PAPER]' if status_reverted else ''}"
        )
    else:
        logger.info(
            f"User {username} retired live strategy {live_id} "
            f"({ls.template_name} / {ls.symbol}) — no open live position to close"
            f"{' [status LIVE→PAPER]' if status_reverted else ''}"
        )
    return {
        "success": True,
        "message": (
            f"{ls.template_name} / {ls.symbol} retired from live trading"
            + (f"; {flagged} open position(s) flagged for closure" if flagged else "")
        ),
        "retired_at": ls.retired_at.isoformat(),
        "positions_flagged_for_closure": flagged,
        "status_reverted_to_paper": status_reverted,
    }


# ── Live position close ───────────────────────────────────────────────────────

@router.post("/positions/{position_id}/close")
async def close_live_position(
    position_id: str,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Close a live position via the live eToro client.
    Only works on positions with account_type='live'.
    """
    pos = db.query(PositionORM).filter_by(id=position_id).first()
    if not pos:
        raise HTTPException(status_code=404, detail=f"Position {position_id} not found")
    if getattr(pos, "account_type", "demo") != "live":
        raise HTTPException(status_code=400, detail="Position is not a live position")
    if pos.closed_at is not None:
        raise HTTPException(status_code=400, detail="Position already closed")

    try:
        from src.api.app import get_live_etoro_client
        from src.utils.instrument_mappings import SYMBOL_TO_INSTRUMENT_ID
        live_client = get_live_etoro_client()
        if not live_client:
            raise HTTPException(status_code=503, detail="Live eToro client not configured")

        instrument_id = SYMBOL_TO_INSTRUMENT_ID.get(pos.symbol)

        # Refresh etoro_position_id before closing — the DB value may be stale
        # due to eToro's ID oscillation. Fetch current positions and find the
        # correct ID for this symbol.
        etoro_id_to_close = pos.etoro_position_id
        try:
            live_positions = live_client.get_positions()
            from src.utils.symbol_normalizer import normalize_symbol as _norm
            _sym = _norm(pos.symbol)
            live_ids = {str(p.etoro_position_id) for p in live_positions
                        if _norm(p.symbol) == _sym}
            if live_ids and str(pos.etoro_position_id) not in live_ids:
                etoro_id_to_close = next(iter(live_ids))
                logger.info(
                    f"Live close: DB etoro_position_id {pos.etoro_position_id} stale "
                    f"for {pos.symbol} — using fresh ID {etoro_id_to_close}"
                )
                pos.etoro_position_id = etoro_id_to_close
        except Exception as _refresh_err:
            logger.warning(f"Could not refresh etoro_position_id for {pos.symbol}: {_refresh_err}")

        live_client.close_position(etoro_id_to_close, instrument_id=instrument_id)

        pos.pending_closure = True
        pos.closure_reason = f"Manual close by {username}"
        db.commit()
        logger.info(f"User {username} closed live position {position_id} ({pos.symbol})")
        return {"success": True, "message": f"Close order submitted for {pos.symbol}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to close live position {position_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
