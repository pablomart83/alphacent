# AlphaCent Trading System — Session Continuation Prompt

Read #File:.kiro/steering/trading-system-context.md for full system context, then read this prompt carefully before proceeding.

## What Was Done This Session (April 7, 2026)

### Critical Math/Calculation Bugs Fixed

1. **Fee double-counting in backtest** (`src/strategy/strategy_engine.py`)
   - vectorbt `fees=0.001` was hardcoded AND manual commission/slippage/spread were deducted separately → returns hit twice
   - Fixed: `fees=0.0` in vectorbt, all costs handled by manual per-asset-class model

2. **Hourly Sharpe underestimated ~2.6x** (`src/strategy/strategy_engine.py`)
   - `freq="1D"` on hourly bars made vectorbt annualize by sqrt(252) instead of sqrt(1764)
   - Fixed: pass actual interval as freq, correct annualization per asset class (stocks=1764h/yr, crypto=8760h/yr, forex=6240h/yr)

3. **Transaction costs used wrong cost model** (`src/strategy/strategy_engine.py`, `src/strategy/portfolio_manager.py`, `config/autonomous_trading.yaml`)
   - Global 0.1% commission applied to all assets — eToro charges 0% on stocks/ETFs
   - Fixed: per-asset-class costs in config (`backtest.transaction_costs.per_asset_class`), loaded in both backtest engine and activation check

4. **`avg_loss` dollar/percentage unit confusion** (`src/strategy/portfolio_manager.py`, `src/strategy/autonomous_strategy_manager.py`)
   - Retirement trigger compared dollar avg_loss against percentage stop_loss using heuristic (`< 1.0 = pct, >= 1.0 = dollars`)
   - This falsely retired a strategy with Sharpe 2.27 and 12% return (showed "avg loss 2442% > 12%")
   - Fixed: always convert dollars to percentage using actual trade size from vectorbt

5. **Risk manager used cash balance instead of equity** (`src/risk/risk_manager.py`, `src/strategy/autonomous_strategy_manager.py`, `src/core/trading_scheduler.py`)
   - All exposure calculations used `account.balance` ($213K cash) instead of `account.equity` ($462K total)
   - System thought exposure was 117% when it was actually 54% → blocked ALL new orders
   - Fixed in 8 places: calculate_position_size, check_exposure_limits, check_position_limits, check_symbol_concentration, check_directional_balance, check_circuit_breaker, cycle log display, allocation budget, batch limit

6. **`max_exposure_pct` was 50%** (`src/models/dataclasses.py`)
   - Changed to 90% — 50% meant you could never deploy more than half your capital

7. **Transaction cost position size assumption** (`src/strategy/strategy_engine.py`)
   - Used fixed `init_cash * 0.1` instead of actual ATR-based position sizes
   - Fixed: use mean of actual entry position sizes

8. **`transaction_costs_pct` hardcoded divisor** — divided by literal 100000 instead of computed variable

9. **`interval` not passed to `_run_vectorbt_backtest`** — would have crashed on first hourly backtest after freq fix

### Strategy Diversity Fixes

10. **Overfitting detection too aggressive** (`src/strategy/strategy_engine.py`)
    - Strategies with test Sharpe >= 0.3 but high degradation from train were killed
    - Fixed: if test Sharpe >= 0.3, not overfitted (train was just unusually strong)

11. **WF pass required both train AND test Sharpe above threshold** (`src/strategy/strategy_proposer.py`)
    - Fixed: "test-dominant" path accepts train >= -0.1 with test >= min_sharpe

12. **Zero-trade blacklist was permanent** (`src/strategy/strategy_proposer.py`)
    - Fixed: entries expire after 7 days

13. **Performance feedback loop too aggressive** (`src/strategy/strategy_proposer.py`, `config/autonomous_trading.yaml`)
    - max_weight 2.0 → 1.3, min_weight 0.3 → 0.5, dampened scaling formula

14. **Soft diversity nudge in proposal scoring** (`src/strategy/strategy_proposer.py`)
    - Templates with >5 active strategies get mild score reduction (10% per excess)

15. **Close order quantity bug for crypto** (`src/strategy/portfolio_manager.py`)
    - Used `position.quantity` (can be units) instead of `invested_amount` (always dollars)
    - Caused $15.3M phantom quantity in orders table for ETH close

### Config Changes (`config/autonomous_trading.yaml`)

