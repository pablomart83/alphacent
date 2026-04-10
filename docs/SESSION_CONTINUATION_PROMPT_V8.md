# AlphaCent Trading System — Session Continuation Prompt V8

Read `#File:.kiro/steering/trading-system-context.md` for full system context, then read this prompt carefully before proceeding.

## What Was Done This Session (April 9, 2026)

Continuation of V7 session. All V7 completed items remain in place. This session was a major upgrade focused on three areas: (1) institutional-grade fundamental analysis improvements from hedge fund research, (2) trailing stop fixes and asset-class-aware profit protection, and (3) CIO dashboard enrichment with strategy lifecycle analytics.

---

### 1. Hedge Fund Research → 14 Implementable Improvements

Conducted deep research into what top quant hedge funds (AQR, Two Sigma, D.E. Shaw) are doing differently. Identified 14 improvements across 3 tiers, implemented 13 of them.

**Tier 1 — High Impact (4 items):**

**Volatility-Scaled Position Sizing (risk_manager.py):**
- Added asset-class-specific volatility estimators: Yang-Zhang (equities/commodities), Parkinson (crypto), EWMA close-to-close (forex)
- Position sizes now inversely proportional to realized volatility with 16% target vol baseline
- Price history auto-fetched in `validate_signal()` for every entry signal (90 days, daily bars)
- High-vol crypto positions get sized ~3.75x smaller than low-vol utility stocks
- Functions: `estimate_realized_volatility()`, `_yang_zhang_vol()`, `_parkinson_vol()`, `_ewma_vol()`

**Cross-Sectional Tercile Ranking (fundamental_filter.py):**
- `_check_valuation()` now uses FundamentalRanker's composite scores when available
- Value stocks must be in top 2 terciles by value rank AND pass F-Score ≥ 7 quality gate
- Falls back to absolute P/E thresholds when ranking data isn't present
- New method: `set_ranker_results()` — called by strategy engine with ranker output
- Ranker results flow: proposer → strategy_engine._ranker_results → filter

**Piotroski F-Score Quality Gate:**
- Integrated into valuation check for value strategies (already computed by data provider since V7)
- Value stocks with F-Score < 7 rejected even if value rank is good
- All 9 criteria computed from FMP: income statement + balance sheet + cash flow

**Expanded FRED Macro Data (market_analyzer.py):**
- Added 4 new FRED series to `get_market_context()`:
  - DGS2 (2-year Treasury) → yield curve slope = DGS10 - DGS2
  - NAPM (ISM Manufacturing PMI)
  - BAMLH0A0HYM2 (ICE BofA High Yield OAS — credit stress)
  - DTWEXBGS (Trade-weighted US dollar index)
- All new fields in market context dict, available to all downstream consumers
- Default values provided when FRED unavailable

**Tier 2 — Moderate Impact (5 items):**

**Accruals Ratio, FCF Yield, SUE:**
- Already computed by data provider (V7) and consumed by ranker
- Now flowing through the filter via cross-sectional ranking (wired up in this session)

**Keltner Channel Breakout DSL Templates (strategy_templates.py):**
- Long: `CLOSE > EMA(20) + 2×ATR(14) AND ADX(14) > 25` — trend-confirmed breakout
- Short: mirror for downtrends
- ATR trailing stop at 1.5×ATR, ADX exit at < 20
- Works across all asset classes

**Bollinger Regime-Gated Mean Reversion DSL Templates:**
- Long: `CLOSE < BB_LOWER(20,2) AND ADX(14) < 25 AND RSI(14) < 35` — only in ranging markets
- Short: mirror at upper band
- ADX < 25 gate prevents buying dips in strong downtrends

**Tier 3 — Additional Items (4 items):**

**BTC → Altcoin Lead-Lag Template:**
- New crypto momentum template using BTC's momentum as leading indicator for altcoins
- Entry: BTC RSI > 55, price > EMA(20) + SMA(50)
- Marked `crypto_optimized`, assigned to ETH, SOL, ADA, LINK etc.

**Intangibles-Adjusted P/B (fundamental_ranker.py):**
- Value composite now includes adjusted book-to-price alongside FCF yield and earnings yield
- R&D capitalized at 33% quarterly depreciation, 30% of SGA at 3.75% quarterly depreciation
- Perpetual inventory method across 8 quarters of historical data
- Data provider now extracts `researchAndDevelopmentExpenses` and `sellingGeneralAndAdministrativeExpenses`

