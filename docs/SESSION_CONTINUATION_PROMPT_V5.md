# AlphaCent Trading System — Session Continuation Prompt V5

Read `#File:.kiro/steering/trading-system-context.md` for full system context, then read this prompt carefully before proceeding.

## What Was Done This Session (April 8, 2026 — Afternoon)

Continuation of V4 session. All V4 completed items remain in place. This session focused entirely on the Alpha Edge (AE) fundamental strategy pipeline — audit, fixes, institutional-grade upgrades, and new templates.

### 1. Alpha Edge Pipeline Audit (COMPLETE)

Full end-to-end audit of the AE pipeline documented in `ALPHA_EDGE_PIPELINE_AUDIT.md`. Identified 12 issues across proposal, backtest, WF validation, signal generation, and execution stages.

### 2. P0-P2 Fixes — 12 Issues Fixed (COMPLETE)

All 12 audit items implemented:

**P0 (Critical):**
- Eliminated price-proxy fallback for AE backtests — if FMP data unavailable, backtest returns zero (no fake signals)
- Raised `min_trades_alpha_edge` from 2 to 4, then reverted to 2 (fundamental strategies are inherently low-frequency — 2 trades with good Sharpe is the right bar)
- Fixed Revenue Acceleration — now requires actual Q-over-Q growth acceleration, not just positive growth
- Fixed Relative Value — now uses sector-relative P/E comparison via FMP profile sector data

**P1 (Important):**
- Added trend confirmation to Quality Deterioration Short (requires price < SMA(200) or declining SMA(50))
- Reclassified Pairs Trading and End-of-Month Momentum from `alpha_edge` to `statistical` category
- Tightened Analyst Revision Momentum (2+ consecutive revisions, 5% minimum)
- Added market cap > $1B check to Share Buyback

**P2 (Improvements):**
- AE portfolio risk config added (`portfolio_risk` section in YAML)
- Fundamental monitoring config clarified with comments
- FMP cache warmer now pre-warms sector performance + historical fundamentals
- Cycle stats now track AE vs DSL performance separately

**Files**: `src/strategy/strategy_engine.py`, `src/strategy/strategy_templates.py`, `src/strategy/strategy_proposer.py`, `src/strategy/autonomous_strategy_manager.py`, `src/data/fmp_cache_warmer.py`, `config/autonomous_trading.yaml`

### 3. Institutional-Grade Fundamental Metrics — Phase 1 (COMPLETE)

Added 16 new quarterly metrics computed from FMP cash flow statement + balance sheet data:

- **Accruals Ratio**: `(net_income - operating_cash_flow) / total_assets` — earnings quality signal (Sloan 1996)
- **FCF Yield**: `free_cash_flow / market_cap` — better than P/E for valuation
- **Piotroski F-Score**: Full 9-point quality composite (was checking 2 of 9, now all 9)
- **SUE (Standardized Unexpected Earnings)**: Earnings surprise normalized by historical volatility
- **Gross Margin, Current Ratio, Asset Turnover, Long-term Debt Ratio, Shares Outstanding**

FMP API calls parallelized (6 endpoints concurrent via ThreadPoolExecutor) — per-symbol fetch time reduced from ~5s to ~1.5s.

DB cache freshness check fixed: now uses `max(fetched_at)` instead of `min(fetched_at)` to avoid re-fetching when old quarter rows have stale timestamps.

**Files**: `src/data/fundamental_data_provider.py`, `src/models/orm.py`, DB migration (16 new columns on `quarterly_fundamentals_cache`)

### 4. Cross-Sectional Fundamental Ranker — Phase 2 (COMPLETE)

New module `src/strategy/fundamental_ranker.py` — ranks all ~75 stock symbols by composite score across 4 orthogonal factors:

1. **Value**: FCF yield + earnings yield
2. **Quality**: Piotroski F-Score + inverse accruals ratio
3. **Momentum**: Trend strength from market stats
4. **Growth**: SUE + revenue acceleration

Percentile-based ranking (0-100) instead of absolute thresholds. Integrated into the proposer — AE scoring now uses cross-sectional ranks when available. SHORT templates get worst-ranked symbols (inverted scoring).

**Files**: `src/strategy/fundamental_ranker.py`, `src/strategy/strategy_proposer.py`

### 5. Multi-Factor Composite Template + 7 New AE Templates (COMPLETE)

Added institutional-grade templates based on academic research:

