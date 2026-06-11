"""Canonical price-freshness definitions (A2 — staleness predicate unification).

`positions.price_updated_at` is the single source of truth for "how fresh is this
position's current_price" — it is stamped by the position sync on every position
present on eToro that cycle. Multiple subsystems need this judgement (TSL breach
enforcement, the TSL pre-breach resync guard, observability/Intel freshness), and
the 180s SLA literal + the age arithmetic had been copy-pasted across them with
drift. This module is the one place that defines both.

Scope note: this is about POSITION PRICE freshness (current_price). It is distinct
from (a) historical-bar freshness used by the SL-recalc/ATR path and Intel D1/D2,
and (b) the live EQUITY-snapshot staleness watched by FIX-09 — those measure
different data and keep their own thresholds. Do not conflate them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

# 3× the 60s position-sync cadence — a position whose price_updated_at is older
# than this has missed multiple syncs and its current_price can no longer be
# trusted for a breach decision without a forced resync.
PRICE_FRESHNESS_SLA_S: float = 180.0


def position_price_age_seconds(position_orm) -> Optional[float]:
    """Seconds since this position's current_price was last synced from eToro.

    Returns None when price_updated_at is unset (e.g. not yet stamped after a
    migration) — callers should treat None as "unknown", never as "fresh".
    """
    ts = getattr(position_orm, "price_updated_at", None)
    if not ts:
        return None
    return (datetime.utcnow() - ts).total_seconds()


def is_position_price_stale(
    position_orm, sla_s: float = PRICE_FRESHNESS_SLA_S
) -> bool:
    """True when the position's price is older than the SLA. Unknown age (no
    price_updated_at) is NOT treated as stale here — the caller decides how to
    handle unknown (breach enforcement, e.g., still acts but annotates)."""
    age = position_price_age_seconds(position_orm)
    return age is not None and age > sla_s
