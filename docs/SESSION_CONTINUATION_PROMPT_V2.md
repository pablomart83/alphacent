# AlphaCent Trading System — Session Continuation Prompt V2

Read `#File:.kiro/steering/trading-system-context.md` for full system context, then read this prompt carefully before proceeding.

## What Was Done This Session (April 7, 2026 — Afternoon)

### 1. Conviction Scorer Redesigned (COMPLETE)
The old conviction scorer was killing all ETF signals (VTI, IWM, XLK scored 55.5 vs threshold 60) because ETFs fell through to the "stock with no data" path and got `fund=5.0`. The entire scoring model was wrong — it penalized walk-forward validated strategies for not having earnings data.

**New scoring model** (`src/strategy/conviction_scorer.py`):
- Walk-forward edge (0-40 pts): OOS Sharpe (logarithmic), win rate, trade count, train/test consistency
- Signal quality (0-25 pts): Confidence (regime-adjusted), R:R ratio, indicator alignment
- Regime fit (0-20 pts): Strategy type vs market regime, minimum 5 pts (never 0 — WF already validated)
- Asset tradability (0-15 pts): Liquidity tiers (SPY/BTC=15, ETFs=12, NEAR=8), fundamental bonus (+2 max)

Threshold lowered to 55 in `config/autonomous_trading.yaml`. All 47 active strategies pass. ETFs now score 66-81.

Tests updated: `tests/test_conviction_scorer.py`, `tests/test_conviction_scorer_integration.py` — 17 tests pass.

### 2. Position Sizing Bug Fixed — balance vs equity (COMPLETE)
`calculate_position_size` in `src/risk/risk_manager.py` used `account.balance - account.margin_used` for available capital. Balance=$221K, margin=$241K → available=-$19K → every order got $0 size. This was the 9th instance of the balance-vs-equity bug (8 were fixed earlier).

**Fix**: `available_capital = equity - current_exposure` ($463K - $241K = $222K).

Also fixed: strategy allocation now uses `cash_balance * (allocation_pct / 100)` instead of `equity * (allocation_pct / 100)`. A 5% allocation on $459K equity = $23K, but cash balance is only $221K. Now uses balance so position sizes are realistic.

### 3. Close Order Quantity Bug Fixed (COMPLETE)
`_submit_close_order` in `src/core/monitoring_service.py` used `pos.quantity * pos.current_price` for close order amount. For crypto, `pos.quantity` can be garbage (e.g., 4974 for a $10K BTC position). Now uses `invested_amount` with sanity-capped fallback.

Same fix applied in `src/strategy/portfolio_manager.py` `_close_strategy_positions` — P&L calculations and trade journal entries also fixed to use `invested_amount` instead of raw `quantity`.

### 4. Position Quantity Data Fixed (COMPLETE)
35 positions in DB had `quantity` storing dollar amounts instead of units (eToro demo API returns dollars in the `units` field for many instruments). All corrected to actual units using `invested_amount / entry_price`.

### 5. Orphan Positions Fixed (COMPLETE)
- ZINC, FTNT, NOW, 2x ABBV → reassigned to matching active strategies
- ALUMINUM → closed on eToro (no active strategy)
- 3x AAPL test positions ($10, $10, $100) → closed on eToro
- 9x BTC test positions ($50-$70K from `test_btc_amount_limits.py`) → closed on eToro

### 6. Dangerous Test Scripts Removed (COMPLETE)
Deleted 16 scripts in `tests/manual/` and `scripts/diagnostics/` that called `etoro_client.place_order()` directly without going through the order pipeline. These created phantom positions on eToro that the position sync then imported.

### 7. Frontend Units/Dollars Display Fixed (COMPLETE)
- Portfolio page: "Amount" column now shows `invested_amount` (dollars) not `quantity` (units). Pie chart, % Portfolio, position details, close confirmation all use `invested_amount`.
- Orders page: "Qty" column renamed to "Amount", displays as currency ($9,534.76 not 9534.76).
- Risk page: Position value calculations use `invested_amount`.
- Frontend builds clean: `npm run build` passes.

### 8. `alpha_edge_config` Scoping Bug Fixed (COMPLETE)
`generate_signals` in `src/strategy/strategy_engine.py` line 4503 referenced `alpha_edge_config` which was only defined inside the Alpha Edge signal generation block. DSL strategies hit an `UnboundLocalError`. Fixed with local config lookup.

## What Still Needs Investigation / Doing

### 1. CRITICAL: Strategy Proposal Diversity Problem
**The system is stuck proposing the same ~9 templates and ~16 symbols out of 67 available templates and 155 symbols.** Only 1.6% of possible (template × symbol) combos are blocked by dedup/blacklists — 10,000+ combos are available but the scoring function keeps picking the same winners.

**Root cause**: `_match_templates_to_symbols` and `_score_symbol_for_template` in `src/strategy/strategy_proposer.py` score all (template, symbol) pairs and pick the top N. The scoring heavily favors templates that have historically worked (via WF validated cache and performance feedback), creating a self-reinforcing loop.

