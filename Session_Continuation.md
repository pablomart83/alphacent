# AlphaCent — Session Continuation

> Permanent rules are in `.kiro/steering/trading-system-context.md`. This file holds current system state, recent fixes, and open items.

---

## ⚡ NEXT SESSION KICKOFF

**Sprint 13 complete (Jun 10 2026). 14 crash-audit fixes + 6 Intel fixes + 6 P1 improvements + 3 session-corruption fixes deployed. Live account updated to $1,300 real / 0.127 mirror ratio. Pullback gate recalibrated. System actively trading again.**

---

## SESSION 2026-06-10 — SPRINT 13: POST-CRASH AUDIT + DEEP FIXES

### Context
Platform ran unattended for 7+ days. Two market crashes (Jun 5 and Jun 9). Full forensic audit via Intel page + DB queries. System had fundamental issues that prevented crash response. All are now fixed.

---

### SPRINT 13a — Crash Audit Fixes (commit `2ba01e0`)

| Fix | What |
|---|---|
| FIX-01 | Intraday circuit breaker — LIVE only, halts new entries if equity drops >1.5% in 2h |
| FIX-03 | Leveraged ETF rules — SOXL/TQQQ/UPRO: 4% SL cap, 0.5× sizing on LIVE entries |
| FIX-04 | `_check_fundamental_exits` uses isolated session + explicit rollback (InFailedSqlTransaction) |
| FIX-05 | Guard `pending_*` etoro_position_id before close — force sync, CRITICAL log if unresolvable |
| FIX-06 | Intraday stress flag — SPY open→current < -1.5% logs WARNING each cycle |
| FIX-07 | TSL minimum lock buffer — 0.5× ATR min distance prevents noise-level breaches |
| FIX-08a | SHORT signal priority queue — SHORTs evaluated before LONGs for demo balance access |
| FIX-08b | activation_approved BACKTESTED bypass — newly-approved strategies bypass interval filter |
| FIX-09 | Live equity staleness watchdog — CRITICAL + force-resync if LIVE snapshot >60min stale |
| FIX-10 | FRED rate limit backoff — 429 detected → 300s backoff, no retry storm |
| FIX-11 | DB-computed balance gate — `equity-invested-pending` replaces eToro spot credit |
| FIX-14 | Removed stale `market_regime: trending_up_strong` from May 18 in autonomous_trading.yaml |
| FIX-15 | Fixed `MACD().shift(1)` DSL syntax → `MACD() CROSSES_ABOVE MACD_SIGNAL()` |

### SPRINT 13b — Intel Findings Fixes (commit `581362d`)

| Fix | What |
|---|---|
| Intel-A2 | SQL now compares `opened_at > pending_retirement_at` (false positive fix) |
| Intel-A3 | `live_trade_count` uses isolated session in order_monitor + backfilled 162 strategies |
| Intel-A4/G9 | WF primary path consistency gate `(test-train ≤ 1.5)` added; 24 regime-luck strategies retired |
| Intel-E5 | E5 no longer flags market-condition gates (pullback/MQS/drawdown) as permanent loops |
| Intel-A10 | Overtrading check counts entry orders only, not exits |
| Intel-C2 | Real portfolio heat formula (invested×SL_pct/equity), downgraded to P2 for paper |
| Intel-F7 | Yahoo batch download: 3-attempt retry with 5s/25s backoff |
| Intel-F7 | FRED: 429 → 300s backoff (commit `df4b0d9`) |
| DB cleanup | `signal_decisions`: pruned 294k stale rows (70%), added composite index `(strategy_id, stage, timestamp)` |
| DB cleanup | 24 regime-luck strategies retired directly in DB |
| DB cleanup | Backfilled `live_trade_count` for 162 strategies from filled orders |

### SPRINT 13c — P1 Improvements (commit `2b44eee`)

