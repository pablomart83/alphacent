# AlphaCent — Session Continuation Prompt

Read `#File:.kiro/steering/trading-system-context.md` for full system context, then read this prompt carefully before proceeding.

---

## Observability & Log Access

### Log files on EC2 (`/home/ubuntu/alphacent/logs/`)

| File | What's in it | When to read it |
|---|---|---|
| `errors.log` | ERROR + CRITICAL only | **First thing every session** — near-empty on healthy days |
| `warnings.log` | WARNING only | Position sizing bumps, stale data, API failures |
| `alphacent.log` | Full INFO+ audit trail (rotates 10MB × 5) | Deep dive into any issue |
| `strategy.log` | All `src.strategy.*`, `src.analytics.*`, `src.ml.*` | Signal gen, WF, conviction scoring |
| `risk.log` | All `src.risk.*` | Position sizing, risk validation |
| `data.log` | All `src.data.*` | Price fetches, data quality, cache hits |
| `api.log` | All `src.api.*` | HTTP requests, eToro API calls |
| `system.log` | All `src.core.*` | Monitoring service, scheduler, order monitor |
| `execution.log` | All `src.execution.*` | Order execution, trailing stops |
| `cycles/cycle_history.log` | Structured autonomous cycle + signal cycle summaries | **Best for cycle diagnostics** |

### How to read logs for troubleshooting

```bash
# 1. Always start here — any errors since last restart?
ssh ... 'cat /home/ubuntu/alphacent/logs/errors.log'

# 2. Check recent signal cycles (what fired, what was rejected, what orders placed)
ssh ... 'tail -100 /home/ubuntu/alphacent/logs/cycles/cycle_history.log'

# 3. Why did a specific signal get rejected?
ssh ... 'grep "HIMS\|APP\|IONQ" /home/ubuntu/alphacent/logs/strategy.log | tail -30'

# 4. Position sizing issues
ssh ... 'grep "below.*minimum\|bump\|Rejecting" /home/ubuntu/alphacent/logs/risk.log | tail -20'

# 5. Full recent activity (last 200 lines of main log)
ssh ... 'tail -200 /home/ubuntu/alphacent/logs/alphacent.log'

# 6. journalctl (volatile/in-memory only — use for live tailing, not history)
ssh ... 'sudo journalctl -u alphacent -f'   # live tail
ssh ... 'sudo journalctl -u alphacent --no-pager -n 200 2>/dev/null'  # last 200 lines since restart
```

### Storage budget
- `logs/` total: ~400MB typical, ~800MB worst case (14GB free on EC2 — fine)
- `alphacent.log`: 10MB × 6 = 60MB max (full audit trail, 5 backups)
- `errors.log` / `warnings.log`: 10MB × 6 = 60MB each (low volume)
- Component logs (`strategy`, `data`, etc.): 10MB × 4 = 40MB each (3 backups)
- `journald`: volatile (in-memory only, cleared on restart) — same data as alphacent.log, no disk cost

---

## Philosophy

AlphaCent is not a side project. It is the technology backbone of a systematic trading operation built to institutional standards. Every line of code, every architectural decision, every deployment choice is made as if managing a $100B book. We don't ship code that "works" — we ship code that is correct, resilient, and auditable.

**Development principles:**
- Correctness over speed. A bug in a trading system is a P&L event.
- Defensive programming. Every external call can fail. Every assumption can be wrong.
- Operational reliability. The system runs 24/7 unattended. If it can't handle 3am on a Sunday, it's not ready.
- Data integrity. Stale data, missing bars, and silent failures are existential risks.
- Risk-first thinking. Every feature is evaluated through the lens of capital preservation.
- Clean architecture. No dead code, no orphaned files, no "temporary" hacks that become permanent.

---

## System Architecture

```
Frontend (React/Vite)  →  Nginx (SSL/443)  →  Backend (FastAPI/uvicorn)
                                                    ├── MonitoringService (24/7)
                                                    │   ├── Position sync (60s)
                                                    │   ├── Trailing stops (30s)
                                                    │   ├── Partial exits (5s)
                                                    │   ├── Position health checks
                                                    │   ├── Quick price update (10min)
                                                    │   ├── Full price sync (55min)
                                                    │   └── Fundamental exits (daily)
                                                    ├── TradingScheduler
                                                    │   ├── Signal generation (30min)
                                                    │   ├── Risk validation
                                                    │   └── Order execution
                                                    └── PostgreSQL 16
```

**Key components:**
- `src/core/monitoring_service.py` — 24/7 position monitoring, trailing stops, price syncs
- `src/core/trading_scheduler.py` — Signal generation and order execution loop
- `src/core/order_monitor.py` — Position sync with eToro, cache management
- `src/core/symbol_registry.py` — Centralized symbol config loaded from `config/symbols.yaml`
- `src/core/auth.py` — DB-backed user authentication with role-based permissions
- `src/strategy/strategy_engine.py` — DSL + Alpha Edge signal generation, backtesting
- `src/strategy/strategy_proposer.py` — Strategy proposal, walk-forward validation, MC bootstrap
- `src/strategy/portfolio_manager.py` — Position-level risk management, decay scoring
- `src/api/etoro_client.py` — eToro API client with circuit breakers
- `src/models/orm.py` — SQLAlchemy ORM with EnumString, NumpySafeJSON type decorators
- `src/models/database.py` — PostgreSQL connection pooling, numpy adapters
- `src/core/config_loader.py` — Merges `autonomous_trading.yaml` + `api_keys.yaml` overlay

---

## Infrastructure (AWS)

| Resource | Details |
|---|---|
| Dashboard | https://alphacent.co.uk |
| EC2 instance | `i-035d5576835fcef0a` (t3.medium, eu-west-1) |
| Public IP | `34.252.61.149` |
| SSH | `ssh -i ~/Downloads/alphacent-key.pem ubuntu@34.252.61.149` |
| GitHub | `github.com/pablomart83/alphacent` (private) |

### Services on EC2

