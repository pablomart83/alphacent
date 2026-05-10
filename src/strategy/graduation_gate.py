"""
Graduation Gate — backend logic for promoting (template, symbol) pairs to live trading.

Qualification criteria (all must pass):
  - paper_trades >= 20
  - paper_sharpe >= 0.6 × wf_sharpe  (live performance tracks walk-forward)
  - paper_win_rate >= 0.45
  - paper_pnl > 0
  - Not already active in live_strategies
  - Not rejected in the last 14 days

Approval flow:
  1. CIO reviews the queue via GET /strategies/graduation-queue
  2. CIO approves via POST /strategies/{id}/graduate with optional overrides
  3. A live_strategies row is created — the HARD GATE is now open for that pair
  4. TradingScheduler checks live_strategies before every live fill (Sprint 5)

Rejection flow:
  - POST /strategies/{id}/reject-graduation records rejected_at
  - 14-day cooldown before the pair can re-appear in the queue
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── Qualification thresholds ──────────────────────────────────────────────────

MIN_PAPER_TRADES = 20
MIN_QUALIFICATION_RATIO = 0.60   # paper_sharpe / wf_sharpe
MIN_PAPER_WIN_RATE = 0.45
MIN_PAPER_PNL = 0.0              # must be profitable
REJECTION_COOLDOWN_DAYS = 14


def get_paper_stats_for_strategy(
    session: Session,
    strategy_id: str,
    symbol: str,
) -> Dict[str, Any]:
    """
    Compute paper trading stats for a (strategy_id, symbol) pair from trade_journal.

    Returns dict with: paper_trades, paper_sharpe, paper_win_rate, paper_total_pnl
    """
    from sqlalchemy import text

    row = session.execute(
        text("""
            SELECT
                COUNT(*)                                                AS trades,
                ROUND(
                    CASE WHEN STDDEV(pnl) > 0
                         THEN (AVG(pnl) / STDDEV(pnl)) * SQRT(252)
                         ELSE 0
                    END::numeric, 4
                )                                                       AS sharpe,
                ROUND(
                    100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0)::numeric, 2
                )                                                       AS win_rate_pct,
                ROUND(COALESCE(SUM(pnl), 0)::numeric, 2)               AS total_pnl
            FROM trade_journal
            WHERE strategy_id = :sid
              AND symbol       = :sym
              AND pnl IS NOT NULL
              AND account_type = 'demo'
        """),
        {"sid": strategy_id, "sym": symbol},
    ).fetchone()

    if not row or not row.trades:
        return {
            "paper_trades": 0,
            "paper_sharpe": None,
            "paper_win_rate": None,
            "paper_total_pnl": None,
        }

    return {
        "paper_trades": int(row.trades),
        "paper_sharpe": float(row.sharpe) if row.sharpe is not None else None,
        "paper_win_rate": float(row.win_rate_pct) / 100.0 if row.win_rate_pct is not None else None,
        "paper_total_pnl": float(row.total_pnl) if row.total_pnl is not None else None,
    }


def is_qualified(
    paper_stats: Dict[str, Any],
    wf_sharpe: Optional[float],
) -> tuple[bool, List[str]]:
    """
    Check whether a (strategy, symbol) pair meets graduation criteria.

    Returns (qualified: bool, reasons: list[str])
    reasons is empty when qualified, contains failure reasons when not.
    """
    reasons = []

    trades = paper_stats.get("paper_trades", 0) or 0
    sharpe = paper_stats.get("paper_sharpe")
    win_rate = paper_stats.get("paper_win_rate")
    pnl = paper_stats.get("paper_total_pnl")

    if trades < MIN_PAPER_TRADES:
        reasons.append(f"paper_trades={trades} < {MIN_PAPER_TRADES}")

    if pnl is None or pnl <= MIN_PAPER_PNL:
        reasons.append(f"paper_pnl={pnl} not > 0")

    if win_rate is None or win_rate < MIN_PAPER_WIN_RATE:
        reasons.append(f"paper_win_rate={win_rate} < {MIN_PAPER_WIN_RATE}")

    if wf_sharpe and wf_sharpe > 0 and sharpe is not None:
        ratio = sharpe / wf_sharpe
        if ratio < MIN_QUALIFICATION_RATIO:
            reasons.append(
                f"qualification_ratio={ratio:.2f} < {MIN_QUALIFICATION_RATIO} "
                f"(paper_sharpe={sharpe:.2f}, wf_sharpe={wf_sharpe:.2f})"
            )
    elif sharpe is None:
        reasons.append("paper_sharpe not computable (no trades with variance)")

    return len(reasons) == 0, reasons


def get_graduation_queue(session: Session) -> List[Dict[str, Any]]:
    """
    Return all (strategy, symbol) pairs that qualify for live trading.

    Excludes:
    - Pairs already active in live_strategies
    - Pairs rejected in the last 14 days
    """
    from src.models.orm import StrategyORM, GraduationApprovalORM, LiveStrategyORM
    from sqlalchemy import text

    # Active live pairs — exclude these
    active_live = set(
        (row.strategy_id, row.symbol)
        for row in session.query(LiveStrategyORM)
        .filter(LiveStrategyORM.retired_at.is_(None))
        .all()
    )

    # Recently rejected pairs — exclude these
    cooldown_cutoff = datetime.now() - timedelta(days=REJECTION_COOLDOWN_DAYS)
    recently_rejected = set(
        (row.strategy_id, row.symbol)
        for row in session.query(GraduationApprovalORM)
        .filter(
            GraduationApprovalORM.rejected_at.isnot(None),
            GraduationApprovalORM.rejected_at >= cooldown_cutoff,
        )
        .all()
    )

    # PAPER strategies with at least MIN_PAPER_TRADES in trade_journal
    candidates_raw = session.execute(
        text("""
            SELECT
                s.id            AS strategy_id,
                s.name          AS strategy_name,
                tj.symbol,
                COUNT(*)        AS trades,
                ROUND(
                    CASE WHEN STDDEV(tj.pnl) > 0
                         THEN (AVG(tj.pnl) / STDDEV(tj.pnl)) * SQRT(252)
                         ELSE 0
                    END::numeric, 4
                )               AS paper_sharpe,
                ROUND(
                    100.0 * SUM(CASE WHEN tj.pnl > 0 THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0)::numeric, 2
                )               AS win_rate_pct,
                ROUND(COALESCE(SUM(tj.pnl), 0)::numeric, 2) AS total_pnl
            FROM trade_journal tj
            JOIN strategies s ON s.id = tj.strategy_id
            WHERE s.status = 'PAPER'
              AND tj.pnl IS NOT NULL
              AND tj.account_type = 'demo'
            GROUP BY s.id, s.name, tj.symbol
            HAVING COUNT(*) >= :min_trades
        """),
        {"min_trades": MIN_PAPER_TRADES},
    ).fetchall()

    queue = []
    for row in candidates_raw:
        pair = (row.strategy_id, row.symbol)
        if pair in active_live or pair in recently_rejected:
            continue

        paper_stats = {
            "paper_trades": int(row.trades),
            "paper_sharpe": float(row.paper_sharpe) if row.paper_sharpe is not None else None,
            "paper_win_rate": float(row.win_rate_pct) / 100.0 if row.win_rate_pct is not None else None,
            "paper_total_pnl": float(row.total_pnl) if row.total_pnl is not None else None,
        }

        # Get WF sharpe from strategy metadata
        strategy = session.query(StrategyORM).filter_by(id=row.strategy_id).first()
        wf_sharpe = None
        template_name = None
        if strategy:
            meta = strategy.strategy_metadata or {}
            wf_sharpe = (
                meta.get("wf_sharpe")
                or meta.get("walk_forward_sharpe")
                or (strategy.backtest_results or {}).get("walk_forward_results", {}).get("test_sharpe")
            )
            template_name = meta.get("template_name") or strategy.name

        qualified, fail_reasons = is_qualified(paper_stats, wf_sharpe)
        if not qualified:
            continue

        ratio = None
        if wf_sharpe and wf_sharpe > 0 and paper_stats["paper_sharpe"] is not None:
            ratio = round(paper_stats["paper_sharpe"] / wf_sharpe, 3)

        queue.append({
            "strategy_id": row.strategy_id,
            "strategy_name": row.strategy_name,
            "template_name": template_name,
            "symbol": row.symbol,
            "paper_trades": paper_stats["paper_trades"],
            "paper_sharpe": paper_stats["paper_sharpe"],
            "paper_win_rate": paper_stats["paper_win_rate"],
            "paper_total_pnl": paper_stats["paper_total_pnl"],
            "wf_sharpe": wf_sharpe,
            "qualification_ratio": ratio,
        })

    # Sort by qualification_ratio desc (best candidates first)
    queue.sort(key=lambda x: x.get("qualification_ratio") or 0, reverse=True)
    return queue


def approve_graduation(
    session: Session,
    strategy_id: str,
    symbol: str,
    position_size: float,
    sl_pct: float,
    tp_pct: float,
    conviction_min: int,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Approve a (strategy, symbol) pair for live trading.

    Creates a graduation_approvals row (approved) and a live_strategies row.
    Returns the created live_strategies record as a dict.
    """
    from src.models.orm import StrategyORM, GraduationApprovalORM, LiveStrategyORM

    strategy = session.query(StrategyORM).filter_by(id=strategy_id).first()
    if not strategy:
        raise ValueError(f"Strategy {strategy_id} not found")

    meta = strategy.strategy_metadata or {}
    template_name = meta.get("template_name") or strategy.name
    wf_sharpe = (
        meta.get("wf_sharpe")
        or meta.get("walk_forward_sharpe")
        or (strategy.backtest_results or {}).get("walk_forward_results", {}).get("test_sharpe")
    )

    paper_stats = get_paper_stats_for_strategy(session, strategy_id, symbol)
    ratio = None
    if wf_sharpe and wf_sharpe > 0 and paper_stats["paper_sharpe"] is not None:
        ratio = round(paper_stats["paper_sharpe"] / wf_sharpe, 3)

    # Check not already active
    existing = (
        session.query(LiveStrategyORM)
        .filter_by(strategy_id=strategy_id, symbol=symbol)
        .filter(LiveStrategyORM.retired_at.is_(None))
        .first()
    )
    if existing:
        raise ValueError(f"({strategy_id}, {symbol}) is already active in live_strategies")

    now = datetime.now()

    # Record approval
    approval = GraduationApprovalORM(
        strategy_id=strategy_id,
        symbol=symbol,
        template_name=template_name,
        approved_at=now,
        notes=notes,
        position_size_override=position_size,
        sl_pct_override=sl_pct,
        tp_pct_override=tp_pct,
        conviction_min_override=conviction_min,
        paper_trades=paper_stats.get("paper_trades"),
        paper_sharpe=paper_stats.get("paper_sharpe"),
        paper_win_rate=paper_stats.get("paper_win_rate"),
        paper_total_pnl=paper_stats.get("paper_total_pnl"),
        wf_sharpe=wf_sharpe,
        qualification_ratio=ratio,
        created_at=now,
    )
    session.add(approval)
    session.flush()  # get approval.id

    # Create live authorization
    live_row = LiveStrategyORM(
        graduation_id=approval.id,
        strategy_id=strategy_id,
        template_name=template_name,
        symbol=symbol,
        activated_at=now,
        position_size=position_size,
        sl_pct=sl_pct,
        tp_pct=tp_pct,
        conviction_min=conviction_min,
    )
    session.add(live_row)
    session.commit()

    logger.info(
        f"GRADUATION APPROVED: ({template_name}, {symbol}) → live_strategies id={live_row.id} "
        f"size=${position_size} sl={sl_pct*100:.1f}% tp={tp_pct*100:.1f}% "
        f"conviction_min={conviction_min}"
    )
    return live_row.to_dict()


