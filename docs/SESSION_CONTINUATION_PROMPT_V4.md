# AlphaCent Trading System — Session Continuation Prompt V4

Read `#File:.kiro/steering/trading-system-context.md` for full system context, then read this prompt carefully before proceeding.

## What Was Done This Session (April 8, 2026)

Continuation of V3 session. All V3 completed items remain in place.

### 1. Disabled 5 Broken Templates (COMPLETE)

Templates with 0% WF approval rate across all symbols — fundamentally broken, not regime-mismatched:
- **OBV Bullish Divergence Long** (48 proposals, 0 approved) — entry condition `CLOSE < LOW_20` logically impossible (current bar included in 20-day low)
- **OBV Bearish Divergence Short** — same structural issue, mirror template
- **Triple EMA Bearish Short** (14/0) — zero trades across 18+ symbols, EMA alignment condition never fires in backtest
- **Volume Climax Reversal Long** (6/0) — 2x volume spike too rare for backtest window
- **Volume Climax Reversal Short** (4/0) — same issue

**File**: `config/.disabled_templates.json`

### 2. Parallel Signal Generation (COMPLETE)

Replaced sequential strategy evaluation with `ThreadPoolExecutor` (4 workers, configurable via `parallel_workers` in YAML). At 100 strategies, signal gen drops from ~185s to ~50s. Thread-safe indicator cache added to `IndicatorLibrary` with `threading.Lock`.

**Files**: `src/strategy/strategy_engine.py` (generate_signals_batch), `src/strategy/indicator_library.py` (thread-safe cache), `config/autonomous_trading.yaml` (parallel_workers: 4)

### 3. Max Active Strategies Raised to 500 (COMPLETE)

Frontend Zod schema, HTML input max, and helper text all updated from 100 to 500. YAML config set to 150.

**Files**: `frontend/src/pages/SettingsNew.tsx`, `config/autonomous_trading.yaml`

### 4. Signal Generation Logic Fixes (COMPLETE)

#### 4a. Entry Conditions: OR → AND Logic
Multiple entry condition strings were combined with OR (any one triggers entry). Fixed to AND (all must be true simultaneously). Exit conditions remain OR (any exit reason is sufficient). 31 templates affected, 0 active strategies impacted (all had single-string conditions).

#### 4b. Exit Signal Generation for Open Positions
DSL exit conditions (e.g., `RSI(14) > 60`) were never evaluated for symbols with open positions — the pre-filter skipped them entirely. Fixed: symbols with open positions are now evaluated for exit signals, with entry signals suppressed.

**File**: `src/strategy/strategy_engine.py` (_parse_strategy_rules, generate_signals)

### 5. ATR-Based Stop-Loss Floor (COMPLETE)

**Problem**: MELI (ATR 3%) got a 2% SL from a forex-calibrated strategy (primary symbol NZDUSD). Stopped out on normal intraday noise after 5.3 hours.

**Fix at two levels**:
1. **Strategy creation** (`_compute_adaptive_risk_config`): ATR floor now applies even when templates specify SL/TP. If template says 2% but ATR says 4.5%, SL widens to 4.5% while preserving R:R ratio.
2. **Order execution** (`order_executor.py`): Second ATR floor check at order time using 30-day Yahoo data. Catches multi-asset-class watchlist issues (forex strategy trading a stock).

**Files**: `src/strategy/strategy_proposer.py`, `src/execution/order_executor.py`

### 6. Overview Page P&L Fix (COMPLETE)

**Problems found**:
- Percentages calculated vs cash balance ($139K) instead of equity ($464K) — 3x worse than reality
- "Today" showed only realized P&L from closed positions (-$479) while eToro showed +$5,608
- All-Time was wrong (realized-only, missing unrealized)

**Fix**:
- Added `EquitySnapshotORM` table for daily equity snapshots
- Today = current_equity - yesterday's snapshot equity (matches eToro)
- All-Time = eToro's `total_pnl` (realized + unrealized)
- Percentages now vs equity
- Equity curve uses snapshots when available
- Snapshots saved on dashboard load + daily sync

**Files**: `src/models/orm.py` (EquitySnapshotORM), `src/api/routers/account.py`, `src/core/monitoring_service.py`

### 7. Time-Based Exit Check: 24h → 5min (COMPLETE)

**Problem**: PYPL intraday position held 42.4h past a 24h limit. The time-based exit check ran once per 24 hours (tied to fundamental check interval).

**Fix**: Now runs every 5 minutes. Intraday positions hitting their max hold will be flagged within 5 minutes.

**File**: `src/core/monitoring_service.py`