| Service | Manager | Command |
|---|---|---|
| Backend (uvicorn) | systemd | `sudo systemctl restart alphacent` |
| Nginx | systemd | `sudo systemctl reload nginx` |
| PostgreSQL 16 | systemd | `sudo systemctl status postgresql` |

**Important:** The systemd service has `ExecStartPre=/bin/bash /home/ubuntu/alphacent/deploy/patch-api-keys.sh` — this runs before uvicorn starts and writes real API keys from AWS Secrets Manager into `config/api_keys.yaml`. Never remove this.

### Agent Operational Procedures

```bash
# SSH
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149

# Single command
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'command here'

# SCP files
scp -i ~/Downloads/alphacent-key.pem src/path/file.py ubuntu@34.252.61.149:/home/ubuntu/alphacent/src/path/file.py

# Restart backend (ExecStartPre patches API keys automatically)
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo systemctl restart alphacent && sleep 12 && curl -sf http://localhost:8000/health'

# Rebuild frontend
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'cd /home/ubuntu/alphacent/frontend && VITE_API_BASE_URL=https://alphacent.co.uk VITE_WS_BASE_URL=wss://alphacent.co.uk npm run build 2>&1 | tail -5'

# DB access
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 "sudo -u postgres psql alphacent -t -A -c 'SQL HERE'"

# Logs
ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149 'sudo journalctl -u alphacent --no-pager -n 100 2>/dev/null | grep -i "search term"'
```

### Standard Deployment Workflow
1. Edit files locally
2. Run `getDiagnostics` to check for errors
3. SCP changed files to EC2
4. Restart backend if Python/config changed
5. Rebuild frontend if .tsx/.ts changed
6. Verify health: `curl -sf http://localhost:8000/health`
7. `git add . && git commit -m "..." && git -c core.hooksPath=/dev/null push`

---

## Current System State (April 18, 2026)

- **Database:** PostgreSQL 16 on EC2, 32+ tables, 780K+ rows
- **Account:** eToro DEMO, balance ~$162K, equity ~$464K
- **Symbol universe:** 297 (232 stocks, 42 ETFs, 8 forex, 5 indices, 8 commodities, 2 crypto — BTC/ETH only)
- **Active strategies:** 116 DEMO + 25 BACKTESTED (ready for activation)
- **Open positions:** ~197
- **Templates:** 185 (was 241 — removed 56 1h crypto templates)
- **Monitoring:** 24/7 + CloudWatch alerting + EXIT signal processing
- **Market regime:** Equity: trending_up_weak, Crypto: strong uptrend, Forex: ranging_low_vol, Commodity: strong uptrend
- **Auth:** DB-backed with role-based permissions (admin/trader/viewer)

---

## Key Parameters (Post Sprint 1-7)

### Risk Management (Sprint 3)
- Stock/ETF SL: 6%, TP: 15% (2.5:1 R:R)
- Forex SL: 2%, TP: 5%
- Crypto SL: 8%, TP: 20%
- Index SL: 5%, TP: 12%
- Commodity SL: 4%, TP: 10%
- ATR trail multiplier: 2.0x (raised from 1.5x)
- Min R:R: 1.5:1 (config), 2:1 enforced in proposer code
- Trailing stop activation: 12% profit, 4% trail distance
- Partial exit: 18% profit, 33% exit

### Position Sizing (Sprint 3)
- Vol scaling: min 0.10x, max 1.50x (target vol 16%)
- Confidence floor: 0.30 (reject signals below)
- Symbol cap: 5% of equity max
- Sector soft cap: 30% (halve size if exceeded)
- Drawdown sizing: 50% reduction at >5% DD, 75% at >10% DD (30d peak)
- Min position: $2,000

### Activation Thresholds
- `min_trades_dsl`: 8 (1d strategies)
- `min_trades_dsl_4h`: 8 (4h strategies)
- `min_trades_alpha_edge`: 8
- `min_trades_commodity`: 6
- `min_trades_dsl_1h`: 20 (1h — crypto removed anyway)
- Sharpe exception: test_sharpe ≥ 2.0 with ≥ 3 trades passes regardless of min_trades

### Conviction Scoring
- Normalized to 0-100 (theoretical max was 139)
- Threshold: 60 (now means 60% of max evidence)
- Components: WF edge (40), signal quality (25), regime fit (20), asset tradability (15), fundamental quality (±15), carry bias (±5), crypto cycle (±5), news sentiment (±8), factor exposure (±6)

### Monte Carlo Bootstrap
- 1000 iterations, p5 Sharpe threshold: 0.2
- Min trades for bootstrap: 15 (strategies with < 15 trades pass through — min_trades gate handles them)
- Correctly filtering noise: strategies with wide return distributions get rejected even with positive test Sharpe

---

## Autonomous Cycle Pipeline

The cycle runs in stages:
1. **Cleanup** — retire stale BACKTESTED strategies
2. **Market analysis** — regime detection, fundamental data loading
3. **Proposal** — 50-200 strategies proposed from template library
4. **Walk-forward validation** — train/test split, Sharpe/trades/overfitting checks
5. **Monte Carlo bootstrap** — resample trade P&L 1000x, require p5 Sharpe ≥ 0.2 (only for ≥15 trades)
6. **Direction-aware thresholds** — regime-specific min Sharpe/win-rate/return
7. **Conviction scoring** — FMP fundamentals, carry bias, crypto cycle, news sentiment
8. **Activation** — top strategies by conviction score → BACKTESTED status
9. **Signal generation** — run signals for newly activated strategies

**Typical cycle results (50 proposals):**
- ~40 go through WF
- ~10 pass WF (25% pass rate)
- ~4 pass MC bootstrap
- ~2-3 approved (BACKTESTED)
- Duration: 60-90 seconds

---

## Known Issues & Bugs Fixed (April 18, 2026)

