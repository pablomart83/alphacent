"""MAE/MFE → SL/TP recommendation engine (Tier 1, Path B → Path A output).

Generalises scripts/diagnose_symbol_edge.py (the analysis that cracked SOXL)
into a scheduled job that emits **evidence-backed SL/TP recommendations** —
PROPOSALS ONLY. Nothing is applied automatically; each recommendation is
persisted to `improvement_recommendations` as 'pending' and only takes effect
when the CIO approves it through the approval rail (Path A).

Method (per cohort — per symbol, and per template×asset-class):
  - Use closed trades with TRACKED excursions (max_favorable/adverse_excursion
    are stored as fractions; many older trades have 0 and are excluded).
  - MAE (adverse excursion, |·|) = the heat a trade took before it resolved.
    If winners routinely take more heat than the current stop, the stop is too
    tight and is cutting winners off (the SOXL signature: avg MFE +11%, stops
    at 6% on a 3x ETF whose daily ATR is 6-10%). → recommend WIDENING the stop
    toward the MAE the cohort actually needs, capped at sl_caps.
  - If the cohort barely uses its stop (MAE p90 ≪ current stop) the stop is
    needlessly wide and bleeds loss size. → recommend TIGHTENING (conservative).
  - MFE (favorable excursion) vs realized return = how much of the move we
    keep. If trades routinely reach an MFE well above the current target while
    we realize far less, the target/trail is leaving money. → recommend RAISING
    the target toward the MFE the cohort actually reaches.

Every recommendation is bounded by sl_caps (sl_cap_pct / a TP sanity cap) and
carries its evidence (n, current vs proposed, MAE/MFE percentiles, expected
capture gain). Conservative thresholds: only material, well-sampled changes.

ATR noise floor (volatility constraint): a recommendation is never allowed to
propose a stop below the instrument's ATR floor (1.5x daily ATR), because a
stop inside the noise band gets stopped out before any edge plays out — and
execution enforces exactly this floor at order time. Flooring it here is what
makes a CIO-approved recommendation EQUAL to what actually executes, instead of
being silently widened at order time (see src/risk/atr_stop.py).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.risk.sl_caps import sl_cap_pct, is_leveraged_etf

logger = logging.getLogger(__name__)

MIN_TRADES = 12            # below this a cohort's MAE/MFE distribution is noise
LOOKBACK_DAYS = 120

# Asset-class default SL/TP (fractions) — used as "current" when a symbol has no
# live_strategies row. Mirrors the documented per-asset-class risk params.
_DEFAULT_SL_TP = {
    "stocks": (0.06, 0.15),
    "etfs": (0.06, 0.15),
    "forex": (0.02, 0.05),
    "crypto": (0.08, 0.20),
    "indices": (0.05, 0.12),
    "commodities": (0.04, 0.10),
}
_LEVERAGED_SL_TP = (0.15, 0.35)   # SOXL/TQQQ live params after the leveraged-ETF fix
_TP_SANITY_CAP = 0.60             # don't propose a target beyond +60% (per-trade)

# Material-change thresholds (avoid churning tiny tweaks).
_WIDEN_MIN_RATIO = 1.20           # proposed SL must be ≥ 20% wider to recommend
_TIGHTEN_MAX_RATIO = 0.60         # MAE p90 < 60% of stop ⇒ stop unused ⇒ tighten
_RAISE_TP_MIN_RATIO = 1.30        # MFE p50 ≥ 130% of current TP ⇒ leaving money
_GIVE_BACK_MAX_CAPTURE = 0.50     # realized < 50% of MFE ⇒ giving the move back


def _asset_class(symbol: str) -> str:
    try:
        from src.core.symbol_registry import get_registry
        return (get_registry().get_asset_class(symbol) or "unknown").lower()
    except Exception:
        return "unknown"


def _default_sl_tp(symbol: str, asset_class: str) -> Tuple[float, float]:
    if is_leveraged_etf(symbol):
        return _LEVERAGED_SL_TP
    return _DEFAULT_SL_TP.get(asset_class, (0.06, 0.15))


def _active_override_sl_tp(session, scope_key: str) -> Optional[Tuple[float, float]]:
    """(sl, tp) from the ACTIVE template_param_override for this scope_key, or
    None. So a recommendation whose change is ALREADY APPLIED is not re-proposed
    every run — 'current' must reflect what is actually in effect."""
    try:
        from sqlalchemy import text
        row = session.execute(text("""
            SELECT sl_pct, tp_pct FROM template_param_overrides
            WHERE scope_key = :k AND status = 'active'
            ORDER BY id DESC LIMIT 1
        """), {"k": scope_key}).fetchone()
        if row and row[0]:
            return float(row[0]), float(row[1] or 0.0)
    except Exception as e:
        logger.debug("active override lookup failed for %s: %s", scope_key, e)
    return None


def _current_sl_tp(session, symbol: str, asset_class: str) -> Tuple[float, float, str]:
    """(sl, tp, source). Precedence: active param override > per-pair live params
    > asset-class default. The override must win so applied recommendations
    aren't re-proposed."""
    ov = _active_override_sl_tp(session, symbol.upper())
    if ov:
        return ov[0], ov[1], "active_override"
    try:
        from sqlalchemy import text
        row = session.execute(text("""
            SELECT sl_pct, tp_pct FROM live_strategies
            WHERE UPPER(symbol) = :sym AND sl_pct IS NOT NULL
            ORDER BY id DESC LIMIT 1
        """), {"sym": symbol.upper()}).fetchone()
        if row and row[0]:
            return float(row[0]), float(row[1] or 0.0), "live_strategies"
    except Exception as e:
        logger.debug("live_strategies lookup failed for %s: %s", symbol, e)
    sl, tp = _default_sl_tp(symbol, asset_class)
    return sl, tp, "asset_class_default"


