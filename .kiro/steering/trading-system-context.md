---
inclusion: auto
---

# AlphaCent — Agent Operating Rules

> For current system state, sprint history, open items and known bugs read `Session_Continuation.md` at the start of every session. That file is the source of truth. This steering file contains only the permanent rules that never change.

---

## Think Like a Trader, Not a Software Engineer

AlphaCent is a trading business, not a code project. Every change is evaluated through the lens of P&L, risk, and capital preservation — not elegance or speed.

- A bug in a trading system is a P&L event.
- Stale data, missing bars, and silent failures are existential risks.
- A chart a quant can't trust to make decisions is a bug, not a cosmetic issue.
- "Does it compile?" is the wrong question. "Would I trade on this?" is the right one.

**Before touching any code, ask:**
1. What is the actual root cause — not the symptom?
2. Is this the right architectural solution, or am I patching around a design flaw?
3. Would a quant at a $100B fund trust this output?
4. Does this work across all modes, intervals, and edge cases?
5. Is there any silent failure path that returns wrong data instead of an error?

If any answer is "no" or "not sure" — redesign before implementing.

No minimal fixes. No silent exception swallowing. No hardcoded fallbacks that mask real failures.

---

## Proper Solutions Only — No Patches, No Stopgaps

This is a hard rule. The system is a working trading business and every line of code will run on it for months. We never ship workarounds.

**What "proper" means:**
- Fix at the root cause, not at the symptom.
- Solve the whole problem, not the visible slice of it.
- If a component is structurally wrong (e.g. a gate that only runs at signal-time but needs to be in backtest), fix the architecture — do not layer a bypass.
- Bake cross-cutting concerns (cross-asset signals, regime-awareness, validation) into the primitives they belong in (DSL, backtest engine, scoring layer) — never as out-of-band runtime gates.
- Work the problem until the solution is self-consistent: backtest, WF, paper-trade, and live-signal paths all see the same edge the same way.

**Explicitly forbidden:**
- "Stopgap" or "pragmatic" options that we plan to fix "later" — later does not come. Do not propose them as real options.
- `validation_mode: shadow` style escape hatches that route around existing gates.
- `skip_*` metadata flags that bypass validation ("we know this template is good, trust us"). If it's good, prove it through the normal path; if the normal path can't see it, fix the path.
- Manually-approved lists / hardcoded allow-lists used as permanent workarounds.
- "Do nothing structural; let the existing filter catch it" — if the filter is the right place, that's a proper solution; if we're relying on a filter to mask a deeper flaw, that's a patch.

**When a proper fix takes 3+ hours and a patch takes 30 minutes, the proper fix is the only option.** Budget for it, ship the right thing, move on. Do not accept a patch and "schedule the proper fix for next session" — next session never arrives and the patch becomes the permanent design.

**When no proper solution exists yet:**
1. Explicitly say "no proper solution yet — I need to research / design before we ship."
2. Do not deploy a stopgap in the meantime. The system keeps running without the new feature.
3. Spend the research/design time first. Ship the proper solution when it's ready.

This rule overrides the "default_to_action" guidance in the identity prompt. For AlphaCent, "ship the right thing slowly" beats "ship something fast."

---

## Deployment Workflow — Mandatory

**The local workspace is the single source of truth. EC2 is a deployment target, never an editing environment.**

Every change follows this exact sequence. No exceptions.

1. Edit files **locally** in the workspace — use `readFile`/`readCode` on the local copy
2. Run `getDiagnostics` — fix all errors before proceeding
3. `scp <local-file> ubuntu@34.252.61.149:/home/ubuntu/alphacent/<path>` — push to EC2
4. `sudo systemctl restart alphacent` if Python or config changed
5. Rebuild frontend if `.tsx`/`.ts` changed
6. Verify: `curl -sf http://localhost:8000/health`
7. `git add . && git commit -m "..." && git -c core.hooksPath=/dev/null push`

