# Alpha Edge Pipeline Audit Report

## Executive Summary

Alpha Edge (AE) strategies are currently disabled (`strategy_types: ['dsl']` filter at the API/cycle level). The previous spec (`alpha-edge-improvements`) fixed individual template issues — real earnings surprise data, insider trading integration, quarterly key-metrics, sector rotation, dividend aristocrat overtrading, rejection blacklist, and improved symbol scoring. Most implementation tasks are complete (6 of 9 fully done, 3 remaining are test-only tasks).

This audit examines the full end-to-end pipeline against institutional standards to determine what's needed before AE can be safely re-enabled alongside DSL strategies.

---

## Pipeline Architecture (Current State)

```
┌──────────────────────┐
│ 1. PROPOSAL           │  StrategyProposer.generate_strategies_from_templates()
│    - 13 AE templates  │  Scored by regime, fundamentals, blacklists
│    - 5 slots reserved │  Separate from DSL pool (force-added)
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ 2. BACKTEST           │  StrategyEngine._backtest_alpha_edge_strategy()
│    - FMP quarterly    │  12 quarters of fundamental data
│    - Price-proxy      │  Fallback when FMP unavailable
│    - Announcement     │  Look-ahead bias prevention
│      date alignment   │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ 3. WALK-FORWARD       │  Same WF validator as DSL
│    - 365d train       │  Direction-aware thresholds
│    - 180d test        │  min_trades_alpha_edge: 2
│    - Sharpe ≥ 0.4     │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ 4. ACTIVATION         │  AutonomousStrategyManager._evaluate_and_activate()
│    - Fundamental      │  FundamentalFilter (3/5 checks)
│      filter           │  Rejection blacklist tracking
│    - Similarity check │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ 5. SIGNAL GEN         │  StrategyEngine._generate_alpha_edge_signal()
│    - Template-specific│  14 handler methods
│      handlers         │  FMP live data for each
│    - Exit management  │  Profit target / stop loss / hold period
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ 6. EXECUTION          │  OrderExecutor
│    - ATR floor check  │  Same as DSL
│    - eToro API        │
└──────────────────────┘
```

---

## Template Inventory (13 Active AE Templates)

| # | Template | Direction | FMP Data Used | Backtest Method | Status |
|---|----------|-----------|---------------|-----------------|--------|
| 1 | Earnings Momentum | LONG | Analyst estimates, earnings surprise | FMP quarterly + announcement dates | ✅ Fixed (real surprise data) |
| 2 | Sector Rotation | LONG | Sector performance, ETF prices | FMP sector data + ETF fallback | ✅ Fixed (real sector data) |
| 3 | Quality Mean Reversion | LONG | Quarterly ROE, D/E, key-metrics | FMP quarterly + RSI technical | ✅ Fixed (quarterly granularity) |
| 4 | Earnings Miss Momentum Short | SHORT | Earnings surprise (negative) | FMP quarterly | ✅ Inherits fix from #1 |
| 5 | Sector Rotation Short | SHORT | Sector performance (negative) | FMP sector data | ✅ Inherits fix from #2 |
| 6 | Quality Deterioration Short | SHORT | ROE declining, D/E rising | FMP quarterly | ⚠️ Needs review |
| 7 | Dividend Aristocrat | LONG | Dividend yield, ROE | FMP quarterly + technical confirmation | ✅ Fixed (180d spacing, pullback) |
| 8 | Insider Buying | LONG | Insider trading (net purchases) | FMP insider endpoint | ✅ Fixed (real insider data) |
| 9 | Revenue Acceleration | LONG | Quarterly revenue growth | FMP quarterly | ⚠️ Simple — just rev_growth > 2% |
| 10 | Relative Value | LONG/SHORT | P/E ratio | FMP quarterly | ⚠️ Single-metric valuation |
| 11 | End-of-Month Momentum | LONG | None (price-only) | Calendar-based | ❌ Disabled (insufficient data) |
| 12 | Pairs Trading | NEUTRAL | None (price-only) | Correlation-based | ⚠️ No fundamental edge |
| 13 | Analyst Revision Momentum | LONG | Analyst estimates | FMP analyst estimates | ⚠️ Needs validation |
| 14 | Share Buyback Momentum | LONG | Shares outstanding change | FMP quarterly | ⚠️ Needs validation |

---

## Issue-by-Issue Analysis

### ISSUE 1: Backtest Quality — Price-Proxy Fallback Is Too Generous

When FMP data is unavailable (rate limit, missing data, non-covered symbol), the system falls back to price-proxy simulations. These use technical patterns (e.g., 3% daily move = "earnings event") that have nothing to do with fundamentals. A strategy that passes WF on price-proxy data may fail completely on real fundamental signals.

