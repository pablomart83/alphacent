# AlphaCent — Session Continuation

> Permanent rules are in `.kiro/steering/trading-system-context.md`. This file holds current system state, recent fixes, and open items.

---

## ⚡ NEXT SESSION KICKOFF

**Platform is in active iteration — live trading is running, graduation pipeline is working, Intel page is live.**

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

## CURRENT SYSTEM STATE (2026-05-15 end of session)

- **DEMO equity:** ~$493K | **Open positions:** ~74 | **Regime:** trending_up_strong
- **DEMO strategies:** ~43 active (mix of PAPER + BACKTESTED), 1h strategies now activating
- **LIVE strategy:** `4H EMA Ribbon Trend Long GOOGL LIVE` (id: `918b0c99`) — status LIVE
- **LIVE positions:** 1 open — GOOGL LONG, entry 389.2, SL 365.82, TP 447.53 ✅
- **live_trading.enabled:** TRUE
- **PAPER conviction threshold:** 70 (lowered from 73 via Settings UI)
- **Latest commit:** `74e0d84`

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
Read .kiro/steering/trading-system-context.md and Session_Continuation.md in full before doing anything.

System state:
- DEMO: ~$493K equity, ~69 open positions, trending_up_strong
- PAPER conviction threshold: 70 (lowered from 73 on 2026-05-14)
- LIVE: 1 open position — GOOGL LONG, entry 389.2, SL 365.82, TP 447.53, strategy 918b0c99 ✅
- live_trading.enabled: TRUE
- Latest commit: 9ad34ad

Key changes this session (do not re-patch):
- Intel page live at /intel — 101 calibrated findings (9ad34ad and prior)
  Calibration fixes: C1/C2 use equity not balance, A7 distinct strategies,
  A10/E5 use order_submitted not signal_emitted, A6 deduped vs A1,
  G9 threshold -1000% + train>0, E5 UUID fallback name lookup
- Regime gate REMOVED from trading_scheduler (b625cdb)
  → Conviction scorer is now the single source of truth for regime fit
  → SHORT concentration limit kept (max 3 open equity shorts, all regimes)
- Conviction scorer: 5 fairness fixes for SHORT/low-freq strategies (82d192e)
  → F SHORT, BB VEEV, Stoch Midrange FOREX, NATGAS Parabolic now pass 70
- Guard System tab: MonitoringServiceCard flattens nested payload (3c83730)
- Attribution tab: removed h-full/shrink-0 wrappers causing chart overlap (3c83730)

Next priorities (use Intel page to triage):
1. P0 B5: eToro position ID collision demo/live — investigate
2. P0 F1: 5367 errors in errors.log — check what they are
3. P0 F2: 33 SQLAlchemy InFailedSqlTransaction — fix transaction handling
4. P1 E5: 18 strategies with gate blocks + 0 orders (Keltner TSM 302 blocks) — investigate gate
5. P2 G5: GOOGL LIVE Sharpe -17.23 vs WF 2.73 — live strategy underperforming
6. P2 E2: WF cache hit rate 27% — cycles slower than needed
7. Monitor SHORT strategies: first paper trades should appear within 1-2 cycles
8. Review crypto min_return_per_trade thresholds (1.5% round-trip now correctly modelled)
9. Graduation gate: raise min_trades back to 20 once live system stable
```