**Forbidden — these will be blocked:**
- `scp ubuntu@34.252.61.149:... ./...` — **never pull files FROM EC2**. The local workspace already has the correct version. If you think EC2 has a newer version, you have a process problem — fix the process, don't pull from EC2.
- `ssh ... 'sed -i ...'` — no in-place edits on EC2
- `ssh ... 'python3 -c ...'` — no inline Python on EC2
- `ssh ... 'tee .../src/...'` or `cat > .../src/...` — no piping files to EC2
- `ssh ... 'cp ... /home/ubuntu/alphacent/src/...'` — no copying on EC2
- Any form of editing files directly on EC2

---

## Infrastructure

| Resource | Value |
|---|---|
| Dashboard | https://alphacent.co.uk |
| EC2 | `i-035d5576835fcef0a` (t3.medium, eu-west-1) — IP `34.252.61.149` |
| SSH | `ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149` |
| SCP | `scp -i ~/Downloads/alphacent-key.pem <local> ubuntu@34.252.61.149:/home/ubuntu/alphacent/<remote>` |
| DB | `ssh ... 'sudo -u postgres psql alphacent -t -A -c "SQL"'` |
| Restart | `ssh ... 'sudo systemctl restart alphacent && sleep 12 && curl -sf http://localhost:8000/health'` |
| Frontend build | `ssh ... 'cd /home/ubuntu/alphacent/frontend && VITE_API_BASE_URL=https://alphacent.co.uk VITE_WS_BASE_URL=wss://alphacent.co.uk npm run build 2>&1 | tail -5'` |

**Critical:** systemd `ExecStartPre` runs `deploy/patch-api-keys.sh` before uvicorn — writes real API keys from AWS Secrets Manager into `config/api_keys.yaml`. Never remove this line from the service file.

---

## Log Access (EC2)

| File | Contents | When to read |
|---|---|---|
| `logs/errors.log` | ERROR + CRITICAL only | **First thing every session** |
| `logs/cycles/cycle_history.log` | Structured cycle summaries | Cycle diagnostics |
| `logs/strategy.log` | Signal gen, WF, conviction | Strategy pipeline issues |
| `logs/risk.log` | Position sizing, risk validation | Sizing / rejection issues |
| `logs/alphacent.log` | Full INFO+ audit trail | Deep dives |

```bash
# Start every session with:
ssh ... 'cat /home/ubuntu/alphacent/logs/errors.log'
ssh ... 'tail -100 /home/ubuntu/alphacent/logs/cycles/cycle_history.log'
```

---

## System Architecture

```
Frontend (React/Vite) → Nginx (SSL/443) → Backend (FastAPI/uvicorn)
                                               ├── MonitoringService (24/7)
                                               │   ├── Position sync (60s)
                                               │   ├── Trailing stops (30s)
                                               │   ├── Partial exits (5s)
                                               │   ├── Quick price update (10min)
                                               │   ├── Full price sync (55min)
                                               │   └── Fundamental exits (daily)
                                               ├── TradingScheduler
                                               │   ├── Signal generation (30min)
                                               │   ├── Risk validation
                                               │   └── Order execution
                                               └── PostgreSQL 16
```

**Key files:**
- `src/core/monitoring_service.py` — 24/7 monitoring, trailing stops, price syncs
- `src/core/trading_scheduler.py` — signal generation and order execution loop
- `src/core/order_monitor.py` — position sync with eToro, cache management
- `src/strategy/strategy_engine.py` — DSL + Alpha Edge signal generation, backtesting
- `src/strategy/strategy_proposer.py` — proposal, walk-forward validation, MC bootstrap
- `src/strategy/portfolio_manager.py` — position-level risk management, decay scoring
- `src/strategy/conviction_scorer.py` — conviction scoring pipeline
- `src/strategy/strategy_templates.py` — full template library (DSL + Alpha Edge)
- `src/api/etoro_client.py` — eToro API client with circuit breakers
- `src/core/config_loader.py` — merges `autonomous_trading.yaml` + `api_keys.yaml`

