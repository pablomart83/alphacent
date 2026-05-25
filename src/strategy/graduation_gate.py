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


def _get_min_trades_for_interval(interval: Optional[str], paper_sharpe: Optional[float] = None, win_rate: Optional[float] = None) -> int:
    """
    Return interval-aware min_trades for graduation.

    Reads paper_trading.graduation_gate.min_trades_{interval} from YAML.
    Falls back to graduation_gate.min_trades (MIN_PAPER_TRADES) if not set.

    Rationale:
      1D strategies fire ~1 trade/month → 10 trades ≈ 10 months of data
      4H strategies fire ~2 trades/month → 15 trades ≈ 7 months of data
      1H strategies fire ~5 trades/month → 25 trades ≈ 5 months of data

    High-conviction exception (mirrors activation gate):
      If paper_sharpe ≥ 2.0 AND win_rate ≥ 0.70, reduce min_trades by 40%.
      A strategy with Sharpe 8.96 and 92% win rate across 13 trades is a
      stronger signal than a strategy with Sharpe 1.2 and 55% win rate across
      15 trades. The exception prevents the threshold from blocking obvious
      graduation candidates.
    """
    try:
        import yaml as _y
        from pathlib import Path as _P
        _p = _P("config/autonomous_trading.yaml")
        if _p.exists():
            with open(_p, "r") as _f:
                _c = _y.safe_load(_f) or {}
            pt_gg = _c.get("paper_trading", {}).get("graduation_gate", {})
            iv = (interval or "1d").lower()
            if iv in ("1h", "2h"):
                base = int(pt_gg.get("min_trades_1h", MIN_PAPER_TRADES))
            elif iv == "4h":
                base = int(pt_gg.get("min_trades_4h", MIN_PAPER_TRADES))
            else:
                base = int(pt_gg.get("min_trades_1d", MIN_PAPER_TRADES))

            # High-conviction exception: strong Sharpe + high win rate → lower bar
            if paper_sharpe is not None and win_rate is not None:
                if paper_sharpe >= 2.0 and win_rate >= 0.70:
                    reduced = max(5, int(base * 0.60))  # 40% reduction, floor at 5
                    return reduced

            return base
    except Exception:
        pass
    return MIN_PAPER_TRADES


def _get_min_sql_having_trades() -> int:
    """
    Return the minimum trades threshold for the graduation SQL HAVING clause.

    G-31: The SQL HAVING must use the LOWEST per-interval threshold so that
    1d strategies with fewer trades than MIN_PAPER_TRADES still appear in the
    query result. The per-interval bar is then enforced by is_qualified().

    Without this, a 1d strategy with 10 trades (which passes min_trades_1d=8)
    is filtered out by HAVING COUNT(*) >= 15 and never reaches is_qualified.
    """
    try:
        import yaml as _y
        from pathlib import Path as _P
        _p = _P("config/autonomous_trading.yaml")
        if _p.exists():
            with open(_p, "r") as _f:
                _c = _y.safe_load(_f) or {}
            pt_gg = _c.get("paper_trading", {}).get("graduation_gate", {})
            candidates = [
                int(pt_gg.get("min_trades_1d", MIN_PAPER_TRADES)),
                int(pt_gg.get("min_trades_4h", MIN_PAPER_TRADES)),
                int(pt_gg.get("min_trades_1h", MIN_PAPER_TRADES)),
            ]
            return min(candidates)
    except Exception:
        pass
    return MIN_PAPER_TRADES


def _get_min_avg_pnl_per_trade() -> float:
    """Return min avg P&L per trade from paper_trading.graduation_gate.min_avg_pnl_per_trade."""
    try:
        import yaml as _y
        from pathlib import Path as _P
        _p = _P("config/autonomous_trading.yaml")
        if _p.exists():
            with open(_p, "r") as _f:
                _c = _y.safe_load(_f) or {}
            return float(_c.get("paper_trading", {}).get("graduation_gate", {}).get("min_avg_pnl_per_trade", 0.0))
    except Exception:
        return 0.0


