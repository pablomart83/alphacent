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
- Symbol cap: 3% equity | Sector soft cap: 30% | Portfolio heat cap: 30%
- Vol scaling: 0.10x–1.50x (target vol 16%)
- Drawdown sizing: 50% reduction >5% DD, 75% reduction >10% DD (30d rolling peak)

### ATR floor (order_executor, applied at order time)
- Multiplier: **1.5× ATR** (standard Wilder — hardcoded at `order_executor.py:241`. Note: `atr_sl_multiplier` in `autonomous_trading.yaml` is unused; the code value is the source of truth.)
- **Timeframe-aware**: 4H strategies use 4H ATR bars, daily strategies use daily
- Max SL clamps: stocks/ETFs 9%, crypto 15%, forex 4%
- When SL widens, position size scales down to preserve dollar risk: `new_size = old_size × old_sl / new_sl`

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

## Known Open Issues (as of May 1, 2026, post-Batch-1 audit)

- **Walk-forward bypass paths admit regime-luck** — test-dominant + excellent-OOS paths in `strategy_proposer.py:1638-1651` allow strategies with near-zero train Sharpe and strong test Sharpe to pass. Average test Sharpe 2.70 vs train 0.79 across 173 live strategies. Fix scheduled for Batch 4.
- **Entry order 82% FAILED rate** — cosmetic: market-closed deferrals written as FAILED then re-fired each cycle. Batch 2 fix pending.
- **NVDA and AMZN at 7.43% of equity each** — symbol concentration cap not enforced cumulatively across strategies. Batch 3 fix pending.
- **Triple EMA Alignment DSL bug** — `EMA(10) > EMA(10)` always false, generates 0 trades. Regex-based param substitution collapses positional literals. Batch 4 fix pending.
- **MQS persistence** — recent `equity_snapshots` have NULL `market_quality_score` despite code path being present. `_save_hourly_equity_snapshot` wraps MQS computation in `except: pass` hiding the real error. Investigation open.
- **Overview chart panel** — 3 separate chart components with misaligned axes; needs multi-pane rewrite (previous attempt failed, design first)
- **FMP insider endpoint** — 403/404 on current plan; insider_buying uses momentum proxy fallback
- **1h strategies** — 0 active; need next cycle on clean data (post May 1 fixes) to validate
- **`proposed` counter in UI** — all 0 in DB, counter never written. Fix or remove.

## Current System State (May 1, 2026)

- **Equity:** ~$476,900
- **Open positions:** ~87 | $409K deployed | +$5,560 unrealized (68% WR open book)
- **Active DEMO:** 64 | **BACKTESTED:** 109 | **RETIRED:** 42
- **Directional split:** 199 LONG / 6 SHORT (all forex — SHORT equity pipeline unblocked but not yet activated)
- **Market regime:** trending_up_weak (80% confidence) | Market Quality Score: 85/100 High
- **Symbol universe:** 297 (232 stocks, 42 ETFs, 8 forex, 5 indices, 8 commodities, 2 crypto)
- **Scheduled cycles:** daily 15:15 UTC + weekdays 19:00 UTC
