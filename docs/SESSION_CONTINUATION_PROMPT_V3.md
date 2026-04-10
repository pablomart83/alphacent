# AlphaCent Trading System — Session Continuation Prompt V3

Read `#File:.kiro/steering/trading-system-context.md` for full system context, then read this prompt carefully before proceeding.

## What Was Done This Session (April 7, 2026 — Evening)

Continuation of V2 session. All V2 completed items remain in place.

### 1. Strategy Proposal Diversity — Complete Redesign (COMPLETE)

**Problem**: System was stuck proposing the same ~9 templates and ~16 symbols out of 67 templates and 155 symbols. The scoring function was fine — the selection algorithm was greedy (sort all pairs by score, pick top N), so the same high-scoring templates always won.

**Solution**: Round-robin template-first selection. Every template gets its best symbol before any template gets a second slot. Score only decides which *symbol* is best for a given template — templates don't compete against each other.

**Algorithm** (`_match_templates_to_symbols` in `src/strategy/strategy_proposer.py`):
1. Score all (template, symbol) pairs purely on signal likelihood — no penalties, no artificial boosts
2. For each template, rank its symbols by score
3. Round-robin: pick best symbol for each template (round 1), then 2nd-best from a *different asset class* (round 2), etc.
4. Directional quotas (LONG/SHORT balance) applied as post-filters
5. Asset class minimums (crypto 10%, forex 5%) enforced at the end

**Key design decisions**:
- No active template penalties — removed the diversity_penalty that penalized templates with many active strategies
- No rotation counters or cycle-based offsets — the market data changes naturally each cycle, scores change with it
- No exploration/exploitation split — round-robin guarantees every template gets slots
- Stratified asset class picking: round 2+ forces different asset classes per template (stock → crypto → ETF → commodity)
- Performance feedback dampened: max weight 1.15x (was 1.3x), symbol bonus ±5 (was ±15)

**Results**: First cycle with new system: 308 proposals, **61 unique templates, 153 unique symbols** (was 9 templates, 16 symbols). 47 passed WF out of 300, 22 approved activation, 5 orders placed.

### 2. WF Failed Cache Persistence (COMPLETE)

**Problem**: Walk-forward failures were only cached in memory. After backend restart, the system re-proposed the same combos, re-ran WF, they failed again — wasting compute and blocking new combos.

**Solution**: `config/.wf_failed_cache.json` persists failed WF results to disk. On startup, loaded back into `_wf_results_cache`. Respects same 2-day TTL — after 2 days, entries expire and combos can be re-tested with fresh market data.

**Files**: `src/strategy/strategy_proposer.py` — `_load_wf_failed_from_disk()`, `_save_wf_failed_to_disk()`

### 3. Active Pairs Excluded at Selection Time (COMPLETE)

**Problem**: Active (template, symbol) pairs were only filtered downstream in `generate_strategies_from_templates`, wasting proposal slots.

**Solution**: `_match_templates_to_symbols` now loads active pairs (DEMO/LIVE/approved-BACKTESTED) from DB and skips them during scoring. Includes all watchlist symbols, not just primary.

### 4. Orders Page — Entry/Close/Retirement Column (COMPLETE)

Added `order_action` column to `OrderORM` (values: `entry`, `close`, `retirement`). Tagged all order creation points. Frontend shows color-coded "Action" column. DB migration added. Legacy orders default to 'entry'.

**Files**: `src/models/orm.py`, `src/models/database.py`, `src/api/routers/orders.py`, `src/core/monitoring_service.py`, `src/core/trading_scheduler.py`, `src/strategy/portfolio_manager.py`, `frontend/src/pages/OrdersNew.tsx`, `frontend/src/types/index.ts`

### 5. Stop-Loss Trailing Stops Re-enabled (COMPLETE)

**Problem**: `_check_trailing_stops` was disabled. eToro API doesn't support modifying SL on open positions, so trailing stops were cosmetic (DB-only).

**Solution**: Re-enabled DB-only trailing stop updates. Added stop-loss breach detection — positions where current price breaches the DB stop-loss are flagged with `pending_closure=True` for automatic closure by `_process_pending_closures`.

**Files**: `src/core/monitoring_service.py`, `tests/test_trailing_stop_etoro_updates.py` (rewritten, 10 tests pass)

### 6. Post-Adjustment Minimum Order Size (COMPLETE)

**Problem**: Correlation adjustment could reduce position size below eToro's minimum ($1000 for indices/commodities/forex), causing order failures (error 720).

**Solution**: Added post-adjustment minimum floor in `validate_signal` in `src/risk/risk_manager.py`. If correlation/regime adjustments push size below eToro minimum, bumps back up to minimum instead of submitting to fail.

### 7. Templates Dashboard — New Columns (COMPLETE)

Redesigned the Templates tab columns:
- **Proposed**: times template was included in a cycle's proposal batch (pre-WF). Tracked in `config/.proposal_tracker.json`.
- **Approved**: times template passed WF validation. Same tracker file.
- **Traded**: total positions ever opened (open + closed) for this template. From positions table.
- **Active**: open positions right now. From positions table.

**Files**: `src/strategy/strategy_proposer.py` (proposal tracker), `src/api/routers/strategies.py` (API), `frontend/src/components/trading/TemplateManager.tsx` (UI)

