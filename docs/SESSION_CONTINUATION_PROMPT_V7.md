# AlphaCent Trading System — Session Continuation Prompt V7

Read `#File:.kiro/steering/trading-system-context.md` for full system context, then read this prompt carefully before proceeding.

## What Was Done This Session (April 8, 2026 — Late Evening)

Continuation of V6 session. All V6 completed items remain in place. This session was a massive overhaul focused on three areas: (1) quant trader logic fixes to the trading engine, (2) complete rewrite of Analytics and Risk page calculations, and (3) institutional-grade CIO dashboard metrics.

---

### 1. Quant Trader Logic Fixes (7 fixes across 6 backend files)

**Regime-Dependent Factor Weights (fundamental_ranker.py):**
- Ranker now detects current market sub-regime and tilts factor weights accordingly
- Trending-down → quality 40% + value 30% (defensive). Trending-up → momentum 35% + growth 35% (offensive)
- REGIME_WEIGHTS class constant maps 8 regime types to specific weight distributions
- `_get_regime_weights()` method detects regime via MarketStatisticsAnalyzer

**Expectancy-Based Activation Gate (portfolio_manager.py):**
- Replaced flat win-rate gate with expectancy check for strategies with 15+ trades
- Formula: (avg_win × WR) - (avg_loss × (1-WR)). Positive expectancy passes regardless of win rate
- Hard floor at 25% WR to filter degenerate outlier strategies
- Falls back to win-rate gate when trade count too low for reliable expectancy

**Explicit Overfitting Thresholds (strategy_engine.py — walk_forward_validate):**
- Two-tier detection: train Sharpe > 1.0 with test < 50% of train is suspicious
- Only flagged if test Sharpe is below 0.3 (the viable threshold)
- Prevents rejecting strategies where train period was unusually good but OOS is solid

**Timeframe-Aware Decay Probation (monitoring_service.py):**
- Monthly strategies (sector rotation, end-of-month, dividend aristocrat): 35-day probation
- Weekly/4H strategies: 14 days. Intraday/daily: 7 days
- Prevents killing monthly strategies before their first trade

**3x Bump-Up Guard for Minimum Order Size (risk_manager.py):**
- Both in calculate_position_size and post-adjustment floor in validate_signal
- If eToro minimum would require >3x inflation, signal is rejected instead of silently over-sizing

**Signal Frequency Validation (strategy_engine.py — generate_signals_batch):**
- Checks data bar frequency matches strategy's intended interval
- Intraday strategy receiving daily-spaced data → skip signal generation

**Market-Cap-Tiered Revision Detection (fundamental_data_provider.py):**
- Large-cap (>$10B): 5% threshold. Mid-cap ($2B-$10B): 3%. Small-cap/unknown: 5% default

---

### 2. Analytics & Risk Page Complete Rewrite

**Root Cause Fix — eToro Position Value:**
- On eToro, `quantity` = dollar amount invested (NOT shares)
- `quantity × current_price` = nonsensical (dollars × price = garbage)
- Added `_get_position_value()` helper in both analytics.py and risk.py
- Fixed ALL instances across: metrics, VaR, beta, drawdown, leverage, exposure, stress tests, sector/asset class breakdowns, directional exposure, margin

**Analytics Page Fixes:**
- Equity curve starts from real account equity (was hardcoded $100K)
- Sharpe ratio uses daily portfolio returns with 30-point minimum, capped ±5 (was per-position, no minimum)
- Sortino ratio: same 30-point minimum, capped ±10
- Monthly returns show percentages (was raw dollar amounts)
- Regime analysis reads from `strategy_metadata.macro_regime` (was `rules.market_regime` → always "UNKNOWN")
- Strategy attribution shows live Sharpe from actual positions (was stale backtest Sharpe)
- Strategy attribution `total_return` is percentage (was raw dollars, frontend called formatPercentage on it)
- `avg_size` no longer multiplies `entry_size × entry_price`
- Correlation matrix uses `_get_position_value()` for return calculation

**Risk Page Fixes:**
- VaR uses asset-class-specific volatility (stocks 16%, crypto 60%, forex 8%, commodities 20%) with correlation adjustment
- Beta uses sector-weighted approach with known asset-class betas (was hardcoded 1.0)
- Drawdown uses unrealized P&L relative to invested capital
- Risk history uses real position snapshots (was randomly generated with np.random)
- Leverage uses equity instead of balance
- Margin uses real account data (was hardcoded $415K)
- Risk score uses equity-based thresholds (was balance-based → false "danger" alerts)
- Exposure alert uses equity (was balance → false positives)

**Decay Score Fix — Now Uses Live Data:**
- Was using stale backtest Sharpe/drawdown (frozen at activation) → penalties never fired → stuck at 10
- Now uses live P&L from actual positions: down >10% = 3pts, >5% = 2pts, >2% = 1pt
- Checks if all positions underwater (2pts) or >70% red (1pt)
- Win rate computed from actual closed positions, not backtest

**Health Score Fix — Correct Denominator:**
- `total_invested` now includes both open + closed position capital (was open-only)
- P&L materiality threshold: 3% (was 1% — too sensitive)
- Realized loss threshold: 5% (was 2%)