### Fixed in this session:
1. **`self.config` AttributeError** — `strategy_proposer.py` WF min_trades check used `self.config` which doesn't exist. Fixed to load from YAML inline.
2. **4-tuple disk cache crash** — `_save_wf_failed_to_disk` stored 4 fields, loaded as 4-tuple, padded to 7 with `wf_results=None`. All loops now guard `if wf is None`. Now stores 6 scalars.
3. **MC bootstrap DataFrame crash** — `test_results.trades` is a DataFrame; `df or []` raises ValueError. Fixed with explicit `hasattr(trades_list, 'to_dict')` check.
4. **`total_cost_pct` uninitialized** — only assigned inside `if commission > 0 or slippage_bps > 0:` block but referenced in return statement. Fixed by initializing to 0.0.
5. **FMP singleton stale key** — `FundamentalDataProvider` singleton created at startup before `api_keys.yaml` written. Fixed: `fmp_api_key` is now a `@property` that re-reads `api_keys.yaml` if cached value is placeholder.
6. **MC bootstrap too aggressive** — `MC_MIN_TRADES_FOR_BOOTSTRAP=5` meant strategies with 8-11 trades got rejected as noise. Raised to 15.
7. **`trades=low` rejecting high-Sharpe strategies** — Added Sharpe exception: test_sharpe ≥ 2.0 with ≥ 3 trades passes regardless of min_trades threshold.
8. **`ExecStartPre` missing** — Backend started before `api_keys.yaml` was written. Added `ExecStartPre=/bin/bash /home/ubuntu/alphacent/deploy/patch-api-keys.sh` to systemd service.

### Known remaining issues:
- **ZINC 1h data missing** — `Intraday Momentum Burst` template fails for commodity symbols on 1h timeframe. ZINC only has daily data.
- **Triple EMA Alignment DSL bug** — `EMA(10) > EMA(10)` always false (comparing indicator to itself). Template generates 0 trades.
- **`4H Commodity Momentum Breakout Long` crash** — `not enough values to unpack (expected 7, got 4)` in a different code path. Non-critical (caught by exception handler).
- **FMP 401 errors during market analysis** — Happen at startup before the lazy property fix can help (singleton created in first milliseconds). Non-blocking — FMP cache has 8 quarters of data for most symbols.

---

## Database Indexes (Sprint 6.1 — Applied April 18)

```sql
idx_positions_strategy_id ON positions(strategy_id)
idx_positions_closed_at ON positions(closed_at)
idx_positions_pending_closure ON positions(pending_closure) WHERE pending_closure = true
idx_orders_status ON orders(status)
idx_orders_strategy_id ON orders(strategy_id)
idx_historical_price_cache_symbol_date ON historical_price_cache(symbol, date DESC)
```

---

## Sprints Completed (April 18, 2026)

### Sprint 3 — Risk Management & Position Sizing ✅
- Pre-trade portfolio VaR check (1-day 95% historical simulation, max 2% of equity, fail-open)
- Drawdown-based position sizing (50% at >5% DD, 75% at >10% DD from 30d peak)
- ATR trail multiplier 1.5 → 2.0
- Conviction score normalized to 0-100 (was 0-139)
- Vol scaling min 0.25→0.10, max 2.5→1.50; confidence floor 0.30; 5% symbol cap; 30% sector soft cap
- Rolling 60-day OLS hedge ratio for pairs trading (was static full-window); hedge_ratio in signal metadata

### Sprint 4 — Template Library Cleanup ✅
- Removed 56 1h crypto templates (1H underperforms 90% of the time for crypto)
- Created `scripts/utilities/cull_low_activation_templates.py` for manual use

### Sprint 5 — Broken Endpoints ✅
- Routes already in correct order; frontend calls already correct

### Sprint 6 — Database & API Layer ✅
- 6 performance indexes applied directly via psql
- `TimeoutMiddleware` (30s, excludes /ws and autonomous cycle)
- `slowapi` rate limiting on `/auth/login` (5/minute per IP)

### Sprint 7 — Analytics & UI ✅
- `GET /analytics/r-multiples` + R-Multiple histogram in Tear Sheet tab
- `GET /analytics/stress-tests` (COVID, Lehman, SVB) + Stress Tests tab in Analytics
- `alpha_vs_spy` field in `GET /strategies` + Alpha column in Strategies table
- `deployed_capital` + `allocated_capital` in `GET /strategies` + allocation bar viz in side panel

---

## Strategy Retirement Decisions (April 18, 2026)

### Retired (pending_retirement — positions run to SL/TP naturally):
34 DEMO strategies with negative P&L + health ≤ 2 + decay = 0. Key ones:
- RSI Dip Buy V99 (-$183), RSI Dip Buy XLE (-$131), EMA Pullback Momentum V168 (-$106)
- 4H Stochastic Swing Long V113 (-$75), ATR Dynamic Trend Follow NSDQ100 (-$72)
- 4H ADX Trend Swing TXN (-$74), 4H BB Squeeze Swing Long V35 (-$56)

### Directly RETIRED (BACKTESTED — no positions):
57 BACKTESTED strategies: 54 with < 8 backtest trades + 3 crypto with SL < 8%

### Kept running (profitable despite failing new thresholds):
~47 DEMO strategies with positive P&L and health ≥ 3. These are grandfathered — live P&L supersedes backtest count concern. Key ones:
- RSI Dip Buy V11 (+$908), BB Midband Reversion Tight V135 (+$404), V59 (+$392)
- EMA Ribbon Expansion Long V44 (+$256), V117 (+$180)
- ATR Dynamic Trend Follow V72 (+$151)

---

## Open Items

### Performance Monitoring
- Monitor win rate impact of wider SL/TP (target: >45% from current ~34%)
- Track how many positions close via EXIT signals vs SL/TP vs trailing stops
- Monitor multi-strategy confluence: are 5 BTC LONGs from different strategies correlated?
- Evaluate if trailing stop activation at 12% is optimal

### Infrastructure
- Consider t3.small downgrade — waiting on CloudWatch memory data
- FMP API rate limit (300/min) — monitor with corrected per-call counting