class _Cohort:
    __slots__ = ("pnl_frac", "mae_abs", "mfe", "exit_reason")

    def __init__(self):
        self.pnl_frac: List[float] = []
        self.mae_abs: List[float] = []
        self.mfe: List[float] = []
        self.exit_reason: List[str] = []

    def add(self, pnl_pct, mae, mfe, exit_reason):
        try:
            self.pnl_frac.append(float(pnl_pct) / 100.0)
            self.mae_abs.append(abs(float(mae)))
            self.mfe.append(float(mfe))
            self.exit_reason.append((exit_reason or "").lower())
        except (TypeError, ValueError):
            pass

    def __len__(self):
        return len(self.pnl_frac)


def _pct(arr: List[float], q: float) -> float:
    if not arr:
        return 0.0
    return float(np.percentile(np.array(arr, dtype=float), q))


def _analyse_cohort(
    coh: _Cohort, current_sl: float, current_tp: float, cap_sl: float,
    atr_floor: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Return a recommendation dict for this cohort, or None if no material,
    well-evidenced change is warranted."""
    n = len(coh)
    if n < MIN_TRADES:
        return None

    pnl = np.array(coh.pnl_frac)
    mae = np.array(coh.mae_abs)
    mfe = np.array(coh.mfe)
    win_mask = pnl > 0

    mae_p50, mae_p80, mae_p90 = _pct(coh.mae_abs, 50), _pct(coh.mae_abs, 80), _pct(coh.mae_abs, 90)
    mfe_p50, mfe_p75 = _pct(coh.mfe, 50), _pct(coh.mfe, 75)
    realized_median = float(np.median(pnl))
    winners_mae_p75 = _pct(list(mae[win_mask]), 75) if win_mask.any() else 0.0

    # Premature stop-outs: stopped while already above the stop distance in MFE.
    stop_terms = ("stop_loss_hit", "trailing stop", "stop ")
    stopped = np.array([any(t in r for t in stop_terms) for r in coh.exit_reason])
    premature = int(np.sum(stopped & (mfe > current_sl)))
    premature_frac = premature / n if n else 0.0

    proposed_sl = current_sl
    proposed_tp = current_tp
    actions: List[str] = []

    # --- Stop loss ---
    # Widen: winners are taking more heat than the stop, or many premature stops.
    widen_target = round(min(max(mae_p80 * 1.10, winners_mae_p75 * 1.05), cap_sl), 4)
    if (winners_mae_p75 > current_sl or premature_frac > 0.15) and widen_target >= current_sl * _WIDEN_MIN_RATIO:
        proposed_sl = widen_target
        actions.append(
            f"widen SL {current_sl:.1%}→{proposed_sl:.1%} (winners' MAE p75={winners_mae_p75:.1%}, "
            f"premature stops={premature}/{n})"
        )
    # Tighten: the stop is barely used (deepest 10% of heat well inside it).
    elif mae_p90 > 0 and mae_p90 < current_sl * _TIGHTEN_MAX_RATIO:
        tighten_target = round(max(mae_p90 * 1.15, 0.01), 4)
        if tighten_target < current_sl * 0.9:
            proposed_sl = tighten_target
            actions.append(
                f"tighten SL {current_sl:.1%}→{proposed_sl:.1%} (MAE p90={mae_p90:.1%} ≪ stop — "
                f"unused headroom bleeds loss size)"
            )

    # --- ATR noise floor (volatility constraint) ---
    # A stop tighter than the instrument's volatility floor (1.5-2x ATR) sits
    # inside normal noise and gets stopped out before the MAE-optimal level ever
    # matters — and execution enforces exactly this floor at order time. So never
    # recommend (or leave) a stop below it; raise the proposal to the floor. This
    # is what makes a CIO-approved recommendation equal to what actually executes,
    # instead of being silently widened at order time.
    if atr_floor and atr_floor > 0:
        floored_sl = round(min(atr_floor, cap_sl), 4)
        if proposed_sl < floored_sl and abs(floored_sl - current_sl) >= max(0.005, current_sl * 0.15):
            mae_wanted = proposed_sl
            # The floor supersedes any MAE-based widen/tighten on the SL itself.
            actions = [a for a in actions if not (a.startswith("widen SL") or a.startswith("tighten SL"))]
            actions.insert(
                0,
                f"set SL to ATR floor {current_sl:.1%}→{floored_sl:.1%} "
                f"(instrument noise floor {atr_floor:.1%}; MAE-optimal {mae_wanted:.1%} "
                f"would be noise-stopped — approval now matches execution)"
            )
            # Preserve R:R on the TP if it wasn't independently raised below.
            if proposed_tp <= current_tp and current_sl > 0:
                _rr = current_tp / current_sl if current_sl > 0 else 2.0
                proposed_tp = round(min(floored_sl * _rr, _TP_SANITY_CAP), 4)
            proposed_sl = floored_sl

    # --- Take profit / capture ---
    capture = (realized_median / mfe_p50) if mfe_p50 > 0 else 1.0
    raise_tp_target = round(min(mfe_p50, _TP_SANITY_CAP), 4)
    if (mfe_p50 >= current_tp * _RAISE_TP_MIN_RATIO or capture < _GIVE_BACK_MAX_CAPTURE) \
            and raise_tp_target > current_tp:
        proposed_tp = raise_tp_target
        actions.append(
            f"raise TP {current_tp:.1%}→{proposed_tp:.1%} (MFE p50={mfe_p50:.1%}, "
            f"capture={capture:.0%} of the move)"
        )

    if not actions:
        return None

    expected_capture_gain = round(max(0.0, mfe_p50 - realized_median), 4)
    return {
        "current_sl": round(current_sl, 4),
        "proposed_sl": round(proposed_sl, 4),
        "current_tp": round(current_tp, 4),
        "proposed_tp": round(proposed_tp, 4),
        "n_trades": n,
        "summary": "; ".join(actions),
        "evidence": {
            "mae_p50": round(mae_p50, 4), "mae_p80": round(mae_p80, 4), "mae_p90": round(mae_p90, 4),
            "mfe_p50": round(mfe_p50, 4), "mfe_p75": round(mfe_p75, 4),
            "winners_mae_p75": round(winners_mae_p75, 4),
            "realized_median": round(realized_median, 4),
            "capture_ratio": round(capture, 3),
            "premature_stops": premature,
            "expected_capture_gain": expected_capture_gain,
            "sl_cap": round(cap_sl, 4),
            "atr_floor": round(atr_floor, 4) if atr_floor else None,
            "win_rate": round(float(win_mask.mean()), 3),
        },
    }


def compute_recommendations(
    min_trades: int = MIN_TRADES, lookback_days: int = LOOKBACK_DAYS,
) -> List[Dict[str, Any]]:
    """Compute SL/TP recommendations across cohorts. Read-only; returns the
    list of recommendation dicts (does NOT persist — caller persists)."""
    from sqlalchemy import text
    from src.models.database import get_database

    cutoff = datetime.now() - timedelta(days=lookback_days)
    db = get_database()
    session = db.get_session()
    try:
        rows = session.execute(text("""
            SELECT symbol, pnl_percent, max_adverse_excursion, max_favorable_excursion,
                   exit_reason, (trade_metadata::jsonb)->>'template_name' AS template_name
            FROM trade_journal
            WHERE exit_time IS NOT NULL
              AND exit_time >= :cutoff
              AND pnl_percent IS NOT NULL
              AND (max_favorable_excursion <> 0 OR max_adverse_excursion <> 0)
        """), {"cutoff": cutoff}).fetchall()

        by_symbol: Dict[str, _Cohort] = {}
        by_template_ac: Dict[Tuple[str, str], _Cohort] = {}
        symbol_ac: Dict[str, str] = {}

        for sym, pnl_pct, mae, mfe, exit_reason, tmpl in rows:
            if not sym:
                continue
            sym = sym.upper()
            ac = symbol_ac.get(sym)
            if ac is None:
                ac = _asset_class(sym)
                symbol_ac[sym] = ac
            by_symbol.setdefault(sym, _Cohort()).add(pnl_pct, mae, mfe, exit_reason)
            if tmpl:
                by_template_ac.setdefault((tmpl, ac), _Cohort()).add(pnl_pct, mae, mfe, exit_reason)

        recs: List[Dict[str, Any]] = []

        # Per-symbol (the per-pair analogue — maps to live_strategies params).
        for sym, coh in by_symbol.items():
            if len(coh) < min_trades:
                continue
            ac = symbol_ac.get(sym, "unknown")
            cur_sl, cur_tp, src = _current_sl_tp(session, sym, ac)
            cap = sl_cap_pct(sym)
            # ATR noise floor for this symbol so we never propose a stop the
            # execution layer would just widen back (daily 1.5x ATR — the
            # standard floor; execution applies the precise per-order value).
            try:
                from src.risk.atr_stop import compute_atr_floor_pct
                _atr_floor = compute_atr_floor_pct(sym, is_4h=False)
            except Exception:
                _atr_floor = None
            rec = _analyse_cohort(coh, cur_sl, cur_tp, cap, atr_floor=_atr_floor)
            if rec:
                rec.update({
                    "rec_type": "sl_tp", "scope_type": "symbol", "scope_key": sym,
                    "symbol": sym, "template_name": None, "asset_class": ac,
                    "account_type": ("live" if src == "live_strategies" else None),
                    "current_source": src,
                })
                recs.append(rec)

        # Per (template, asset_class) — the template default for a class.
        for (tmpl, ac), coh in by_template_ac.items():
            if len(coh) < min_trades:
                continue
            scope_key = f"{tmpl}::{ac}"
            # "Current" reflects an applied override if one exists, so an
            # already-applied recommendation is not re-proposed every run.
            cap = {"crypto": 0.15, "forex": 0.04, "indices": 0.09,
                   "commodities": 0.10, "etfs": 0.09, "stocks": 0.09}.get(ac, 0.10)
            ov = _active_override_sl_tp(session, scope_key)
            if ov:
                cur_sl, cur_tp = ov
            else:
                cur_sl, cur_tp = _default_sl_tp("", ac)
            rec = _analyse_cohort(coh, cur_sl, cur_tp, cap)
            if rec:
                rec.update({
                    "rec_type": "sl_tp", "scope_type": "template_asset_class",
                    "scope_key": scope_key, "symbol": None,
                    "template_name": tmpl, "asset_class": ac,
                    "account_type": None,
                    "current_source": ("active_override" if ov else "asset_class_default"),
                })
                recs.append(rec)
    finally:
        session.close()

    return recs


def persist_recommendations(recs: List[Dict[str, Any]]) -> int:
    """Replace the 'pending' set for each scope_key with the fresh computation.
    Applied/rejected/reverted rows are history and are never touched. Returns
    the number of pending recommendations written."""
    from src.models.database import get_database
    from src.models.orm import ImprovementRecommendationORM

    # Robustness: never wipe the pending queue on a completely empty computation.
    # An empty result is more often a transient inability to compute (e.g. the
    # ATR floor needs a MarketDataManager that isn't ready right after a restart)
    # than a genuine "nothing to recommend". Wiping on empty deleted a freshly
    # persisted queue at startup. If there's genuinely nothing, the next run with
    # data will clear stale scopes via the in-scope replace below.
    if not recs:
        logger.info("persist_recommendations: empty computation — leaving existing pending queue untouched")
        return 0

    db = get_database()
    session = db.get_session()
    written = 0
    try:
        scope_keys = {r["scope_key"] for r in recs}
        if scope_keys:
            session.query(ImprovementRecommendationORM).filter(
                ImprovementRecommendationORM.rec_type == "sl_tp",
                ImprovementRecommendationORM.status == "pending",
                ImprovementRecommendationORM.scope_key.in_(scope_keys),
            ).delete(synchronize_session=False)
        # Also clear stale pending recs that no longer recur (cohort changed).
        session.query(ImprovementRecommendationORM).filter(
            ImprovementRecommendationORM.rec_type == "sl_tp",
            ImprovementRecommendationORM.status == "pending",
            ~ImprovementRecommendationORM.scope_key.in_(scope_keys or {"__none__"}),
        ).delete(synchronize_session=False)

        for r in recs:
            session.add(ImprovementRecommendationORM(
                created_at=datetime.now(),
                rec_type=r["rec_type"], scope_type=r["scope_type"], scope_key=r["scope_key"],
                symbol=r.get("symbol"), template_name=r.get("template_name"),
                asset_class=r.get("asset_class"), account_type=r.get("account_type"),
                current_sl=r.get("current_sl"), proposed_sl=r.get("proposed_sl"),
                current_tp=r.get("current_tp"), proposed_tp=r.get("proposed_tp"),
                n_trades=r.get("n_trades"), summary=r.get("summary"),
                evidence=r.get("evidence"), status="pending",
            ))
            written += 1
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error("persist_recommendations failed: %s", e)
        raise
    finally:
        session.close()
    return written


def compute_and_store(
    min_trades: int = MIN_TRADES, lookback_days: int = LOOKBACK_DAYS,
) -> Dict[str, Any]:
    """Compute + persist. Returns a small summary for logs/endpoints."""
    recs = compute_recommendations(min_trades=min_trades, lookback_days=lookback_days)
    written = persist_recommendations(recs)
    logger.info("SL/TP recommender: %d recommendations (%d pending persisted)", len(recs), written)
    return {
        "computed_at": datetime.now().isoformat(),
        "recommendations": len(recs),
        "pending_written": written,
    }