def reject_graduation(
    session: Session,
    strategy_id: str,
    symbol: str,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Reject a (strategy, symbol) pair with a 14-day cooldown.
    """
    from src.models.orm import StrategyORM, GraduationApprovalORM

    strategy = session.query(StrategyORM).filter_by(id=strategy_id).first()
    template_name = (strategy.strategy_metadata or {}).get("template_name") or (strategy.name if strategy else strategy_id)

    now = datetime.now()
    rejection = GraduationApprovalORM(
        strategy_id=strategy_id,
        symbol=symbol,
        template_name=template_name,
        rejected_at=now,
        notes=notes,
        created_at=now,
    )
    session.add(rejection)
    session.commit()

    logger.info(f"GRADUATION REJECTED: ({template_name}, {symbol}) — cooldown until {(now + timedelta(days=REJECTION_COOLDOWN_DAYS)).date()}")
    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "rejected_at": now.isoformat(),
        "cooldown_until": (now + timedelta(days=REJECTION_COOLDOWN_DAYS)).isoformat(),
        "notes": notes,
    }


def get_live_strategies(session: Session) -> List[Dict[str, Any]]:
    """Return all active live_strategies rows with paper stats for comparison."""
    from src.models.orm import LiveStrategyORM

    rows = (
        session.query(LiveStrategyORM)
        .filter(LiveStrategyORM.retired_at.is_(None))
        .order_by(LiveStrategyORM.activated_at.desc())
        .all()
    )

    result = []
    for row in rows:
        d = row.to_dict()
        # Attach current paper stats for divergence monitoring
        paper = get_paper_stats_for_strategy(session, row.strategy_id, row.symbol)
        d["current_paper_sharpe"] = paper.get("paper_sharpe")
        d["current_paper_win_rate"] = paper.get("paper_win_rate")
        d["current_paper_pnl"] = paper.get("paper_total_pnl")
        # Divergence: live_sharpe vs paper_sharpe
        if row.live_sharpe and paper.get("paper_sharpe") and paper["paper_sharpe"] > 0:
            d["divergence_pct"] = round(row.live_sharpe / paper["paper_sharpe"] * 100, 1)
        else:
            d["divergence_pct"] = None
        result.append(d)

    return result


def get_live_approval(
    session: Session,
    strategy_id: str,
    symbol: str,
) -> Optional[Any]:
    """
    Return the active LiveStrategyORM row for (strategy_id, symbol), or None.

    Used by TradingScheduler to check whether a live fill is authorized.
    """
    from src.models.orm import LiveStrategyORM

    return (
        session.query(LiveStrategyORM)
        .filter_by(strategy_id=strategy_id, symbol=symbol)
        .filter(LiveStrategyORM.retired_at.is_(None))
        .first()
    )