- `activation_thresholds.min_trades_dsl`: 3 → 4
- `activation_thresholds.min_trades_dsl_1h`: 5 (new)
- `activation_thresholds.min_trades_dsl_4h`: 3 (new)
- `activation_thresholds.min_return_per_trade`: per-asset-class (new)
- `backtest.transaction_costs.per_asset_class`: per-asset-class costs (new, zero commission for all)
- `performance_feedback.max_weight_adjustment`: 2.0 → 1.3
- `performance_feedback.min_weight_adjustment`: 0.3 → 0.5

### Cycle Log Cleanup

- Trimmed `logs/cycles/cycle_history.log` from 32K to 3.7K lines (April only)
- Cycle logger now auto-trims to last 10 cycles (`src/core/cycle_logger.py`)
- Old data backed up at `logs/cycles/cycle_history.log.pre_april_backup`

## What Still Needs Investigation / Doing

### 1. Orders Page — Entry vs Close identification
The Orders page doesn't distinguish between new entry orders and close/retirement orders. The SNAP and ETH orders from strategy retirement show as regular BUY/SELL with truncated strategy IDs. Need to add an "Action" column (Entry / Close / Retirement) to the frontend orders table.
- Files: `frontend/src/pages/OrdersNew.tsx`, possibly `src/api/routers/orders.py`
- The backend already has context: close orders from `_close_strategy_positions` could set metadata like `{"order_type": "close", "reason": "strategy_retired"}`

### 2. Conviction scoring blocking signals
Min conviction threshold is 60 (`alpha_edge.min_conviction_score`). ETF signals (XLK, IWM, VTI) score 55.5 (signal: 25.5, fundamental: 5.0, regime: 25.0) and get killed. This blocks a lot of valid signals. Consider:
- Lowering to 50
- Or making it asset-class-aware (ETFs don't have strong fundamental scores by nature)

### 3. Verify the fixes are working in production
Run a full autonomous cycle and check:
- Are hourly strategies getting correct Sharpe ratios now? (should be ~2.6x higher than before)
- Are transaction costs realistic? (stocks should show ~0.06% round trip, not 0.2%)
- Is the risk manager allowing new orders? (exposure should be calculated against equity)
- Are diverse templates getting activated? (not just RSI Dip Buy and BB Middle Band Bounce)
- Check `logs/cycles/cycle_history.log` for the new cycle results

### 4. Portfolio concentration from before fixes
You still have 90 active strategies dominated by 5 templates (20 RSI Dip Buy, 17 BB Middle Band Bounce, 13 SMA Proximity Entry). These were activated before the diversity fixes. They won't be retired unless they underperform. Consider:
- Running a manual review of the worst performers
- The retirement system should naturally thin them over time

### 5. Stop-loss effectiveness audit
The false retirement of the ETH strategy (Sharpe 2.27, 12% return) was caused by the avg_loss unit bug, now fixed. But worth verifying:
- Are stops actually being pushed to eToro? (trailing stop rate limiting: 1 update per 5 min per position)
- Are stop prices correct for SHORT positions? (SL should be above entry, not below)
- Check `_check_trailing_stops` in `src/core/monitoring_service.py`

### 6. Alpha Edge strategies not being proposed
Recent cycles show `AE=0` in proposals. The `_filter_templates_by_macro_regime` force-adds Alpha Edge templates, but they might be getting filtered by the active strategy dedup check. Worth investigating why no AE strategies are being proposed.

## Key Files Modified This Session

- `src/strategy/strategy_engine.py` — backtest fees, Sharpe annualization, interval passing, cost model, overfitting detection
- `src/strategy/portfolio_manager.py` — activation cost check, avg_loss unit fix, close order quantity, min_trades
- `src/risk/risk_manager.py` — balance→equity in 6 methods, max_exposure_pct
- `src/strategy/autonomous_strategy_manager.py` — template cap removed, avg_loss fix, exposure display, budget calc
- `src/strategy/strategy_proposer.py` — WF pass criteria, feedback dampening, diversity nudge, blacklist expiry
- `src/core/cycle_logger.py` — cycle-count-based rotation
- `src/core/trading_scheduler.py` — batch limit equity fix
- `src/models/dataclasses.py` — max_exposure_pct 50%→90%
- `config/autonomous_trading.yaml` — per-asset-class costs, min_trades, feedback dampening

## How to Troubleshoot

1. Read `logs/cycles/cycle_history.log` for cycle summaries
2. Read `logs/alphacent.log` for detailed backend logs (grep for specific strategies/symbols)
3. Check DB: `sqlite3 alphacent.db "SELECT name, status, json_extract(performance, '$.sharpe_ratio') as sharpe FROM strategies WHERE status IN ('DEMO','LIVE') ORDER BY sharpe DESC LIMIT 20"`
4. Check active strategy template distribution: see the Python snippet used in this session (queries strategies table, groups by template_name from metadata)
