# AlphaCent — Session Continuation

> Permanent rules are in `.kiro/steering/trading-system-context.md`. This file holds current system state, recent fixes, and open items.

---

## ⚡ NEXT SESSION KICKOFF

**Platform is in active iteration — live trading is running (GOOGL + SOXL + XLK LIVE), graduation pipeline working. WATCHLIST ELIMINATION COMPLETE (2026-05-18). Every strategy is now a single (template, symbol) pair.**

---

## SESSION 2026-05-25 — TRADE JOURNAL INTEGRITY FIX (CRITICAL)

### Root cause: log_exit fallback had no account_type filter

`TradeJournal.log_exit` has three lookup paths to find the entry to close:
1. Primary: `filter_by(trade_id=trade_id)` — fails when trade_id is position ID but entry was created with order UUID
2. Fallback 1: `filter_by(entry_order_id=trade_id)` — fails when entry_order_id stores eToro numeric ID
3. Fallback 2: `filter_by(symbol=symbol).filter(exit_time IS NULL)` — **had no account_type filter**

Fallback 2 matched the most recent open entry for the symbol regardless of account. This caused:
- Live exits written to DEMO trade_journal rows (corrupting DEMO P&L/win-rate used by graduation gate)
- Live trade_journal rows left open when positions were actually closed (phantom open positions in UI)
- DEMO trade_journal rows incorrectly marked closed (hiding real open positions)

**Specific corruptions found and fixed:**
- Row 1816 (GOOGL live): left open — fixed with correct zombie_exit data from positions table
- Row 1799 (XLK live): incorrectly closed — reopened (position still open)
- Row 1929 (GOOGL demo): orphaned duplicate — closed with correct exit data matching row 1960
- 13 rows with account_type='demo' but linked to live positions — corrected to account_type='live'

**Full integrity audit after fixes: 0 mismatches across all 5 checks.**

**Code fix (commit f79fbec):**
- `log_exit` now accepts `account_type` parameter
- All three fallback lookups filter by `account_type` when provided
- All callers (order_monitor ×2, order_executor ×2) pass `account_type`

**Impact on graduation gate:** The 13 mismatched rows were all from May 11-12 testing (GOOGL live positions during infrastructure setup). They are now correctly tagged as `live` and excluded from DEMO paper stats. Graduation gate paper stats for active strategies are unaffected (those strategies were not live during the contamination period).

---

## SESSION 2026-05-18 — WATCHLIST ELIMINATION

### Architectural change: Strategy IS a (template, symbol) pair

| Commit | What |
|---|---|
| `e70a2f5` | Phase 1 migration + Phase 2-5 code changes |
| `3bd873f` | Library: replace watchlist count with symbol name column |
| `b291073` | Fix open position orphans from watchlist migration |

**Phase 1 — DB migration** (`scripts/migrate_watchlist_to_single_symbol.py`):
- 256 multi-symbol strategies trimmed to `symbols=[primary]`
- 87 new single-symbol PAPER strategies created for watchlist symbols with actual trades
- 184 positions, 163 orders, 175 trades, 14,114 signal_decisions reassigned
- 33 open positions that had no closed trades (missed by first pass) fixed by `scripts/fix_open_position_orphans.py` — reassigned to correct single-symbol strategies
- 0 multi-symbol strategies remaining across all statuses

**Phase 2 — Proposer** (`strategy_proposer.py`):
- `_build_watchlists` call removed
- 224-line watchlist WF validation loop removed
- Every proposal is `symbols=[single_symbol]` always

**Phase 3 — Signal gen** (`strategy_engine.py`):
- `symbols_to_trade = [symbols[0]]` — no multi-symbol loop

**Phase 4 — Graduation gate** (`graduation_gate.py`):
- `wf_by_template_symbol` proxy (wf_validated_combos.json) removed
- Representative strategy WF sharpe is always correct now

**Phase 5 — Frontend** (`strategyColumns.tsx`):
- Watchlist count column replaced with actual symbol name (AAPL, GOOGL, etc.)

### Post-migration state
- 0 multi-symbol strategies (all statuses)
- PAPER = has open position or recently traded, BACKTESTED = passed WF waiting for signal
- GOOGL LIVE intact, SOXL LIVE strategy active (no position yet)
- `_demote_idle_strategies` in monitoring_service handles PAPER→BACKTESTED automatically when positions close

---

## SESSION 2026-05-18 — CRASH FIX + P2 BATCH (earlier)

### Crash fix + 604 cascade prevention
| Commit | What |
|---|---|
| `8a1b753` | Fix `_template_dup_rejected_symbols` NameError crash at 00:58 UTC |
| `c9dfebf` | Fix 604 cascade: deduct pending orders from balance (Part 1), delete ghost positions on rejection (Part 2), seed dedup from DB on restart (Part 3) |

### P2 batch deployed
| Commit | What |
|---|---|
| `d1b6b26` | G-22 (market-closed deferred), G-24 (heat cap actual SL), G-31 (graduation SQL HAVING), G-17 (pending_retirement force-close 14d), G-14 (cache regime per cycle), G-49 (AE freq cap bypass PAPER), G-47 (PAPER symbol cap 5%→10%) |