def _get_regime_adjusted_max_ratio() -> float:
    """
    Return the regime-adjusted qualification ratio cap.

    Fix 1 (2026-05-18): A flat 2.0× cap blocks everything during a bull run
    because paper Sharpe is inflated for all LONG strategies simultaneously.
    The cap should be calibrated to what's actually surprising given the regime.

    Regime → cap:
      trending_up_strong:  3.5× (strong bull — outperformance vs WF is expected)
      trending_up / weak:  3.0×
      ranging / neutral:   2.0× (WF test period is a fair comparison)
      trending_down:       1.5× (bear — outperformance vs WF is suspicious)
      high_vol:            1.5× (volatile — same)
      unknown / fallback:  2.0×

    Result is cached for 10 minutes to avoid hitting the market data manager
    on every graduation candidate evaluation.
    """
    import time as _time
    _now = _time.time()
    _cache = getattr(_get_regime_adjusted_max_ratio, '_cache', None)
    if _cache and (_now - _cache[0]) < 600:  # 10-minute TTL
        return _cache[1]

    result = MAX_QUALIFICATION_RATIO  # fallback
    try:
        from src.data.market_data_manager import get_market_data_manager
        from src.strategy.market_analyzer import MarketStatisticsAnalyzer
        _mdm = get_market_data_manager()
        if _mdm:
            _msa = MarketStatisticsAnalyzer(_mdm)
            _regime, _, _, _ = _msa.detect_sub_regime()
            _regime_name = _regime.value.lower() if _regime else ""
            if "trending_up_strong" in _regime_name:
                result = 3.5
            elif "trending_up" in _regime_name:
                result = 3.0
            elif "trending_down" in _regime_name or "high_vol" in _regime_name:
                result = 1.5
            else:
                result = 2.0
    except Exception:
        pass

    _get_regime_adjusted_max_ratio._cache = (_now, result)
    return result


