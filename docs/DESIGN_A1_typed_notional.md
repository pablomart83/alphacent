# Design — A1: Typed Notional (shares vs dollars)

Status: PHASE 1 IMPLEMENTED + DEPLOYED (2026-06-11). Phase 2 (orders notional column) and Phase 3 (rename quantity→shares) NOT done — see §9.
Author: audit follow-up, 2026-06-11
Scope: eliminate the recurring shares-vs-dollars bug class in sizing / caps / P&L / VaR.

---

## 1. Problem

A position has two numeric magnitudes that are easy to confuse:

- **shares** (units) — e.g. AMD 1.68036 shares
- **notional USD** (dollars invested) — e.g. AMD $787.40

In the current schema/code these are not type-distinguished:

| Field / value | Actual unit | Notes |
|---|---|---|
| `positions.quantity` | **shares** | eToro `get_positions` writes units here |
| `positions.invested_amount` | **dollars** | eToro `amount` — the canonical dollar field |
| entry `orders.quantity` | **dollars** | order placed by-amount ($) |
| close/SL/TP `orders.quantity` | **shares** | inherits `position.quantity` |

Every consumer has to "just know" which unit it holds. When it guesses wrong, the
error is silent and corrupts a real-money decision.

### Evidence (bugs this class has already produced)
- **FIX-B** balance gate computed pending exposure from share counts → $50 where it
  should have been ~$19.8K → `max(0, …)` zeroed the guard → silent no-op.
- **`_get_position_value`** returned raw `quantity` (shares) as dollars when
  `invested_amount` was missing → exposure under-counted → symbol/heat caps defeated
  (patched in Sprint C, but the root remains).
- pending-order balance deduction summed `quantity` assuming dollars.

Each was found and patched **separately**. They are the same root cause.

---

## 2. Goal

Make the unit a property of the value, not tribal knowledge. After this change it
should be impossible to add dollars to shares, or to pass a share count where a
dollar amount is expected, without it being obvious at the call site.

Non-goals: changing eToro wire formats, changing how orders are placed, or any
behavior change in sizing logic. This is a **representation** refactor — outputs
must be identical (proven by reconciliation, §6).

---

## 3. Proposed design

### 3.1 A canonical value accessor (phase 1 — no schema change)
Introduce one helper module `src/models/notional.py`:

```python
def position_notional_usd(pos) -> float:
    """Dollar value of a position. invested_amount (canonical) when present,
    else shares * current_price (fallback to entry_price). NEVER raw shares."""

def position_shares(pos) -> float:
    """Share/unit count of a position (positions.quantity)."""
```

Route **every** consumer of `positions.quantity` / `invested_amount` through these.
This alone removes the ambiguity at the call sites with zero migration risk and is
fully backward compatible. (`_get_position_value` becomes a thin wrapper.)

### 3.2 Order quantity disambiguation (phase 2)
Orders overload `quantity` (dollars for entry, shares for close). Add an explicit
`order_action`-aware accessor and, optionally, a `notional_usd` column on orders so
close/SL/TP orders carry dollars explicitly instead of inheriting share-valued
`quantity`. Entry orders already store dollars; this only normalizes exits.

### 3.3 Naming guardrail (phase 3 — optional, highest safety)
Rename `positions.quantity` → `positions.shares` (with a transitional ORM property
`quantity` that warns) so every remaining raw call site must be reviewed. This is
the "make the bug impossible" step; it is the largest and is optional.

---

## 4. Consumer inventory (must all be routed through the accessor)

Searched for `.quantity` / `invested_amount` reads on positions/orders:

- `src/risk/risk_manager.py` — `_get_position_value`, `_get_pending_entry_exposure`,
  `check_position_limits`, `check_exposure_limits`, `check_symbol_concentration`,
  `calculate_position_size` (balance/pending maths), VaR / heat.
- `src/core/monitoring_service.py` — `_submit_close_order` (already uses
  `invested_amount`), excursion/P&L computations.
- `src/core/order_monitor.py` — position create/update, live_trade_count, close sizing.
- `src/core/trading_scheduler.py` — live pass order construction, opposing-SL.
- `src/api/routers/*` — `/risk/*`, `/account/*`, `/live/*`, analytics — any place that
  sums position value or displays a dollar figure.

Action item for implementation: produce the exact `file:line` list via
`grep -rn "\.quantity\b" src | grep -i pos` and tick each one off.