### Sprint 4 (remaining)
- **4.2 Cull Low-Activation Templates** — run `scripts/utilities/cull_low_activation_templates.py --apply` manually when ready (needs `config/.proposal_tracker.json` populated with enough data)

### Sprint 9 — Autonomous Cycle Deep Dive ✅ (April 20, 2026)

**Audit findings from last cycle (500 proposals, 17:36 UTC):**
- 495 DSL + 5 Alpha Edge proposed
- 730 zero-trade blacklist entries, 135 rejection blacklist entries, 449 WF validated combos loaded
- WF pass rate: 34/473 = **7.2%** (expected ~25%) — MC bootstrap was the bottleneck
- MC bootstrap filtered 47 strategies — p5 values of -0.57 to -6.33 (annualization bug + threshold too high)
- 22 strategies reached activation; 14/22 failed on trade count (3-7 trades vs 8 threshold)
- Only 4 activated: Pairs Trading Market Neutral NEM, 4H VWAP TGT, Gold Momentum GOLD, Insider Buying CHTR
- ZINC/ALUMINUM crashing WF every cycle ("No historical data available") — LME guard was firing too late
- SHORT templates (MACD Divergence Short, EMA Rejection Short, BB Squeeze Reversal Short) wasting slots in trending_up regime

**Fixes shipped:**
1. **MC bootstrap annualization** — `sqrt(n_trades)` → `sqrt(trades_per_year)` using 180-day test window
2. **MC bootstrap threshold** — 0.2 → 0.0 (break-even bar; standard quant practice for post-WF filter)
3. **Activation Sharpe exception** — mirrors WF gate: Sharpe ≥ 2.0 + ≥ 3 trades bypasses min_trades at activation (not just at WF). Reads from `strategy.metadata['wf_test_sharpe']`
4. **Regime-directional filter** — in `trending_up*` regimes, SHORT-direction templates (non-neutral, non-AE) are suppressed before proposal. Recovers wasted proposal slots.
5. **LME metals guard** — moved ZINC/ALUMINUM/NICKEL intraday block to top of `get_historical_data()` before DB/Yahoo/FMP chain. Eliminates WF crash. Daily data path (FMP) preserved.

**Files changed:**
- `src/strategy/strategy_proposer.py` — MC bootstrap fix + regime short filter
- `src/strategy/portfolio_manager.py` — activation Sharpe exception
- `src/data/market_data_manager.py` — LME guard moved to top of function

**Remaining Sprint 9 items:**
- Monitor next cycle: expect WF pass rate to recover toward 20-25%, MC bootstrap to pass more strategies
- Strategy lifespan analysis (avg 5.4 days DEMO) — investigate why strategies retire fast
- Template diversity: Insider Buying 16/66 BACKTESTED (24%) — watch for over-concentration
- Consider longer test windows for low-frequency strategies (forex, commodities)
- Triple EMA Alignment DSL bug (`EMA(10) > EMA(10)` always false) — still open

**Signal generation audit (April 20):**
- 0 signals during autonomous cycle = expected — entry conditions not met at that moment
- 39 strategies excluded from signal gen = correct — `pending_retirement: true` (Sprint 8 retirements)
- 4 signals passed conviction in regular scheduler cycle → 2 orders filled (CAT, GE)
- IONQ rejected: vol-scaled size $458 < $2000 minimum, bump would be 4.4x (>3x guard)

**Position sizing review — deferred to Sprint 10:**
- Current design: `position_size = allocated_capital × confidence × vol_adjustment`
- Problem: 3x bump guard too conservative — rejects valid trades on high-vol symbols
- Correct approach: percentage-of-equity check instead of fixed multiplier
- Must account for: available balance, open exposure, margin, concentration limits
- Full design pass needed — not a quick fix
**Priority focus:** Audit and improve the autonomous cycle end-to-end.
- How are proposals being generated? Are templates being scored correctly?
- Walk-forward validation pass rate — is 25% healthy or are good strategies being filtered?
- MC bootstrap threshold (p5=0.2) — is it too conservative?
- Conviction scoring calibration — are the component weights right?
- Strategy lifespan analysis — why are strategies retiring so fast (avg 3d)?
- Template diversity — are we over-proposing the same templates?
- Proposal-to-activation funnel — where are strategies dropping out?
- Consider: longer test windows for low-frequency strategies
- Consider: regime-specific proposal filters (only propose trend strategies in trending_up)

### Sprint 8+ (Backlog)
- **R-Multiple Distribution** — histogram in Tear Sheet tab (backend done, needs frontend wiring)
- **Historical Stress Tests** — backend done, frontend tab added
- **Benchmark-Relative Performance Per Strategy** — alpha_vs_spy column added
- **Strategy Allocation Visualization** — deployed_capital bar chart added
- **ATR-based dynamic SL per position** — instead of fixed percentage per asset class
- **Portfolio-level VaR check** — implemented but needs monitoring to tune the 2% threshold
- **Template weight decay over time** — addressed with dynamic weighting but could be improved
- **Transcript sentiment** — module built but not integrated into conviction scorer

### Cycle Quality Issues to Watch
- **`trades=low` still dominant rejection** — even with Sharpe exception, many strategies have 0-2 trades in test window. Consider whether the test window (120-180 days) is appropriate for low-frequency strategies.
- **MC bootstrap p5 threshold** — 0.2 is conservative. Monitor whether good strategies are being blocked. The 4H MACD AUDUSD (1.28 Sharpe, 32 trades, p5=-0.64) was borderline.
- **WF pass rate ~25%** — healthy. Too high would mean insufficient filtering.

---

## Files Changed This Session (April 21, 2026)

