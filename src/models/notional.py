"""
A1 — typed notional: the single source of truth for "shares vs dollars".

A position/order carries two magnitudes that are trivially confused:
  - SHARES (units)      — e.g. AMD 1.68036 shares
  - NOTIONAL USD ($)    — e.g. AMD $787.40 invested

eToro / our schema overload `quantity`:
  - positions.quantity        = SHARES (units)              ← NOT dollars
  - positions.invested_amount = NOTIONAL USD (canonical $)
  - entry orders.quantity     = NOTIONAL USD ($, by-amount order)
  - close/SL/TP orders.quantity = SHARES (inherited from the position)

Confusing the two silently corrupts sizing, caps, heat, VaR, balance gates and
P&L (see FIX-B, the _get_position_value share-fallback, the paper pending-exposure
bug). This module centralises the unit logic so every consumer asks for the
magnitude it actually wants, by name, instead of guessing from `quantity`.

These helpers accept any object exposing the relevant attributes (PositionORM,
the Position dataclass, OrderORM) — duck-typed on purpose so both layers share
one definition.
"""
from __future__ import annotations

from typing import Any


def position_shares(pos: Any) -> float:
    """Share/unit count of a position (positions.quantity is units)."""
    return float(getattr(pos, "quantity", 0) or 0.0)


def position_notional_usd(pos: Any) -> float:
    """Dollar value (capital invested) of a position.

    `invested_amount` is the canonical dollar field (eToro `amount`). When it is
    missing/zero, `quantity` is SHARES — convert to dollars via current_price
    (falling back to entry_price). NEVER returns a raw share count as dollars.
    """
    invested = getattr(pos, "invested_amount", None)
    if invested and invested > 0:
        return float(invested)
    shares = float(getattr(pos, "quantity", 0) or 0.0)
    price = float(
        getattr(pos, "current_price", None)
        or getattr(pos, "entry_price", None)
        or 0.0
    )
    if shares and price:
        return shares * price
    # Last resort: raw quantity (legacy). Better than 0 for the cap maths, but
    # this path means we have neither invested_amount nor a usable price.
    return shares


# NOTE: an order-level `order_notional_usd(order)` accessor (entry orders =
# dollars, close/SL/TP = shares × price) belongs here too, but every current
# order-value call site queries specific columns (not order objects) and already
# applies the entry-only dollar rule correctly (see RiskManager.
# _get_pending_entry_exposure). It will be added when the orders notional work
# (A1 phase 2) is done, to avoid shipping an unused function now.