### Graduation gate overhaul
| Commit | What |
|---|---|
| `ec808aa` | Regime-adjusted ratio cap (3.5× in trending_up_strong), strategy-type win rate floor (45% trend, 55% mean_reversion), expand list to 20 |
| `e866cb6` | Fix template_type field name |
| `b8a5f92` | Restore _get_min_avg_pnl_per_trade, cache regime detection (10min TTL) |
| `c86eb0f` | Bulk-fetch strategy_type (1 query vs 20) |
| `7ac51e9` | Fix interval from rules fallback in graduation SQL CTE |
| `8ce2153` | High-conviction trade count exception (Sharpe≥2.0 + WR≥70% → 40% reduction), fix UI threshold display |
| `15cdef7` | Use best-template WF sharpe for watchlist symbol pairs |
| `d8caac1` | Use wf_validated_combos.json for symbol-specific WF sharpe (interim fix) |

### SOXL graduated to LIVE
- `4H EMA Ribbon Trend Long SOXL LIVE` — strategy_id `0d0b75d6`, position_size $900, SL 6%, TP 15%, conviction_min 73
- Now 2 LIVE strategies: GOOGL + SOXL

### Market hours fix
| Commit | What |
|---|---|
| `77f031b` | Fix DST-aware UTC offsets in market-hours.ts (was showing Pre-market at 14:55 London) |

---

## 🚨 NEXT SESSION MISSION: P1 OPEN GAPS

Watchlist elimination is done. Resume P1 open gaps:
- G-01: WF test-dominant consistency gate
- G-02: Deflated Sharpe Ratio at activation
- G-09: Correlation dedup at graduation approval (LIVE only)
- G-19: Real slippage model from trade_journal data

**This is the most important architectural change since the LIVE pass was added.**