**Earnings Transcript Sentiment (NEW: src/analytics/transcript_sentiment.py):**
- Loughran-McDonald financial dictionary (~120 negative, ~80 positive, ~50 uncertainty words)
- Negation-aware scoring (2-word window)
- Prepared remarks vs Q&A splitting (40/60 weighting per Matsumoto et al. 2011)
- `fetch_and_score_transcript()` plugs into FMP's `/earning-call-transcript` endpoint
- Ready to wire into AE signal generation

**Macro-Conditioned Sector Rotation (strategy_engine.py):**
- Sector rotation AE template now uses yield curve slope + ISM PMI as leading indicators
- Inverted curve + PMI < 50 → defensives (XLU, XLP, XLV)
- Positive curve + PMI > 50 → cyclicals (XLY, XLI, XLF)
- Late cycle (inverted curve, PMI > 50) → quality/defensive growth (XLV, XLK, XLP)
- Overrides price-based regime fallback when macro data gives clear signal

---

### 2. Trailing Stop Fixes — Asset-Class-Aware Profit Protection

**Position Sync Stop-Loss Overwrite Bug (order_monitor.py):**
- CRITICAL FIX: `sync_positions()` was unconditionally overwriting DB stop_loss with eToro's stale value
- eToro doesn't support modifying SL on open positions → always reports original SL
- Trailing stop would set 594.08, position sync would overwrite back to 556.13
- Fixed in ALL THREE code paths: `reconcile_on_startup`, `sync_positions` main loop, and strategy-match path
- Logic: preserve DB stop_loss when it's better (higher for longs, lower for shorts)

**Asset-Class-Aware Trailing Stops (position_manager.py):**
- Replaced single fixed 5%/3% activation/distance with per-asset-class thresholds:
  - Stocks: 3% activation, 5% distance
  - ETFs: 3% activation, 4% distance
  - Crypto: 6% activation, 8% distance
  - Forex: 2% activation, 3% distance
  - Commodities: 4% activation, 6% distance
  - Indices: 3% activation, 4% distance
- Coverage went from 11 positions to 32 positions
- Config overrides still respected if user explicitly sets values

**Position Closure Reason Inference (order_monitor.py):**
- Both `reconcile_on_startup` and `sync_positions` now infer WHY a position closed:
  1. Check if `closure_reason` already set (trailing stop breach, retirement, etc.)
  2. Check if `pending_closure` flagged by system
  3. Check for recent exit orders
  4. Compare price vs SL/TP (within 0.5% tolerance)
  5. Fallback: "closed_on_etoro" with price/SL/TP details
- Stored in `closure_reason` field and passed to trade journal

---

### 3. CIO Dashboard Enrichment

**New Metrics (analytics.py + AnalyticsNew.tsx):**

Strategy Pipeline Health:
- Proposal → Activation conversion rate
- Pipeline funnel: Proposed → Activated → Active → Retired → Avg Lifespan

Retirement Analysis:
- Retired profitable vs unprofitable count
- Total P&L from retired strategies
- Retirement reasons breakdown (positions_hit_tp, positions_stopped_out, exit_signals, decay_score, health_score)
- Counts demoted strategies (DEMO → BACKTESTED) as "retired" since system recycles via demotion

Active Strategy Health:
- Profitable vs unprofitable active strategies
- Total unrealized P&L across active strategies
- Average P&L per active strategy

Trade Quality:
- Total closed trades, win/loss count, win rate
- Average win/loss size, profit factor (gross profit / gross loss)
- Average holding period

Position Closure Analysis:
- Breakdown: take_profit, stop_loss, exit_signal, etoro_closed, strategy_retired, manual

**Sharpe/Sortino Minimum Data Points:**
- Raised from 5 back to 10 (7 days produced Sharpe = 5 which is nonsensical)
- Returns 0 until 10+ trading days of data

**Trade Quality — Open + Combined Win Rate (analytics.py + AnalyticsNew.tsx):**
- Trade Quality card now shows Closed WR, Open WR, and Combined WR
- Closed WR alone was misleading (29%) because winners are still running as open positions
- Open WR shows the real picture (most open positions are profitable)
- Combined WR = (closed wins + open winners) / total positions