### Backend
- `src/strategy/strategy_proposer.py` — fixed_symbols dedup race condition (Gold Momentum GOLD was being proposed 10x — dedup checked assigned_symbol but fixed_symbols templates override that; now also checks actual fixed_symbols list against active_symbol_template_pairs)
- `src/core/monitoring_service.py` — proper multi-slot autonomous scheduler: slot-based dedup (fire_key per day+time), 3-min window, 30s check interval (was 60s ±1min — too tight, missed cycles); auto-migrates legacy config
- `src/api/routers/control.py` — new GET/POST /control/autonomous/schedules endpoints; ScheduleSlot model (id/enabled/days[]/hour/minute); legacy /schedule endpoints preserved
- `src/strategy/trade_frequency_limiter.py` — monthly trade cap + minimum holding period now Alpha Edge only; DSL strategies trade on every valid signal (was blocking GS, XLE, SILVER, URA etc at 4/month)
- `src/strategy/conviction_scorer.py` — DSL signal confidence baseline: 8/12 pts at confidence floor (0.3), scales to 12 at 1.0 (was linear 0-12, penalising DSL for parser behaviour); float epsilon fix in passes_threshold (60.0 was being rejected as < 60)
- `src/strategy/autonomous_strategy_manager.py` — cycle report now tracks raw signals (pre-conviction) vs signals that passed; "0 Signals" no longer misleading
- `src/strategy/strategy_engine.py` — _last_batch_raw_signals counter for accurate reporting; _last_batch_raw_signals reset at start of each batch
- `src/core/trading_scheduler.py` — **critical bug fix**: `existing_template_names` was only initialized inside `if existing_count > 0` block but referenced unconditionally at line 1908 in `_coordinate_signals`; caused UnboundLocalError on every signal for symbols with no existing positions — silently dropped ALL signals from new strategies; raw signal count surfaced in result dict

### Frontend
- `frontend/src/pages/AutonomousNew.tsx` — SchedulerPanel component: add/remove slots, multi-day toggle (Mon-Sun), hour/minute picker, per-slot enable toggle, next run display; replaces old single frequency/day/time picker
- `frontend/src/services/api.ts` — getScheduleSlots() + updateScheduleSlots() + ScheduleSlot type

### Key Fixes This Session
1. **`existing_template_names` UnboundLocalError** — every signal for a new symbol (no existing positions) crashed _coordinate_signals, silently dropping all orders. This was killing signal execution for all newly activated BACKTESTED strategies. Fixed by initializing the variable before the conditional block.
2. **Monthly trade cap blocking DSL** — 4/month cap was Alpha Edge config applied to all strategies. GS, XLE, SILVER, URA etc were blocked. Fixed: DSL strategies bypass frequency limiter entirely.
3. **DSL conviction scores clustering 55-59** — signal confidence component was penalising DSL strategies for parser behaviour (0.3-0.5 confidence = 3.6-6/12 pts). Fixed: baseline 8/12 pts for any DSL signal clearing the confidence floor.
4. **Conviction float precision** — 60.0 was being rejected as < 60 due to floating point arithmetic. Fixed with 0.05 epsilon.
5. **Autonomous scheduler missing cycles** — ±1 min window + 60s check interval was too tight. Fixed: 3-min window, 30s check, slot-based dedup.
6. **Multi-slot scheduler** — replaced single frequency/day/time with proper multi-slot system. Default: weekdays 8:00+13:00 UTC, weekends 10:00 UTC.
7. **Gold Momentum GOLD 10x duplicates** — race condition in fixed_symbols dedup. Fixed.

### System State (April 21, 2026)
- **Equity:** ~$475,588 (+0.10% today, outperforming SPY -0.3% for 2nd consecutive day)
- **Open positions:** ~149
- **Active DEMO strategies:** ~101 (39 pending_retirement)
- **BACKTESTED:** ~96 (95 activation_approved)
- **Signal gen:** 28 signals passing conviction per cycle (post-fix), orders now being submitted
- **Orphaned positions cleared:** LCID, FXI, COPPER, ZINC (~$620 loss, ~$15K freed)

---

## Sprint 9 — Autonomous Cycle Deep Dive ✅ (April 20-21, 2026)

**Audit findings from last cycle (500 proposals, 17:36 UTC):**
- 495 DSL + 5 Alpha Edge proposed
- 730 zero-trade blacklist entries, 135 rejection blacklist entries, 449 WF validated combos loaded
- WF pass rate: 34/473 = **7.2%** (expected ~25%) — MC bootstrap was the bottleneck
- MC bootstrap filtered 47 strategies — p5 values of -0.57 to -6.33 (annualization bug + threshold too high)
- 22 strategies reached activation; 14/22 failed on trade count (3-7 trades vs 8 threshold)
- Only 4 activated: Pairs Trading Market Neutral NEM, 4H VWAP TGT, Gold Momentum GOLD, Insider Buying CHTR
- ZINC/ALUMINUM crashing WF every cycle ("No historical data available") — LME guard was firing too late
- SHORT templates (MACD Divergence Short, EMA Rejection Short, BB Squeeze Reversal Short) wasting slots in trending_up regime

**Fixes shipped:**
1. **MC bootstrap annualization** — `sqrt(n_trades)` → `sqrt(trades_per_year)` using 180-day test window
2. **MC bootstrap threshold** — 0.2 → 0.0 (break-even bar; standard quant practice for post-WF filter)
3. **Activation Sharpe exception** — mirrors WF gate: Sharpe ≥ 2.0 + ≥ 3 trades bypasses min_trades at activation (not just at WF). Reads from `strategy.metadata['wf_test_sharpe']`
4. **Regime-directional filter** — in `trending_up*` regimes, SHORT-direction templates (non-neutral, non-AE) are suppressed before proposal. Recovers wasted proposal slots.
5. **LME metals guard** — moved ZINC/ALUMINUM/NICKEL intraday block to top of `get_historical_data()` before DB/Yahoo/FMP chain. Eliminates WF crash. Daily data path (FMP) preserved.

**Signal generation audit (April 21):**
- 0 signals during autonomous cycle = was caused by _coordinate_signals crash (now fixed)
- 39 strategies excluded from signal gen = correct — `pending_retirement: true` (Sprint 8 retirements)
- Post-fix: 28 signals passing conviction per cycle, orders being submitted