**Impact**: Strategies can be activated based on fake fundamental signals.
**Institutional standard**: No fallback — if fundamental data isn't available, the strategy shouldn't be proposed for that symbol.

### ISSUE 2: Walk-Forward Validation Uses Same Thresholds as DSL

AE strategies have `min_trades_alpha_edge: 2` (vs DSL's 4-5), but otherwise use the same WF thresholds (Sharpe ≥ 0.4, win rate ≥ 45%). With only 2 trades in a 180-day test window, statistical significance is essentially zero. A hedge fund would require 20+ trades minimum for any statistical confidence.

**Impact**: AE strategies pass WF with 2 lucky trades.
**Institutional standard**: Either require more trades (longer backtest window) or use different validation criteria for low-frequency strategies (e.g., information ratio, hit rate on fundamental signals).

### ISSUE 3: Revenue Acceleration Entry Is Too Loose

The `revenue_acceleration` branch enters on `rev_growth > 0.02` (2% YoY). That's barely above noise for most companies. The template description says "3 consecutive quarters of accelerating growth" but the backtest only checks single-quarter growth.

**Impact**: Enters on nearly any company with positive revenue growth.
**Institutional standard**: Require acceleration (Q3 growth > Q2 growth > Q1 growth), not just positive growth.

### ISSUE 4: Relative Value Uses Single P/E Metric

The template description mentions "P/E, P/S, EV/EBITDA" but the backtest only checks P/E. A P/E < 18 threshold is arbitrary and doesn't account for sector norms (tech P/E of 18 is cheap, utility P/E of 18 is expensive).

**Impact**: Enters on any stock with P/E < 18 regardless of sector context.
**Institutional standard**: Compare to sector median, use composite valuation score (P/E + P/S + EV/EBITDA), require discount > 1 standard deviation from sector mean.

### ISSUE 5: Quality Deterioration Short Lacks Trend Confirmation

The backtest enters SHORT when ROE is declining and RSI > 75. But RSI > 75 in a strong uptrend is normal — the stock may continue higher. No trend filter means shorting into momentum.

**Impact**: Shorts strong stocks that happen to have slightly declining ROE.
**Institutional standard**: Require price below SMA(200) or declining SMA(50) as trend confirmation before shorting on fundamental deterioration.

### ISSUE 6: Pairs Trading Has No Fundamental Edge

Pairs Trading is purely statistical (correlation + z-score). It's labeled "Alpha Edge" but uses zero fundamental data. It doesn't belong in the AE pipeline — it's a statistical arbitrage strategy.

**Impact**: Misclassified, consumes AE proposal slots.
**Recommendation**: Move to DSL pipeline or create a separate "statistical" category.

### ISSUE 7: End-of-Month Momentum Is Disabled But Still Occupies a Template Slot

Marked `disabled: True` with reason "insufficient_fundamental_data". It's a calendar effect strategy with no fundamental component. Should either be reclassified or removed from AE.

### ISSUE 8: Analyst Revision Momentum — Untested Signal Logic

The `_handle_analyst_revision_momentum` handler tracks consecutive upward revisions using FMP analyst estimates. The logic looks sound conceptually but hasn't been validated against real data. The backtest simulation in `_simulate_alpha_edge_with_fundamentals` tracks `prev_analyst_est` and `analyst_consecutive_up` state across quarters.

**Risk**: FMP analyst estimate data may not have sufficient history or granularity for reliable backtesting.

### ISSUE 9: Share Buyback — Weak Signal

Enters when shares outstanding decreased > 1% YoY. This is a well-known factor but the implementation only checks a single data point. No verification of whether the buyback is ongoing vs. one-time, and no check on buyback yield relative to market cap.

### ISSUE 10: FMP API Rate Limiting During Proposal Scoring

The improved AE symbol scoring (Task 7 from previous spec) fetches quarterly data and insider data for each symbol during scoring. With 75+ stock symbols and 13 AE templates, this could generate hundreds of FMP calls during a single proposal phase. The 24h cache helps but cold-start cycles will be slow.

**Impact**: First cycle after restart could take 10+ minutes just for AE scoring.
**Mitigation**: Cache warming step already exists but may not cover all AE-specific endpoints.

### ISSUE 11: No Position-Level Risk Management for AE

AE strategies use template-level stop loss / profit target / hold period. There's no portfolio-level risk management specific to AE — no max AE exposure, no correlation check between AE positions, no sector concentration limit within AE.

**Config exists**: `alpha_edge.max_active_strategies: 10` — but this is just a count limit, not risk-aware.

### ISSUE 12: Fundamental Monitoring Is Configured But Unclear Integration

```yaml
fundamental_monitoring:
  enabled: true
  check_interval_hours: 24
  earnings_miss_threshold: -0.05
  revenue_decline_exit: true
  sector_rotation_exit: true
```

This config exists but it's unclear if the monitoring service actually checks these conditions for open AE positions and triggers exits. The signal generation handlers have their own exit logic — are these redundant or complementary?

---

## What Works Well

1. **Earnings surprise computation** — Real analyst estimates from FMP `/analyst-estimates` with sequential fallback. Source tagging for auditability.
2. **Insider trading integration** — Real FMP `/insider-trading` data with net purchase aggregation and 24h cache.
3. **Look-ahead bias prevention** — Backtest uses announcement dates (not quarter-end dates) for entry timing.
4. **Rejection blacklist** — Prevents wasting proposal slots on repeatedly-rejected combos. Persisted to disk with cooldown.
5. **Fundamental filter** — 5-check system (profitable, growing, valuation, dilution, insider) with configurable minimum.
6. **ATR-based stop loss floor** — Prevents forex-calibrated stops on high-ATR stocks.
7. **Quarterly key-metrics** — ROE/D/E at quarterly granularity instead of annual interpolation.

---

## Recommendations (Prioritized) — ALL IMPLEMENTED

### P0 — Must Fix Before Re-enabling ✅

1. **Eliminate price-proxy fallback for AE backtests** ✅ — If FMP data unavailable, backtest returns zero results instead of faking signals with price patterns. (`strategy_engine.py`)
2. **Raise min_trades for AE walk-forward** ✅ — Changed `min_trades_alpha_edge` from 2 to 4 in config. (`autonomous_trading.yaml`)
3. **Fix Revenue Acceleration** ✅ — Now requires actual acceleration (Q-over-Q growth increasing), not just positive growth. Tracks `prev_rev_growth_for_accel` across quarters. (`strategy_engine.py`)
4. **Fix Relative Value** ✅ — Now uses sector-relative P/E comparison (ratio to sector median) instead of absolute P/E < 18 threshold. Fetches sector from FMP profile. (`strategy_engine.py`)

### P1 — Should Fix Before Re-enabling ✅

5. **Add trend confirmation to Quality Deterioration Short** ✅ — Requires price below SMA(200) or declining SMA(50) before shorting. (`strategy_engine.py`)
6. **Reclassify non-fundamental templates** ✅ — Pairs Trading and End-of-Month Momentum moved from `alpha_edge` to `statistical` category. Removed `alpha_edge_bypass` flag. (`strategy_templates.py`)
7. **Validate Analyst Revision Momentum** ✅ — Tightened: requires 2+ consecutive upward revisions (was 1) and 5% minimum revision (was 3%). Resets base on downward revision. (`strategy_engine.py`)
8. **Validate Share Buyback** ✅ — Added market cap > $1B check to ensure buyback is meaningful. (`strategy_engine.py`)

### P2 — Improve After Re-enabling ✅

9. **AE-specific portfolio risk limits** ✅ — Added `portfolio_risk` config section (max sector exposure 40%, max correlated positions 3). Added per-template concentration limit (max 2 strategies per AE template type) in proposer. (`autonomous_trading.yaml`, `strategy_proposer.py`)
10. **Clarify fundamental monitoring integration** ✅ — Confirmed monitoring service already checks earnings miss, revenue decline, and sector rotation for open positions daily. Added clarifying comments to config. (`autonomous_trading.yaml`)
11. **Optimize FMP cache warming for AE endpoints** ✅ — Added sector performance pre-warm (once per cycle) and historical fundamentals pre-warm (per stock symbol) to cache warmer. (`fmp_cache_warmer.py`)
12. **Add AE-specific performance tracking** ✅ — Cycle stats now track AE vs DSL active count and avg Sharpe separately. Logged per cycle. (`autonomous_strategy_manager.py`)

---

## Current Config State

```yaml
alpha_edge:
  max_active_strategies: 10
  min_conviction_score: 55
  min_holding_period_days: 3
  max_holding_period_days: 30
  max_trades_per_strategy_per_month: 4
  allow_multiple_positions_per_symbol: false
```

Activation thresholds:
```yaml
min_trades_alpha_edge: 2    # ← Too low
min_sharpe: 0.4             # ← Same as DSL
min_win_rate: 0.45          # ← Same as DSL
```

---

## Files Involved

| File | Role |
|------|------|
| `src/strategy/strategy_templates.py` | 13 AE template definitions |
| `src/strategy/strategy_engine.py` | AE backtest + signal generation (14 handlers) |
| `src/data/fundamental_data_provider.py` | FMP API integration |
| `src/strategy/strategy_proposer.py` | AE scoring, blacklists, proposal logic |
| `src/strategy/autonomous_strategy_manager.py` | Cycle orchestration |
| `src/strategy/fundamental_filter.py` | Fundamental quality checks |
| `config/autonomous_trading.yaml` | All AE configuration |