**Phantom BTC Trade Cleanup:**
- Deleted 8 phantom BTC positions from RSI Dip Buy V2 (0 P&L, < 1 hour hold, duplicate entries)
- These were polluting trade metrics (9 of 89 "closed trades" were garbage)

**RSI Dip Buy Regime Gate — Investigated and Kept:**
- Initially removed TRENDING_DOWN_WEAK from RSI Dip Buy template
- Data showed the template is actually profitable: +$668 realized + $3,857 unrealized = +$4,525
- The 29% closed win rate is misleading — winners are still running as open positions
- Reverted the change — buying dips in weak downtrends works when you let winners run

---

### 4. Bug Fixes

**CVX Instrument ID (etoro_client.py, instrument_mappings.py):**
- CVX was mapped to instrument ID 100512 (Convex Finance crypto token, ~$20)
- Correct mapping: 1014 (Chevron stock, ~$155)
- Orders were failing because SL/TP calculated from wrong price
- Added safeguard: search fallback now matches `.US` suffix and prefers stock instruments (type 5) over crypto (type 10) for symbols in stock universe

**Position Sync Duplicate Insert (order_monitor.py):**
- UNIQUE constraint violation when position exists in DB but `etoro_position_id` doesn't match
- Added safety check: before INSERT, check if position with that `id` already exists → update instead

**SQLite Contention — Position Sync (order_monitor.py):**
- eToro API call (10-30s) was inside the DB session → held write lock during network I/O
- Moved `_get_positions_cached()` call BEFORE opening DB session
- DB session now only open for the actual update loop (~1-2s)

**SQLite Connection Pool (database.py):**
- Reduced pool from 20+40 overflow (60 connections) to 10+5 (15 total)
- SQLite only allows 1 writer — 60 connections just means 59 threads waiting
- Added `pool_timeout=10` to prevent infinite waits
- Reduced `pool_recycle` from 1h to 30min

**CIO Dashboard N+1 Queries (analytics.py):**
- Retirement analysis: 52 individual queries → 1 bulk query with in-memory grouping
- Active strategy health: ~190 individual queries → 2 bulk queries with in-memory grouping

---

## Key Files Modified This Session (V8)

- `src/risk/risk_manager.py` — Volatility-scaled position sizing (Yang-Zhang, Parkinson, EWMA estimators)
- `src/strategy/fundamental_filter.py` — Cross-sectional tercile ranking, F-Score quality gate, `set_ranker_results()`
- `src/strategy/fundamental_ranker.py` — Intangibles-adjusted P/B in value composite
- `src/strategy/market_analyzer.py` — Expanded FRED data (DGS2, NAPM, HY spread, trade-weighted dollar)
- `src/strategy/strategy_templates.py` — 7 new templates (Keltner long/short, Bollinger regime-gated long/short, BTC lead-lag)
- `src/strategy/strategy_engine.py` — Ranker results injection into filter, macro-conditioned sector rotation
- `src/strategy/strategy_proposer.py` — Stores ranker results on strategy engine
- `src/data/fundamental_data_provider.py` — R&D and SGA extraction for intangibles-adjusted P/B
- `src/execution/position_manager.py` — Asset-class-aware trailing stops
- `src/core/order_monitor.py` — Trailing stop preservation in sync, closure reason inference, duplicate insert fix, DB session optimization
- `src/core/monitoring_service.py` — (unchanged but benefits from order_monitor fixes)
- `src/api/routers/analytics.py` — CIO dashboard enrichment, Sharpe/Sortino minimum fix, bulk queries
- `src/api/etoro_client.py` — CVX instrument ID fix, stock-preference search fallback
- `src/utils/instrument_mappings.py` — CVX ID corrected (100512 → 1014)
- `src/analytics/transcript_sentiment.py` — NEW: Loughran-McDonald earnings call sentiment scorer
- `src/models/database.py` — Connection pool optimization
- `frontend/src/pages/AnalyticsNew.tsx` — CIO dashboard UI enrichment (pipeline, retirement, trade quality, closures)
- `tests/test_position_manager.py` — Updated for asset-class-aware trailing stop thresholds
- `tests/test_risk_manager.py` — All 42 core tests passing

## Current System State

