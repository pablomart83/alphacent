"""Path-A parameter override store (Tier 1 approval rail).

The running system reads ACTIVE template_param_overrides each cycle (cached
~60s) and applies them to the SL/TP the proposer assigns — bounded by sl_caps.
Approvals therefore take effect within a minute, with no deploy and no restart,
and are instantly reversible (status='reverted').

This module is the single read/write surface:
  - get_active_overrides()  : cached {scope_key: {...}} for the proposer.
  - resolve_override(symbol, template_name, asset_class) : the proposer lookup
    (symbol-scope wins over template×asset-class scope).
  - apply_recommendation(rec_id, reviewer) / revert_recommendation(rec_id) :
    the approval-rail actions (also update the recommendation + live_strategies
    when the target is a live pair).
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_CACHE: Optional[Dict[str, Dict[str, Any]]] = None
_CACHE_TS: float = 0.0
_CACHE_TTL = 60.0
_LOCK = threading.Lock()


def get_active_overrides(force: bool = False) -> Dict[str, Dict[str, Any]]:
    """Return {scope_key: {scope_type, symbol, template_name, asset_class,
    sl_pct, tp_pct}} for all ACTIVE overrides. Cached ~60s. Fail-safe to {}."""
    global _CACHE, _CACHE_TS
    now = time.time()
    with _LOCK:
        if not force and _CACHE is not None and (now - _CACHE_TS) < _CACHE_TTL:
            return _CACHE
    try:
        from src.models.database import get_database
        from src.models.orm import TemplateParamOverrideORM
        db = get_database()
        session = db.get_session()
        try:
            rows = session.query(TemplateParamOverrideORM).filter(
                TemplateParamOverrideORM.status == "active"
            ).all()
            out: Dict[str, Dict[str, Any]] = {}
            for r in rows:
                out[r.scope_key] = {
                    "scope_type": r.scope_type, "symbol": r.symbol,
                    "template_name": r.template_name, "asset_class": r.asset_class,
                    "sl_pct": r.sl_pct, "tp_pct": r.tp_pct,
                }
        finally:
            session.close()
        with _LOCK:
            _CACHE = out
            _CACHE_TS = now
        return out
    except Exception as e:
        logger.debug("get_active_overrides failed: %s", e)
        return _CACHE or {}


def invalidate_cache() -> None:
    global _CACHE_TS
    with _LOCK:
        _CACHE_TS = 0.0


def resolve_override(
    symbol: str, template_name: Optional[str], asset_class: Optional[str],
) -> Optional[Dict[str, float]]:
    """Return {'sl_pct', 'tp_pct'} for the most specific active override, or
    None. Symbol-scope wins over template×asset-class scope."""
    overrides = get_active_overrides()
    if not overrides:
        return None
    sym = (symbol or "").upper()
    if sym and sym in overrides:
        o = overrides[sym]
        return {"sl_pct": o.get("sl_pct"), "tp_pct": o.get("tp_pct")}
    if template_name and asset_class:
        key = f"{template_name}::{asset_class}"
        if key in overrides:
            o = overrides[key]
            return {"sl_pct": o.get("sl_pct"), "tp_pct": o.get("tp_pct")}
    return None


# ── Approval-rail actions ──────────────────────────────────────────────────

def _is_live_pair(session, symbol: str) -> bool:
    from sqlalchemy import text
    try:
        row = session.execute(text(
            "SELECT 1 FROM live_strategies WHERE UPPER(symbol) = :s LIMIT 1"
        ), {"s": (symbol or "").upper()}).fetchone()
        return row is not None
    except Exception:
        return False


def apply_recommendation(rec_id: int, reviewer: str = "cio") -> Dict[str, Any]:
    """Approve + APPLY a recommendation (Path A). Validates the envelope
    (proposed SL ≤ sl_cap), then either updates live_strategies (live pair) or
    upserts an active template_param_override. Returns a result dict."""
    from src.models.database import get_database
    from src.models.orm import ImprovementRecommendationORM, TemplateParamOverrideORM
    from src.risk.sl_caps import sl_cap_pct
    from sqlalchemy import text

    db = get_database()
    session = db.get_session()
    try:
        rec = session.query(ImprovementRecommendationORM).filter(
            ImprovementRecommendationORM.id == rec_id
        ).first()
        if rec is None:
            return {"success": False, "message": f"recommendation {rec_id} not found"}
        if rec.status != "pending":
            return {"success": False, "message": f"recommendation is '{rec.status}', not pending"}

        # Envelope guard — never apply a stop beyond the asset-class cap.
        cap = sl_cap_pct(rec.symbol) if rec.symbol else 0.20
        if rec.proposed_sl is not None and rec.proposed_sl > cap + 1e-9:
            return {"success": False,
                    "message": f"proposed SL {rec.proposed_sl:.1%} exceeds cap {cap:.1%} — rejected"}

        applied_via = None
        # Live pair → update live_strategies (read live each cycle, no restart).
        if rec.scope_type == "symbol" and rec.symbol and _is_live_pair(session, rec.symbol):
            session.execute(text("""
                UPDATE live_strategies SET sl_pct = :sl, tp_pct = :tp
                WHERE UPPER(symbol) = :s
            """), {"sl": rec.proposed_sl, "tp": rec.proposed_tp, "s": rec.symbol.upper()})
            applied_via = "live_strategies"
        else:
            # Template/paper scope → active param override (proposer reads it).
            # Deactivate any prior active override for the same scope_key first.
            session.query(TemplateParamOverrideORM).filter(
                TemplateParamOverrideORM.scope_key == rec.scope_key,
                TemplateParamOverrideORM.status == "active",
            ).update({"status": "reverted", "reverted_at": datetime.now()},
                     synchronize_session=False)
            session.add(TemplateParamOverrideORM(
                created_at=datetime.now(), scope_type=rec.scope_type, scope_key=rec.scope_key,
                symbol=rec.symbol, template_name=rec.template_name, asset_class=rec.asset_class,
                sl_pct=rec.proposed_sl, tp_pct=rec.proposed_tp, status="active",
                source_recommendation_id=rec.id, created_by=reviewer,
            ))
            applied_via = "template_param_overrides"

        rec.status = "applied"
        rec.reviewed_at = datetime.now()
        rec.applied_at = datetime.now()
        rec.reviewer = reviewer
        rec.notes = f"applied via {applied_via}"
        session.commit()
        invalidate_cache()
        return {"success": True, "message": f"applied via {applied_via}", "applied_via": applied_via}
    except Exception as e:
        session.rollback()
        logger.error("apply_recommendation(%s) failed: %s", rec_id, e)
        return {"success": False, "message": str(e)}
    finally:
        session.close()


def reject_recommendation(rec_id: int, reviewer: str = "cio") -> Dict[str, Any]:
    from src.models.database import get_database
    from src.models.orm import ImprovementRecommendationORM
    db = get_database()
    session = db.get_session()
    try:
        rec = session.query(ImprovementRecommendationORM).filter(
            ImprovementRecommendationORM.id == rec_id
        ).first()
        if rec is None:
            return {"success": False, "message": "not found"}
        rec.status = "rejected"
        rec.reviewed_at = datetime.now()
        rec.reviewer = reviewer
        session.commit()
        return {"success": True, "message": "rejected"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()


def revert_recommendation(rec_id: int, reviewer: str = "cio") -> Dict[str, Any]:
    """Undo an applied recommendation: deactivate its override (or note the
    live_strategies row should be restored manually) and mark reverted."""
    from src.models.database import get_database
    from src.models.orm import ImprovementRecommendationORM, TemplateParamOverrideORM
    db = get_database()
    session = db.get_session()
    try:
        rec = session.query(ImprovementRecommendationORM).filter(
            ImprovementRecommendationORM.id == rec_id
        ).first()
        if rec is None:
            return {"success": False, "message": "not found"}
        if rec.status != "applied":
            return {"success": False, "message": f"recommendation is '{rec.status}', not applied"}
        n = session.query(TemplateParamOverrideORM).filter(
            TemplateParamOverrideORM.source_recommendation_id == rec_id,
            TemplateParamOverrideORM.status == "active",
        ).update({"status": "reverted", "reverted_at": datetime.now()},
                 synchronize_session=False)
        rec.status = "reverted"
        rec.reverted_at = datetime.now()
        rec.reviewer = reviewer
        note = "override deactivated" if n else "no active override (live_strategies change must be reverted manually)"
        rec.notes = (rec.notes or "") + f"; reverted: {note}"
        session.commit()
        invalidate_cache()
        return {"success": True, "message": f"reverted ({note})"}
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()