### The problem
A Strategy is currently `(template, primary_symbol, watchlist=[sym1, sym2, sym3])`. One strategy row trades multiple symbols. This causes:
- Identity confusion in the Library (strategy named "SPY LONG" has a position in XLK)
- Graduation gate broken (WF sharpe from SPY used for XLK's qualification ratio)
- Performance attribution wrong (P&L aggregated across 5 symbols)
- Risk management confused (symbol cap, sector cap operate on positions but strategy view is misleading)

### The decision
**A Strategy IS a `(template, symbol)` pair. One strategy row = one symbol. Always.**

### Answers to design questions
1. Watchlist symbols that fail full WF → **do not exist** (delete/retire, no PAPER status)
2. Watchlist WF validation (lighter pass) → **remove entirely**. Full WF only.
3. Frontend migration → **migrate backend first, frontend follows naturally**

### Implementation plan (5 phases, implement in order)

**Phase 1 — Stop service, run migration script**

Migration script (`scripts/migrate_watchlist_to_single_symbol.py`):

For each strategy where `json_array_length(symbols) > 1`:
  - For each watchlist symbol (symbols[1:]):
    - Run full WF on `(template, watchlist_symbol)` using the parent strategy's rules
    - If WF passes: create new strategy row (clone parent rules/risk_params/metadata, `symbols=[watchlist_symbol]`, name=`{template} {watchlist_symbol}`, status=PAPER if has paper trades else BACKTESTED, store wf_test_sharpe)
    - If WF fails: do NOT create strategy. Reassign positions/orders/trades to a "retired watchlist" holding strategy or just close them.
    - Reassign `positions`, `orders`, `trade_journal`, `signal_decisions` rows where `strategy_id=parent AND symbol=watchlist_symbol` → new strategy_id (or close if WF failed)
  - Update parent: `symbols = [symbols[0]]` (primary only)

LIVE strategies (GOOGL, SOXL) are already single-symbol — skip them.

**Phase 2 — Proposer change (`strategy_proposer.py`)**

- Remove `_build_watchlists` method entirely
- Remove watchlist WF validation loop (lines ~2789-3011)
- Remove `config/.wf_validated_combos.json` usage for watchlist building
- Each proposal is a single `(template, symbol)` pair
- `generate_strategies_from_templates` outputs strategies with `symbols=[symbol]` always
- The per-cycle cap (200) applies to total `(template, symbol)` proposals
- Dedup: if `(template, symbol)` strategy already exists in PAPER/BACKTESTED/LIVE → skip

**Phase 3 — Signal generation (`strategy_engine.py`)**

- `generate_signals`: replace `for symbol in strategy.symbols:` loop with single `symbol = strategy.symbols[0]`
- Remove all watchlist-related branching in signal gen
- `_coordinate_signals` in trading_scheduler: already works per symbol, no change needed

**Phase 4 — Graduation gate (`graduation_gate.py`)**

- `latest_strategy` CTE: trivial now — just pick most recent strategy for `(template, symbol)`. No proxy WF sharpe needed.
- Remove `wf_by_template_symbol` and `best_wf_by_template` fallback logic (added in d8caac1) — no longer needed
- `is_qualified`: no changes needed

**Phase 5 — Frontend (`Library`, `ApproachingGraduationPanel`)**

- Remove "versions" badge from Library rows
- Strategy name is always `{template} {symbol}` — no parsing needed
- `ApproachingGraduationPanel`: already works correctly after migration (each row is a real strategy)
- Library filters: "Promoted today", "Activated today", "Live today" — no change needed

### Key invariants to preserve
- LIVE GOOGL and SOXL positions must not be touched
- TSL continues to work (reads position.strategy_id → strategy rules — rules are identical after clone)
- trade_journal reassignment preserves graduation stats (graduation gate already groups by template+symbol across all strategy_ids)
- The `wf_validated_combos.json` cache can be kept as a performance hint for the proposer (which symbols pass WF for a template) but is no longer used for watchlist building

### Files to change
| File | Change |
|---|---|
| `scripts/migrate_watchlist_to_single_symbol.py` | NEW — migration script |
| `src/strategy/strategy_proposer.py` | Remove `_build_watchlists`, watchlist WF loop, multi-symbol strategy creation |
| `src/strategy/strategy_engine.py` | `generate_signals`: use `symbols[0]` only |
| `src/strategy/graduation_gate.py` | Simplify `latest_strategy` CTE, remove WF proxy fallback |
| `frontend/src/pages/strategies/Library*.tsx` | Remove "versions" badge |

### Rollback
If migration fails mid-way: `git revert` the migration script commit. The DB changes are the hard part — run migration in a transaction so it's atomic per strategy.

---

## CURRENT SYSTEM STATE (2026-05-18 end of session)

- **DEMO equity:** ~$479K | **Open positions:** 128 PAPER (draining to 1:1 as pre-migration watchlist positions close) | **Regime:** trending_up_strong
- **LIVE strategies:** 2 — GOOGL LONG (id: `918b0c99`) + SOXL LONG (id: `0d0b75d6`)
- **LIVE positions:** GOOGL LONG entry 389.2, current ~403, +$31 unrealised. SOXL no position yet.
- **Strategy counts:** ~134 PAPER · ~267 BACKTESTED · 2 LIVE
- **Architecture:** Every strategy is now a single (template, symbol) pair. 0 multi-symbol strategies.
- **Latest commit:** `b291073` (fix open position orphans)

---

## SESSION 2026-05-17 — WHAT WAS DONE (continued)

### G-44 + G-45 fixed and deployed (P0 closure)
| Commit | What |
|---|---|
| `8d07eef` | G-44/G-45: wire `validate_signal` + `calculate_position_size` into LIVE pass. Both LIVE pass paths (independent pass + DEMO-cycle routing) now call the full risk framework with `is_live=True`. CIO `position_size` becomes a cap, not the absolute. Verified: GOOGL position unaffected, conviction gate (73) still fires, no new errors. |

**What changed:**

`risk_manager.py`:
- `calculate_position_size`: new `is_live=True` parameter. LIVE parameter override block reads `live_trading.{base_risk_pct, symbol_cap_pct, portfolio_heat_cap, min_order_size}` from YAML. Steps 1/6/8/11 use LIVE values when `is_live=True`. Early balance check skipped for LIVE ($200 minimum, not $2,000).
- `validate_signal`: new `is_live=True` parameter, passed through to `calculate_position_size`.

`trading_scheduler.py`:
- Independent LIVE pass: fetches live account info (`etoro_client.get_account_info()`) + live positions (scoped to `account_type='live'`) once per cycle. Calls `validate_signal(is_live=True)`. Applies CIO cap after pipeline. Logs `pipeline=$X CIO_cap=$Y → final=$Z`.
- DEMO-cycle LIVE routing: same pattern.

**Order of operations for LIVE sizing:**
1. 11-step pipeline runs with LIVE parameters → `pipeline_size`
2. CIO cap: `min(pipeline_size, live_strategies.position_size)`
3. Final clamp: `max(min_order_size=200, min(max_order_size=1500, ...))`

**P2 note added:** G-57 — surface LIVE risk metrics (heat used, vol scalar, CIO cap vs pipeline size) on Guard → Risk tab frontend. Backend `/risk/metrics` already scopes by `account_type`; frontend needs a LIVE section. Deferred until G-44/G-45 are stable.

**Rollback:** `git revert 8d07eef --no-edit` then scp both files + restart.

---

## SESSION 2026-05-17 — WHAT WAS DONE

### Full system audit + gap analysis
| File | What |
|---|---|
| `docs/ALPHACENT_SYSTEM_AUDIT_2026-05.md` | 1,169-line component-by-component documentation. Architecture diagram, 15 sections covering data pipeline / proposer / WF / conviction / activation / sizing / execution / monitoring / graduation / decay / analytics / frontend / infrastructure. Adds §16 Strategy Lifecycle (RESEARCH→PAPER→LIVE) — the structural realisation that PAPER inherits LIVE-grade risk discipline it doesn't need (slowing data collection) AND LIVE bypasses the risk framework entirely (concentrating risk on real capital). |
| `docs/GAP_ANALYSIS_2026-05.md` | 56 gaps catalogued (G-01 through G-56), file:line refs, lifecycle-aware. P0/P1/P2/P3 prioritisation in §20. |

### G-43 fixed and deployed
| Commit | What |
|---|---|
| `b1378e1` | G-43: branch signal-time conviction by account_type. PAPER reads `paper_trading.conviction_threshold` (60/55) — was reading `alpha_edge.min_conviction_score` (70/62). LIVE unchanged via `conviction_override` from `live_strategies.conviction_min`. Patched `src/strategy/strategy_engine.py:5572-5605`, deployed to EC2, verified at runtime — logs show `Conviction thresholds (PAPER): min=60, crypto_min=55` and `Applying conviction scoring (min: 73, crypto min: 73)` for LIVE. The 60-69 conviction band is now unblocked for PAPER data collection. |

### The lifecycle realisation (most important takeaway)

The system was originally built **research → paper** as one pipeline. LIVE was added later as a separate signal pass that **completely bypasses the risk framework**:

- `_live_order_executor.execute_signal` is called directly in `trading_scheduler._run_trading_cycle:2148+` with a CIO-clamped size.
- `RiskManager.validate_signal` is **NOT** called for LIVE — no heat cap, sector cap, directional balance, VaR, correlation, circuit breaker.
- `RiskManager.calculate_position_size` is **NOT** called for LIVE — no vol scaling, drawdown sizing, conviction-tier sizing, MQS multiplier, sector cap, loser penalty. The CIO `position_size` is fixed at graduation and clamped to `[live_trading.min_order_size, live_trading.max_order_size]`.

This is masked today because there's only **1 LIVE strategy (GOOGL LONG)**. Breaks at LIVE strategy #2.

Conversely, PAPER inherits gates that hurt data collection:
- `MAX_PER_SYMBOL_PER_TIMEFRAME = 4` (limits paper book breadth)
- C1 VIX gate + C3 trend-consistency gate run on PAPER (block exactly the data points we need to learn from; bias paper Sharpe upward, misleading the graduation `qualification_ratio`)
- Avg-loss gate at `autonomous_strategy_manager.py:2258` has no paper-mode disable
- AE frequency limiter (4 trades/month) caps paper data accumulation

### P0/P1/P2/P3 prioritisation (full list in `docs/GAP_ANALYSIS_2026-05.md` §20)

**P1 — CLOSED (batch 1 deployed 2026-05-17, commit `c158650`):**
- ~~G-46: MAX_PER_SYMBOL_PER_TIMEFRAME 4→8 for PAPER~~ ✅
- ~~G-48: avg-loss gate bypass for PAPER~~ ✅
- ~~G-50: Skip C1/C3 gates on PAPER orders~~ ✅
- ~~G-10: Wire correlation_adjustment config from YAML~~ ✅
- ~~G-35: Write cycle_error to signal_decisions~~ ✅

**P1 — OPEN (next session):**
- G-01: WF test-dominant consistency gate
- G-02: Deflated Sharpe Ratio at activation
- G-09: Correlation dedup at graduation approval (LIVE only)
- G-19: Real slippage model from trade_journal data

**P1 — current sprint (lifecycle + statistical robustness):**
- G-46: PAPER `MAX_PER_SYMBOL_PER_TIMEFRAME` 4→8
- G-48: PAPER avg-loss gate disable
- G-50: Skip C1/C3 gates on PAPER
- G-01: WF test-dominant path consistency gate
- G-02: Deflated Sharpe Ratio at activation
- G-09: Reject proposals correlated >0.65 with active strategies (post-WF)
- G-10: Wire dead `position_management.correlation_adjustment.*` config
- G-19: Real slippage model from trade_journal data
- G-35: `cycle_error` stage in signal_decisions

**P2 (22 gaps), P3 (16 gaps)** — see §20.

### State pulled from EC2 at audit time
- DEMO equity: $479,224 · 70 open positions / 1,025 lifetime
- LIVE equity: $9,903 · 1 GOOGL LONG +$16.63 unrealised
- 267 BACKTESTED · 46 PAPER · 1 LIVE
- Regime: trending_up_strong (confidence 0.87) · MQS 84 (high)
- errors.log: 15,965 lines since 2026-05-01 (mostly DSL parse errors on broken templates)

---

## SESSION 2026-05-15 — WHAT WAS DONE

### Intel page built end-to-end + calibrated
| Commit | What |
|---|---|
| `74e0d84` | Intel page: analyst, 50 checks A-H, findings DB, nav badge |
| `ccca21d` | Fix 504: async background thread + polling (POST /run returns immediately) |
| `f6e4bbb` | Fix C1/C2 equity (use equity_snapshots not balance), A7 distinct strategies, A10/E5 per-symbol-day |
| `12457ea` | Fix A10/E5: use order_submitted not signal_emitted (quick-update signals are expected) |
| `9ad34ad` | Fix A6 dedup (suppress when A1 exists), E5 UUID fallback, G9 threshold -1000% + train>0 |

**Intel is live at https://alphacent.co.uk/intel**
- Manual trigger, configurable lookback (1/7/14/30/90 days), runs in ~75s background thread
- 101 findings after calibration: 3 P0, 67 P1, 22 P2, 9 opportunities
- "Ask Kiro →" button copies pre-filled prompt to clipboard
- Nav badge shows P0+P1 open count (red if P0, amber if P1), fetched every 60s
- Findings persist across sessions, deduplicated by (check_id, key)

**Key findings from first calibrated run (2026-05-15, 7d lookback):**
- P0: B5 (eToro ID collision demo/live), F1 (5367 errors in errors.log), F2 (33 SQLAlchemy InFailedSqlTransaction)
- P1: 15 strategies BACKTESTED with 0 signals (A1), 20 regime luck (A4), 18 permanent gate loops (E5 — signals fire, 0 orders), 73 strategies scoring 65-69 (A7), 0% short exposure (A8)
- P2: GOOGL LIVE Sharpe -17.23 vs WF 2.73 (G5), WF cache hit rate 27% (E2), 10 extreme degradation (G9)
- Opportunities: RKLB 47% missed alpha, LUNR 40%, indices underweighted at 4% of strategies (G2)

**Calibration fixes applied (do not re-patch):**
- C1/C2: use `equity_snapshots WHERE account_type='demo'` not bare `account_info.balance`
- A7: COUNT(DISTINCT strategy_id) not raw row count
- A10/E5: measure order_submitted not signal_emitted (signals fire every 10min by design)
- A6: only fires when signals ARE generating but not converting (not when 0 signals — that's A1)
- G9: threshold -1000% + train_sharpe > 0 + trades >= 8 (genuine regime luck, not thin train data)

### Intel page spec written
| File | What |
|---|---|
| `INTEL_SPEC.md` | Complete spec for the Intel analyst page — 50 checks across 8 categories (Strategy Health, Execution Quality, Risk, Data Pipeline, Cycle/Signal, System Health, Alpha Opportunities, Config Integrity), full backend/frontend architecture, log rotation handling, nav integration, implementation order |

### Regime gate removed from scheduler
| Commit | What |
|---|---|
| `b625cdb` | Remove redundant regime gate — conviction scorer is single source of truth for regime fit. Scheduler gate was blocking uptrend exhaustion SHORTs that conviction correctly approved. Kept: SHORT concentration limit (max 3 equity shorts). |

### Conviction scorer: 5 fairness fixes for SHORT/low-frequency strategies

**Root cause investigation:** All 16 SHORT strategies were generating signals but blocked at `signal_emitted` stage with conviction 57–61 against a 70 threshold. Zero paper trades across all SHORT strategies. Four compounding structural issues identified — none intentional SHORT discrimination, but all hitting SHORTs harder than LONGs.

| Commit | What |
|---|---|
| `82d192e` | Fix conviction scorer: 5 fairness fixes for SHORT/low-freq strategies |

**Fix 1 — Per-asset-class effective denominator** (replaces flat 111):
- stock/etf: 101, forex: 104, crypto: 106, commodity: 98, index: 100
- The 111 denominator included carry(5)+crypto(5) that stocks can never earn, structurally depressing stock scores by ~9pts vs their actual ceiling.

**Fix 2 — Low-freq trade confidence denominator** for SHORT mean_reversion/volatility:
- `sqrt(trades/8)` instead of `sqrt(trades/15)` for parabolic/exhaustion/BB squeeze shorts
- These setups fire 3–6× per year by design; calibrating against 15 (LONG trend norm) halved their Sharpe component. 8 trades = full confidence for low-freq setups.

**Fix 3 — Degradation penalty gated by trade count:**
- `trades >= 8`: softer penalty (−3 at deg<−200, −1.5 at deg<−100)
- `trades < 8`: full penalty unchanged (−7/−4/−2)
- With <8 trades the train period may have 1–2 trades → low train Sharpe → large deg% even when edge is real (e.g. PFE SHORT 100% WR, deg=−470).

**Fix 4 — Parabolic/Exhaustion/Volume Climax SHORT → mean_reversion type:**
- `_detect_strategy_type` now checks name before metadata `template_type`
- These counter-trend setups were typed as `volatility`, routing them to trend-following persistence scoring (persistence=1 → 5pts instead of 12pts)

**Fix 5 — Asset tradability base scores:**
- Stock base: 10 → 12 (PFE/NKE/VEEV/ENPH/F are large/mid-cap, more liquid than many ETFs that score 13)
- Commodity: 11 → 12 (NATGAS/GOLD are highly liquid CFDs on eToro)

**Net effect on SHORT strategies (simulated):**
- Strong (Sharpe 2.5+, 8+ trades): 54–69 → 72–77 ✓ PASS (F SHORT, BB VEEV, Stoch Midrange FOREX, NATGAS Parabolic, SMA Env FOREX)
- Medium (Sharpe 2.0–2.5, 4–6 trades): 54–63 → 63–70 near threshold (ENPH, SHOP, Exhaustion VEEV)
- Weak (Sharpe 1.1–1.6, 50% WR): 54–63 → 62–64 ✗ correctly blocked (Stoch OB AUDUSD, NATGAS BB, BB USDCHF)
- No threshold change needed.

**Side effects on LONG strategies:** Fix 1 (denominator) and Fix 5 (asset scores) also improve LONG stock/commodity/index scores by ~5–9pts. This is correct — they were also being under-scored by the same structural issues. Monitor for any unexpected activation surge in the next 1–2 cycles.

---

## SESSION 2026-05-14 — WHAT WAS DONE

## SESSION 2026-05-14 — WHAT WAS DONE

### Sync Log tab (Guard page)
| Commit | What |
|---|---|
| `f0976eb` | Add Sync Log tab to Guard — live terminal with color-coded service badges, polls /data/service-log every 5s |
| `dca2858` | Fix quick_update: always emit complete with stats |
| `2f38526` | Persist service log to disk (logs/service_log.jsonl, 2000-entry ring buffer, survives restarts) + fix last_run from DB for quick_update/news_sentiment/FMP |
| `260da64` | Fix trailing_stops_interval: 30s → 60s (aligned with position sync, halves TSL log noise) |

### Trading fixes
| Commit | What |
|---|---|
| `a43fc2f` | Fix race condition: position sync creates row before fill sets strategy_id (UNH position was showing "—" strategy) |
| `689daab` | Increase MAX_PER_SYMBOL_PER_TIMEFRAME: 2 → 4 (PAPER dynamism) |
| `b5a8495` | Optimistic position write: create DB row at order submit time (prevents duplicate positions from quick-update race) |
| `3cf814d` | Fix zombie exit: remove blanket forex exemption, add forex-specific thresholds (±2%, 14d min age) |
| `a3dd268` | Add quick filter pills to Book Positions and Orders tabs |
| `00b35f7` | Interval-aware avg-loss gate: 1h=5×, 4h=4×, 1d=3× stop-loss |
| `bc10c5b` | 1h strategy improvements: WF cache TTL 2d→1h, MC bootstrap p5 floor -0.1 for 1h equity |

### PAPER trading dynamism analysis
- Signal gen runs via two paths: main scheduler (~55 min gap) AND quick update (every 10 min, 5 min gap)
- **Primary blocker identified: conviction threshold 73 applied to PAPER** — blocks the entire 70–72 band which is profitable (+$70 avg P&L, +$4,577 total, 65 trades last 60d)
- **65–69 band is genuinely bad** (negative avg P&L) — correct to block
- **Decision: lower PAPER conviction to 70** (set manually in Settings UI)
- Rationale: graduation gate is the real quality filter; paper needs trade data to graduate strategies; 50% balance idle is opportunity cost
- Live conviction stays at 73

### 1h strategy pipeline fixes
- `min_trades_dsl_1h: 12` (was 15) — set via Settings UI
- Avg-loss gate now interval-aware: 1h uses 5× multiplier (was 3×), 4h uses 4×, 1d stays 3×
- WF cache TTL: 2 days → 1 hour (config changes take effect within one cycle)
- MC bootstrap: 1h equity now uses p5 ≥ -0.1 (was 0.0) — wider bootstrap distribution for intraday
- Result: 4 new 1h strategies activated in first post-fix cycle (LUNR, MU, Opening Range Breakout MU/MS)

### Transaction cost correction (eToro Diamond+)
Real costs confirmed from eToro fee pages:
- **Stocks/ETFs LONG (non-leveraged BUY):** zero commission, zero spread markup, zero overnight fee
- **Crypto (Diamond, $100K-$250K):** 0.75% per position (was modelled at 0.1%)
- **Forex:** ~10 bps spread (was 1.5 bps)

YAML updated in `config/autonomous_trading.yaml`:
- `stock/etf spread_percent: 0.0015 → 0.0` (phantom cost removed)
- `stock/etf overnight_financing_pct_per_day: 0.0002 → 0.0` (non-leveraged BUY has no overnight)
- `crypto commission_percent: 0.001 → 0.0075` (Diamond tier 0.75%)
- `crypto spread_percent: 0.0038 → 0.0` (no eToro markup on non-leveraged crypto)
- `forex spread_percent: 0.00015 → 0.0001` (1 pip ≈ 10 bps)
- BTC/ETH per-symbol overrides corrected to match Diamond tier

Impact: stock/ETF strategies show higher backtest Sharpe (phantom costs gone), crypto strategies show lower Sharpe (real 1.5% round-trip now modelled). Opening Range Breakout template now activating multiple symbols per cycle.

### Trading limits audit (full list in session notes)
Key hardcoded limits found:
- `MAX_PER_SYMBOL_PER_TIMEFRAME = 4` (was 2) — in trading_scheduler.py
- `MAX_ORDERS_PER_RUN = 15` — hardcoded
- `MIN_GAP_SECONDS = 3300` (55 min) — main scheduler only; quick update path uses 300s gap
- `MINIMUM_ORDER_SIZE = $2,000` — hardcoded
- `MAX_PORTFOLIO_HEAT_PCT = 30%` — hardcoded
- Symbol cap: 5% of equity — hardcoded
- `alpha_edge.max_trades_per_strategy_per_month = 4` — YAML, Alpha Edge only
- YAML `position_management.max_positions_per_symbol: 5` is NOT read by code (dead config)

---

### Live trading infrastructure (all shipped)

| Commit | What |
|---|---|
| `a6918de` | P0: duplicate guard, position ID oscillation, miss counter, live_trades wiring |
| `e48f3a6` | reconcile_on_startup scoped to demo account_type only |
| `a5ff668` | ROOT CAUSE FIX: scope OrderMonitor queries to account_type |
| `871bd53` | Fix _submit_close_order: refresh etoro_position_id before closing live positions |
| `1e67485` | Fix live.py close endpoint: refresh etoro_position_id before closing |
| `49d7c00` | Fix circuit breaker: exclude live positions from template win rate check |
| `c603c6d` | Fix live position tracking: scope sync to account_type, fix PK/etoro_id collision |
| `a65b986` | Fix order matching: scope Pass 1 and Pass 2 to account_type |
| `c48ef27` | Fix all 6 post-investigation items (circuit breaker, orphan position, startup reconcile, gitignore, migrations/) |

### Graduation pipeline

| Commit | What |
|---|---|
| `0b9f993` | Fix approaching-graduation: add wf_test_sharpe to WF sharpe SQL lookup |
| `abde7ff` | Graduation: fix WR bar, add max_qualification_ratio cap (2.0×), update labels |
| `231e140` | Add Promoted Today, Activated Today, Live Today pill filters to Library |

### Analytics & UI

| Commit | What |
|---|---|
| `c2bd491` | Fix pending-open and pending-closures endpoints: add account_type filter |
| `c59500c` | Fix Library pill filters: add last_signal_at and live_pnl to slim metadata |
| `b2d8183` | Add total_return_dollars to performance analytics |
| `1c79447` | Add realized P&L, alpha vs SPY, dollar returns across Fund Scorecard, Research tiles, chart hover |
| `5d81da7` | Move Execution tab Book→Research, fix Attribution overlap, add Realised alpha vs SPY to chart hover |
| `e4ab95b` | Guard: fix slow load (N+1 batch queries), UUID display, tab order, Risk tab layout |

### Other fixes

| Commit | What |
|---|---|
| `7aec120` | Untrack autonomous_trading.yaml from git (EC2 authoritative) |
| `07b33be` | Fix live pass duplicate guard: 4h cooldown on recent orders |
| `7d4170a` | Add Portfolio VaR limit to Settings / Risk Limits |

---

## CURRENT SYSTEM STATE (2026-05-17 end of session)

- **DEMO equity:** ~$479K | **Open positions:** 70 / 1,025 lifetime | **Regime:** trending_up_strong (conf 0.87) | **MQS:** 84 (high)
- **DEMO strategies:** 267 BACKTESTED · 46 PAPER · 1 LIVE
- **LIVE strategy:** `4H EMA Ribbon Trend Long GOOGL LIVE` (id: `918b0c99`) — status LIVE
- **LIVE positions:** 1 open — GOOGL LONG, entry 389.2, current 396.82, +$16.63, SL 365.82 ✅
- **PAPER conviction threshold:** 60 (crypto 55) — **NEW: G-43 fix deployed today**, now reading `paper_trading.conviction_threshold`
- **LIVE conviction threshold:** 73 (crypto 67) via `live_strategies.conviction_min`
- **Latest commit:** `c158650` (P1 batch 1: G-46, G-48, G-50, G-10, G-35)

---

## LIVE TRADING ARCHITECTURE — HOW IT WORKS NOW

### Key invariants (do not re-patch)
- `OrderMonitor` takes `account_type` param — DEMO monitor only sees DEMO orders/positions, live monitor only sees live
- `_sync_positions` scoped to `account_type` — live sync never finds DEMO rows by etoro_position_id
- `positions.etoro_position_id` unique constraint is **composite** `(etoro_position_id, account_type)` — eToro reuses numeric IDs across accounts
- PK collision path: if eToro position ID already exists as a PK in DB (from different account), a synthetic UUID is used
- Order matching Pass 1 + Pass 2 both filter `OrderORM.account_type == account_type` — DEMO orders never match live positions
- `reconcile_on_startup` is account_type-aware — live monitor runs its own startup reconcile via `monitoring_service._live_reconcile_done`
- Circuit breaker excludes `account_type='live'` positions from template win rate

### Duplicate guard (trading_scheduler live pass)
Three checks before firing a live entry:
- (a) Open live position for this symbol → skip
- (b) Pending live order for this symbol → skip
- (c) Any live entry order submitted in last 4h → skip (covers pre-market window)

### DB schema changes (migrations/)
- `migrations/migrate_etoro_id_constraint.sql` — replaced global `positions_etoro_position_id_key` with composite `uq_positions_etoro_id_account`

---

## GRADUATION PIPELINE — HOW IT WORKS NOW

### Thresholds (from `autonomous_trading.yaml` graduation_gate section)
- `min_trades: 15` (lowered from 20 to enable GOOGL test graduation)
- `min_win_rate_pct: 55.0`
- `min_qualification_ratio: 0.6` (paper Sharpe ≥ 60% of WF Sharpe)
- `max_qualification_ratio_cap: 2.0` (paper Sharpe must not exceed 2× WF Sharpe — regime-luck guard)
- `rejection_cooldown_days: 14`

### Key fix: wf_test_sharpe lookup
The approaching-graduation SQL was looking for `wf_sharpe` and `walk_forward_sharpe`. All 120 active strategies store WF Sharpe under `wf_test_sharpe`. Fixed in `strategies.py` — COALESCE priority: `wf_test_sharpe → wf_sharpe → walk_forward_sharpe`.

### Graduation pipeline state
- No pairs currently qualify at 15-trade threshold with the 2.0× ratio cap
- MU / 4H EMA Ribbon is closest: 13 trades, 76.9% WR, ratio 2.46 (blocked by ratio cap)
- XLK / 4H EMA Ribbon: 10 trades, 90% WR, ratio 2.94 (blocked by ratio cap)
- Pipeline will fill ~July-August as 4H strategies accumulate 15+ trades per pair

---

## UI NAVIGATION — CURRENT STRUCTURE

### Book page tabs
Positions · Orders · Live  
(Execution moved to Research)

### Research page tabs
Performance · **Execution** · Attribution · Trades · Regime · Alpha Edge · Tear Sheet · Stress · Journal

### Guard page tabs
**System** · Risk · Gates · Circuit Breakers · Alerts · Audit  
(System is now first tab and default landing)

### Key analytics surfaces
- **Fund Scorecard (Command)**: 3×3 grid — Sharpe · Sortino · Max DD / Win rate · Profit factor · Alpha vs SPY / Total return (% + $) · Realised P&L (% + $) · Unrealised P&L ($)
- **Research/Performance headline tiles**: Total return (% + $) · Realised P&L (% + $) · Alpha vs SPY · Sharpe · Sortino · Max DD · Win rate · Profit factor · Daily returns
- **Equity chart hover**: Equity · Realised · Realised α SPY (when SPY toggle on) · Drawdown · Alpha vs SPY
- **Library pills**: Signals today · Idle 7d+ · Negative live P&L · Graduation eligible · Paper ≥20 trades · Promoted today · Activated today · Live today

---

## KNOWN ISSUES / TECHNICAL DEBT

- **PAPER conviction threshold** — lowered to 70 (was 73) on 2026-05-14. Monitor 70–72 band performance. If win rate holds up over 15+ trades per strategy, graduation gate will filter correctly. Revisit graduation gate ratio cap (2.0×) once more data accumulates in 70–72 band.
- **min_trades=15 in graduation_gate** — intentionally lowered to enable GOOGL test graduation. Raise back to 20 once live system is stable and you want stricter graduation criteria.
- **Transaction costs — crypto min_return_per_trade** — now that crypto round-trip is correctly modelled at 1.5% (Diamond tier), the `min_return_per_trade` thresholds for crypto (1d: 3%, 4h: 1.5%, 1h: 0.9%) should be reviewed upward. Monitor a few cycles first.
- **VaR check disabled** — portfolio VaR was 97.97% (model artefact from young equity curve). Disabled in Settings. Re-enable after 90+ days of equity history.
- **4h cooldown on live orders** — belt-and-suspenders guard. May delay re-entry after legitimate position close. Consider reducing to 1h once system is stable.
- **Triple EMA Alignment DSL bug** — `EMA(10) > EMA(10)` always false, generates 0 trades.
- **Sector Rotation + Pairs Trading templates** — structurally broken, need design session.
- **Walk-forward bypass paths admit regime-luck** — LONG test-dominant path still loose. Consider consistency gate `(test_sharpe - train_sharpe) ≤ 1.5`.
- **Entry order 82% FAILED rate** — cosmetic: market-closed deferrals written as FAILED then re-fired each cycle.
- **Cycle-error observability gap** — stage failures log silently, no `signal_decisions` row written.
- **Optimistic position write** — `etoro_position_id` is now nullable (migration applied). Pending positions use `pending_<order_id>` placeholder. Fill handlers update to real ID. Monitor for any edge cases with position sync or TSL on pending rows.

---

## SESSION START CHECKLIST

```bash
# Health + errors
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'tail -20 /home/ubuntu/alphacent/logs/errors.log'
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'tail -10 /home/ubuntu/alphacent/logs/cycles/cycle_history.log'

# Live position status
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo -u postgres psql alphacent -c "SELECT id, symbol, side, entry_price, current_price, unrealized_pnl, account_type, opened_at, stop_loss FROM positions WHERE account_type='"'"'live'"'"' AND closed_at IS NULL;"'

# Live pass activity
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'grep "Live pass\|LIVE FILL\|UniqueViolation\|PK collision" /home/ubuntu/alphacent/logs/system.log | tail -10'

# Strategy counts
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo -u postgres psql alphacent -t -A -c "SELECT status, COUNT(*) FROM strategies GROUP BY status ORDER BY status;"'

# Sync autonomous_trading.yaml (always do this)
scp -i ~/Downloads/alphacent-key.pem ubuntu@34.252.61.149:/home/ubuntu/alphacent/config/autonomous_trading.yaml config/autonomous_trading.yaml
```

---

## NEXT SESSION PROMPT

```
Read .kiro/steering/trading-system-context.md and Session_Continuation.md in full
before doing anything. Then read docs/ALPHACENT_SYSTEM_AUDIT_2026-05.md §16
(Strategy Lifecycle) and docs/GAP_ANALYSIS_2026-05.md §17–§20 (lifecycle gaps +
prioritisation).

System state at start of this session:
- DEMO: ~$479K equity, 70 open positions, trending_up_strong, MQS 84
- PAPER conviction threshold: 60 / 55 (crypto) — G-43 fix landed 2026-05-17
- LIVE: 1 open position — GOOGL LONG +$16.63, strategy 918b0c99
- live_trading.enabled: TRUE
- Latest commit: b1378e1 (G-43)

Mission this session — close the P0 gaps before LIVE strategy #2

P0 gaps (LIVE pass currently bypasses the entire risk framework):
  G-44: trading_scheduler._run_trading_cycle:2148+ does NOT call
        RiskManager.validate_signal for LIVE. No heat cap, sector cap,
        directional balance, VaR, correlation, circuit breaker on real capital.
  G-45: LIVE pass does NOT call RiskManager.calculate_position_size. No vol
        scaling, drawdown sizing, conviction-tier sizing, MQS multiplier on
        LIVE. CIO size at graduation is fixed for the strategy's lifetime
        regardless of regime.

Both close together — same architectural change. The pattern is already there
for PAPER (is_paper=True branch in calculate_position_size). LIVE needs the
parallel is_live=True branch.

Steps:
  1. Study the lifecycle adaptation gaps
     - Read trading_scheduler._run_trading_cycle:1948-2200 (LIVE pass).
     - Read risk_manager.calculate_position_size:757-1370 (the 11-step
       pipeline) and validate_signal:557-755.
     - Confirm the gap by tracing the LIVE call path.
  2. Make a plan for G-44 + G-45 together (Option A from §19: pass account_type
     through and add an is_live=True branch). Write the plan as a steering note
     OR a doc in docs/ before coding.
  3. Implement:
     - Add is_live=True parameter to calculate_position_size with branching:
       - LIVE base risk: live_trading.base_risk_pct (0.6%)
       - LIVE symbol cap: live_trading.symbol_cap_pct (20%)
       - LIVE heat cap: live_trading.portfolio_heat_cap (90%)
       - LIVE min order: live_trading.min_order_size (200)
       - LIVE max order: live_trading.max_order_size (1500)
       - Apply vol scaling, conviction tier, drawdown sizing, MQS multiplier,
         sector cap, correlation adjustment.
       - Cap final size at CIO live_strategies.position_size (the CIO sets
         the max; the pipeline sizes lower if risk demands).
     - Call validate_signal(..., is_paper=False) and
       calculate_position_size(..., is_live=True) in the LIVE pass.
  4. Verify:
     - Restart, watch logs/alphacent.log for LIVE pass invocation.
     - Confirm the existing GOOGL position is still tracked correctly.
     - Confirm LIVE pass conviction gate (73) still fires on signals.
     - Sanity-check that on the next signal cycle, sizing logs show vol
       scaling, sector cap, etc applied to LIVE.
  5. Document in Session_Continuation post-fix and commit.

Do NOT touch P1/P2/P3 in this session unless directly required to land G-44/G-45.
Stage discipline: this is a foundational architectural change; ship it clean.

If anything in the gap analysis or audit feels wrong, say so — those documents
are working artefacts, not gospel. Read the code, then decide.
```