---

### 3. CIO Dashboard — Institutional-Grade Metrics (NEW)

**New Endpoint: GET /analytics/cio-dashboard**
- Calmar Ratio (CAGR / Max Drawdown)
- CAGR (Compound Annual Growth Rate)
- Information Ratio (excess return vs risk-free / tracking error)
- Realized vs Unrealized P&L split
- Daily P&L table (date, starting/ending equity, daily P&L $/%,  cumulative, realized, unrealized, trades closed)
- Drawdown duration (days since last equity high)
- Win/Loss streak analysis (current, longest win, longest loss)
- Slippage summary (avg entry/exit slippage %, total cost) — reads from trade_metadata.entry_slippage_pct
- Strategy lifecycle (proposed/activated/retired in 30d, avg lifespan, active count)
- Total expectancy including open positions (not just closed-trade expectancy)

**New Endpoint: GET /risk/cio-risk**
- Gross/Net exposure ($ and % of equity)
- Expected Shortfall CVaR 95% and 99% (historical simulation)
- Concentration metrics (top 5 positions %, top 3 sectors %, Herfindahl index, largest position)
- Factor exposure with regime detection (value/quality/momentum/growth weights and overweight/underweight tilt)
- Risk budget utilization (VaR budget %, exposure budget %, drawdown budget %)

**Risk Status Banner — Now Shows Reasons:**
- Backend returns `risk_reasons` array explaining each flag
- Frontend shows bullet points with red/yellow dots: "VaR $14,200 exceeds limit $13,950 (DANGER)"
- When safe: "All clear — VaR $X, DD X%, Leverage Xx, N positions"

**Risk Alerts — Now Persistent:**
- Alerts persisted to `alert_history` table (was ephemeral, regenerated on each page load)
- Deduplication: same alert type only once per hour
- Returns last 30 days of alerts (up to 30)
- Warning-level alerts at 80% of limits (not just breach alerts)
- Always shows status summary so section is never empty

---

### 4. Frontend Improvements

**Lazy Loading — Analytics Page:**
- Phase 1: 3 core endpoints (performance, perfStats, CIO dashboard) → page renders immediately
- Phase 2: Tab-specific data fetches only when that tab is active
- Reduced initial API calls from 11 to 3

**Lazy Loading — Risk Page:**
- Phase 1: 5 essential calls (metrics, positions, config, alerts, account) → page renders immediately
- Phase 2: 5 heavy calls (history, position risks, correlation, advanced, CIO risk) load in background

**Exposure Charts — Pie → Bar:**
- Replaced unreadable pie charts with horizontal bar charts for sector and asset class exposure
- Sector chart includes red dashed reference line at 40% limit
- Asset class tooltip shows both percentage and dollar value

**Autonomous Page — Quick Controls Bar:**
- Research Filters + Run Cycle button moved above Trading Cycle Pipeline
- Compact inline layout: asset class pills, timeframe pills, strategy type pills, Run Cycle button
- Removed duplicates from System box and Controls card
- Run Cycle button: green (was light blue)

**Expectancy Card — Dual View:**
- Shows both closed-trade expectancy AND total expectancy including open positions
- Subtitle shows breakdown: "110 closed + 118 open (95W/23L), open P&L: $341,000"

---

### 5. Bug Fixes

**SQLite "database is locked" — Trade Journal:**
- Added retry-with-backoff to `log_entry` and `log_exit`
- On "database is locked", waits 1s, opens fresh session, re-checks for duplicates, retries

**yfinance Cache Crash (TypeError: stat: path should be string, not NoneType):**
- `yf.set_tz_cache_location(None)` crashes in newer yfinance versions
- Fixed: redirect cache to `/tmp/yfinance_tz_cache` with env vars as belt-and-suspenders
- Lazy initialization via `ensure_yfinance_cache()` — thread-safe, called before first yf.Ticker()
- Removed import-time DB initialization that was causing SQLAlchemy connection pool interference

**Position SL/TP Not Inherited from Orders:**
- `order_executor.py`: positions created from fills now inherit `order.stop_price` and `order.take_profit_price`
- `order_monitor.py`: position creation falls back to order SL/TP when eToro doesn't return them

**Dashboard Sector Exposure — Wrong Math:**
- Was using `entry_price × quantity` (garbage on eToro)
- Fixed to use `invested_amount or abs(quantity)`

**SQLite Performance:**
- Busy timeout: 30s → 60s
- Added 64MB page cache (`PRAGMA cache_size=-64000`)
- Less frequent WAL checkpoints (`PRAGMA wal_autocheckpoint=1000`)
- Axios timeout: 30s → 60s to match

**Test Fixes:**
- Fixed 4 pre-existing test failures in test_risk_manager.py
- Root cause: test fixtures used `quantity=10` meaning "10 shares" but eToro treats it as "$10 invested"
- Updated sample_position to `quantity=1550.0`, exposure tests to `quantity=1000.0`
- Fixed correlation adjustment to exclude external positions from same-symbol check
- All 63 tests now pass (was 48 pass + 4 fail)

---