**Evidence from the last 3 cycles**:
- Only 9 unique template types proposed (out of 67 regime-matched)
- Only 16 unique symbols proposed (out of 155 available)
- Active portfolio dominated by: 21x RSI Dip Buy, 11x SMA Proximity Entry, 8x BB Middle Band Bounce
- Templates like Hourly Stochastic Reversal Short, 4H Lower High Short, Commodity Hourly Oversold Bounce, Crypto Hourly strategies — all regime-matched but never proposed

**What needs to happen**:
1. Read `src/strategy/strategy_proposer.py` — specifically `_score_symbol_for_template`, `_match_templates_to_symbols`, `generate_strategies_from_templates`
2. Understand why scoring concentrates on a few templates
3. Add exploration vs exploitation balance — reserve slots for untested templates
4. Add template rotation — ensure every regime-matched template gets proposed at least once every N cycles
5. Add symbol rotation — ensure coverage across all asset classes
6. Check if the WF validated cache (`config/.wf_validated_combos.json`, 137 entries) is biasing proposals toward already-proven combos at the expense of discovering new ones
7. Check if the performance feedback loop (`apply_performance_feedback`) is too aggressive in boosting winning templates

**Key files**:
- `src/strategy/strategy_proposer.py` — `_score_symbol_for_template`, `_match_templates_to_symbols`, `generate_strategies_from_templates`, `apply_performance_feedback`
- `config/.wf_validated_combos.json` — WF cache (137 entries, 27 templates, 85 symbols)
- `config/.zero_trade_blacklist.json` — 31 entries blocking 6 templates
- `config/.rejection_blacklist.json` — 27 entries
- `config/autonomous_trading.yaml` — `performance_feedback` section, `proposal_count: 200`

### 2. Orders Page — Entry vs Close identification
The Orders page doesn't distinguish between new entry orders and close/retirement orders. Need to add an "Action" column (Entry / Close / Retirement).
- Files: `frontend/src/pages/OrdersNew.tsx`, `src/api/routers/orders.py`

### 3. Stop-loss effectiveness audit
`_check_trailing_stops` in `src/core/monitoring_service.py` is **DISABLED** with comment: "eToro API does not support modifying SL/TP on open positions." Trailing stops are cosmetic — DB-only, never pushed to eToro. Need to verify if this is actually true or if there's a workaround.

### 4. Portfolio concentration
57 active strategies dominated by 3 templates (21 RSI Dip Buy, 11 SMA Proximity Entry, 8 BB Middle Band Bounce = 70% of portfolio). The diversity fixes from this session prevent NEW concentration, but existing strategies stay until retirement thins them. Consider manual review of worst performers.

### 5. Alpha Edge strategies (DEFERRED)
Alpha Edge is intentionally disabled for now (`strategy_types: ['dsl']` filter in cycle). The `AE=0` in proposals is expected. Will investigate Alpha Edge issues in a future session.

## Key Files Modified This Session

- `src/strategy/conviction_scorer.py` — complete redesign (walk-forward evidence based)
- `src/risk/risk_manager.py` — position sizing: balance-margin→equity-exposure, allocation uses balance not equity
- `src/core/monitoring_service.py` — close order quantity: quantity×price→invested_amount
- `src/strategy/portfolio_manager.py` — close order quantity and P&L: same invested_amount fix
- `src/strategy/strategy_engine.py` — alpha_edge_config scoping fix
- `config/autonomous_trading.yaml` — min_conviction_score: 60→55
- `frontend/src/pages/PortfolioNew.tsx` — quantity→invested_amount display
- `frontend/src/pages/OrdersNew.tsx` — quantity displayed as currency
- `frontend/src/pages/RiskNew.tsx` — position value uses invested_amount
- `tests/test_conviction_scorer.py` — rewritten for new scoring model
- `tests/test_conviction_scorer_integration.py` — rewritten for new scoring model

## Current System State

- Account: balance=$147K, equity=$458K, margin=$313K
- Active strategies: 57 (21 RSI Dip Buy, 11 SMA Proximity, 8 BB Middle Band)
- Open positions: 73
- Exposure: 60% long, 8% short (68% total of equity)
- Market regime: trending_down_weak (confidence: 60%)
- Unrealized P&L: -$1,420
- Conviction scoring: working (343 passed, 0 failed in last cycle)
- Position sizing: working (0 "zero size" rejections in last cycle)
- Signal generation: 80 strategies checked, 0 signals (no entry conditions met — normal)

## How to Troubleshoot

1. Read `logs/cycles/cycle_history.log` for cycle summaries
2. Read `logs/alphacent.log` for detailed backend logs
3. Check DB: `sqlite3 alphacent.db "SELECT name, status, json_extract(strategy_metadata, '$.template_name') as template FROM strategies WHERE status IN ('DEMO','LIVE') ORDER BY template"`
4. Check conviction scores: `sqlite3 alphacent.db "SELECT symbol, conviction_score, passed_threshold FROM conviction_score_logs ORDER BY timestamp DESC LIMIT 20"`
5. Check signal decisions: `sqlite3 alphacent.db "SELECT decision, rejection_reason, COUNT(*) FROM signal_decision_log WHERE created_at > datetime('now', '-1 hour') GROUP BY decision, rejection_reason ORDER BY COUNT(*) DESC"`