def _get_strategy_type_win_rate_floor(strategy_type: Optional[str]) -> float:
    """
    Return the win rate floor appropriate for the strategy type.

    Fix 2 (2026-05-18): A flat 55% win rate floor is wrong for trend-following
    strategies, which make money on large winners with many small losses.
    The P&L and qualification ratio are the right gates for trend-following.
    Mean-reversion relies on high hit rate — 55% is appropriate there.

    strategy_type → floor:
      trend_following / momentum / breakout / ema_* / adx_* / atr_*: 45%
      mean_reversion / volatility / rsi_* / bb_* / stochastic:        55%
      everything else:                                                  50%
    """
    if not strategy_type:
        return MIN_PAPER_WIN_RATE

    st = strategy_type.lower()
    trend_types = {
        'trend_following', 'momentum', 'breakout', 'trend',
        'ema_crossover', 'macd_trend', 'adx_trend', 'vwap_trend',
        'ema_ribbon', 'atr_trend', 'sma_trend',
    }
    reversion_types = {
        'mean_reversion', 'volatility', 'rsi_dip', 'bb_midband',
        'stochastic', 'reversion', 'oscillator',
    }
    if any(t in st for t in trend_types):
        return 0.45
    if any(t in st for t in reversion_types):
        return 0.55
    return 0.50
    """Return min avg P&L per trade from paper_trading.graduation_gate.min_avg_pnl_per_trade."""
    try:
        import yaml as _y
        from pathlib import Path as _P
        _p = _P("config/autonomous_trading.yaml")
        if _p.exists():
            with open(_p, "r") as _f:
                _c = _y.safe_load(_f) or {}
            return float(_c.get("paper_trading", {}).get("graduation_gate", {}).get("min_avg_pnl_per_trade", 0.0))
    except Exception:
        return 0.0


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
    interval: Optional[str] = None,
    strategy_type: Optional[str] = None,
) -> tuple[bool, List[str]]:
    """
    Check whether a (strategy, symbol) pair meets graduation criteria.

    Returns (qualified: bool, reasons: list[str])
    reasons is empty when qualified, contains failure reasons when not.

    Args:
        paper_stats: Dict with paper_trades, paper_sharpe, paper_win_rate, paper_total_pnl
        wf_sharpe: Walk-forward Sharpe from the representative strategy
        interval: Strategy interval ('1d', '4h', '1h') for interval-aware min_trades
        strategy_type: Strategy type string for type-aware win rate floor (Fix 2)
    """
    reasons = []

    trades = paper_stats.get("paper_trades", 0) or 0
    sharpe = paper_stats.get("paper_sharpe")
    win_rate = paper_stats.get("paper_win_rate")
    pnl = paper_stats.get("paper_total_pnl")

    # Interval-aware min_trades — 1D strategies fire less often than 1H
    # High-conviction exception: strong Sharpe + high win rate → lower bar
    min_trades = _get_min_trades_for_interval(interval, paper_sharpe=sharpe, win_rate=win_rate)
    if trades < min_trades:
        reasons.append(f"paper_trades={trades} < {min_trades} (interval={interval or '1d'})")

    if pnl is None or pnl <= MIN_PAPER_PNL:
        reasons.append(f"paper_pnl={pnl} not > 0")

    # Avg P&L per trade gate — prevents graduating strategies with technically
    # positive total P&L but near-zero per-trade expectancy
    min_avg_pnl = _get_min_avg_pnl_per_trade()
    if trades > 0 and pnl is not None:
        avg_pnl_per_trade = pnl / trades
        if avg_pnl_per_trade <= min_avg_pnl:
            reasons.append(
                f"avg_pnl_per_trade=${avg_pnl_per_trade:.2f} not > ${min_avg_pnl:.2f}"
            )

    # Fix 2: strategy-type-aware win rate floor.
    # Trend-following strategies make money on large winners with many small
    # losses — a 45% win rate with positive P&L is fine. Mean-reversion relies
    # on high hit rate — 55% is appropriate. Flat 55% was blocking valid
    # trend-following strategies (e.g. GOOGL 4H EMA Ribbon at 44% WR, +$91 P&L).
    effective_win_rate_floor = _get_strategy_type_win_rate_floor(strategy_type)
    if win_rate is None or win_rate < effective_win_rate_floor:
        reasons.append(
            f"paper_win_rate={win_rate:.1%} < {effective_win_rate_floor:.0%} "
            f"(floor for {strategy_type or 'unknown'} strategy type)"
        )

    if wf_sharpe and wf_sharpe > 0 and sharpe is not None:
        ratio = sharpe / wf_sharpe
        # Fix 1: regime-adjusted max ratio cap.
        # A flat 2.0× cap blocks everything in a bull run because paper Sharpe
        # is inflated for all LONG strategies simultaneously. The cap scales
        # with the current regime — outperformance vs WF is expected in
        # trending_up_strong, suspicious in trending_down.
        effective_max_ratio = _get_regime_adjusted_max_ratio()
        if ratio < MIN_QUALIFICATION_RATIO:
            reasons.append(
                f"qualification_ratio={ratio:.2f} < {MIN_QUALIFICATION_RATIO} "
                f"(paper_sharpe={sharpe:.2f}, wf_sharpe={wf_sharpe:.2f})"
            )
        elif ratio > effective_max_ratio:
            reasons.append(
                f"qualification_ratio={ratio:.2f} > {effective_max_ratio:.1f} "
                f"(paper_sharpe={sharpe:.2f} is {ratio:.1f}× wf_sharpe={wf_sharpe:.2f} "
                f"— paper period was regime-lucky, not a genuine edge confirmation; "
                f"regime-adjusted cap={effective_max_ratio:.1f}×)"
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
                    ROUND(COALESCE(AVG(tj.pnl), 0)::numeric, 4)        AS avg_pnl,
                    COUNT(DISTINCT tj.strategy_id)                      AS strategy_versions,
                    MIN(tj.entry_time)                                  AS first_trade_at
                FROM trade_journal tj
                JOIN strategies s ON s.id = tj.strategy_id
                WHERE tj.pnl IS NOT NULL
                  AND tj.account_type = 'demo'
                GROUP BY template_name, tj.symbol
                HAVING COUNT(*) >= :min_trades
            ),
            latest_strategy AS (
                -- For each (template_name, symbol) pair, find the most recently
                -- created strategy_id whose WF was run on that specific symbol.
                -- This ensures the WF sharpe used for the qualification ratio
                -- was calibrated on the same symbol, not on a different primary
                -- symbol that happened to trade this one via its watchlist.
                --
                -- Priority: strategies where symbols[0] = this symbol (WF was
                -- run on this symbol directly) over watchlist strategies.
                -- Within each priority tier, most recently created wins.
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
                    s.name                                              AS strategy_name,
                    COALESCE(
                        s.strategy_metadata->>'interval',
                        s.rules->>'interval'
                    )                                                   AS strategy_interval,
                    COALESCE(
                        s.strategy_metadata->>'template_type',
                        s.strategy_metadata->>'strategy_type'
                    )                                                   AS strategy_type
                FROM trade_journal tj
                JOIN strategies s ON s.id = tj.strategy_id
                WHERE tj.pnl IS NOT NULL
                  AND tj.account_type = 'demo'
                ORDER BY
                    COALESCE(s.strategy_metadata->>'template_name', REGEXP_REPLACE(s.name, ' V[0-9]+$', '')),
                    tj.symbol,
                    -- Prefer strategies where this symbol appears first in the symbols
                    -- array (i.e. was the primary symbol for WF validation).
                    -- JSON array: symbols[0] = primary. We check if the symbol name
                    -- appears as the first element by looking for it at position 0.
                    CASE WHEN s.symbols::jsonb->0 = to_jsonb(tj.symbol::text)
                         THEN 0 ELSE 1 END ASC,
                    s.created_at DESC
            )
            SELECT
                ps.template_name,
                ps.symbol,
                ls.strategy_id  AS representative_strategy_id,
                ls.strategy_name,
                ls.strategy_interval,
                ls.strategy_type AS sql_strategy_type,
                ps.trades,
                ps.paper_sharpe,
                ps.win_rate_pct,
                ps.total_pnl,
                ps.avg_pnl,
                ps.strategy_versions,
                ps.first_trade_at
            FROM pair_stats ps
            JOIN latest_strategy ls
              ON ls.template_name = ps.template_name
             AND ls.symbol        = ps.symbol
        """),
        # G-31: use the minimum per-interval threshold so 1d strategies with
        # fewer trades than MIN_PAPER_TRADES still appear. is_qualified() applies
        # the correct per-interval bar after the SQL filter.
        {"min_trades": _get_min_sql_having_trades()},
    ).fetchall()

    queue = []

    # Best WF sharpe per template — kept as a secondary fallback from strategies table.
    # After watchlist elimination (2026-05-18), the representative strategy's WF sharpe
    # is always the correct one (WF was run on the primary symbol directly).
    # wf_by_template_symbol from wf_validated_combos.json is no longer needed.
    best_wf_by_template = {}
    try:
        _wf_rows = session.execute(
            text("""
                SELECT
                    COALESCE(
                        strategy_metadata->>'template_name',
                        REGEXP_REPLACE(name, ' V[0-9]+$', '')
                    )                                                   AS template_name,
                    MAX(
                        COALESCE(
                            (strategy_metadata->>'wf_test_sharpe')::float,
                            (strategy_metadata->>'wf_sharpe')::float,
                            (strategy_metadata->>'walk_forward_sharpe')::float,
                            0
                        )
                    )                                                   AS best_wf_sharpe
                FROM strategies
                WHERE strategy_metadata IS NOT NULL
                GROUP BY template_name
            """),
        ).fetchall()
        for r in _wf_rows:
            if r.template_name and r.best_wf_sharpe:
                v = float(r.best_wf_sharpe or 0)
                if v > best_wf_by_template.get(r.template_name, 0):
                    best_wf_by_template[r.template_name] = v
    except Exception:
        pass

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
        strategy_interval = None
        strategy_type = None
        if representative_id:
            # Use interval and strategy_type from SQL CTE (reads both metadata and rules)
            strategy_interval = row.strategy_interval
            strategy_type = row.sql_strategy_type
            # Load the ORM row for WF sharpe
            strategy = session.query(StrategyORM).filter_by(id=representative_id).first()
            if strategy:
                meta = strategy.strategy_metadata or {}
                wf_sharpe = (
                    meta.get("wf_test_sharpe")
                    or meta.get("wf_sharpe")
                    or meta.get("walk_forward_sharpe")
                    or (strategy.backtest_results or {}).get("walk_forward_results", {}).get("test_sharpe")
                )

        # Use symbol-specific WF sharpe from the representative strategy directly.
        # After watchlist elimination (2026-05-18), the representative strategy's WF
        # was always run on this exact symbol — no proxy fallback needed.
        # best_wf_by_template is kept as a last-resort fallback only.
        best_template_wf = best_wf_by_template.get(row.template_name, 0.0)
        if best_template_wf > 0 and (not wf_sharpe or wf_sharpe < best_template_wf):
            wf_sharpe = best_template_wf

        qualified, fail_reasons = is_qualified(paper_stats, wf_sharpe, interval=strategy_interval, strategy_type=strategy_type)
        if not qualified:
            continue

        ratio = None
        if wf_sharpe and wf_sharpe > 0 and paper_stats["paper_sharpe"] is not None:
            ratio = round(paper_stats["paper_sharpe"] / wf_sharpe, 3)

        avg_pnl_per_trade = float(row.avg_pnl) if row.avg_pnl is not None else None

        queue.append({
            "strategy_id": representative_id,  # most recent strategy_id for this pair
            "strategy_name": strategy_name,
            "template_name": row.template_name,
            "symbol": row.symbol,
            "paper_trades": paper_stats["paper_trades"],
            "paper_sharpe": paper_stats["paper_sharpe"],
            "paper_win_rate": paper_stats["paper_win_rate"],
            "paper_total_pnl": paper_stats["paper_total_pnl"],
            "avg_paper_pnl_per_trade": avg_pnl_per_trade,
            "wf_sharpe": wf_sharpe,
            "qualification_ratio": ratio,
            "strategy_versions": int(row.strategy_versions),
            "strategy_interval": strategy_interval,
            "first_paper_trade": row.first_trade_at.isoformat() if row.first_trade_at else None,
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
    from src.models.orm import LiveStrategyORM, StrategyORM, PositionORM

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

        # Add unrealized P&L from open live positions so the UI shows current
        # exposure even before the first trade closes (live_trades=0 / live_pnl=0).
        try:
            open_pos = session.query(PositionORM).filter(
                PositionORM.strategy_id == row.strategy_id,
                PositionORM.account_type == 'live',
                PositionORM.closed_at.is_(None),
            ).all()
            d["open_position_count"] = len(open_pos)
            d["unrealized_pnl"] = round(
                sum(float(p.unrealized_pnl or 0) for p in open_pos), 2
            )
            d["open_position_entry"] = float(open_pos[0].entry_price) if open_pos else None
            d["open_position_current"] = float(open_pos[0].current_price) if open_pos else None
        except Exception:
            d["open_position_count"] = 0
            d["unrealized_pnl"] = 0.0
            d["open_position_entry"] = None
            d["open_position_current"] = None

        # Add last signal cycle outcome for this live strategy
        try:
            from src.models.orm import OrderORM, SignalDecisionORM
            from src.models.enums import OrderStatus

            # eToro status code labels
            _ETORO_STATUS = {
                1: "Pending",
                2: "Filled",
                3: "Executed",
                4: "Failed/Rejected",
                7: "Active",
                11: "Pending Execution",
            }

            # Check for pending orders first
            pending = session.query(OrderORM).filter(
                OrderORM.strategy_id == row.strategy_id,
                OrderORM.account_type == 'live',
                OrderORM.status == OrderStatus.PENDING,
            ).order_by(OrderORM.submitted_at.desc()).first()

            if pending:
                submitted_str = pending.submitted_at.strftime('%H:%M UTC') if pending.submitted_at else '—'
                age_mins = int((datetime.now() - pending.submitted_at).total_seconds() / 60) if pending.submitted_at else 0
                age_str = f"{age_mins}m" if age_mins < 60 else f"{age_mins // 60}h {age_mins % 60}m"

                # Try to get live eToro status for this order
                etoro_status_label = None
                etoro_units = None
                etoro_amount = None
                try:
                    if pending.etoro_order_id:
                        from src.data.market_data_manager import get_market_data_manager
                        from src.api.etoro_client import EToroAPIClient
                        from src.core.config import Configuration
                        from src.models.enums import TradingMode
                        cfg = Configuration()
                        creds = cfg.load_credentials(TradingMode.LIVE)
                        live_client = EToroAPIClient(
                            public_key=creds["public_key"],
                            user_key=creds["user_key"],
                            mode=TradingMode.LIVE,
                        )
                        order_data = live_client.get_order_status(str(pending.etoro_order_id))
                        status_id = order_data.get("statusID")
                        etoro_status_label = _ETORO_STATUS.get(status_id, f"Status {status_id}")
                        etoro_units = order_data.get("units")
                        etoro_amount = order_data.get("amount")
                except Exception:
                    pass  # fail-open — show basic info if eToro call fails

                d["last_signal_status"] = "order_pending"
                if etoro_status_label and etoro_units and etoro_amount:
                    d["last_signal_detail"] = (
                        f"eToro: {etoro_status_label} · "
                        f"${etoro_amount:.0f} · {etoro_units:.4f} units · "
                        f"submitted {submitted_str} ({age_str} ago)"
                    )
                else:
                    d["last_signal_detail"] = f"Order pending since {submitted_str} ({age_str} ago)"
                # Store structured data for richer UI
                d["pending_order"] = {
                    "order_id": str(pending.id),
                    "etoro_order_id": str(pending.etoro_order_id) if pending.etoro_order_id else None,
                    "submitted_at": pending.submitted_at.isoformat() if pending.submitted_at else None,
                    "quantity": float(pending.quantity) if pending.quantity else None,
                    "etoro_status": etoro_status_label,
                    "etoro_units": etoro_units,
                    "etoro_amount": etoro_amount,
                    "age_mins": age_mins,
                }
            else:
                # Get last signal_decisions row for this strategy
                last_sd = session.execute(
                    __import__('sqlalchemy').text("""
                        SELECT stage, decision, reason, score, timestamp
                        FROM signal_decisions
                        WHERE strategy_id = :sid
                        ORDER BY timestamp DESC LIMIT 1
                    """),
                    {"sid": row.strategy_id}
                ).fetchone()

                if last_sd:
                    age_mins = int((datetime.now() - last_sd.timestamp).total_seconds() / 60)
                    age_str = f"{age_mins}m ago" if age_mins < 60 else f"{age_mins // 60}h ago"
                    if last_sd.stage == "order_submitted":
                        d["last_signal_status"] = "order_submitted"
                        d["last_signal_detail"] = f"Order submitted {age_str}"
                    elif last_sd.stage == "signal_emitted" and last_sd.decision == "rejected":
                        reason = last_sd.reason or ""
                        if "conviction" in reason.lower():
                            d["last_signal_status"] = "blocked_conviction"
                            score = f" (score {last_sd.score:.0f})" if last_sd.score else ""
                            d["last_signal_detail"] = f"Blocked: conviction{score} {age_str}"
                        elif "frequency" in reason.lower():
                            d["last_signal_status"] = "blocked_frequency"
                            d["last_signal_detail"] = f"Blocked: frequency limit {age_str}"
                        else:
                            d["last_signal_status"] = "blocked"
                            d["last_signal_detail"] = f"Blocked: {reason[:40]} {age_str}"
                    elif last_sd.stage == "gate_blocked":
                        d["last_signal_status"] = "gate_blocked"
                        d["last_signal_detail"] = f"Gate blocked {age_str}"
                    elif last_sd.stage == "signal_emitted":
                        d["last_signal_status"] = "signal_emitted"
                        d["last_signal_detail"] = f"Signal emitted {age_str}"
                    else:
                        d["last_signal_status"] = last_sd.stage
                        d["last_signal_detail"] = f"{last_sd.stage} {age_str}"
                else:
                    d["last_signal_status"] = "no_signal_yet"
                    d["last_signal_detail"] = "No signal generated yet"
        except Exception:
            d["last_signal_status"] = None
            d["last_signal_detail"] = None

        # Divergence: live_sharpe vs paper_sharpe
        if row.live_sharpe and paper.get("paper_sharpe") and paper["paper_sharpe"] > 0:
            d["divergence_pct"] = round(row.live_sharpe / paper["paper_sharpe"] * 100, 1)
        else:
            d["divergence_pct"] = None

        # Live trade history from trade_journal — gives closed trade breakdown,
        # win rate, avg P&L, last opened/closed, and individual trade rows.
        try:
            from sqlalchemy import text as _text
            live_tj = session.execute(
                _text("""
                    SELECT id, entry_price, exit_price, pnl, pnl_percent,
                           entry_time, exit_time, hold_time_hours, exit_reason
                    FROM trade_journal
                    WHERE strategy_id = :sid AND symbol = :sym
                      AND account_type = 'live'
                    ORDER BY entry_time DESC
                    LIMIT 20
                """),
                {"sid": row.strategy_id, "sym": row.symbol},
            ).fetchall()

            closed_trades = [t for t in live_tj if t.exit_time is not None]
            open_trades   = [t for t in live_tj if t.exit_time is None]

            wins   = [t for t in closed_trades if t.pnl is not None and t.pnl > 0]
            losses = [t for t in closed_trades if t.pnl is not None and t.pnl < 0]
            realized_pnl = sum(float(t.pnl) for t in closed_trades if t.pnl is not None)
            avg_pnl = realized_pnl / len(closed_trades) if closed_trades else None
            win_rate = len(wins) / len(closed_trades) * 100 if closed_trades else None
            best  = max((float(t.pnl) for t in closed_trades if t.pnl is not None), default=None)
            worst = min((float(t.pnl) for t in closed_trades if t.pnl is not None), default=None)
            avg_hold = (
                sum(float(t.hold_time_hours) for t in closed_trades if t.hold_time_hours is not None)
                / len([t for t in closed_trades if t.hold_time_hours is not None])
                if any(t.hold_time_hours for t in closed_trades) else None
            )
            last_opened = live_tj[0].entry_time.isoformat() if live_tj else None
            last_closed = (
                max((t.exit_time for t in closed_trades), default=None)
            )

            d["live_closed_trades"]  = len(closed_trades)
            d["live_open_trades"]    = len(open_trades)
            d["live_realized_pnl"]   = round(realized_pnl, 2)
            d["live_win_rate"]       = round(win_rate, 1) if win_rate is not None else None
            d["live_avg_pnl"]        = round(avg_pnl, 2) if avg_pnl is not None else None
            d["live_best_trade"]     = round(best, 2) if best is not None else None
            d["live_worst_trade"]    = round(worst, 2) if worst is not None else None
            d["live_avg_hold_hours"] = round(avg_hold, 1) if avg_hold is not None else None
            d["live_last_opened"]    = last_opened
            d["live_last_closed"]    = last_closed.isoformat() if last_closed else None
            d["live_trade_history"]  = [
                {
                    "id": str(t.id),
                    "entry_price": float(t.entry_price) if t.entry_price else None,
                    "exit_price":  float(t.exit_price)  if t.exit_price  else None,
                    "pnl":         float(t.pnl)          if t.pnl         else None,
                    "pnl_percent": float(t.pnl_percent)  if t.pnl_percent else None,
                    "entry_time":  t.entry_time.isoformat() if t.entry_time else None,
                    "exit_time":   t.exit_time.isoformat()  if t.exit_time  else None,
                    "hold_time_hours": float(t.hold_time_hours) if t.hold_time_hours else None,
                    "exit_reason": t.exit_reason,
                    "is_open":     t.exit_time is None,
                }
                for t in live_tj
            ]
        except Exception as _tj_err:
            logger.debug(f"Could not fetch live trade journal for {row.strategy_id}: {_tj_err}")
            d["live_closed_trades"]  = None
            d["live_open_trades"]    = None
            d["live_realized_pnl"]   = None
            d["live_win_rate"]       = None
            d["live_avg_pnl"]        = None
            d["live_best_trade"]     = None
            d["live_worst_trade"]    = None
            d["live_avg_hold_hours"] = None
            d["live_last_opened"]    = None
            d["live_last_closed"]    = None
            d["live_trade_history"]  = []

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
