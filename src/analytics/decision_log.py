"""Signal-decision audit log.

Central helper for writing rows to `signal_decisions`. Every caller uses
`record()` (sync, fire-and-forget) or `record_batch()` (bulk).

Design goals:
- Never raise. Analytics failures must not break trading.
- Idempotent: a caller can call `record()` multiple times per combo per cycle
  (e.g. proposed + then wf_rejected) — each call is a separate row. Consumers
  pivot by (cycle_id, template, symbol).
- Retention: a cleanup job trims rows older than 30 days. If the job is not
  scheduled yet, the table grows ~10k rows/cycle × 2 cycles/day = 20k/day =
  600k/month. Acceptable short-term given we're the only DB user.

Observability:
- On write failure we still don't raise (trading must not break), but we
  surface the error at WARNING level with a 5-minute cooldown per error
  signature. Previously every failure was DEBUG, which hid a week-long
  silent outage caused by a missing GRANT on `signal_decisions` after the
  table was created as `postgres`. DEBUG meant alphacent_user couldn't
  INSERT, and because the logger root was INFO, nothing ever surfaced.

Usage:
    from src.analytics.decision_log import record_decision
    record_decision(
        stage="proposed", decision="accepted",
        template="RSI Dip Buy", symbol="TSLA", direction="long",
        cycle_id=cycle_id, score=28.7, reason="base_score >0",
    )

Query:
    SELECT stage, COUNT(*) FROM signal_decisions
    WHERE symbol='TSLA' AND timestamp > NOW() - INTERVAL '7 days'
    GROUP BY stage ORDER BY COUNT(*) DESC;
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

# Per-process cooldown state for surfacing write failures. We never raise from
# the writer (trading must not break), but we DO want a human-visible warning
# when writes are silently failing — capped at 5 min per error signature so
# a persistent fault (e.g. missing GRANT) does not flood logs.
_FAILURE_COOLDOWN_SECS = 300.0
_last_failure_log: Dict[str, float] = {}


def _log_write_failure(context: str, err: Exception) -> None:
    """Surface a write failure at WARNING with a per-signature cooldown.

    Signature is (context, exception-class, first 60 chars of message). Tight
    enough to distinguish "permission denied" from "serialization failure"
    but loose enough to not spam on row-specific differences.
    """
    sig = f"{context}|{type(err).__name__}|{str(err)[:60]}"
    now = time.monotonic()
    last = _last_failure_log.get(sig, 0.0)
    if now - last >= _FAILURE_COOLDOWN_SECS:
        _last_failure_log[sig] = now
        logger.warning(
            f"decision_log {context} failed (non-fatal, next-log-in={_FAILURE_COOLDOWN_SECS:.0f}s): "
            f"{type(err).__name__}: {err}"
        )
    else:
        # Still keep a DEBUG breadcrumb for full-log forensics.
        logger.debug(f"decision_log {context} failed (suppressed warning): {err}")


def record_decision(
    stage: str,
    decision: str,
    *,
    template: Optional[str] = None,
    symbol: Optional[str] = None,
    direction: Optional[str] = None,
    strategy_id: Optional[str] = None,
    cycle_id: Optional[str] = None,
    market_regime: Optional[str] = None,
    score: Optional[float] = None,
    reason: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Fire-and-forget single-row write. Never raises."""
    try:
        from src.models.database import get_database
        from src.models.orm import SignalDecisionORM

        db = get_database()
        session = db.get_session()
        try:
            row = SignalDecisionORM(
                timestamp=datetime.now(),
                cycle_id=cycle_id,
                strategy_id=strategy_id,
                template_name=template,
                symbol=symbol,
                direction=direction,
                market_regime=market_regime,
                stage=stage,
                decision=decision,
                reason=(reason[:500] if reason else None),
                score=score,
                decision_metadata=metadata,
            )
            session.add(row)
            session.commit()
        finally:
            session.close()
    except Exception as e:
        _log_write_failure("record_decision", e)


def record_batch(rows: Iterable[Dict[str, Any]]) -> None:
    """Bulk insert decisions. Same semantics — never raises.

    Each dict may contain: stage, decision, template, symbol, direction,
    strategy_id, cycle_id, market_regime, score, reason, metadata.
    """
    rows = list(rows)
    if not rows:
        return
    try:
        from src.models.database import get_database
        from src.models.orm import SignalDecisionORM

        db = get_database()
        session = db.get_session()
        try:
            orm_rows: List[SignalDecisionORM] = []
            now = datetime.now()
            for r in rows:
                reason = r.get("reason")
                orm_rows.append(SignalDecisionORM(
                    timestamp=r.get("timestamp") or now,
                    cycle_id=r.get("cycle_id"),
                    strategy_id=r.get("strategy_id"),
                    template_name=r.get("template") or r.get("template_name"),
                    symbol=r.get("symbol"),
                    direction=r.get("direction"),
                    market_regime=r.get("market_regime"),
                    stage=r["stage"],
                    decision=r["decision"],
                    reason=(reason[:500] if reason else None),
                    score=r.get("score"),
                    decision_metadata=r.get("metadata"),
                ))
            session.bulk_save_objects(orm_rows)
            session.commit()
        finally:
            session.close()
    except Exception as e:
        _log_write_failure("record_batch", e)


def prune_old(days: int = 30) -> int:
    """Delete decision rows older than `days`. Returns count deleted."""
    try:
        from src.models.database import get_database
        from src.models.orm import SignalDecisionORM

        db = get_database()
        session = db.get_session()
        try:
            cutoff = datetime.now() - timedelta(days=days)
            deleted = session.query(SignalDecisionORM).filter(
                SignalDecisionORM.timestamp < cutoff
            ).delete(synchronize_session=False)
            session.commit()
            return int(deleted or 0)
        finally:
            session.close()
    except Exception as e:
        _log_write_failure("prune_old", e)
        return 0
