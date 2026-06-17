"""
Execution-cost (slippage) backfill from eToro ground truth — Option B.

The production close paths (monitoring_service TSL/zombie/partial, the canonical
position_close.finalize_position_close, order_monitor sync-close) journal an exit
using the close-DECISION price (last-synced current_price / TSL-breach price) and
never capture eToro's actual executed close rate, so trade_journal.exit_slippage
was 100% NULL on every real close. The only path that captures exit slippage
(order_executor fill handlers) is dead for production closes.

This module is the off-hot-path repair: pull eToro's REAL executed open/close
rates via get_trade_history (LIVE) and, per matched closed trade, compute true
execution slippage as (close-decision price) vs (eToro's actual closeRate), then
reconcile the journal row to broker ground truth (price + P&L + fees). Read-only
w.r.t. the live close path; NEVER fabricates 0 (the same drift guard as entries
nulls queued/deferred closes whose delta is market drift, not execution slippage).

Match key: trade_journal.entry_order_id == eToro history 'orderId'.
Idempotent: a row is processed once (skipped when exit_slippage is set OR the row
already carries trade_metadata.execution_cost_backfilled_at). The pre-correction
decision price is stashed in trade_metadata.exit_decision_price so re-runs never
compare closeRate-vs-closeRate.

Used by: scripts/backfill_execution_costs.py (CLI) and
MonitoringService._run_daily_sync (daily reconcile).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _parse_etoro_ts(ts) -> Optional[datetime]:
    """Parse an eToro ISO timestamp ('...Z' / fractional secs) to naive UTC."""
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts.replace(tzinfo=None)
    s = str(ts).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        return None


def backfill_live_execution_costs(
    min_date: Optional[str] = None,
    apply: bool = True,
    client: Any = None,
    db: Any = None,
    log: Any = None,
) -> Dict[str, int]:
    """Reconcile LIVE closed trades to eToro ground truth and capture exit slippage.

    Args:
        min_date: earliest close date (YYYY-MM-DD). Default: 90 days ago.
        apply: write changes when True; dry-run when False.
        client: a LIVE EToroAPIClient (built from Configuration if None).
        db: a Database (get_database() if None).
        log: optional logger (module logger by default).

    Returns:
        stats dict (records / matched / unmatched / exit_slip_set /
        exit_slip_drift_null / already_done / entry_slip_set).
    """
    _log = log or logger
    from src.analytics.trade_journal import compute_execution_slippage, TradeJournalEntryORM
    from src.models.orm import OrderORM

    if min_date is None:
        min_date = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")

    if client is None:
        from src.core.config import Configuration
        from src.api.etoro_client import EToroAPIClient
        from src.models.enums import TradingMode
        cr = Configuration().load_credentials(TradingMode.LIVE)
        client = EToroAPIClient(
            public_key=cr["public_key"], user_key=cr["user_key"], mode=TradingMode.LIVE
        )
    if db is None:
        from src.models.database import get_database
        db = get_database()

    records = client.get_trade_history(min_date)
    stats = {
        "records": len(records), "matched": 0, "unmatched": 0,
        "exit_slip_set": 0, "exit_slip_drift_null": 0, "already_done": 0,
        "entry_slip_set": 0,
    }

    with db.session_scope() as session:
        for rec in records:
            order_id = rec.get("orderId")
            if not order_id:
                stats["unmatched"] += 1
                continue
            entry = (
                session.query(TradeJournalEntryORM)
                .filter(TradeJournalEntryORM.entry_order_id == str(order_id))
                .filter(TradeJournalEntryORM.account_type == "live")
                .first()
            )
            if entry is None:
                stats["unmatched"] += 1
                continue
            stats["matched"] += 1

            if entry.exit_time is None:
                continue  # still open per our records
            meta_existing = entry.trade_metadata or {}
            if entry.exit_slippage is not None or meta_existing.get("execution_cost_backfilled_at"):
                stats["already_done"] += 1
                continue

            open_rate = rec.get("openRate")
            close_rate = rec.get("closeRate")
            is_buy = bool(rec.get("isBuy", True))
            close_side = "SELL" if is_buy else "BUY"  # close a long → sell; close a short → buy
            close_ts = _parse_etoro_ts(rec.get("closeTimestamp"))
            open_ts = _parse_etoro_ts(rec.get("openTimestamp"))
            net_profit = rec.get("netProfit")
            fees = rec.get("fees")
            investment = rec.get("investment") or entry.entry_size

            # Decision/expected exit reference: prefer the stashed value so re-runs
            # never compare closeRate-vs-closeRate after the correction below.
            decision_exit_price = meta_existing.get("exit_decision_price") or entry.exit_price
            exit_slip = compute_execution_slippage(
                expected_price=decision_exit_price,
                filled_price=close_rate,
                order_side=close_side,
                submitted_at=entry.exit_time,
                filled_at=close_ts,
            )

            entry_slip_new = None
            if entry.entry_slippage is None and open_rate:
                ord_row = (
                    session.query(OrderORM)
                    .filter(OrderORM.etoro_order_id == str(order_id))
                    .first()
                )
                exp_entry = getattr(ord_row, "expected_price", None) if ord_row else None
                sub_at = getattr(ord_row, "submitted_at", None) if ord_row else None
                if exp_entry:
                    entry_slip_new = compute_execution_slippage(
                        expected_price=exp_entry,
                        filled_price=open_rate,
                        order_side="BUY" if is_buy else "SELL",
                        submitted_at=sub_at,
                        filled_at=open_ts,
                    )

            if exit_slip is None:
                stats["exit_slip_drift_null"] += 1
            else:
                stats["exit_slip_set"] += 1

            if not apply:
                continue

            meta = dict(entry.trade_metadata or {})
            meta["exit_decision_price"] = decision_exit_price
            if fees is not None:
                meta["etoro_fees"] = fees
            if net_profit is not None:
                meta["etoro_net_profit"] = net_profit
            meta["execution_cost_backfilled_at"] = datetime.utcnow().isoformat()
            entry.trade_metadata = meta

            entry.exit_slippage = exit_slip
            if entry_slip_new is not None:
                entry.entry_slippage = entry_slip_new
                stats["entry_slip_set"] += 1
            if open_rate:
                entry.entry_price = open_rate
            if close_rate:
                entry.exit_price = close_rate
            if net_profit is not None:
                entry.pnl = net_profit
                if investment and investment > 0:
                    entry.pnl_percent = (net_profit / investment) * 100.0

    if stats["exit_slip_set"] or stats["entry_slip_set"]:
        _log.info(
            f"Execution-cost backfill: matched={stats['matched']} "
            f"exit_slip_set={stats['exit_slip_set']} "
            f"entry_slip_set={stats['entry_slip_set']} "
            f"drift_null={stats['exit_slip_drift_null']} "
            f"already_done={stats['already_done']} unmatched={stats['unmatched']}"
        )
    return stats
