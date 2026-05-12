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
MAX_QUALIFICATION_RATIO = 2.0    # paper_sharpe must not exceed 2× wf_sharpe
                                  # A ratio > 2 means the paper period was regime-lucky,
                                  # not a genuine edge confirmation. Graduating a strategy
                                  # with paper_sharpe 3× its WF sharpe is graduating the
                                  # regime, not the strategy.
MIN_PAPER_WIN_RATE = 0.55        # raised from 0.45 — 45% is too permissive for real money
MIN_PAPER_PNL = 0.0              # must be profitable
REJECTION_COOLDOWN_DAYS = 14

# Override constants from YAML if graduation_gate section exists.
# This means Settings page changes take effect immediately (the PUT endpoint
# also patches the in-memory constants directly, but this covers the startup
# case where the YAML was already updated before the process started).
try:
    import yaml as _yaml
    from pathlib import Path as _Path
    _cfg_path = _Path("config/autonomous_trading.yaml")
    if _cfg_path.exists():
        with open(_cfg_path, "r") as _f:
            _cfg = _yaml.safe_load(_f) or {}
        _gg = _cfg.get("graduation_gate", {}) or {}
        if "min_trades" in _gg:
            MIN_PAPER_TRADES = int(_gg["min_trades"])
        if "min_win_rate_pct" in _gg:
            MIN_PAPER_WIN_RATE = float(_gg["min_win_rate_pct"]) / 100.0
        if "min_qualification_ratio" in _gg:
            MIN_QUALIFICATION_RATIO = float(_gg["min_qualification_ratio"])
        if "max_qualification_ratio_cap" in _gg:
            MAX_QUALIFICATION_RATIO = float(_gg["max_qualification_ratio_cap"])
        if "rejection_cooldown_days" in _gg:
            REJECTION_COOLDOWN_DAYS = int(_gg["rejection_cooldown_days"])
except Exception:
    pass  # Fall back to hardcoded defaults — never crash at import time


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