---

## Autonomous Cycle Pipeline

1. Cleanup — retire stale BACKTESTED strategies
2. Market analysis — regime detection, fundamental data loading
3. Proposal — 50-200 strategies from template library
4. Walk-forward validation — train/test split, Sharpe/trades/overfitting checks
5. Monte Carlo bootstrap — resample P&L 1000x, p5 Sharpe ≥ 0.0
6. Direction-aware thresholds — regime-specific min Sharpe/win-rate/return
7. Conviction scoring — FMP fundamentals, carry bias, crypto cycle, news sentiment
8. Activation — top strategies by conviction → BACKTESTED
9. Signal generation — run signals for newly activated strategies

---

## Current Key Parameters

### Risk (per asset class)
- Stock/ETF: SL 6%, TP 15%
- Forex: SL 2%, TP 5%
- Crypto: SL 8%, TP 20%
- Index: SL 5%, TP 12%
- Commodity: SL 4%, TP 10%
- Uptrend SHORT templates: SL 4%, TP 8-10% (wider — trending market noise)

### Position Sizing (post Apr 29 overhaul)
- `BASE_RISK_PCT`: 0.6% of equity per trade | `CONFIDENCE_FLOOR`: 0.50 | `MINIMUM_ORDER_SIZE`: $5,000
- Symbol cap: 5% | Sector soft cap: 30% | Portfolio heat cap: 30%
- Vol scaling: 0.10x–1.50x (target vol 16%)
- Drawdown sizing: 50% reduction >5% DD, 75% reduction >10% DD (30d rolling peak)

### ATR floor (order_executor, applied at order time)
- Multiplier: **1.5× ATR** (standard Wilder — hardcoded at `order_executor.py:241`. Note: `atr_sl_multiplier` in `autonomous_trading.yaml` is unused; the code value is the source of truth.)
- **Timeframe-aware**: 4H strategies use 4H ATR bars, daily strategies use daily
- Max SL clamps: stocks/ETFs 9%, crypto 15%, forex 4%
- When SL widens, position size scales down to preserve dollar risk: `new_size = old_size × old_sl / new_sl`

### Trailing Stop-Loss System — DB-Side Enforcement

eToro's public API does not expose SL-modification for open positions. `etoro_client.update_position_stop_loss` is a no-op stub returning `{"status": "db_only"}`. **Trailing stops are enforced DB-side** — any `except EToroAPIError` around SL updates is dead code.

Pipeline every 60s in `monitoring_service._check_trailing_stops`:

1. **SL recalculation** (breakeven → profit_lock → ATR-aware trail). Gated by market-open AND freshness-SLA (strategy's own timeframe bars). Stale bars keep the existing SL; the ratchet only moves favourably so a preserved SL is always safe.
2. **Breach enforcement**. Runs for **all** open positions regardless of historical-bar freshness — only needs `current_price` + `stop_loss` (both in DB from the 60s position sync). A Yahoo outage must NOT disable stop enforcement.

Ratchet ladder (stock as example):
- +3% profit → SL to entry (breakeven)
- +5% → SL to entry × 1.02 (profit lock)
- +5% activation → trail SL = current × (1 − effective_distance); `effective_distance = max(fixed_pct, ATR_pct × ATR_MULTIPLIER_BY_ASSET_CLASS[class])`
- ATR multipliers: stock/etf/commodity 2.0x, crypto/index 1.5x, forex 1.0x (forex previously too wide at 2x)
- ATR bars use the strategy's **own** interval (`position_intervals` dict passed from monitoring_service). 4H strategies no longer inherit daily ATR.

Per-cycle summary log line emitted at INFO (added 2026-05-01):
```
TSL cycle: total=90 recalc_eligible=88 skipped_market=0 skipped_stale=0 breakeven=1 lock=0 trail=3 db_updated=3 breach=0 errors=0
```
Never silent-no-op; every cycle produces this line so outages surface in one `tail`.

### Activation Thresholds
- `min_sharpe`: **1.0** (was 0.4) | `min_sharpe_crypto`: 0.5 | `min_sharpe_commodity`: 0.5
- `min_trades_dsl`: 8 (1d) | `min_trades_dsl_4h`: 8 | `min_trades_alpha_edge`: 8 | `min_trades_commodity`: 6 | `min_trades_dsl_1h`: 15
- Sharpe exception: test_sharpe ≥ 2.0 + ≥ 3 trades bypasses min_trades

### Conviction Scoring
- Threshold: **65/100** (was 70, dropped — was above DSL ceiling)
- Components: WF edge (40) + signal quality (25) + regime fit (20) + asset tradability (15) + fundamental quality (±15) + carry bias (±5) + crypto cycle (±5) + news sentiment (±1) + factor exposure (±6)
- Theoretical max: 132 (normalized to 100)
- Asset tradability: Tier 1 stocks & major instruments 15pts | Tier 2 liquid 13pts | **ETFs 13pts, Indices 14pts** (bumped May 1 — 64.6% ETF WR, 85.7% index WR live)
- Uptrend SHORT strategies score 20/20 on regime fit (they are the hedge, not fighting the regime)

### Zombie Exit Thresholds (flat ±1%, differentiated by strategy type)
- Trend-following: 5 days (1D) / 3 days (4H)
- Mean reversion: 7 days (1D) / 4 days (4H)
- Alpha Edge: 14 days (1D) / 7 days (4H)
- Retirement blocker: pending_retirement strategies flat ±2% for 5+ days

### Market Quality Score (0-100)
- Components: ADX(14) of SPY (40pts) + ATR/price inverted (30pts) + 5-day consistency (20pts) + VIX (10pts)
- Grades: High (>70) / Normal (40-70) / Choppy (<40)
- Actions: score < 40 → position sizing -30%, trend templates -50% weight, trend/momentum LONG entries blocked
- Persisted in `equity_snapshots` (market_quality_score, market_quality_grade). **Known issue:** persistence path in `_save_hourly_equity_snapshot` wraps MQS computation in `except: pass`; recent snapshots have NULL values because the computation is silently failing. Investigation open (see Session_Continuation).

### Directional Quotas (trending_up regimes)
- `trending_up`: min_long 80%, min_short 5%
- `trending_up_weak`: min_long 75%, min_short 8%
- `trending_up_strong`: min_long 85%, min_short 3%
- Never run zero short exposure in any regime

### SHORT Template Policy
- Generic shorts (RSI Overbought Short, Moving Average Breakdown, etc.) suppressed in trending_up — correct
- Uptrend-specific shorts (Exhaustion Gap, BB Squeeze Reversal, MACD Divergence, EMA Rejection, Parabolic Move, Volume Climax) are **exempted** — they are the hedge designed for corrections within uptrends
- Exemption logic: templates whose `market_regimes` explicitly include a trending_up variant pass through the regime filter

### Alpha Edge Proposer Flow (post-2026-05-01)

Alpha Edge templates use the fundamental signal path (not DSL walk-forward). Proposer rules:

- **Per-cycle cap**: up to 8 Alpha Edge strategies proposed per cycle (raised 5 → 8 on 2026-05-01)
- **Template rotation**: `alpha_edge_templates_filtered` is shuffled by hour-of-year offset each cycle so different AE templates get first shot across cycles. Without this, templates defined later in `strategy_templates.py` never reached the loop.
- **Regime filter** applies upstream: `get_templates_for_regime(market_regime)` narrows the pool before AE phase. Under `trending_up_strong` typically ~8 AE templates match; under `trending_up_weak` or `ranging` typically ~15-20 match.
- **Dedup is per (template, symbol)**, not per template. A template with active strategies keeps being proposed with different symbols.
- **Failure modes don't consume slots**: templates that find no eligible symbols or raise during generation do NOT decrement `alpha_edge_count`. Slot-consumption is success-path only.

### Proposer Feedback Loops (post-2026-05-02 TSLA audit)

Performance feedback to the proposer must decay over time or it becomes a permanent lockout. TSLA audit showed the system shorted a name 4×, lost every time, then locked that symbol out for weeks while the stock rallied 16%.

- **Recency-weighted symbol score**: `trade_journal.get_performance_feedback` emits `recency_weight` per symbol — exponential decay with 14-day half-life. `strategy_proposer.apply_performance_feedback` multiplies the symbol penalty by recency (floor 0.2). Trades 14d old weight 0.5×, 28d old 0.25×.
- **Rejection-blacklist cooldown 14 days** (was 30). Regime-scoped early expiry: entries recorded under `trending_down` expire when current regime is `trending_up` and vice versa (min 3-day age to avoid noise). Regime recorded on every `record_rejection` call.
- **Neglected-symbol slot reservation** (`_build_watchlists` Phase 3): 15% of each template's watchlist (min 1 slot) reserved for symbols not seen in any proposal in the last 7 days. Prevents round-robin lockout of negatively-scored symbols.
- **Directional-rebalance bonus** (`_match_templates_to_symbols`): +8 score when symbol has all-one-side losing history (≥3 trades, net-negative P&L) and current template is counter-direction. Surfaces TSLA-like imbalances automatically.
- **Per-pair sizing penalty** (`risk_manager.calculate_position_size` Step 10b): halves position size when (template, symbol) has ≥3 net-losing trades in trade_journal. Resets when net P&L flips positive.
- **SHORT-side WF tightening**: min_sharpe +0.3 for shorts on primary path; relaxed-OOS rescue path **removed** for shorts (too much overfit risk); test-dominant path requires ≥4 test trades for shorts.

### Symbol Analytics — Current vs Lifetime

Two orthogonal views on symbol performance:

- **Current view** (from `strategies` table): active_strategies, usage_count. Reflects strategy-library churn; symbols vanish when strategies retire and get deleted.
- **Lifetime view** (from `trade_journal`): traded_count, win_rate, total_pnl. Survives retirement; ground truth for "has this symbol ever made us money".

`strategy_proposals` table gets a new row per proposal (via `track_proposals`) with snapshot of `symbols` JSON and `template_name`. Lifetime `proposed_count` comes from this table, which survives retirement. Columns: `id, strategy_id, proposed_at, market_regime, backtest_sharpe, activated, symbols, template_name`.

`/strategies/symbols` endpoint combines both views. Symbols tab columns: Proposed, Active (open positions), Traded, Sharpe, Win%, P&L, Best Template.

### Signal-Time Risk Gates (post-2026-05-02)

Three runtime gates sit between signal generation and execution:

- **C1 VIX Signal-Time Gate** (`order_executor.execute_signal`): blocks ENTER_LONG when VIX > 25 AND VIX_5d > +15%. Rationale: post-VIX-spike forward returns are weak (Bilello research). Crypto exempt. Fail-open on data error (log + proceed). 5-min TTL cache. Existing LONG positions continue to exit normally.
- **C2 Momentum Crash Circuit Breaker** (`conviction_scorer._score_regime_fit`): when SPY_5d < -3% AND VIX_1d > +10%, reduces regime_fit by 10 points for LONG momentum/trend_following/breakout strategies. Floored at 5 (matches existing weak-match floor). Rationale: Byun & Jeon (SSRN 2900073) — momentum crashes during market rebounds. Fail-open.
- **C3 Trend-Consistency Gate** (`order_executor._check_trend_consistency_gate`, added 2026-05-02 TSLA audit): blocks ENTER_SHORT when stock is above rising 50d SMA (uptrend) OR dropped >1 ATR in 3d AND is within 3% of 20d low (oversold bounce). Symmetric LONG block when stock is below falling 50d SMA. Crypto/forex exempt. 5-min TTL cache per (symbol, action). Catches the TSLA-style losing SHORT setups where signals fire on late-stage downtrends already reversing.

All three gates are armed by default, use live data via `market_data_manager`, scope: equity/ETF/index/commodity entries. Never block exits, stops, or gate-exempt instruments.

### Signal-Decision Audit Log (post-2026-05-02)

Every template × symbol × stage decision per cycle is persisted in `signal_decisions`. One row per (stage, decision) per strategy per cycle. Stages written:

- `proposed` — proposer emits a strategy (track_proposals → decision_log.record_batch)
- `wf_validated` / `wf_rejected` — walk-forward outcome with train/test Sharpe + reason
- `activated` / `rejected_act` — autonomous_strategy_manager's activation-criteria pass/fail
- `signal_emitted` — strategy_engine.generate_signals output (after conviction/frequency/ML filters)
- `gate_blocked` — VIX / trend-consistency / MQS gate blocked the signal at execute_signal
- `order_submitted` — successful submit path in order_executor.execute_signal
- `order_filled` — async fill in order_monitor.check_submitted_orders with slippage + fill_time
- `order_failed` — reserved for explicit failures (not yet wired — add when needed)

Writer: `src/analytics/decision_log.py` `record_decision` / `record_batch` / `prune_old`. Every call is fire-and-forget and NEVER raises — an analytics bug must not break trading. Retention: 30 days via `prune_old(30)` (manual schedule TBD).

Analytics layer (`src/analytics/observability.py`):
- `mae_at_stop_analysis` — per-symbol MAE/MFE with pattern detection (entry_bad / trail_tight / exit_late).
- `wf_live_divergence` — strategies where live Sharpe diverges from WF test Sharpe by ≥1.0.
- `regime_template_pnl_matrix` — (regime, template, direction) → P&L cells for regime-aware suppression.
- `template_graduation_funnel` — proposal → fill funnel with per-stage drop-off %.
- `per_symbol_opportunity_cost` — symbol forward return minus captured % (missed-alpha detector).

Endpoints under `/analytics/observability/*` and `/health/trading-gates`.

### System Page Observability (post-2026-05-02)

The System page surfaces the above via:
- **Trading Gates** card (side panel): every blocker that can prevent a trade — kill_switch, market_hours, vix_gate, rejection_blacklist, freshness_sla. Green=clear, amber-pulsing=blocking.
- **Observability** card (main panel): 4 metric tiles + 30-day decision funnel + top-5 missed-alpha symbols.
- **Background Threads** card: real last_run / duration_s / symbols_updated for quick_price_update and full_price_sync from `_last_quick_update_result` and `_last_price_sync_result` on MonitoringService.

All ISO timestamps emitted from `control.py` include explicit `Z` suffix. Frontend `formatAge` appends `Z` defensively for legacy sources.

---

## Data Pipeline — Critical Rules

The price data pipeline has three layers. Each has distinct responsibilities. Violating these causes silent data corruption.

**Full hourly sync (`_sync_price_data`):**
- Writes 1d and 1h bars to `historical_price_cache`
- Only caches DB data into memory **if fresh**. Stale DB data (gap > 1.2 days, excluding weekends for stock markets) queues the symbol for Yahoo batch fetch.
- Source of truth for end-of-day 1d bars.

**Quick price update (`_quick_price_update`, every 10 min):**
- **Only touches 1h bars** — never 1d
- Updates current 1h bar's OHLC with live tick OR appends new bar on hour rollover
- Rationale: 1d bars are end-of-day data. Building an intraday-provisional "today" 1d bar mislead daily indicators (RSI(14) treats it as complete).

**Yahoo/yfinance handling:**
- All yfinance calls pass **tz-aware UTC datetimes** for `start`/`end` bounds. Naive datetimes trigger yfinance's internal local-tz inference, which crashes on DST ambiguous hours (e.g. 2025-11-02 01:30 in America/New_York). See `src/utils/yfinance_compat.py` — `to_tz_aware_utc()` for input conversion, `normalize_yf_index_to_utc_naive()` for post-return safety.
- DST boundaries (EU last Sunday Oct/Mar, US first Sunday Nov/Mar) create ambiguous local hours that crash `pd.resample()` and `Timestamp.to_pydatetime()` with AmbiguousTimeError. tz-aware UTC input prevents the crash; post-return tz_localize(None) makes downstream iteration safe.
- Batch downloads that return partial data trigger per-ticker retry (capped at 20 misses) for defence in depth.
- Yahoo returns 1h for 4H requests — system resamples to 4H in `_fetch_historical_from_yahoo_finance`. Normalise tz BEFORE resample.

**Symbol canonicalization:**
- **DB key**: always display form — `BTC`, `ETH`, `AAPL`, `EURUSD` (used in positions, orders, trade_journal, historical_price_cache)
- **eToro wire format**: `to_etoro_wire_format()` converts display → wire (`BTC` → `BTCUSD`). Used ONLY for eToro API calls.
- **Yahoo ticker**: `to_yahoo_ticker()` converts display → Yahoo (`BTC` → `BTC-USD`, `SPX500` → `^GSPC`). Used ONLY for yfinance calls.
- Never store eToro wire format in DB. Two functions named `normalize_symbol` existed historically — `symbol_mapper.normalize_symbol` is aliased from `to_etoro_wire_format` for backward compat; `symbol_normalizer.normalize_symbol` resolves instrument IDs. Use explicit names in new code.

---

## Known Open Issues (as of May 2, 2026)

- **Walk-forward bypass paths admit regime-luck** — test-dominant path in `strategy_proposer.py` allows strategies with ts ≥ -0.1 to pass if test Sharpe clears. SHORT side has been tightened; LONG still loose. Consider a consistency gate `(test_sharpe - train_sharpe) ≤ 1.5` post-Batch-4.
- **Entry order 82% FAILED rate** — cosmetic: market-closed deferrals written as FAILED then re-fired each cycle. Batch 2 fix pending.
- **NVDA and AMZN at 7.43% of equity each** — symbol concentration cap not enforced cumulatively across strategies. Batch 3 fix pending.
- **Triple EMA Alignment DSL bug** — `EMA(10) > EMA(10)` always false, generates 0 trades. Regex-based param substitution collapses positional literals. Batch 4 fix pending.
- **MQS persistence** — recent `equity_snapshots` have NULL `market_quality_score` despite code path being present. `_save_hourly_equity_snapshot` wraps MQS computation in `except: pass` hiding the real error. Investigation open.
- **Sector Rotation + Pairs Trading templates structurally broken** — Sector Rotation `fixed_symbols` covers only 5 of 11 SPDR sectors. Pairs Trading Market Neutral's DSL conditions are momentum-long signals, not pairs. Need design session, don't fix piecemeal.
- **Regime classification two-tier inconsistency** — `market_analyzer.detect_sub_regime` and proposer regime gate can disagree. Worth tracing; affects which template pool gets used.
- **Overview chart panel** — 3 separate chart components with misaligned axes; needs multi-pane rewrite.
- **FMP insider endpoint** — 403/404 on current plan; insider_buying uses momentum proxy fallback.
- **1h strategies** — ~1 active. Emergent from `min_trades_dsl_1h=15` + MC annualization inflation, not an explicit block. Revisit post-Batch-4.
- **Cycle-error observability gap** — when a cycle stage throws (e.g. the `SignalAction` NameError on 2026-05-02 08:08 UTC), it only logs `Error proposing strategies:` and continues silently. No `signal_decisions` row written, no alert. Add a `cycle_error` stage write so stage failures are visible in the funnel.
- **Entry-timing score (#5 from observability ranking)** — deferred; needs per-minute post-entry price snapshots we don't capture yet.
- **Deploy-validation auto-tracker (#10)** — subsumed by signal_decisions once it's fully populated across a few cycles.