### 8. Performance Feedback Dampened (COMPLETE)

`apply_performance_feedback` defaults: max_weight 1.15 (was 1.3), min_weight 0.7 (was 0.5). Config updated in `config/autonomous_trading.yaml`. Symbol bonus capped at ±5 in scoring (was ±15).

## What Still Needs Investigation / Doing

### 1. 0% Approval Rate Templates — Investigate & Fix or Disable
Several templates have been proposed many times but NEVER pass WF:
- **OBV Bullish Divergence Long** (48 proposed, 0 approved) — OBV data may be unreliable or divergence logic broken
- **Crypto RSI Dip Buy** (22/0) — crypto-specific RSI thresholds too tight?
- **Triple EMA Bearish Short** (14/0) — produces 0 trades consistently
- **Crypto Hourly Fast Stoch Reversal** (11/0), **Crypto Hourly VWAP Reversion** (10/0), **Crypto Hourly Tight BB Reversion** (8/0), **Crypto Hourly Stoch Momentum Burst** (7/0) — all hourly crypto templates failing

**Action needed**: Investigate each 0% template. Determine if fundamentally broken (disable) or regime-mismatched (leave enabled, will work in different conditions). Check if crypto hourly data quality is the root cause.

**Key files**: `src/strategy/strategy_templates.py` (template definitions), `config/.proposal_tracker.json` (proposal counts), `logs/cycles/cycle_history.log` (WF failure details)

### 2. SQLite "database is locked" Errors During Position Closures
Multiple close orders firing in rapid succession cause `database is locked` errors on trade journal writes. The closures themselves succeed (eToro API calls go through), but journal entries fail, causing "Trade entry not found" warnings on exit logging.

**Root cause**: Each close order opens a new TradeJournal/session. Multiple concurrent sessions contend for the SQLite write lock.

**Fix options**: Add WAL mode timeout, serialize journal writes through a queue, or batch close orders.

### 3. Portfolio Concentration — Existing Strategies
57 active strategies still dominated by 3 templates (RSI Dip Buy, SMA Proximity, BB Middle Band Bounce). The diversity fix prevents NEW concentration, but existing strategies stay until retirement thins them. The round-robin is working — new cycles now propose 61+ unique templates.

### 4. Alpha Edge Strategies (DEFERRED)
Alpha Edge is intentionally disabled (`strategy_types: ['dsl']` filter). AE=0 in proposals is expected.

### 5. Orders Page — Entry vs Close Identification Enhancement
The `order_action` column is working but legacy orders (pre-change) all show as "Entry". Could backfill by checking if the order's strategy had `pending_closure=True` at the time.

## Key Files Modified This Session (V3 additions)

- `src/strategy/strategy_proposer.py` — round-robin selection, WF failed cache persistence, proposal tracker, performance feedback dampening
- `src/risk/risk_manager.py` — post-adjustment minimum order size floor
- `src/core/monitoring_service.py` — trailing stop re-enabled with breach detection, order_action tagging
- `src/core/trading_scheduler.py` — order_action='entry' tagging
- `src/strategy/portfolio_manager.py` — order_action='retirement' tagging
- `src/api/routers/orders.py` — order_action in API response
- `src/api/routers/strategies.py` — templates API: proposed/approved/traded/active columns from positions table + proposal tracker
- `src/models/orm.py` — order_action column on OrderORM
- `src/models/database.py` — migration for order_action column
- `frontend/src/pages/OrdersNew.tsx` — Action column in orders table
- `frontend/src/types/index.ts` — order_action on Order type
- `frontend/src/components/trading/TemplateManager.tsx` — Proposed/Approved/Traded/Active columns
- `config/autonomous_trading.yaml` — performance_feedback dampened, max_active_strategies raised to 100
- `config/.proposal_tracker.json` — proposal/approval counts per template (backfilled from April logs)
- `config/.wf_failed_cache.json` — persisted WF failures
- `tests/test_trailing_stop_etoro_updates.py` — rewritten for DB-only trailing stops

## Current System State

- Account: balance=$135K, equity=$456K, margin=$313K
- Active strategies: 56 DEMO + 22 BACKTESTED (max_active_strategies raised to 100)
- Open positions: 75
- Exposure: 63% long, 8% short
- Market regime: trending_down_weak (confidence: 60%)
- Proposal diversity: 61 unique templates, 153 unique symbols per cycle (was 9/16)
- WF pass rate: ~16% (expected — testing new untested combos)
- Proposal tracker: 77 templates tracked, 673 total proposals, 292 approvals

## How to Troubleshoot

1. Read `logs/cycles/cycle_history.log` for cycle summaries (WF pass/fail details)
2. Read `logs/alphacent.log` for detailed backend logs
3. Check proposal tracker: `cat config/.proposal_tracker.json | python3 -m json.tool`
4. Check WF failed cache: `cat config/.wf_failed_cache.json | python3 -m json.tool`
5. Check DB strategy counts: `sqlite3 alphacent.db "SELECT status, COUNT(*) FROM strategies GROUP BY status"`
6. Check template diversity in last cycle: grep for "Final:.*unique templates.*unique symbols" in alphacent.log
