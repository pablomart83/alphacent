# AlphaCent — Session Continuation

> Permanent rules are in `.kiro/steering/trading-system-context.md`. This file holds current system state, recent fixes, and open items.

---

## ⚡ NEXT SESSION KICKOFF

**Sprint C + D complete + follow-ups (Jun 11 2026). A1 now interval-aware (1h/2h→2d, 4h→5d, 1d→10d; 81→39 genuinely-stuck); INTEL_SPEC A1 doc corrected; fixed pre-existing graduation size-estimate 500 (AccountInfo missing mode/updated_at). LIVE BOOK CLEANED UP (CIO actions done): GOOGL, COPPER, TXN retired (losers); SOXL re-graduated (winner, new live_strategies row id 15, position_size 100.4 / conviction_min 72). Active live: AMD, DELL, INTC, MU×4, PANW, SOXL, TQQQ, XLK. COPPER live fully wound down (strategy retired + $1,000 position closed 09:59 UTC via the pending-closure pass). Live-retire endpoint now flags open live positions for closure automatically (commit `8474f3e`).**

**Sprint B complete (Jun 11 2026, 07:36 UTC). Graduation-gate statistical-power fixes deployed & verified live (P0-2).**

---

## SESSION 2026-06-11 — SPRINT C + D

### Sprint C — P2 correctness / quick wins (deployed, commit `65f1e9a`)
| Fix | What |
|---|---|
| market_regime crash | `strategies.py` `get_autonomous_status`: `(full_config.get('market_regime') or {})` — the `{}` default only applied when the key was absent; a present-but-None value crashed the endpoint (errors.log 06-10 11:48). |
| `_get_position_value` units | `risk_manager`: when `invested_amount` missing, value = `quantity × price` (shares→dollars) instead of raw share count (was under-counting exposure, defeating symbol/heat caps). Docstring corrected. |
| Leveraged-ETF consolidation | `position_manager._classify_symbol` now routes through canonical `sl_caps.is_leveraged_etf`; added the previously-divergent NAIL/CURE/DFEN/WANT/HIBL/HIBS to the canonical set (finishes P0-4 consolidation — nothing regresses). |
| NEW-08 404 dead-end | `order_monitor.cancel_stale_orders`: on a 404 cancelling an already-stale (>24h) order with NO open position, mark CANCELLED instead of leaving PENDING forever (status-poll also 404s → infinite churn). If an open position exists, leave for the fill/reconcile path. |
| Graduation queue consistency | `strategies.py` approaching-graduation view now mirrors `is_qualified`'s Wilson WR lower-bound gate, so a Wilson-blocked pair doesn't vanish from both the queue and the approaching list. |
| (verified, no change) | LIVE strategies are already skipped at the top of the autonomous retirement loop (rule #7 satisfied); `auto_retire_strategy` is a legacy no-op. Clarifying comment only. |

### Sprint D — RESEARCH: the "156 zero-signal BACKTESTED strategies" (Intel A1) — FALSIFIED
**Conclusion: A1 was a 100% false positive. There are NO structurally-dead strategies. No mass retirement is warranted.** (commit `<intel>`)

Ground truth (live DB, signal_decisions):
- All 300 BACKTESTED strategies had `performance->>'last_signal_at'` = NULL — not "stale", *never populated*.
- The `performance` JSON only ever contains `{avg_loss, sharpe_ratio, avg_win, sortino_ratio, max_drawdown, win_rate, total_return, total_trades}` — **`last_signal_at` and `paper_trades` keys are never written**.
- Real signal history (signal_decisions): **188/300 BACKTESTED strategies emitted signals in the last 7 days** (22,111 `signal_emitted` rows, 554 orders submitted, 48 fills).
- Of the 171 strategies A1 flagged as "0 signals": **138 emitted in the last 7d, 160 ever, and all 171 submitted orders.**

Root cause: A1 read `strategies.performance->>'last_signal_at'`, a field nothing writes. The `/strategies` API computes last-signal correctly from `signal_decisions` (`strategies.py:667`) — A1 just used the wrong source. **Same root cause broke A6** (its `last_signal_at IS NOT NULL` guard was never true → A6 never fired → a dead "signals firing but not converting to trades" detector, a false negative).

Fix deployed (both checks re-pointed at the real sources):
- **A1** now reads `signal_decisions` (stage=`signal_emitted`). Flagged count drops 171 → **81** (the genuinely-idle-3d+ set, mostly low-frequency daily strategies — not broken). Title reworded "no signal in 3d+", stays P2.
- **A6** now reads `signal_decisions` for signals + `trade_journal` (account_type=demo) for paper trades. Restored from dead → working; currently **0 findings** (signals are converting fine — fires only when a real conviction/gate conversion problem appears).

Minor follow-up (not done): A1's 3-day idle threshold is aggressive for daily strategies (a daily trend strategy idle 3d is normal); consider an interval-aware idle threshold. INTEL_SPEC.md still documents A1 as P1 — stale doc.

**Sprint A complete (Jun 10 2026, 23:27 UTC). Second forensic audit (Opus 4.8) + live-capital correctness fixes deployed & verified live. Service healthy, no post-deploy errors, TSL clean. See "SESSION 2026-06-10 — SPRINT A" below.**

---

## SESSION 2026-06-11 — SPRINT B: GRADUATION RIGOR (P0-2) + LIVE BLEEDER FLAGGING (P0-1)

Deployed `graduation_gate.py` + `config/autonomous_trading.yaml`, restarted 07:36 UTC, health green, zero post-deploy errors.

### P0-2 — graduation gate statistical power (deployed)
Root cause of GOOGL/TXN reaching live: the gate had no real min-trades floor and a point-estimate win-rate gate with no statistical power.

| Fix | What |
|---|---|
| **Hard min_trades floor = 15** | `_get_min_trades_for_interval` used a dynamic Sharpe formula `max(5, ceil((1.96/sharpe)²))` as the PRIMARY path, which collapses to **3–5 trades** for paper_sharpe ≥ 1.0 — i.e. a strategy could graduate to real money on 5 paper trades. The YAML `graduation_gate.min_trades: 15` was LOADED into `MIN_PAPER_TRADES` but never used in this function. Now `MIN_PAPER_TRADES` is enforced as a hard floor the dynamic formula AND the high-conviction exception cannot undercut. (User-set floor = 15.) |
| **Wilson lower-bound win-rate gate** | The point-estimate WR gate (≥55%/type floor) has no power at small n — a sub-floor strategy clears it by luck; with ~300 candidates (multiple testing) false positives are expected (GOOGL 11% WR/18 live, TXN 0%/3). Added a 90%-confidence Wilson lower-bound check on win rate, taken RELATIVE to the strategy-type floor (`lower_bound ≥ type_floor − 0.10`). Type-relative so the all-trend-following live book (legitimately low WR) is not blocked — only small-sample flukes whose lower bound collapses below the floor. Config: `graduation_gate.wr_ci_confidence: 0.9`, `wr_ci_floor_tolerance: 0.1`. Both gates live in `is_qualified` (the authoritative gate via `get_graduation_queue`). |

Verification: py_compile + YAML valid; service restarted healthy; `graduation_gate` imports at startup (strategies router) with no error; no U+2500/import errors on 06-11. A legitimate trend strategy (type floor 0.35, 55% WR over 18 trades, Sharpe 1.2) still passes both gates (worked example confirmed); a 5-trade or barely-above-floor fluke now fails.

### P0-1 — live bleeders: FLAGGED for CIO (NOT auto-retired, per steering rule)
Live book is +$73v total **only** because of one SOXL outlier (+$868, n=4). Ex-SOXL: **−$795v ≈ −$101 real (~7.8% of the $1.3K stake)** across 48 trades. Recommend CIO retire:
- **GOOGL** (4H EMA Ribbon Trend Long) — 11% WR over **18** live trades, −$105v. Statistically broken, not a small sample.
- **TXN** (Keltner Channel Breakout) — 0% WR / 3, −$196v (worst dollar loss).
- **COPPER** (Dual MA Volume Surge) — G5 WF-divergence retirement candidate, −$19v.

**Why not auto-retired:** steering rule #7 (no irreversible real-money actions without CIO confirmation). Note discovered during Sprint B: `portfolio_manager.auto_retire_strategy` is a **legacy no-op** (logs only; "risk managed at position level"), so the autonomous cycle's retirement path does NOT actually retire live strategies — yet it still broadcasts a "Strategy Retired" notification, which is misleading. Real retirement is CIO-driven / position-level. **Watch item:** the no-op auto-retire + misleading broadcast means performance-retirement triggers never act — worth a proper fix next (make the LIVE path emit a real `[LIVE-REVIEW]` flag + accurate notification rather than a phantom "retired" broadcast).

### Still open after Sprint B
- CIO action: retire GOOGL/TXN/COPPER via dashboard.
- Graduation queue endpoint (`strategies.py:~1955`) has an inline eligibility duplicate that applies the min_trades floor (via `_get_min_trades_for_interval`) but NOT the Wilson gate — secondary display only; authoritative `is_qualified` gate is correct. Route through `is_qualified` in a future cleanup (duplicate-logic debt).
- Sprint C (P2 quick wins): `strategies.py:3174` market_regime None crash; NEW-08 404 churn; `position_manager._classify_symbol` leveraged-ETF set consolidation; `_get_position_value` share-fallback.

**Sprint 14 complete (Jun 10 2026). Forensic audit P0+P1 fixes deployed & verified live. Service healthy, trading cycle + live pass running clean, position sync clean, fresh live snapshot, zero post-deploy errors. See "SESSION 2026-06-10 — SPRINT 14" below.**

---

## SESSION 2026-06-10 — SPRINT A: LIVE-CAPITAL CORRECTNESS (2nd audit)

Second full forensic audit (Opus 4.8) re-verified every Sprint 14 claim against live DB/logs/source. Most infra fixes held. Sprint A executed the four live-capital *correctness* findings. Deployed `trading_scheduler.py` + `monitoring_service.py`, restarted 23:27 UTC, health green, zero post-deploy errors, TSL running clean.

| Fix | What | Root cause |
|---|---|---|
| **P1-1** | Live order size now `min(pipeline, CIO/mirror)` (was raw `CIO/mirror`, pipeline discarded as "advisory"). | `validate_signal` computed vol/drawdown/heat-adjusted size + validated symbol/exposure/VaR caps against it, then the live pass threw it away and traded a *different* number — caps validated one size, executed another. Now executed ≤ validated, so caps hold and the risk framework can scale live DOWN in adverse regimes (never above CIO cap → risk only decreases). |
| **P1-2** | `_adjust_opposing_position_sl`: deleted dead duplicate def (was shadowed), removed the no-op positional call site, added `account_type` filter to the query. | Two methods same name/different signatures; call site 1896 passed positional args → `new_tp=None` → silent no-op; effective method (3554) queried positions with NO account_type filter → a DEMO short on MU/AMD could widen a LIVE position's DB stop (the value TSL breach reads). |
| **P1-3** | Price-freshness guard at top of `_check_trailing_stops`: if a monitor's last *successful* sync (`_last_full_sync`) > 180s, force a resync before breach enforcement so stops act on fresh `current_price`. | Breach enforcement trusted `current_price` with only a `>0` check. During the 76–86 min loop gaps (observed 2026-06-10), price went stale → real breach missed / ghost breach on live capital. Self-heals the exact gap scenario; never disables stops on outage. |
| **P1-4** | Per-phase + per-cycle timing instrumentation in the monitoring loop (`[loop-timing]` WARNING when position-sync/trailing phase >30s or cycle >45s). | The 76–86 min loop gaps (root cause of the FIX-09 storms) were invisible — only surfaced downstream as staleness storms. Now greppable in real time so the offending eToro call can be fixed with evidence. Note: eToro calls already have a 30s timeout + bounded retry, so the proper next step was instrumentation, not a guessed timeout change. |

**Verified-correct during audit (no action):** session-rollback-on-checkout; both unique indexes live; P0-2 in-memory live symbol guard; live-pass account scoping; WF (test−train)≤1.5 gate on all 3 paths; transaction costs read `backtest.transaction_costs` (no phantom costs; top-level `transaction_costs` block is dead/unread); conviction normalization denominators internally consistent (no Tier-1 inflation — the `Asset(12)` comment is a typo, denom 101 assumes 15); Intel auto-resolution logic correct; MQS persisting (52.8); P0-4 leveraged SL (20% cap, 0.5× sizing, dead 4% cap gone).

**Still open from 2nd audit (NOT done in Sprint A):**
- **Sprint B (P0-1/P0-2):** Live book +$73v total is ENTIRELY one SOXL outlier (+$868, n=4, one +46% hold). Ex-SOXL: −$795v ≈ −$101 real (~7.8% of $1.3K stake) across 48 trades. GOOGL 11% WR/18 trades, TXN 0%/3, COPPER (G5). Root cause: graduation gate min_trades 10/15/25 + 55% WR gives a ~±23% WR CI → sub-50% strategies pass by luck; ~300 candidates (multiple testing) ⇒ expected false graduations. Fix: Wilson-lower-bound WR≥0.50 gate, raise min_trades→20, cumulative live-loss/WR auto-halt. Then CIO-flag GOOGL/TXN/COPPER for retirement (NOT auto-retired — rule).
- **P2 quick wins:** `strategies.py:3174` `(full_config.get('market_regime') or {})` crash; NEW-08 stale-order 404 churn; `position_manager._classify_symbol` still has its own leveraged-ETF set (P0-4 consolidation incomplete); `risk_manager._get_position_value` falls back to share count when `invested_amount` missing.
- **P1-1 follow-up:** `check_position_limits`/`check_exposure_limits` still use demo `self.config.max_position_size_pct` as the live gate threshold (conservative, not a hole — left untouched to avoid destabilizing the working live gate).

**Sprint 13 complete (Jun 10 2026). 14 crash-audit fixes + 6 Intel fixes + 6 P1 improvements + 3 session-corruption fixes deployed. Live account updated to $1,300 real / 0.127 mirror ratio. Pullback gate recalibrated. System actively trading again.**

---

## SESSION 2026-06-10 — SPRINT 14: FORENSIC AUDIT P0 + P1 EXECUTION

Full forensic audit (Opus 4.8) + execution of every P0 and P1 finding. All deployed to EC2 and verified.

### Research outcomes (root causes confirmed)
- **`quantity` unit ambiguity**: `etoro_client.get_positions` writes `quantity=units` (shares) and `invested_amount=amount` (dollars). Entry orders store dollars (`position_size`); close/SL/TP orders inherit share-valued `position.quantity`. `invested_amount` is the only reliable dollar field. FIX-B's `quantity × price` premise was a misdiagnosis (entry orders are already dollars).
- **Intel never auto-resolves**: `_upsert_finding` only INSERT/UPDATEs — findings stay `open` forever. Root cause of the 244-open-P1 pileup and stale E5/A1/D2 noise.
- **E5 false positives**: balance-exclusion only matched the `$0` variant, so `$409/$1059/$1432` balance blocks survived as "structural". D1/D2 measured raw wall-clock staleness (no market-hours awareness) → fired for every open position every overnight/Monday.

### P0 — live capital (all deployed + verified)
| Fix | What |
|---|---|
| P0-1 | FIX-09 watchdog rewrite. Cooldown stamp now set BEFORE remediation (the 5s storm was caused by the stamp being after a raising sync). Remediation now WRITES a fresh live snapshot (the thing the check reads) — a position resync never refreshed it. Threshold 60m→90m (> 60m snapshot cadence) kills boundary aliasing. CRITICAL only after 2× threshold. Verified: fresh snapshot at startup, no storms. |
| P0-2 | Live pass in-memory per-cycle symbol guard (`_live_symbols_submitted_this_cycle`). Added the instant `execute_signal` returns, BEFORE the DB write — closes the MU×4 duplicate window where a failed order-row write (DELL-orphan path) let strategies 2..N re-fire. |
| P0-3 | Partial unique index `uq_open_pos_strategy_symbol_acct (strategy_id, symbol, account_type) WHERE closed_at IS NULL`. DB-level enforcement of one-open-position-per-pair (was code-only; had already failed → PLATINUM demo ×2). Resolved the existing demo dup via pending_closure first. `migrations/migrate_open_position_unique.sql`. |
| P0-4 | Leveraged-ETF SL: removed the dead FIX-03 4% cap (it was silently overwritten by the ATR floor → TQQQ/SOXL actually got up to 20% stops; forcing 4% guarantees noise-stopouts on a 3× ETF). Risk is bounded by the 0.5× sizing (kept) + small CIO size + ATR-realistic stop clamped at the leveraged cap. Canonical leveraged set now in `sl_caps.is_leveraged_etf` (was duplicated 4× with drift). **NEW-07 escalated**: 3× ETFs are still the wrong instrument for a medium-term live book — CIO decision to retire TQQQ/SOXL from live. |

### P1 (all deployed)
| Fix | What |
|---|---|
| P1-1 | Balance gate (FIX-B) corrected: pending = sum of ENTRY-order `quantity` (already dollars), no `× price`. Old formula computed $21.8M pending for a $3K index order → `max(0,…)`=0 → `>0` guard → silent no-op. |
| P1-2 | `_fetch_historical_from_fmp` now delegates to `fmp_ohlc.fetch_klines` (correct `/stable/historical-price-eod/full` + SYMBOL_MAP) instead of the legacy `/api/v3/historical-price-full` (empty on Starter). Fixes the dead LME/forex FMP primary path (FIX-D part 2). |
| P1-3 | `live_trade_count` now atomic `UPDATE … SET col = col + 1` in both order_executor + order_monitor (was read-modify-write → lost updates; needed the Sprint-13 backfill). |
| P1-4 | Zombie exits no longer auto-close LIVE positions — LIVE candidates logged `[ZombieExit][LIVE-REVIEW]` WARNING for CIO; demo keeps auto-flag. (Real-money exits are a CIO decision, not a demo-tuned gate.) |
| P1-5 | D1/D2 freshness now measured in BUSINESS days (`_business_days_stale`) — kills the weekend/overnight false-positive storm; still catches genuine multi-day gaps. |
| P1-6 | `signal_decisions` stage-aware prune (`prune_old(30)`) now CALLED in `_run_daily_sync` (was "manual schedule TBD" — audit rows had grown to 44d). |
| P1-7 | A1 (BACKTESTED-0-signals) downgraded P1→P2 — it was 213 of 244 P1s, burying real P1s. RESEARCH-stage, not a capital risk. |
| P1-8 | Intel auto-resolution: findings not re-seen in a clean run are auto-resolved (guarded — skipped if any check raised). Fixes the write-only-log accumulation. Plus E5 balance-exclusion broadened to any amount. |

Intel changes (P1-5/7/8) take effect on the next `/intel/run`; P1-6 prune runs on the next daily sync.

**Intel validation (run 21:20, post-deploy) — CONFIRMED:** open P1 244→1 (only A7 remains, a real finding), P2 14→169 (A1's 156 reclassified here), 104 stale findings auto-resolved. D1/D2/E5/B4 false positives gone; genuine findings (G5 COPPER, G9) persisted — no over-resolution. Run clean in 70s. All observability fixes verified live.

### Verified resolved during audit (no action needed)
- No dual `risk_manager` / `monitoring_service` files (only `src/risk/risk_manager.py`, `src/core/monitoring_service.py`).
- WF `(test−train) ≤ 1.5` consistency gate wired on all 3 paths (primary/test-dominant/relaxed-OOS).
- MQS null snapshot fixed (showing 52.8/normal).
- historical_price_cache duplicate-bar constraint working.
- Startup demotion properly guarded (60-min fill + 24h trade cooldown).

### Still open (deferred — trading/CIO decisions, not code)
- **NEW-07 (CORRECTED — do NOT retire)**: TQQQ/SOXL live performance is positive, not broken. SOXL live: 4 trades, +$868, 50% WR, +15.8% avg (one +46% hold). SOXL demo: 102 trades +$8,948. TQQQ demo: 80 trades +$7,530 (TQQQ has 0 live trades yet). The genuine defect was the dead 4% SL cap (now fixed). Action: **monitor** via G5 divergence as live_trade_count accumulates; the +46% trade means SOXL's live edge is promising but n=4 (not yet proven). Revisit only if G5 shows decay.
- **P1-9 / G5 (genuine retirement candidate)**: COPPER live diverging hard from WF — RSI Midrange COPPER live −2.37 vs WF 1.72; Dual MA Volume Surge COPPER −3.58 vs 1.37. Real-money underperformance. Recommend CIO review for retirement.
- 423 silent `except: pass`/`logger.debug` handlers (28% of all) — systemic; lint rule + targeted audit recommended.

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

## SESSION 2026-06-10 — POST-SPRINT-13 VERIFICATION FIXES (commit `8f733c2`)

Full post-deploy verification run confirmed all 10 Sprint 13 checks. Five
remaining issues identified and fixed:

| Fix | What |
|---|---|
| FIX-A | E5 gate-loop check: `MAX(reason)` → `ARRAY_AGG(DISTINCT reason)`. Old code picked lexicographically largest reason, so "Insufficient balance: $0" masked "Pullback gate" and skipped the filter. Now checks ALL reasons; strategy only flagged if ≥1 is structural. Added transient-balance ($0 settlement window) and symbol-cap to the temporary-exclusion list. |
| FIX-B | DB balance formula: pending order deduction used `quantity` (shares) not `quantity × price` (dollars). 50 shares at $396 was deducted as $50. Now uses `expected_price` with fallback to `price`. |
| FIX-C | EEM ADX retired in DB (`ADX Trend Following EEM LONG` → INVALID). G9 finding: -57838% degradation. Slipped Sprint 13 batch because A4 and G9 use different degradation metrics. |
| FIX-D | ALUMINUM/ZINC FMP routing: (1) `fmp_ohlc.SYMBOL_MAP` now maps ALUMINUM→ALIUSD, ZINC→ZNUSD. Added ALIUSD/ZNUSD intraday to `EXPLICIT_BLOCKED` (LME metals are EOD-only on FMP Starter). (2) `market_data_manager` LME/forex primary path was passing `normalized_symbol` (Yahoo wire form `ALI=F`) instead of `db_symbol` (display form `ALUMINUM`) to `_fetch_historical_from_fmp` — bypassed SYMBOL_MAP entirely, fell through to thin Yahoo data silently. Root cause of ALUMINUM 1d bars being 162h stale. |
| FIX-E | `VACUUM ANALYZE signal_decisions` + `strategies`. Reclaimed dead tuple bloat from Sprint 13's 294K row deletion. |

**Note on signal_decisions disk size:** VACUUM ran successfully. `pg_relation_size` (live data) = 262 MB, `pg_total_relation_size` (including indexes/toast) = 398 MB. Size has not shrunk because VACUUM marks pages as reusable but does not return them to the OS — that requires `VACUUM FULL` which locks the table. The live data is 262 MB which is correct for 130K rows. No further action needed; new rows will use reclaimed pages.

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
1. **ALUMINUM 1d data fresh** — after next price sync, confirm `historical_price_cache` has recent ALUMINUM 1d bars from FMP (ALIUSD). Check errors.log for "FMP (forex/LME primary)" log line.
2. **E5 Intel count near zero** — run fresh Intel scan; E5 should show 0 after ARRAY_AGG fix.
3. **Demo orders executing** — moderate pullback should resolve; once SPY 5d return moves above -2%, daily trend strategies should start submitting orders again.
4. **signal_decisions size stable** — 130K rows / 262 MB live. New retention policy should keep it from growing back.
5. **FIX-B in effect** — if any PENDING orders exist during settlement, confirm balance log shows `invested + pending_dollars` not `invested + pending_shares`.

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