| Template | Factor | Source |
|---|---|---|
| Multi-Factor Composite Long | Multi (V+Q+M+G) | AQR/Two Sigma approach |
| Multi-Factor Composite Short | Multi (inverse) | AQR/Two Sigma approach |
| Gross Profitability Long | Quality | Novy-Marx 2013 |
| Accruals Quality Long | Quality | Sloan 1996 |
| Accruals Quality Short | Quality (inverse) | Sloan 1996 |
| FCF Yield Value Long | Value | Better than P/E |
| Price Target Upside Long | Sentiment | Analyst consensus |
| Shareholder Yield Long | Income | Meb Faber |
| Earnings Momentum Combo Long | Growth+Momentum | PEAD enhanced |
| Quality Value Combo Long | Quality+Value | Novy-Marx enhanced |
| Deleveraging Long | Quality | Debt paydown thesis |

New FMP endpoints integrated: `/price-target-consensus`, `/upgrades-downgrades-consensus`

Total AE templates: **23** (was 13 before this session)

**Files**: `src/strategy/strategy_templates.py`, `src/strategy/strategy_engine.py` (backtest simulation + signal handlers)

### 6. AE Watchlist Architecture (COMPLETE)

Replaced the old "1 strategy per template with 1 symbol" approach with DSL-style watchlists:
- Each AE template now gets ONE strategy with a watchlist of top 5 best-fit symbols
- Symbols scored by ranker composite + template-specific eligibility
- SHORT templates get worst-ranked symbols (inverted ranker score)
- Signal generation evaluates all 5 watchlist symbols per cycle

**Files**: `src/strategy/strategy_proposer.py`

### 7. Frontend — DSL/AE Template Tabs (COMPLETE)

- Renamed "Templates" tab to "DSL Templates"
- Added new "AE Templates" tab
- Both use same `TemplateManager` component with `category` prop filter
- Summary bar (count, enabled/disabled, active strategies, P&L) scoped to category
- Backend `TemplateResponse` model now includes `strategy_category` field

**Files**: `frontend/src/pages/StrategiesNew.tsx`, `frontend/src/components/trading/TemplateManager.tsx`, `src/api/routers/strategies.py`

### 8. Similarity/Correlation Check Disabled (COMPLETE)

Disabled `similarity_detection.enabled: false` in config. The correlation analyzer was running hundreds of pairwise calculations during activation (5 watchlist symbols × ~87 active strategies) without meaningful impact on strategy selection. The ranker already handles diversification.

**File**: `config/autonomous_trading.yaml`

## What Still Needs Investigation / Doing

### 1. AE Backtest 0-Trade Problem — CRITICAL PRIORITY

Most AE templates produce 0 trades in the 2-year backtest window because quarterly fundamental data only provides ~8 data points per symbol. Entry conditions are met in 0-2 quarters out of 8, which fails WF validation.

**Root cause**: Fundamental strategies are inherently low-frequency (quarterly signals, monthly rebalance). The WF validation framework was designed for DSL strategies that trade 5-20 times per month. Requiring even 2 trades in a 180-day test window is asking a quarterly strategy to fire twice in 6 months — that's a 1-in-4 chance per quarter.

**Possible solutions** (not yet implemented):
1. **Cross-symbol backtest aggregation**: Test the template across ALL 5 watchlist symbols and aggregate trades. 5 symbols × 8 quarters = 40 data points → more likely to get 2+ trades.
2. **Longer backtest window**: Extend from 730 days to 1460 days (4 years) for AE strategies. More quarters = more opportunities.
3. **Different validation for AE**: Skip WF entirely for AE and use a simpler validation (e.g., positive expected return from the fundamental signal, F-Score gate, accruals gate) instead of requiring historical trades.
4. **Loosen entry conditions**: Some thresholds are too strict for the universe (FCF yield > 5% when average is 1-3%, accruals > 10% when only 0.3% of quarters qualify). But this was rejected as curve-fitting — the thresholds are academically correct.

### 2. FMP Data Cache Not Sticking Between Restarts

The quarterly fundamentals cache uses `max(fetched_at)` freshness check (fixed from `min`), but many symbols still re-fetch on restart because:
- Old quarter rows from March have different `quarter_date` values than new fetches
- The upsert matches on `symbol + quarter_date`, so old rows persist with stale timestamps
- Need to either: (a) delete old rows before re-inserting, or (b) update ALL rows' `fetched_at` on any save for that symbol

### 3. Decay Score Stuck at 10

The decay score (10→0 countdown as strategy edge expires) never changes from 10 for any strategy. The monitoring service isn't updating it. Needs investigation in `src/core/monitoring_service.py`.