## Key Files Modified This Session (V7)

- `src/strategy/fundamental_ranker.py` — Regime-dependent factor weights (REGIME_WEIGHTS, _get_regime_weights)
- `src/strategy/portfolio_manager.py` — Expectancy-based activation gate
- `src/strategy/strategy_engine.py` — Explicit overfitting thresholds, signal frequency validation
- `src/core/monitoring_service.py` — Timeframe-aware decay probation, live P&L decay penalties, live win rate
- `src/risk/risk_manager.py` — 3x bump-up guard, external position correlation filter
- `src/data/fundamental_data_provider.py` — Market-cap-tiered revision detection
- `src/api/routers/analytics.py` — Complete rewrite of all calculations, CIO dashboard endpoint, slippage from trade_metadata
- `src/api/routers/risk.py` — Complete rewrite of all calculations, CIO risk endpoint, persistent alerts, risk reasons
- `src/api/routers/account.py` — Dashboard sector exposure fix (invested_amount not entry_price×quantity)
- `src/execution/order_executor.py` — Position inherits SL/TP from order
- `src/core/order_monitor.py` — Position creation falls back to order SL/TP
- `src/analytics/trade_journal.py` — SQLite retry logic for log_entry and log_exit
- `src/data/market_data_manager.py` — yfinance cache redirect, ensure_yfinance_cache()
- `src/models/database.py` — Increased busy timeout, page cache, WAL checkpoint tuning
- `frontend/src/pages/AnalyticsNew.tsx` — Lazy loading, CIO dashboard UI, expectancy dual view, monthly returns as %
- `frontend/src/pages/RiskNew.tsx` — Lazy loading, CIO risk UI, bar charts, risk reasons banner, persistent alerts
- `frontend/src/pages/AutonomousNew.tsx` — Quick controls bar, removed duplicates
- `frontend/src/services/api.ts` — CIO dashboard/risk API methods, 60s timeout
- `tests/test_risk_manager.py` — Fixed 4 tests for eToro position value model

## Current System State

- Account: balance=$124K, equity=$465K
- Active strategies: ~90 (DEMO) including 5+ AE strategies now live
- Open positions: ~126
- Market regime: trending_down_weak (confidence: 59%)
- Decay scores: now computing real penalties from live P&L (was stuck at 10)
- Health scores: using correct denominator (open + closed capital)
- Analytics: daily P&L table, Calmar, CAGR, Information Ratio, drawdown duration, streaks, slippage
- Risk: CVaR, gross/net exposure, HHI concentration, factor exposure, risk budget utilization
- All 63 risk manager tests passing

## What Needs Investigation — V8 Priority

### Still Open from V6 Audit (Services 1-10)

The V6 quant trader logic audit identified 10 services to review. This session addressed items 2 (position sizing — 3x guard), 3 (activation — expectancy gate), 4 (retirement — live decay/health), 5 (walk-forward — overfitting thresholds), and 9 (fundamental pipeline — regime weights, revision detection). Still open:

1. **Signal Generation** — Are conviction scores using meaningful inputs? Signal frequency for each strategy type?
6. **Template-Symbol Matching** — Should template weights from performance feedback decay over time?
7. **Risk Controls** — Portfolio-level VaR check before new positions (excluded from this session)
8. **Order Execution** — Is signal coordination too aggressive? Missing opportunities?
10. **Performance Feedback Loop** — Is it chasing past winners? Should feedback be factor-level?

### Analytics/Risk Page — Remaining Items from Research

Higher effort items not yet implemented:
- Historical named stress tests (COVID, Lehman, SVB — use actual historical return patterns)
- Drawdown recovery analysis (peak date, trough date, recovery date, duration for each historical DD)
- R-Multiple distribution (trade P&L as multiple of initial risk)
- Systematic vs Idiosyncratic risk split
- Correlation heatmap weighted by position size
- Liquidity risk assessment
- SPY benchmark comparison on equity curve

### Infrastructure

- SQLite contention remains the bottleneck — signal generation (4 threads) + monitoring + API all compete
- Consider moving to PostgreSQL or at minimum a read-replica pattern for API reads
- yfinance hourly batch downloads still fail intermittently (DNS errors, cache issues)
- Exit slippage not tracked (would need expected-vs-filled comparison on close orders)

## How to Troubleshoot

1. Read `logs/cycles/cycle_history.log` for cycle summaries
2. Read `logs/alphacent.log` for detailed backend logs
3. Check decay scores: Look for "[StrategyDecay]" — now shows live P&L penalties
4. Check health scores: Look for "[StrategyHealth]" — uses correct denominator
5. Check CIO dashboard: `GET /analytics/cio-dashboard?mode=DEMO&period=3M`
6. Check CIO risk: `GET /risk/cio-risk?mode=DEMO`
7. Check risk alerts: `GET /risk/alerts?mode=DEMO` — now persistent in alert_history table
8. Check yfinance cache: `ls /tmp/yfinance_tz_cache/` — should have tkr-tz.db
9. Check factor weights: Look for "FundamentalRanker: regime=" in logs
10. Check position SL/TP: New positions should have stop_loss inherited from order
