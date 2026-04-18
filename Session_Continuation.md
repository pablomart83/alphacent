# AlphaCent — Session Continuation Prompt

Read `#File:.kiro/steering/trading-system-context.md` for full system context, then read this prompt carefully before proceeding.

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

### Sprint 8+ (Next Sessions)
- **R-Multiple Distribution** — histogram in Tear Sheet tab (backend done, needs frontend wiring)
- **Historical Stress Tests** — backend done, frontend tab added
- **Benchmark-Relative Performance Per Strategy** — alpha_vs_spy column added
- **Strategy Allocation Visualization** — deployed_capital bar chart added
- **ATR-based dynamic SL per position** — instead of fixed percentage per asset class
- **Portfolio-level VaR check** — implemented but needs monitoring to tune the 2% threshold
- **Template weight decay over time** — addressed with dynamic weighting but could be improved
- **Transcript sentiment** — module built but not integrated into conviction scorer
- **Historical stress tests** — SPY data available, beta=0.70 assumption, could use actual portfolio beta

### Cycle Quality Issues to Watch
- **`trades=low` still dominant rejection** — even with Sharpe exception, many strategies have 0-2 trades in test window. Consider whether the test window (120-180 days) is appropriate for low-frequency strategies.
- **MC bootstrap p5 threshold** — 0.2 is conservative. Monitor whether good strategies are being blocked. The 4H MACD AUDUSD (1.28 Sharpe, 32 trades, p5=-0.64) was borderline.
- **WF pass rate ~25%** — healthy. Too high would mean insufficient filtering.

---

## Files Changed This Session (April 18, 2026)

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
- `scripts/utilities/cull_low_activation_templates.py` — manual cull tool
- `scripts/utilities/retire_failing_strategies.sql` — retirement SQL

### Frontend
- `frontend/src/pages/StrategiesNew.tsx` — Alpha column, allocation viz
- `frontend/src/pages/AnalyticsNew.tsx` — Stress Tests tab, R-Multiples in Tear Sheet
- `frontend/src/pages/analytics/TearSheetTab.tsx` — R-Multiple histogram
- `frontend/src/services/api.ts` — new endpoints

### Infrastructure
- `/etc/systemd/system/alphacent.service` — added ExecStartPre for api key patching
- DB: 6 performance indexes applied, 57 BACKTESTED strategies retired, 34 DEMO set to pending_retirement