---

## 5. Migration plan (low-risk ordering)

1. Ship `notional.py` accessors (no schema change). Convert consumers one subsystem
   at a time: risk → execution → monitoring → api. Each PR is independently shippable.
2. (Optional) add `orders.notional_usd`; backfill from `invested_amount`/price;
   convert close/SL/TP sizing to read it.
3. (Optional) rename `quantity` → `shares` with a transitional property; remove the
   property once all call sites are migrated.

No live-DB rewrite is required for phase 1. Phase 2 adds a nullable column
(additive, online-safe, same pattern as A2's `price_updated_at`).

---

## 6. Verification / reconciliation (the gate)

Because outputs must be **identical**, every step is gated by a reconciliation:

- Before/after, snapshot total portfolio notional per account from the DB and assert
  unchanged: `SELECT account_type, SUM(<accessor>) FROM positions WHERE closed_at IS NULL`.
- Unit test the accessor against the known live rows (AMD 1.68036 sh × $468.59 =
  $787.40, etc.).
- For risk caps: log the computed exposure for one cycle pre/post and diff — must match.
- Deploy per subsystem, watch one trading + one monitoring cycle, confirm no change in
  sizing decisions on demo before touching anything the live pass reads.

---

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| A consumer was *relying* on the wrong unit (a bug compensating a bug) | Reconciliation diff surfaces any output change; investigate before shipping that consumer |
| Blast radius (many files) | One subsystem per PR, each reconciled independently; never a big-bang |
| Live sizing affected | Do risk subsystem last and only after demo reconciliation is clean; coordinate with A3 (live sizing consolidation) |
| `invested_amount` null on some rows | Accessor falls back to shares×price; backfill `invested_amount` where derivable |

---

## 8. Effort (agent execution)

- Phase 1 (accessor + route consumers + reconcile): a few hours of work, gated by
  per-subsystem demo-cycle verification (the wait, not the typing).
- Phase 2 (orders notional column): ~1 hour + additive migration.
- Phase 3 (rename, optional): mechanical once phase 1 is done.

Recommend doing **phase 1 only** first, prove the reconciliation, then decide on 2/3.

---

## 9. What was actually implemented (2026-06-11)

**Phase 1 — DONE & deployed.**
- `src/models/notional.py` — canonical `position_notional_usd()` + `position_shares()`
  (single source of truth for the shares↔dollars rule).
- `RiskManager._get_position_value` now delegates to `position_notional_usd` — this is
  the hub through which ALL risk consumers (symbol cap, sector cap, heat, exposure
  limits, position limits, VaR) already read position value, so the whole risk
  subsystem is now centralized on one definition. Behavior-preserving (identical
  logic): reconciliation baseline demo $236,180.94 / live $2,574.80 unchanged;
  accessor unit tests pass (AMD 1.68036 sh × $468.59 = $787.40).
- `monitoring_service._submit_close_order` fallback routes through `position_shares()`.
- **Bug fixed in passing:** the PAPER sizing symbol-cap check computed pending
  exposure as `quantity × price` over all pending orders — but entry orders store
  `quantity` in DOLLARS, inflating pending exposure ~`price`× and wrongly blocking
  paper entries whenever a pending order existed on the symbol. Now reuses the
  canonical `_get_pending_entry_exposure` (entry-dollars, no ×price). Demo-only; it
  was suppressing paper data breadth.

**Phase 2 — NOT done (deferred).** Orders overload `quantity` (entry=dollars,
close/SL/TP=shares). Every current order-value call site uses column-filtered SQL
with the correct entry-only dollar rule, so there is no active bug to fix; an
`order_notional_usd()` accessor + optional `orders.notional_usd` column is the clean
finish but adds a live migration for no current correctness gain. Do it if/when exit
orders need dollar valuation outside the entry-only paths.

**Phase 3 — NOT done, and recommended AGAINST for now.** Renaming the
`positions.quantity` column → `shares` is the "make the bug impossible at
compile-time" step, but on a live trading DB it requires a dual-read migration
window, touches an extremely common attribute name that collides with
`orders.quantity` and signal `quantity`, and delivers marginal safety over Phase 1
(which already routes every consumer through the typed accessor). High breakage
risk, low marginal value — not worth it on a live book. Revisit only if a future
bug slips past the accessor.