| Fix | What |
|---|---|
| NEW-01 | Intraday regime detection: MQS grade capped at "normal" if SPY intraday <-1.5%, forced "low" if <-2.5% |
| NEW-02 | Live SL/TP regime multiplier: tightens stops at signal time (0.75× mild, 0.60× severe) |
| NEW-03 | TSL activation lower for LIVE: 3% stock (vs 5% paper), 1.8% breakeven (vs 3% paper) |
| NEW-04 | Retirement gate: `min_live_trades_before_evaluation: 3` (was 5); dollar-loss threshold 30% of CIO size |
| NEW-05 | COPPER live SL fixed: 6% → 4% (commodity). Graduation gate validates SL vs asset-class max |
| NEW-06 | `signal_decisions` stage-aware retention: 14d for high-volume diagnostic stages, 30d for audit stages |

### Pullback Gate Recalibration (commit `b1b8481`)

**Root cause of system sitting idle with $364K free balance and 302 BACKTESTED strategies:**
- Mild pullback (-1.4%, RSI 36) was blocking ALL trend entries — 172 blocks per cycle
- 228/302 strategies are trend_following — the gate was blocking 75% of the universe on routine weekly oscillation
- Keyword match `'trend'` caught nearly every template name

**Fix:** Severity-aware blocking:
- **Mild** (-1% to -2%): only block intraday/aggressive templates (breakout, momentum, ATR dynamic)
- **Moderate** (-2% to -3.5%): block intraday + broad trend (EMA ribbon, ADX)
- **Severe** (>-3.5%): block all trend LONGs (unchanged)

Daily trend strategies now correctly enter on mild pullbacks — that's when they're supposed to.

### Live Session Corruption Fixes (commits `7d0aae4`, `28911e1`, `42aa454`)

**Root cause identified:** `InFailedSqlTransaction` cascade. The FMP call at 12:37 UTC leaves the shared DB session in an aborted state. All subsequent queries in the same session fail silently or raise. This caused:
1. DELL orphan position (Jun 10 10:43) — live order committed to eToro but DB write failed
2. PANW triple-position — duplicate guard read stale/no data, 3 separate entries placed

