"""Analytics that turn trade/position data into alpha-insight signals.

Each function here is read-only and cheap (DB aggregates, cached). They power
observability endpoints: MAE-at-stop, regime×template P&L matrix, template
graduation funnel, opportunity cost, WF-vs-live divergence alarm.

Design: every function returns a plain dict. Callers decide presentation
(endpoint JSON, dashboard card, Slack summary, etc.). Fail-quiet on data
issues — return empty results with an "error" key instead of raising.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── #4. MAE-at-stop analysis ────────────────────────────────────────────────

def mae_at_stop_analysis(lookback_days: int = 60, min_trades: int = 5) -> Dict[str, Any]:
    """For each symbol, how much did price move against us before the trade closed?

    Distinguishes 'entry was bad' from 'trail was too tight':
      - If |MAE| approaches |SL%| → trail fired immediately, entry was off
      - If |MFE| was large but net P&L negative → we gave back a winner

    Returns: {symbol: {trades, avg_mae_pct, avg_mfe_pct, avg_pnl_pct,
                        pattern: 'entry_bad'|'trail_tight'|'exit_late'|'ok'}}
    """
    try:
        from src.models.database import get_database
        from src.analytics.trade_journal import TradeJournalEntryORM

        db = get_database()
        session = db.get_session()
        try:
            cutoff = datetime.now() - timedelta(days=lookback_days)
            trades = session.query(TradeJournalEntryORM).filter(
                TradeJournalEntryORM.exit_time.isnot(None),
                TradeJournalEntryORM.exit_time >= cutoff,
                TradeJournalEntryORM.max_adverse_excursion.isnot(None),
            ).all()
        finally:
            session.close()

        by_symbol: Dict[str, List] = {}
        for t in trades:
            by_symbol.setdefault(t.symbol, []).append(t)

        result: Dict[str, Any] = {}
        for sym, tlist in by_symbol.items():
            if len(tlist) < min_trades:
                continue
            avg_mae = sum(t.max_adverse_excursion or 0 for t in tlist) / len(tlist)
            avg_mfe = sum(t.max_favorable_excursion or 0 for t in tlist) / len(tlist)
            avg_pnl = sum(t.pnl_percent or 0 for t in tlist) / len(tlist) / 100.0
            wins = sum(1 for t in tlist if t.pnl and t.pnl > 0)
            win_rate = wins / len(tlist)

            # Heuristic pattern detection
            pattern = "ok"
            if avg_pnl < 0 and abs(avg_mae) > 0.03:
                if abs(avg_mae) > 0.8 * 0.06:  # 80% of typical 6% SL
                    pattern = "entry_bad_or_stop_hit"
                elif avg_mfe > abs(avg_mae):
                    pattern = "exit_late_gave_back"
            elif avg_pnl > 0 and avg_mfe > 3 * avg_pnl:
                pattern = "trail_tight_leaving_money"
            elif win_rate < 0.35 and abs(avg_mae) < 0.02:
                pattern = "entry_bad_immediate_reversal"

            result[sym] = {
                "trades": len(tlist),
                "avg_mae_pct": round(avg_mae * 100, 2),
                "avg_mfe_pct": round(avg_mfe * 100, 2),
                "avg_pnl_pct": round(avg_pnl * 100, 2),
                "win_rate": round(win_rate, 3),
                "pattern": pattern,
            }

        return {"symbols": result, "lookback_days": lookback_days, "total_symbols": len(result)}
    except Exception as e:
        logger.debug(f"mae_at_stop_analysis failed: {e}")
        return {"error": str(e)[:200], "symbols": {}}


# ── #7. WF-vs-live divergence alarm ─────────────────────────────────────────

def wf_live_divergence(min_live_trades: int = 5) -> List[Dict[str, Any]]:
    """Compare each strategy's WF test Sharpe vs its actual live Sharpe.

    Returns strategies where |wf_sharpe - live_sharpe| > 1.0 — candidates for
    either a broken WF methodology or a regime shift that invalidates the
    strategy.
    """
    try:
        import math
        from src.models.database import get_database
        from src.models.orm import StrategyORM, PositionORM

        db = get_database()
        session = db.get_session()
        try:
            strategies = session.query(StrategyORM).filter(
                StrategyORM.status.in_(['DEMO', 'LIVE', 'BACKTESTED'])
            ).all()

            alerts: List[Dict[str, Any]] = []
            for s in strategies:
                meta = s.strategy_metadata or {}
                wf_sharpe = meta.get('wf_test_sharpe')
                if wf_sharpe is None:
                    continue
                closed = session.query(PositionORM).filter(
                    PositionORM.strategy_id == s.id,
                    PositionORM.closed_at.isnot(None),
                ).all()
                n = len(closed)
                if n < min_live_trades:
                    continue
                returns = [(p.realized_pnl or 0) / (p.invested_amount or 1) for p in closed if p.invested_amount]
                if len(returns) < 3:
                    continue
                mean = sum(returns) / len(returns)
                var = sum((r - mean) ** 2 for r in returns) / len(returns)
                std = math.sqrt(var) if var > 0 else 0
                if std == 0:
                    continue
                live_sharpe = (mean / std) * math.sqrt(252)
                divergence = abs(float(wf_sharpe) - live_sharpe)

                if divergence >= 1.0:
                    alerts.append({
                        "strategy_id": s.id,
                        "name": s.name,
                        "status": str(s.status),
                        "wf_test_sharpe": round(float(wf_sharpe), 2),
                        "live_sharpe": round(live_sharpe, 2),
                        "divergence": round(divergence, 2),
                        "live_trades": n,
                        "live_mean_pct": round(mean * 100, 2),
                    })

            alerts.sort(key=lambda a: -a['divergence'])
            return alerts[:50]  # top-50 biggest mismatches
        finally:
            session.close()
    except Exception as e:
        logger.debug(f"wf_live_divergence failed: {e}")
        return []


# ── #12. Regime × template P&L matrix ───────────────────────────────────────

def regime_template_pnl_matrix(lookback_days: int = 90) -> Dict[str, Any]:
    """Matrix: (regime, template, direction) -> {trades, pnl, win_rate}.

    Consumer uses this to identify template families that lose in specific
    regimes and suppress them there.
    """
    try:
        from src.models.database import get_database
        from src.analytics.trade_journal import TradeJournalEntryORM

        db = get_database()
        session = db.get_session()
        try:
            cutoff = datetime.now() - timedelta(days=lookback_days)
            trades = session.query(TradeJournalEntryORM).filter(
                TradeJournalEntryORM.exit_time.isnot(None),
                TradeJournalEntryORM.exit_time >= cutoff,
                TradeJournalEntryORM.market_regime.isnot(None),
            ).all()
        finally:
            session.close()

        # (regime, template, direction) -> [pnls]
        cells: Dict[tuple, List[float]] = {}
        for t in trades:
            meta = t.trade_metadata or {}
            tname = meta.get('template_name') or 'unknown'
            side = 'long' if t.side and 'LONG' in str(t.side).upper() else 'short'
            key = (t.market_regime or 'unknown', tname, side)
            cells.setdefault(key, []).append(float(t.pnl or 0))

        matrix = []
        for (regime, tname, side), pnls in cells.items():
            n = len(pnls)
            if n < 2:
                continue
            total = sum(pnls)
            wins = sum(1 for p in pnls if p > 0)
            matrix.append({
                "regime": regime,
                "template": tname,
                "direction": side,
                "trades": n,
                "total_pnl": round(total, 2),
                "win_rate": round(wins / n, 3),
                "avg_pnl": round(total / n, 2),
            })

        matrix.sort(key=lambda r: r['total_pnl'])
        return {"lookback_days": lookback_days, "cells": matrix}
    except Exception as e:
        logger.debug(f"regime_template_pnl_matrix failed: {e}")
        return {"error": str(e)[:200], "cells": []}


# ── #13. Template graduation funnel ─────────────────────────────────────────

def template_graduation_funnel(lookback_days: int = 30) -> Dict[str, Any]:
    """Show how proposals progress through the pipeline stages.

    Reads signal_decisions. Stages: proposed → wf_validated → mc_validated →
    activated → signal_emitted → order_submitted → order_filled.
    Computes per-stage counts and drop-off percentages.
    """
    try:
        from src.models.database import get_database
        from src.models.orm import SignalDecisionORM
        from sqlalchemy import func as sa_func

        db = get_database()
        session = db.get_session()
        try:
            cutoff = datetime.now() - timedelta(days=lookback_days)
            rows = session.query(
                SignalDecisionORM.stage,
                sa_func.count(SignalDecisionORM.id).label('n'),
            ).filter(
                SignalDecisionORM.timestamp >= cutoff,
            ).group_by(SignalDecisionORM.stage).all()
        finally:
            session.close()

        counts = {r.stage: int(r.n) for r in rows}
        ordered_stages = ['proposed', 'wf_validated', 'wf_rejected',
                          'mc_validated', 'mc_rejected', 'activated',
                          'rejected_act', 'signal_emitted', 'gate_blocked',
                          'order_submitted', 'order_filled', 'order_failed']

        funnel = []
        prev = None
        for stg in ordered_stages:
            n = counts.get(stg, 0)
            drop = None if prev is None or prev == 0 else round(1 - (n / prev), 3)
            funnel.append({"stage": stg, "count": n, "drop_from_prev": drop})
            if stg in ('proposed', 'wf_validated', 'mc_validated', 'activated', 'signal_emitted', 'order_submitted'):
                prev = n  # track primary-path stages for drop-off

        return {"lookback_days": lookback_days, "funnel": funnel}
    except Exception as e:
        logger.debug(f"template_graduation_funnel failed: {e}")
        return {"error": str(e)[:200], "funnel": []}


# ── #14. Per-symbol opportunity cost ────────────────────────────────────────

def per_symbol_opportunity_cost(lookback_days: int = 30) -> List[Dict[str, Any]]:
    """Forward-return of symbol minus captured P&L.

    For each symbol in the trading universe:
      - symbol_forward_return = (price_now - price_N_days_ago) / price_N_days_ago
      - captured_pct = lifetime_pnl / (avg_invested_per_trade * n_trades)
      - opportunity_cost = symbol_forward_return - captured_pct

    Positive opportunity_cost means we left alpha on the table. Negative means
    we outperformed the symbol (shorted a drop, caught a reversal). Useful to
    find where the system systematically misses moves.
    """
    try:
        from src.models.database import get_database
        from src.analytics.trade_journal import TradeJournalEntryORM
        from src.models.orm import HistoricalPriceCacheORM
        from sqlalchemy import func as sa_func

        db = get_database()
        session = db.get_session()
        try:
            cutoff = datetime.now() - timedelta(days=lookback_days)

            # Per-symbol trade aggregates (lifetime, not windowed — captured is
            # lifetime so it's comparable across symbols regardless of activity)
            journal_rows = session.query(
                TradeJournalEntryORM.symbol,
                sa_func.count(TradeJournalEntryORM.id).label('trades'),
                sa_func.coalesce(sa_func.sum(TradeJournalEntryORM.pnl), 0.0).label('pnl_sum'),
                sa_func.coalesce(sa_func.sum(TradeJournalEntryORM.entry_size), 0.0).label('invested_sum'),
            ).filter(
                TradeJournalEntryORM.pnl.isnot(None),
            ).group_by(TradeJournalEntryORM.symbol).all()
            journal_map = {r.symbol: {
                'trades': int(r.trades),
                'pnl': float(r.pnl_sum or 0),
                'invested': float(r.invested_sum or 0),
            } for r in journal_rows}

            # Per-symbol forward return: latest close vs close N days ago
            results: List[Dict[str, Any]] = []
            for sym, stats in journal_map.items():
                px_now_row = session.query(HistoricalPriceCacheORM.close).filter(
                    HistoricalPriceCacheORM.symbol == sym,
                    HistoricalPriceCacheORM.interval == '1d',
                ).order_by(HistoricalPriceCacheORM.date.desc()).first()
                px_then_row = session.query(HistoricalPriceCacheORM.close).filter(
                    HistoricalPriceCacheORM.symbol == sym,
                    HistoricalPriceCacheORM.interval == '1d',
                    HistoricalPriceCacheORM.date <= cutoff,
                ).order_by(HistoricalPriceCacheORM.date.desc()).first()
                if not px_now_row or not px_then_row or not px_then_row[0]:
                    continue
                symbol_forward_return = (px_now_row[0] - px_then_row[0]) / px_then_row[0]

                captured = stats['pnl'] / stats['invested'] if stats['invested'] > 0 else 0
                opp_cost = symbol_forward_return - captured

                results.append({
                    "symbol": sym,
                    "trades": stats['trades'],
                    "lifetime_pnl": round(stats['pnl'], 2),
                    "symbol_fwd_return_pct": round(symbol_forward_return * 100, 2),
                    "captured_pct": round(captured * 100, 2),
                    "opportunity_cost_pct": round(opp_cost * 100, 2),
                })

            results.sort(key=lambda r: -r['opportunity_cost_pct'])
            return results[:50]  # top-50 missed movers
        finally:
            session.close()
    except Exception as e:
        logger.debug(f"per_symbol_opportunity_cost failed: {e}")
        return []