**Position sizing review — deferred to Sprint 10:**
- Current design: `position_size = allocated_capital × confidence × vol_adjustment`
- Problem: 3x bump guard too conservative — rejects valid trades on high-vol symbols
- Correct approach: percentage-of-equity check instead of fixed multiplier
- Must account for: available balance, open exposure, margin, concentration limits
- Full design pass needed — not a quick fix

---

## Open Items for Next Session

### Signal Generation Quality
- **Conviction scores still clustering 55-59 for some strategies** — wf_edge 24-28/40 is the bottleneck (WF Sharpe 0.5-0.8). These are genuinely modest-conviction strategies. Monitor whether post-fix order flow is healthy before further tuning.
- **HIMS 57.7 rejected** — regime: 12.0 (weak match, mean_reversion in trending_up). This is correct behaviour — regime fit is a legitimate signal. Watch whether these strategies improve as regime shifts.
- **PYPL 59.5, AMD 58.5** — just under threshold. News sentiment penalty (-0.4, -0.8) is the marginal factor. Consider whether Marketaux free tier news is reliable enough to be a marginal gate factor.

### Position Sizing (Sprint 10)
- Full redesign of minimum order size logic
- Account for available balance, open exposure, margin
- Percentage-of-equity check instead of fixed 3x bump guard

### Strategy Lifespan
- Avg 5.7 days — investigate whether this is healthy or strategies are retiring too fast
- 39 pending_retirement strategies: ~45 open positions, -$513 unrealized, clearing over next 3-7 days

### Template Diversity
- Insider Buying: 16/66 BACKTESTED (24%) — watch for over-concentration
- Gold Momentum GOLD: 10 duplicates in BACKTESTED — harmless but should clean up (delete 9 duplicates from DB)
- Triple EMA Alignment DSL bug (`EMA(10) > EMA(10)` always false) — still open

### WF Pass Rate
- Currently ~8% — target 15-20%
- MC bootstrap (p5 threshold 0.0) is working correctly — genuinely noisy strategies being filtered
- Consider longer test windows for low-frequency strategies (forex, commodities currently 180d test)

---

## Sprint 10 — Log Audit & Watchlist Quality (April 22, 2026)

### Fixes Shipped

**Backend**
- `src/strategy/strategy_proposer.py` — DAILY_ONLY_SYMBOLS guard: skip ZINC/ALUMINUM/PLATINUM/NICKEL on 1h/4h templates before WF (eliminates 50+ errors/cycle); dividend_aristocrat pre-WF filter (yield < 1.5% skipped); watchlist overhaul: tiered WF thresholds by asset class (same: S>0.2/t≥3, adjacent: S>0.3/t≥4, cross-asset: S>0.5/t≥6), cap at 3 symbols, regime compatibility check, no floor guarantee
- `src/strategy/strategy_engine.py` — insider_buying fallback to momentum+volume proxy when FMP returns [] (403/404); intraday expected bar count fix (multiply by bars/day for 1h/4h, eliminates false 53% coverage warnings)
- `src/strategy/autonomous_strategy_manager.py` — AE dividend pre-filter before FMP backtest; gate3 `in_right_quintile` hard enforcement (was approving strategies where primary symbol not in right factor quintile)
- `src/data/market_data_manager.py` — OHLC epsilon fix in validate_data (strict < with 1e-8, eliminates false EURUSD warnings on valid open=high bars)
- `src/utils/symbol_mapper.py` — NICKEL added to DAILY_ONLY_SYMBOLS
- `src/core/monitoring_service.py` — duplicate `_check_strategy_decay()` call confirmed already removed

**Scripts (one-time ops)**
- `scripts/backfill_gap.py` — backfilled Apr 22–Sep 1 2025 data gap for 152 symbols (~91 trading days each); gap was causing WF test period to return 102 bars instead of 193, corrupting Sharpe/trade counts for all affected strategies
- `scripts/retire_null_sharpe.py` — retired 21 BACKTESTED strategies approved via factor_validation fallback with null wf_test_sharpe (FMP insider endpoint 403/404 + gate3 not enforced)
- `scripts/trim_watchlists.py` — trimmed 167 strategies to new watchlist rules; 54 single-symbol, 14 two-symbol, 158 three-symbol after cleanup
- `scripts/restore_active_position_symbols.py` — restored 58 orphaned positions (symbols removed by trim but with open positions); 45 strategies updated
- `scripts/flag_weak_watchlist_losers.py` — flagged 33 losing weak-watchlist positions for pending_closure (-$1,080 P&L, ~$85K capital freed)

### Key Findings from Log Audit

1. **ALUMINUM/ZINC errors** — LME guard was working but strategy_engine raised ValueError on empty return; fixed at proposal stage (DAILY_ONLY guard before WF)
2. **152-symbol data gap (Apr–Sep 2025)** — WF test period fell entirely in this gap, producing corrupted Sharpe/trade counts for months; backfilled
3. **21 null-Sharpe AE strategies** — approved via factor_validation fallback because FMP insider endpoint unavailable (403/404); gate3 `in_right_quintile=false` not enforced; all retired
4. **Watchlist was too permissive** — S>0.15/t≥2 allowed cross-asset noise (stock strategies trading forex, commodity strategies trading stocks); 34% of open positions were on weak-evidence watchlist symbols; 33 losing ones flagged for closure
5. **EURUSD OHLC false warnings** — valid down-day bars (open=high) were being rejected; epsilon fix
6. **Coverage warnings were false positives** — intraday expected bar count was using daily bar formula; fixed

### System State (April 22, 2026)
- **Equity:** ~$475K
- **Open positions:** ~170 (33 pending_closure from weak watchlist audit)
- **Active DEMO strategies:** ~99
- **BACKTESTED:** ~106 (21 null-Sharpe retired, watchlists cleaned)
- **Watchlist distribution:** 54 single / 14 two-symbol / 158 three-symbol (was mostly 4-5)
- **Capital being freed:** ~$85K from 33 weak-watchlist closures
- **Data gap:** filled for all 152 affected symbols