def get_aggregated_paper_stats(
    session: Session,
    template_name: str,
    symbol: str,
) -> Dict[str, Any]:
    """
    Compute paper trading stats aggregated across ALL strategy versions for a
    (template_name, symbol) pair — the same cross-version view used by the
    graduation queue.  This is the correct denominator for the approval record
    because the queue qualifies pairs on aggregate history, not single-version.
    """
    from sqlalchemy import text

    row = session.execute(
        text("""
            SELECT
                COUNT(*)                                                AS trades,
                ROUND(
                    CASE WHEN STDDEV(tj.pnl) > 0
                         THEN (AVG(tj.pnl) / STDDEV(tj.pnl)) * SQRT(252)
                         ELSE 0
                    END::numeric, 4
                )                                                       AS sharpe,
                ROUND(
                    100.0 * SUM(CASE WHEN tj.pnl > 0 THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0)::numeric, 2
                )                                                       AS win_rate_pct,
                ROUND(COALESCE(SUM(tj.pnl), 0)::numeric, 2)            AS total_pnl
            FROM trade_journal tj
            JOIN strategies s ON s.id = tj.strategy_id
            WHERE tj.pnl IS NOT NULL
              AND tj.account_type = 'demo'
              AND tj.symbol = :sym
              AND COALESCE(
                    s.strategy_metadata->>'template_name',
                    REGEXP_REPLACE(s.name, ' V[0-9]+$', '')
                  ) = :tname
        """),
        {"tname": template_name, "sym": symbol},
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
        elif ratio > MAX_QUALIFICATION_RATIO:
            reasons.append(
                f"qualification_ratio={ratio:.2f} > {MAX_QUALIFICATION_RATIO} "
                f"(paper_sharpe={sharpe:.2f} is {ratio:.1f}× wf_sharpe={wf_sharpe:.2f} "
                f"— paper period was regime-lucky, not a genuine edge confirmation)"
            )
    elif sharpe is None:
        reasons.append("paper_sharpe not computable (no trades with variance)")

    return len(reasons) == 0, reasons


def get_graduation_queue(session: Session) -> List[Dict[str, Any]]:
    """
    Return all (template_name, symbol) pairs that qualify for live trading.

    Groups by (template_name, symbol) across ALL strategy IDs — not just the
    currently-PAPER strategy. When a strategy retires and the same
    (template, symbol) pair is re-proposed, the new strategy_id gets a fresh
    UUID but the historical trade_journal rows from previous activations still
    count toward the graduation threshold. Grouping by strategy_id would reset
    the counter on every re-activation.

    Excludes:
    - Pairs already active in live_strategies (matched by template_name + symbol)
    - Pairs rejected in the last 14 days (matched by template_name + symbol)
    """
    from src.models.orm import StrategyORM, GraduationApprovalORM, LiveStrategyORM
    from sqlalchemy import text

    # Active live pairs — exclude by (template_name, symbol)
    active_live = set(
        (row.template_name, row.symbol)
        for row in session.query(LiveStrategyORM)
        .filter(LiveStrategyORM.retired_at.is_(None))
        .all()
    )

    # Recently rejected pairs — exclude by (template_name, symbol)
    cooldown_cutoff = datetime.now() - timedelta(days=REJECTION_COOLDOWN_DAYS)
    recently_rejected = set(
        (row.template_name, row.symbol)
        for row in session.query(GraduationApprovalORM)
        .filter(
            GraduationApprovalORM.rejected_at.isnot(None),
            GraduationApprovalORM.rejected_at >= cooldown_cutoff,
        )
        .all()
    )

    # Aggregate trade_journal by (template_name, symbol) across ALL strategy IDs.
    # COALESCE: prefer strategy_metadata->>'template_name', fall back to name
    # with version suffix stripped.
    #
    # The representative_strategy_id (most recent strategy for this pair) is
    # resolved in a separate CTE rather than a correlated subquery — PostgreSQL
    # cannot reference outer-query columns (s.strategy_metadata) inside a
    # correlated subquery when the outer query uses GROUP BY.
    candidates_raw = session.execute(
        text("""
            WITH pair_stats AS (
                SELECT
                    COALESCE(
                        s.strategy_metadata->>'template_name',
                        REGEXP_REPLACE(s.name, ' V[0-9]+$', '')
                    )                                                   AS template_name,
                    tj.symbol,
                    COUNT(*)                                            AS trades,
                    ROUND(
                        CASE WHEN STDDEV(tj.pnl) > 0
                             THEN (AVG(tj.pnl) / STDDEV(tj.pnl)) * SQRT(252)
                             ELSE 0
                        END::numeric, 4
                    )                                                   AS paper_sharpe,
                    ROUND(
                        100.0 * SUM(CASE WHEN tj.pnl > 0 THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0)::numeric, 2
                    )                                                   AS win_rate_pct,
                    ROUND(COALESCE(SUM(tj.pnl), 0)::numeric, 2)        AS total_pnl,
                    COUNT(DISTINCT tj.strategy_id)                      AS strategy_versions
                FROM trade_journal tj
                JOIN strategies s ON s.id = tj.strategy_id
                WHERE tj.pnl IS NOT NULL
                  AND tj.account_type = 'demo'
                GROUP BY template_name, tj.symbol
                HAVING COUNT(*) >= :min_trades
            ),
            latest_strategy AS (
                -- For each (template_name, symbol) pair, find the most recently
                -- created strategy_id. Used as the representative ID for the
                -- approval flow (needs a valid strategy_id to reference).
                SELECT DISTINCT ON (
                    COALESCE(s.strategy_metadata->>'template_name', REGEXP_REPLACE(s.name, ' V[0-9]+$', '')),
                    tj.symbol
                )
                    COALESCE(
                        s.strategy_metadata->>'template_name',
                        REGEXP_REPLACE(s.name, ' V[0-9]+$', '')
                    )                                                   AS template_name,
                    tj.symbol,
                    s.id                                                AS strategy_id,
                    s.name                                              AS strategy_name
                FROM trade_journal tj
                JOIN strategies s ON s.id = tj.strategy_id
                WHERE tj.pnl IS NOT NULL
                  AND tj.account_type = 'demo'
                ORDER BY
                    COALESCE(s.strategy_metadata->>'template_name', REGEXP_REPLACE(s.name, ' V[0-9]+$', '')),
                    tj.symbol,
                    s.created_at DESC
            )
            SELECT
                ps.template_name,
                ps.symbol,
                ls.strategy_id  AS representative_strategy_id,
                ls.strategy_name,
                ps.trades,
                ps.paper_sharpe,
                ps.win_rate_pct,
                ps.total_pnl,
                ps.strategy_versions
            FROM pair_stats ps
            JOIN latest_strategy ls
              ON ls.template_name = ps.template_name
             AND ls.symbol        = ps.symbol
        """),
        {"min_trades": MIN_PAPER_TRADES},
    ).fetchall()

    queue = []
    for row in candidates_raw:
        pair = (row.template_name, row.symbol)
        if pair in active_live or pair in recently_rejected:
            continue

        paper_stats = {
            "paper_trades": int(row.trades),
            "paper_sharpe": float(row.paper_sharpe) if row.paper_sharpe is not None else None,
            "paper_win_rate": float(row.win_rate_pct) / 100.0 if row.win_rate_pct is not None else None,
            "paper_total_pnl": float(row.total_pnl) if row.total_pnl is not None else None,
        }

        # Get WF sharpe from the most recent strategy version for this template.
        # Use the representative_strategy_id from the subquery.
        representative_id = row.representative_strategy_id
        wf_sharpe = None
        strategy_name = row.template_name
        if representative_id:
            strategy = session.query(StrategyORM).filter_by(id=representative_id).first()
            if strategy:
                meta = strategy.strategy_metadata or {}
                wf_sharpe = (
                    meta.get("wf_test_sharpe")
                    or meta.get("wf_sharpe")
                    or meta.get("walk_forward_sharpe")
                    or (strategy.backtest_results or {}).get("walk_forward_results", {}).get("test_sharpe")
                )

        qualified, fail_reasons = is_qualified(paper_stats, wf_sharpe)
        if not qualified:
            continue

        ratio = None
        if wf_sharpe and wf_sharpe > 0 and paper_stats["paper_sharpe"] is not None:
            ratio = round(paper_stats["paper_sharpe"] / wf_sharpe, 3)

        queue.append({
            "strategy_id": representative_id,  # most recent strategy_id for this pair
            "strategy_name": strategy_name,
            "template_name": row.template_name,
            "symbol": row.symbol,
            "paper_trades": paper_stats["paper_trades"],
            "paper_sharpe": paper_stats["paper_sharpe"],
            "paper_win_rate": paper_stats["paper_win_rate"],
            "paper_total_pnl": paper_stats["paper_total_pnl"],
            "wf_sharpe": wf_sharpe,
            "qualification_ratio": ratio,
            "strategy_versions": int(row.strategy_versions),
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

    Creates:
      1. A new StrategyORM row with status=LIVE, symbols=[symbol] — the live
         strategy is a separate entity from the source PAPER/BACKTESTED strategy.
         The source strategy is NOT mutated and continues generating DEMO trades.
      2. A graduation_approvals row recording the approval snapshot.
      3. A live_strategies row pointing at the new LIVE strategy_id.

    The new LIVE strategy carries over the template rules, risk params, and WF
    metadata from the source strategy, plus a `parent_strategy_id` reference so
    the full lineage is traceable.

    Returns the created live_strategies record as a dict.
    """
    import uuid
    import json
    from src.models.orm import StrategyORM, GraduationApprovalORM, LiveStrategyORM
    from src.models.enums import StrategyStatus

    source = session.query(StrategyORM).filter_by(id=strategy_id).first()
    if not source:
        raise ValueError(f"Strategy {strategy_id} not found")

    meta = source.strategy_metadata or {}
    template_name = meta.get("template_name") or source.name
    wf_sharpe = (
        meta.get("wf_test_sharpe")
        or meta.get("wf_sharpe")
        or meta.get("walk_forward_sharpe")
        or (source.backtest_results or {}).get("walk_forward_results", {}).get("test_sharpe")
    )

    # Aggregated cross-version paper stats for the approval snapshot.
    paper_stats = get_aggregated_paper_stats(session, template_name, symbol)
    if not paper_stats.get("paper_trades"):
        paper_stats = get_paper_stats_for_strategy(session, strategy_id, symbol)
    ratio = None
    if wf_sharpe and wf_sharpe > 0 and paper_stats["paper_sharpe"] is not None:
        ratio = round(paper_stats["paper_sharpe"] / wf_sharpe, 3)

    # Check not already active — scope to template+symbol, not strategy_id,
    # so re-graduation after retirement is caught correctly.
    existing = (
        session.query(LiveStrategyORM)
        .filter_by(template_name=template_name, symbol=symbol)
        .filter(LiveStrategyORM.retired_at.is_(None))
        .first()
    )
    if existing:
        raise ValueError(f"({template_name}, {symbol}) is already active in live_strategies")

    now = datetime.now()

    # ── 1. Create the LIVE strategy row ──────────────────────────────────────
    # Inherits rules and risk params from the source strategy.
    # symbols is scoped to the single approved symbol — a live strategy trades
    # exactly one symbol, not the full paper watchlist.
    live_meta = dict(meta)  # copy source metadata
    live_meta["parent_strategy_id"] = strategy_id   # lineage reference
    live_meta["graduated_from"] = source.name
    live_meta["graduated_at"] = now.isoformat()
    live_meta["activation_approved"] = True
    # Override risk params with CIO-approved values
    live_meta["live_position_size"] = position_size
    live_meta["live_sl_pct"] = sl_pct
    live_meta["live_tp_pct"] = tp_pct
    live_meta["live_conviction_min"] = conviction_min

    # Build risk_params for the live strategy using CIO-approved SL/TP
    live_risk_params = dict(source.risk_params or {})
    live_risk_params["stop_loss_pct"] = sl_pct
    live_risk_params["take_profit_pct"] = tp_pct

    live_strategy_id = str(uuid.uuid4())
    live_strategy = StrategyORM(
        id=live_strategy_id,
        name=f"{template_name} {symbol} LIVE",
        description=f"Live strategy — graduated from {source.name} on {now.date()}",
        status=StrategyStatus.LIVE,
        rules=source.rules,
        symbols=json.dumps([symbol]) if isinstance(source.symbols, str) else [symbol],
        allocation_percent=source.allocation_percent or 0.0,
        risk_params=live_risk_params,
        created_at=now,
        activated_at=now,
        performance={"total_return": 0.0, "sharpe_ratio": 0.0, "sortino_ratio": 0.0,
                     "max_drawdown": 0.0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                     "total_trades": 0},
        reasoning=source.reasoning,
        backtest_results=source.backtest_results,
        strategy_metadata=live_meta,
    )
    session.add(live_strategy)

    # ── 2. Record approval snapshot ──────────────────────────────────────────
    approval = GraduationApprovalORM(
        strategy_id=live_strategy_id,   # points at the new LIVE strategy
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

    # ── 3. Create live authorization row ─────────────────────────────────────
    live_row = LiveStrategyORM(
        graduation_id=approval.id,
        strategy_id=live_strategy_id,   # the new LIVE strategy, not the source
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
        f"GRADUATION APPROVED: ({template_name}, {symbol}) → "
        f"new LIVE strategy {live_strategy_id[:8]} | "
        f"source={strategy_id[:8]} (continues as PAPER/BACKTESTED) | "
        f"live_strategies id={live_row.id} "
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
    from src.models.orm import LiveStrategyORM, StrategyORM

    rows = (
        session.query(LiveStrategyORM)
        .filter(LiveStrategyORM.retired_at.is_(None))
        .order_by(LiveStrategyORM.activated_at.desc())
        .all()
    )

    result = []
    for row in rows:
        d = row.to_dict()
        # Use cross-version aggregated stats (same as graduation queue) so the
        # paper Sharpe reflects the full (template, symbol) history, not just
        # the single strategy_id that happens to be the representative version.
        paper = get_aggregated_paper_stats(session, row.template_name, row.symbol)
        if not paper.get("paper_trades"):
            # Fallback: single-strategy stats if aggregation returns nothing
            paper = get_paper_stats_for_strategy(session, row.strategy_id, row.symbol)
        d["current_paper_sharpe"] = paper.get("paper_sharpe")
        d["current_paper_win_rate"] = paper.get("paper_win_rate")
        d["current_paper_pnl"] = paper.get("paper_total_pnl")
        d["current_paper_trades"] = paper.get("paper_trades")
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


def get_all_live_approvals(session: Session) -> list:
    """
    Return all active LiveStrategyORM rows (retired_at IS NULL).

    Used by TradingScheduler's live-independent signal pass to iterate over
    every authorized (strategy, symbol) pair and fire live entries independently
    of the DEMO signal path.
    """
    from src.models.orm import LiveStrategyORM

    return (
        session.query(LiveStrategyORM)
        .filter(LiveStrategyORM.retired_at.is_(None))
        .all()
    )