- Account: balance=$124K, equity=$465K+
- Active strategies: ~93 (DEMO)
- Open positions: ~123-127 (fluctuating with trades)
- Market regime: trending_down_weak → high_vol (VIX 25.8)
- Trailing stops: 32 positions protected (was 11), asset-class-aware distances
- New FRED data: yield curve slope, ISM PMI, HY spread, trade-weighted dollar flowing
- Cross-sectional ranking: active, feeding into fundamental filter
- 7 new DSL templates: Keltner breakout, Bollinger regime-gated, BTC lead-lag
- All 42 risk manager tests + 21 position manager tests passing

## What Needs Investigation — V9 Priority

### PRIORITY 1: Analytics Dashboard Performance

The Analytics page takes too long to load, and switching tabs or returning from another page triggers a full re-fetch. Issues to investigate:

1. **CIO Dashboard endpoint is heavy** — queries all strategies, all positions (open + closed), trade journal entries, and FRED data in a single request. With 178 strategies and 120+ positions, this is a lot of DB work.
2. **Tab switching re-fetches everything** — the lazy loading (Phase 1/Phase 2) from V7 should prevent this, but may not be caching between tab switches.
3. **No server-side caching** — the CIO dashboard computes everything from scratch on every request. Should cache for 60-120s since the data doesn't change that fast.
4. **Frontend polling at 120s** — but initial load is the bottleneck, not polling.
5. **Multiple concurrent API calls on page load** — Phase 1 fires 3 endpoints simultaneously, all hitting the DB.

Recommended approach:
- Add server-side caching (in-memory, 60s TTL) to the CIO dashboard endpoint
- Cache the retirement/active strategy analysis separately (changes rarely)
- Consider pre-computing CIO metrics in the monitoring service background loop
- Profile which specific queries are slowest

### PRIORITY 2: SQLite → PostgreSQL Migration

SQLite contention remains the #1 infrastructure bottleneck. The system hangs when:
- Trading cycle runs (4 threads signal generation + DB writes)
- Position sync holds write lock during 125-position update
- API endpoints compete for read access during writes
- Trade journal retries fail after 60s lock timeout

Migration plan to investigate:
- Use Alembic for schema migration management
- PostgreSQL supports true concurrent reads + writes (no single-writer bottleneck)
- Connection pooling via pgBouncer or SQLAlchemy's built-in pool
- Data migration: dump SQLite → import to PostgreSQL
- Environment: local PostgreSQL for dev, or managed (e.g., Supabase, Railway)
- Minimal code changes: SQLAlchemy abstracts the dialect, main changes are connection string + removing SQLite-specific PRAGMAs

### From V7 Audit (Still Open)

1. **Signal Generation** — Are conviction scores using meaningful inputs?
6. **Template-Symbol Matching** — Should template weights from performance feedback decay over time?
7. **Risk Controls** — Portfolio-level VaR check before new positions
8. **Order Execution** — Is signal coordination too aggressive?
10. **Performance Feedback Loop** — Is it chasing past winners?

### From This Session

- **Backtest avg_loss bug** — Strategies pass activation but get blocked by "avg loss 258% > 12%" guard. The avg_loss calculation uses eToro quantity-as-dollars incorrectly
- **Forex carry bias** — FRED rate data available but not wired into forex strategy scoring
- **Transcript sentiment wiring** — Module built but not integrated into AE signal generation
- **Daily P&L timezone** — Dates in DB are UTC, frontend displays as-is

### Analytics/Risk Page — Remaining Items

- Historical named stress tests (COVID, Lehman, SVB)
- Drawdown recovery analysis
- R-Multiple distribution
- SPY benchmark comparison on equity curve
- Activation rejection reasons tracking

## How to Troubleshoot

1. Read `logs/cycles/cycle_history.log` for cycle summaries
2. Read `logs/alphacent.log` for detailed backend logs
3. Check trailing stops: Look for "trailing stop:" — now shows asset class and distance %
4. Check position closures: Look for "CLOSED:" — now shows inferred reason (TP hit, SL hit, etc.)
5. Check CIO dashboard: `GET /analytics/cio-dashboard?mode=DEMO&period=3M`
6. Check FRED data: Look for "yield_curve_slope", "ism_pmi" in market context logs
7. Check cross-sectional ranking: Look for "FundamentalRanker: ranked" in logs
8. Check vol-scaling: Look for "Vol-scaling" in logs during signal validation
9. Check CVX orders: Should now use instrument ID 1014 (Chevron), not 100512 (crypto)
10. Check DB contention: `ls -la alphacent.db-wal` — WAL > 5MB = potential stuck transaction