### 4. Health Score Shows 1-3 for New Strategies

New AE strategies show health score 1-3 immediately after creation. This is expected (no live trades yet), but the scoring logic should be reviewed to ensure it properly handles strategies with 0 live trades.

### 5. SQLite "database is locked" Errors

Still present from V3/V4. Multiple close orders firing in rapid succession cause `database is locked` errors on trade journal writes.

### 6. Sector Rotation Templates — ETF Backtest Issue

Sector Rotation templates use `fixed_symbols: ["XLF", "XLK", "XLI", "XLP", "XLY"]` but the backtest tries to fetch income statements for ETFs (which don't exist). The sector rotation backtest should route to `_simulate_sector_rotation_with_fundamentals` which uses sector performance data, not income statements. Currently produces 0 trades.

## Key Files Modified This Session (V5 additions)

- `src/data/fundamental_data_provider.py` — Parallelized FMP calls, added cash flow/balance sheet fetch, computed 16 new metrics (accruals, FCF yield, F-Score, SUE, etc.), added `get_price_target_consensus()`, `get_upgrades_downgrades()`, `get_institutional_ownership()`, fixed cache freshness check
- `src/strategy/fundamental_ranker.py` — **NEW** — Cross-sectional ranking engine (value, quality, momentum, growth factors)
- `src/strategy/strategy_engine.py` — Eliminated price-proxy fallback, fixed Revenue Acceleration/Relative Value/Quality Deterioration Short, added backtest simulation + signal handlers for 10 new template types, added `_handle_multi_factor_composite()`, `_handle_factor_template_signal()`
- `src/strategy/strategy_proposer.py` — Integrated ranker into proposal cycle, AE scoring uses cross-sectional ranks, AE watchlist builder (top 5 symbols per template, inverted for shorts), removed per-template concentration limit
- `src/strategy/strategy_templates.py` — Reclassified Pairs Trading/End-of-Month Momentum, added 10 new AE templates (23 total)
- `src/strategy/autonomous_strategy_manager.py` — AE vs DSL performance tracking in cycle stats
- `src/models/orm.py` — 16 new columns on QuarterlyFundamentalsORM
- `src/data/fmp_cache_warmer.py` — Pre-warms sector performance + historical fundamentals for AE
- `frontend/src/pages/StrategiesNew.tsx` — DSL Templates + AE Templates tabs
- `frontend/src/components/trading/TemplateManager.tsx` — Category prop, scoped summary stats
- `src/api/routers/strategies.py` — `strategy_category` field in TemplateResponse
- `config/autonomous_trading.yaml` — min_trades_alpha_edge: 2, portfolio_risk section, multi_factor_composite config, similarity_detection disabled
- `ALPHA_EDGE_PIPELINE_AUDIT.md` — Full pipeline audit report
- `HEDGE_FUND_FUNDAMENTAL_ANALYSIS_RESEARCH.md` — Research on institutional fundamental analysis approaches

## Current System State

- Account: balance=$140K, equity=$464K
- Active strategies: ~87 DEMO + ~14 BACKTESTED
- Open positions: ~114
- Market regime: trending_down_weak (confidence: 59%)
- AE templates: 23 (was 13), 0 currently active (backtest 0-trade problem)
- DSL templates: ~64 (5 disabled)
- Signal gen: parallelized (4 workers), ~50s per cycle
- FMP data: 16 new quarterly metrics (F-Score, accruals, FCF yield, SUE, etc.)
- Cross-sectional ranker: ranks 93 stocks by composite score
- Similarity detection: DISABLED (was causing unnecessary correlation calculations)
- Correlation cache: 7-day TTL (in-memory only, doesn't survive restarts)

## How to Troubleshoot

1. Read `logs/cycles/cycle_history.log` for cycle summaries
2. Read `logs/alphacent.log` for detailed backend logs
3. Check AE quarterly data: `sqlite3 alphacent.db "SELECT symbol, quarter_date, piotroski_f_score, accruals_ratio, fcf_yield FROM quarterly_fundamentals_cache WHERE piotroski_f_score IS NOT NULL ORDER BY symbol, quarter_date DESC LIMIT 20"`
4. Check ranker results: Look for "FundamentalRanker: ranked" in logs
5. Check AE watchlists: Look for "AE watchlist for" in logs
6. Check AE backtest results: Look for "Alpha Edge results:" in logs
7. Check proposal tracker: `cat config/.proposal_tracker.json | python3 -m json.tool`
8. Check disabled templates: `cat config/.disabled_templates.json`