### Open Items for Next Session
- **Triple EMA Alignment DSL bug** (`EMA(10) > EMA(10)` always false) — still open
- **Position sizing Sprint 10** — 3x bump guard too conservative; percentage-of-equity redesign needed
- **Strategy lifespan** — avg 5.7 days; investigate whether healthy or retiring too fast
- **Gold Momentum GOLD duplicates** — 10 copies in BACKTESTED; delete 9
- **FMP insider endpoint** — currently 403/404 on current plan; insider_buying now uses momentum proxy fallback; consider plan upgrade to restore real insider data
- **gate3 in_right_quintile** — fix shipped; monitor next AE cycle to confirm no false approvals
- **WF pass rate** — data gap now filled; expect improvement in next cycle (was ~8%, target 15-20%)
- **Group 1 high-Sharpe BACKTESTED strategies** — validated on single-regime test period (Sep-Oct 2025 rally only due to data gap); monitor live performance; decay scorer will retire underperformers naturally

### Backend (Previous Session — April 21, 2026)
- `src/strategy/strategy_engine.py` — exit signals bypass conviction/ML filters (critical fix); improved rejection log
- `src/strategy/conviction_scorer.py` — news sentiment impact reduced to ±1pt (was ±8, 90% negative bias on free tier)
- `src/data/news_sentiment_provider.py` — articles 5→10, sort=published_at, get_article_count() method
- `src/core/monitoring_service.py` — zombie exit rule (_check_zombie_exits, 6h interval); _last_zombie_check init
- `src/core/trading_scheduler.py` — cross-cycle same-template dedup (blocks EMA Ribbon V7+V106+V117 all opening QQQ)
- `src/api/routers/analytics.py` — template win rate double-division fix (was /100 twice → 0.9% instead of 90%)
- `src/api/routers/strategies.py` — template rankings win_rate ×100 fix; template-rankings endpoint
- `src/api/routers/account.py` — PositionResponse: add sector/asset_class fields; use SymbolRegistry directly
- `src/api/routers/risk.py` — _get_asset_class uses SymbolRegistry instead of sector-map hack
- `src/api/routers/data_management.py` — score_distribution (bullish/neutral/bearish/avg) in sentiment coverage
- `src/data/news_sentiment_provider.py` — TTL threshold 4→8 articles for earnings-week

### Frontend (Previous Session — April 21, 2026)
- `frontend/src/pages/analytics/PerformanceTab.tsx` — full Performance tab redesign (new component)
- `frontend/src/pages/AnalyticsNew.tsx` — interval/period buttons now trigger refetch (stale closure fix); forceRefresh param
- `frontend/src/components/charts/EquityCurveChart.tsx` — SPY benchmark fetch via dedicated API call
- `frontend/src/components/charts/TvChart.tsx` — toChartTime handles Unix timestamp strings for intraday
- `frontend/src/components/trading/TradingCyclePipeline.tsx` — live cycle log panel with autoscroll
- `frontend/src/pages/DataManagementNew.tsx` — score distribution display (bullish/neutral/bearish)

### Key Fixes (April 21, 2026)
1. **Exit signals were being filtered by conviction scorer** — DSL exits never fired, positions only closed via SL/TP
2. **Asset class/sector showing Unknown** — PositionResponse missing fields, Pydantic was dropping them
3. **News sentiment ±8pts on 3 articles** — 90% negative bias on Marketaux free tier, reduced to ±1pt
4. **Template win rate 0.9%** — double /100 division bug in two separate endpoints
5. **Same-template cross-cycle duplicates** — EMA Ribbon V7/V106/V117/V179 all opened QQQ independently
6. **1H/4H interval buttons did nothing** — stale closure captured old equityInterval value
7. **Sharpe ratio 7.82** — only 15 daily snapshots, inflated by tiny std dev; added daily_returns_count field

### System State (April 20, 2026)
- **Equity:** ~$474K (+3.7% since Mar 31)
- **Open positions:** ~185 (down from 188 after exit signal fix)
- **Today's realized P&L:** +$1,047 (13 DSL exits: +$1,893, 3 stale underwater: -$530, 1 SL: -$316)
- **Exit signal fix impact:** 12 positions closed in first cycle after fix (ADI, GLD, HYG, TLT, OKTA, XBI, AMGN, SPY, SPX500, NSDQ100, DJ30, XBI)
- **vs SPY today:** -0.08% vs SPY -0.30% ✓ outperformed
- **Zombie exit rule:** 23 flat positions flagged (±1% for 14+ days), ~$58K capital to redeploy
- **Orphaned positions flagged:** COPPER/FXI/ZINC/LCID (~$15K freed)

## Files Changed Previous Session (April 18, 2026)

### Backend
- `src/risk/risk_manager.py` — VaR check, drawdown sizing, vol scaling, symbol/sector caps
- `src/strategy/conviction_scorer.py` — score normalization to 0-100
- `src/execution/position_manager.py` — ATR multiplier 1.5→2.0
- `src/strategy/strategy_engine.py` — total_cost_pct initialization fix
- `src/strategy/strategy_proposer.py` — self.config fix, 4-tuple→6-tuple disk cache, MC threshold 5→15, Sharpe exception, wf=None guards (3 loops)
- `src/strategy/strategy_templates.py` — remove 56 1h crypto templates
- `src/data/fundamental_data_provider.py` — fmp_api_key lazy property, singleton reset
- `src/api/app.py` — TimeoutMiddleware, SlowAPI rate limiter
- `src/api/routers/auth.py` — rate limiting on /auth/login
- `src/api/routers/analytics.py` — r-multiples endpoint, stress-tests endpoint
- `src/api/routers/strategies.py` — alpha_vs_spy, deployed_capital, allocated_capital
- `config/autonomous_trading.yaml` — all Sprint 3 risk params, relaxed min_trades thresholds
- `requirements.txt` — added slowapi==0.1.9
- `migrations/add_performance_indexes.py` — 6 DB indexes