Three layers of defense deployed:
1. **Live order write**: isolated session (can't be rolled back by main cycle exceptions)
2. **Duplicate guard**: isolated session (always reads fresh position data)
3. **Root fix** (`database.py`): `get_session()` now calls `session.rollback()` on checkout — aborted transaction state is cleared before any caller sees the connection. Cost: 0.1ms. Also added `session_scope()` context manager for new code.

---

### Operational Changes

**Live account updated:**
- Real investment: $1,000 → $1,300 (added $300 to Agent Portfolio)
- Mirror ratio: 0.10 → 0.127 (recalculated as $1,300 / $10,239 virtual equity)
- UI now shows correct real equity (~$1,300)

**PANW duplicate positions closed:**
- Closed: `3473111498` (Jun 8 entry $267.83, -$7) and `3476155097` (Jun 10 13:33 entry $258.75, +$21)
- Kept: `3476115401` (Jun 10 13:16 entry $255.2, breakeven stop, +$39)

---

## CURRENT SYSTEM STATE (2026-06-10 end of session)

- **DEMO equity:** ~$535K | **Open positions:** ~55 PAPER | **Regime:** trending_up_weak (normal)
- **DEMO balance (free):** ~$385K | **Deployed:** ~$147K
- **LIVE strategies:** 14 active (DELL, MU×4, COPPER, PANW, TQQQ, SOXL, TXN, INTC, XLK, GOOGL, AMD)
- **LIVE equity:** ~$10,240 virtual / ~$1,300 real | **Mirror ratio:** 0.127
- **LIVE open positions:** 6 (AMD, DELL, MU, COPPER, INTC, PANW)
- **BACKTESTED strategies:** 302 (approved, generating signals)
- **Pullback gate:** ACTIVE (mild, -1.4% 5d SPY) — only blocks intraday/aggressive, not daily trend
- **Latest commits:** `42aa454` (DB session fix) → `28911e1` (duplicate guard) → `7d0aae4` (live order write) → `b1b8481` (pullback gate) → `2b44eee` (P1 fixes) → `581362d` (Intel fixes) → `2ba01e0` (crash audit fixes)

---

## OPEN ITEMS (P1/P2)

### P2 — This Month
- **NEW-07**: TQQQ in live book — review whether 3× leveraged ETF belongs in medium-term strategy. FIX-03 applies 4% SL / 0.5× sizing but may still be wrong instrument.
- **NEW-08**: `cancel_stale_orders` 404 dead end — after 404 on cancel, schedule 4h re-check; if still PENDING + no fill, mark CANCELLED.
- **NEW-09**: `backtested_ttl_cycles: 168` — review whether 72 is more appropriate (currently 3.5 days, effectively 10.5 days for 4H).
- **NEW-10**: TSL breach enforcement — add price freshness check before breach evaluation (stale `current_price` can cause missed or ghost breaches).

### Architecture (no rush)
- **G-01**: WF test-dominant consistency gate (already partially added in Sprint 13)
- **G-09**: Correlation dedup at graduation approval (LIVE only) — already removed from concern given multi-strategy-per-symbol is intentional
- **G-19**: Real slippage model from trade_journal data

---

## KEY NUMBERS TO TRACK NEXT SESSION

When checking logs/DB next session, verify:
1. **No new `InFailedSqlTransaction` errors** in errors.log (root fix deployed)
2. **PANW has exactly 1 open live position** (3476115401)
3. **DEMO book actively opening new positions** (pullback gate fix — daily trend entries should be flowing)
4. **Intel findings count** — should be significantly lower after all Intel fixes; run a new Intel scan
5. **live_trade_count** — should be incrementing correctly for new fills
6. **signal_decisions table size** — should stay manageable with new retention policy
7. **TSL summary log line** — check for `min_buffer_pct` appearing in trail logs (FIX-07 active)
8. **Live order writes** — check errors.log for any "CRITICAL — order DB write failed" (new isolation fix)

---

## SESSION 2026-05-25 — (earlier history below, unchanged)

### Trade Journal Integrity Fix
`log_exit` fallback had no account_type filter — corrupted demo/live P&L separation. Fixed commit `f79fbec`. 0 mismatches after fix.

## SESSION 2026-05-18 — Watchlist Elimination
Every strategy is now a single (template, symbol) pair. Commits `e70a2f5`, `3bd873f`, `b291073`. 0 multi-symbol strategies remaining.

## SESSION 2026-05-17 — G-43 + G-44/G-45 + P1 Batch
- G-43: Paper conviction threshold 60/55 (was 73/67) — commit `b1378e1`
- G-44/G-45: LIVE pass wired to full risk framework — commit `8d07eef`
- P1 batch: G-46/G-48/G-50 PAPER gate relaxations — commit `c158650`

## CURRENT LIVE STRATEGIES (as of Jun 10)
14 LIVE strategies. All trend-following. All LONG. No shorts yet in live book (graduation pipeline needs more short paper trades to accumulate).

| Strategy | Symbol | CIO Size | SL | Status |
|---|---|---|---|---|
| EMA Ribbon Expansion Long DELL LIVE | DELL | $100r | 6% | open |
| 4H EMA Ribbon Trend Long MU LIVE | MU | $100r | 6% | open |
| 4H Strong Uptrend Momentum MU LIVE | MU | $100r | 6% | no position |
| ATR Expansion Breakout MU LIVE | MU | $100r | 6% | no position |
| Triple EMA Alignment MU LIVE | MU | $100r | 6% | no position |
| Dual MA Volume Surge COPPER LIVE | COPPER | $100r | **4%** (fixed) | open |
| EMA Trend Following PANW LIVE | PANW | $100r | 6% | open (1 position) |
| EMA Ribbon Expansion Long TQQQ LIVE | TQQQ | $100r | 6% | no position |
| 4H EMA Ribbon Trend Long SOXL LIVE | SOXL | $100r | 6% | no position |
| Keltner Channel Breakout TXN LIVE | TXN | $100r | 6% | no position |
| ADX Trend Following INTC LIVE | INTC | $100r | 6% | open |
| 4H EMA Ribbon Trend Long XLK LIVE | XLK | $100r | 6% | no position |
| Triple EMA Alignment MU LIVE | MU | $100r | 6% | no position |
| 4H EMA Ribbon Trend Long GOOGL LIVE | GOOGL | $100r | 6% | no position |
| EMA Trend Following AMD LIVE | AMD | $100r | 6% | open |