### 8. Position Sync Attribution Fix (COMPLETE)

**Problem**: When multiple strategies traded the same symbol (e.g., AXP), position sync matched eToro positions to strategies by symbol only, not by the strategy that placed the order. This caused positions to be attributed to the wrong strategy.

**Fix**: Order matching now checks for double-attribution (won't assign a position to a strategy that already has one for that symbol+side). Dedup check is strategy-scoped, not global symbol-scoped.

**File**: `src/core/order_monitor.py` (sync_positions)

### 9. Confidence Calculation: Strategy-Type-Aware (COMPLETE)

**Problem**: Confidence = signal persistence (how many of last 10 bars had signal true). For mean-reversion, this is backwards — 8/10 bars means stuck oversold (dangerous), not high conviction.

**Fix**:
- **Mean reversion**: Confidence peaks at 2-3 bars persistence (0.80), drops to 0.40 at 6+ bars. Indicator extremity boost: RSI < 20 adds +0.15.
- **Trend following**: Linear scaling with persistence (strong trend = high confidence).
- **Breakout/volatility**: Moderate scaling.

**File**: `src/strategy/strategy_engine.py` (_generate_signal_for_symbol)

### 10. Template Entry Conditions Tightened (COMPLETE)

**Problem**: RSI Dip Buy used RSI < 45 (not a dip — neutral territory). 4H MACD Short used RSI < 55 (almost always true). This created a 25-point overlap zone where LONG and SHORT strategies fired simultaneously on the same symbol.

**Fixes**:
| Template | Old | New |
|---|---|---|
| RSI Dip Buy | RSI < 45 | RSI < 35 |
| BB Middle Band Bounce | RSI < 60 | RSI < 55 |
| SMA Proximity Entry | RSI < 55 | RSI < 45 |
| 4H MACD Bearish Cross Short | RSI < 55 | RSI < 45 |

All 83 existing active strategies updated in DB to match. 50 of 58 DEMO strategies are profitable ($6,064 net).

**Files**: `src/strategy/strategy_templates.py`, database migration (in-place update)

### 11. Forex & Crypto Asset Class SL/TP Updated (COMPLETE)

- Forex: SL 0.8% → 1.5%, TP 1.6% → 3.0% (old was inside daily ATR for NZDUSD, AUDUSD)
- Crypto: SL 4% → 6%, TP 10% → 12% (ETH/SOL/ADA have ATR > 4%)

**File**: `config/autonomous_trading.yaml`

### 12. Proposer Parameter Variation Fixes (COMPLETE)

**Problem 1**: SL/TP varied independently — could produce SL=1% TP=2% (noise stop) or SL=3% TP=2% (negative R:R).
**Fix**: Coherent risk profiles as pairs: (1.5%/3%), (2%/4%), (2.5%/5%), (3%/6%), (4%/8%). All maintain 2:1 R:R.

**Problem 2**: `customize_template_parameters` relaxed RSI thresholds when signals were "too rare" (RSI < 30 fires 5% → relax to 40). This created the loose thresholds.
**Fix**: Can only tighten, never loosen beyond template's own threshold.

**File**: `src/strategy/strategy_proposer.py`

### 13. Seven New 2026 Regime-Optimized Templates (COMPLETE)

Based on hedge fund research (QuantLabs, Morgan Stanley, Algomatic Trading, Cambridge Associates):

1. **Bear Rally Fade Short** — Short RSI > 70 spikes when price < SMA(200). Fades exhaustion rallies in confirmed downtrends. 60% WR per research.
2. **Gold Momentum Long** — Trend-following on GOLD. Price > SMA(50) + RSI > 50. Central bank buying + geopolitical demand.
3. **Defensive Sector Rotation Long** — Buy XLU/XLV/XLP/XLI/GLD/HYG when showing relative strength in weak market.
4. **High VIX Oversold Bounce** — Buy RSI < 25 only when ATR is elevated (real panic, not slow drift).
5. **EURUSD Policy Divergence Short** — Short EUR/USD on Fed-hawkish/ECB-dovish divergence. Fixed to EURUSD.
6. **ATR Dynamic Trend Follow** — Long when price > SMA(20) + SMA(50) with RSI > 50.
7. **ATR Dynamic Trend Follow Short** — Mirror for downtrends.

**File**: `src/strategy/strategy_templates.py`

## What Still Needs Investigation / Doing

### 1. Alpha Edge Strategy Pipeline — INVESTIGATE & IMPROVE (PRIORITY)

Alpha Edge strategies are intentionally disabled (`strategy_types: ['dsl']` filter). AE=0 in proposals is expected. The Alpha Edge system uses fundamental data (earnings, revenue, sector rotation) from FMP API instead of DSL technical rules.

**Current Alpha Edge templates** (all disabled):
- Earnings Momentum (buy post-earnings surprise)
- Sector Rotation (long/short sector ETFs based on macro)
- Quality Mean Reversion (buy quality stocks on deep pullbacks)
- Earnings Miss Momentum Short
- Dividend Aristocrat
- Insider Buying
- Revenue Acceleration
- Relative Value (sector P/E comparison)
- Quality Deterioration Short
- End-of-Month Momentum Long
- Pairs Trading Market Neutral
- Analyst Revision Momentum
- Share Buyback Momentum

**Key files for Alpha Edge**:
- `src/strategy/strategy_engine.py` — `_generate_alpha_edge_signal()`, `_simulate_earnings_momentum()`, `_simulate_sector_rotation()`, etc.
- `src/data/fundamental_data_provider.py` — FMP API integration for earnings, revenue, sector data
- `src/strategy/fundamental_filter.py` — Fundamental quality filters
- `config/autonomous_trading.yaml` — `alpha_edge` section (disabled)
- `src/strategy/strategy_templates.py` — Alpha Edge template definitions (natural language conditions)

**What needs to happen**:
1. Investigate why Alpha Edge was disabled — was it broken, underperforming, or just not prioritized?
2. Review the FMP API integration — is data quality sufficient?
3. Test each Alpha Edge template individually to see which ones produce viable signals
4. Fix any broken signal generation logic
5. Enable Alpha Edge alongside DSL strategies (`strategy_types: ['dsl', 'alpha_edge']`)
6. Ensure Alpha Edge strategies go through the same WF validation pipeline

### 2. SQLite "database is locked" Errors During Position Closures
Still present from V3. Multiple close orders firing in rapid succession cause `database is locked` errors on trade journal writes.

### 3. Portfolio Concentration — Existing Strategies
57 active strategies still dominated by 3 templates (RSI Dip Buy, SMA Proximity, BB Middle Band Bounce). The tighter thresholds will reduce new entries from these templates, and the 7 new templates will add diversity over time.

## Key Files Modified This Session (V4 additions)

- `src/strategy/strategy_engine.py` — parallel signal gen, entry AND logic, exit signal for open positions, confidence calculation, entry suppression
- `src/strategy/indicator_library.py` — thread-safe cache with Lock
- `src/strategy/strategy_proposer.py` — ATR floor on template SL, coherent SL/TP variations, no RSI relaxation
- `src/strategy/strategy_templates.py` — tightened 4 templates, added 7 new regime-optimized templates, disabled 5 broken
- `src/execution/order_executor.py` — ATR floor at order time
- `src/core/monitoring_service.py` — time-based exit every 5min, equity snapshots, daily sync
- `src/core/order_monitor.py` — strategy-scoped position attribution
- `src/api/routers/account.py` — equity-based P&L, snapshot-based periods
- `src/models/orm.py` — EquitySnapshotORM table
- `frontend/src/pages/SettingsNew.tsx` — max strategies 500
- `config/autonomous_trading.yaml` — parallel_workers, forex/crypto SL/TP, max_active_strategies 150
- `config/.disabled_templates.json` — 5 broken templates

## Current System State

- Account: balance=$140K, equity=$464K
- Active strategies: ~62 DEMO + ~38 BACKTESTED (max raised to 150)
- Open positions: ~91
- Market regime: trending_down_weak (confidence: 60%)
- Signal gen: parallelized (4 workers), ~50s per cycle
- Template count: 226 (was 219), 81 for current regime (was 74)
- Entry conditions tightened on 83 strategies
- 7 new hedge-fund-research-based templates active
- DSL exit conditions now evaluating for open positions
- ATR-based SL floor at both strategy creation and order execution

## How to Troubleshoot

1. Read `logs/cycles/cycle_history.log` for cycle summaries
2. Read `logs/alphacent.log` for detailed backend logs
3. Check proposal tracker: `cat config/.proposal_tracker.json | python3 -m json.tool`
4. Check disabled templates: `cat config/.disabled_templates.json`
5. Check equity snapshots: `sqlite3 alphacent.db "SELECT * FROM equity_snapshots ORDER BY date DESC LIMIT 10"`
6. Check strategy entry conditions: `sqlite3 alphacent.db "SELECT name, json_extract(rules, '$.entry_conditions') FROM strategies WHERE status IN ('DEMO','BACKTESTED') LIMIT 20"`