### Frontend
- `frontend/src/pages/StrategiesNew.tsx` — Alpha column, allocation viz
- `frontend/src/pages/AnalyticsNew.tsx` — Stress Tests tab, R-Multiples in Tear Sheet
- `frontend/src/pages/analytics/TearSheetTab.tsx` — R-Multiple histogram
- `frontend/src/services/api.ts` — new endpoints

### Infrastructure
- `/etc/systemd/system/alphacent.service` — added ExecStartPre for api key patching
- DB: 6 performance indexes applied, 57 BACKTESTED strategies retired, 34 DEMO set to pending_retirement

---

## Session April 23-24, 2026 — Frontend Charts & Scheduler Fixes

### Fixes Shipped

**Backend**
- `src/core/monitoring_service.py` — scheduled autonomous cycle was calling `AutonomousStrategyManager()` with no args (TypeError). Fixed: imports and calls `launch_autonomous_cycle_thread()` from `strategies.py`
- `src/api/routers/strategies.py` — extracted `launch_autonomous_cycle_thread(cycle_id, filters)` as shared module-level function; `trigger_autonomous_cycle` endpoint now delegates to it; eliminates code duplication
- `src/core/order_monitor.py` — "Could not find eToro position for filled order" false alarm suppressed: checks if DB position already exists before warning (sync_positions handles it)
- `src/core/trading_scheduler.py` — eToro 404 race condition on immediate post-order status check: increased sleep 1s→3s, catches 404 as propagation delay (debug log only)
- `src/api/routers/account.py` — dashboard summary now accepts `interval` param (1d/4h/1h); equity curve deduplicates to one point per calendar day for 1d; returns hourly snapshots for 4h/1h; `realized` field added to `EquityPoint` from `realized_pnl_cumulative`

**Frontend**
- `frontend/src/components/charts/PortfolioEquityChart.tsx` — **ground-up rewrite** of equity curve chart: single `createChart` instance, absolute dollar values on left axis, drawdown histogram on right axis (bottom 28%), SPY scaled to same starting equity, correct timestamp handling for both daily ("YYYY-MM-DD") and intraday ("YYYY-MM-DD HH:MM" → UTC timestamp), period selector filters client-side, interval selector triggers parent re-fetch
- `frontend/src/components/charts/DailyPnLChart.tsx` — **ground-up rewrite** of daily P&L histogram: single `createChart`, green/red bars, zero baseline, dollar scale ($K), always uses daily-only data regardless of interval
- `frontend/src/components/charts/EquityCurveChart.tsx` — **deleted** (was using TvMultiPane, caused BusinessDay crash)
- `frontend/src/components/charts/TvMultiPane.tsx` — fixed `toChartTime` to handle Unix timestamp strings correctly
- `frontend/src/pages/OverviewNew.tsx` — uses `PortfolioEquityChart` + `DailyPnLChart`; Rolling Sharpe replaced with `InteractiveChart` (SVG, no lightweight-charts crash); `fetchAll` accepts `intervalOverride` param so interval change triggers immediate re-fetch with correct value; `rollingSharpe30` and `dailyPnlBars` filter to daily-only points
- `frontend/src/pages/analytics/PerformanceTab.tsx` — uses `PortfolioEquityChart`; `pm?.equity_curve` takes priority over `perfStats?.equity_curve` (respects interval)
- `frontend/src/lib/chart-utils.ts` — `filterDataByPeriod` normalises date strings to first 10 chars before `parseISO` (handles "YYYY-MM-DD HH:MM")
- `frontend/src/components/DashboardLayout.tsx` — `BottomWidgetZone` moved here (persistent across navigation, no remount)
- `frontend/src/components/PageTemplate.tsx` — removed `BottomWidgetZone` (now in DashboardLayout)

### Outstanding Issue — MUST FIX NEXT SESSION

**`time must be of type BusinessDay` crash on 4H/1H in Overview**

Stack: `onIntervalChange @ OverviewNew` → `onClick @ TearSheetGenerator-qajbHZ-m.js:2:3656` → `setData` in lightweight-charts

Root cause: `TvMultiPane.toChartTime` converts `"2026-04-22 00:00"` to `"2026-04-22"` (BusinessDay string). `PortfolioEquityChart.toTime` converts the same string to a UTC Unix timestamp. When both are mounted in the same app and a chart previously initialized with UTC timestamps receives BusinessDay strings (or vice versa), lightweight-charts throws.

**The fix (do this first next session):**
Update `TvMultiPane.toChartTime` to match `PortfolioEquityChart.toTime` exactly — convert `"YYYY-MM-DD HH:MM"` to UTC Unix timestamp instead of slicing to `"YYYY-MM-DD"`. This makes all lightweight-charts instances in the app use the same time format:

```typescript
function toChartTime(t: string | number): Time {
  if (typeof t === 'number') return t as Time;
  const s = String(t);
  if (/^\d{9,11}$/.test(s)) return parseInt(s, 10) as Time;
  // Sub-daily: convert to UTC Unix timestamp
  if (s.length > 10 && s[10] === ' ') {
    try {
      const dt = new Date(s.replace(' ', 'T') + ':00Z');
      if (!isNaN(dt.getTime())) return Math.floor(dt.getTime() / 1000) as Time;
    } catch {}
  }
  return s.slice(0, 10) as Time;
}
```

File: `frontend/src/components/charts/TvMultiPane.tsx`

After fixing, SCP to EC2 and rebuild frontend. No backend changes needed.

### System State (April 24, 2026)
- **Equity:** ~$475,294
- **Open positions:** ~138
- **Active DEMO strategies:** ~87
- **BACKTESTED:** ~264
- **Scheduled cycles:** slot_1 (daily 15:15 UTC) + slot_1776883375962 (weekdays 19:00 UTC) — both now working after monitoring_service fix
- **Charts:** PortfolioEquityChart working on both Overview (1D) and Analytics (1D/4H/1H); 4H/1H crashes on Overview due to TvMultiPane BusinessDay issue (fix above)
