# Design Document

## Overview

This design addresses 8 requirements to fix broken Alpha Edge backtests, integrate missing FMP endpoints, add a rejection blacklist, improve symbol scoring, and handle the End-of-Month Momentum template. The changes span 4 primary files: `fundamental_data_provider.py`, `strategy_engine.py`, `strategy_proposer.py`, and `autonomous_strategy_manager.py`.

## Architecture

### Component Interaction

```
┌─────────────────────────┐
│  Autonomous_Manager     │
│  (cycle orchestration)  │
│  - rejection tracking   │
│  - disabled template    │
│    logging              │
└──────┬──────────────────┘
       │ proposes / evaluates
       ▼
┌─────────────────────────┐     ┌──────────────────────────────┐
│  Strategy_Proposer      │────▶│  Fundamental_Data_Provider   │
│  - rejection blacklist  │     │  + get_analyst_estimates()   │
│  - improved AE scoring  │     │  + get_insider_trading()     │
│  - template disable     │     │  + get_sector_performance()  │
│    check                │     │  + quarterly key-metrics     │
└──────┬──────────────────┘     └──────────────────────────────┘
       │ backtests
       ▼
┌─────────────────────────┐
│  Strategy_Engine         │
│  - fixed simulations    │
│  - real data in signals │
│  - trade frequency caps │
└─────────────────────────┘
```

### Data Flow for Earnings Surprise Fix

```
FMP /analyst-estimates ──▶ estimated_eps per quarter
FMP /income-statement  ──▶ actual_eps per quarter
                            │
                            ▼
              earnings_surprise = (actual - estimated) / |estimated|
                            │
                            ▼
              Stored in quarterly_data with source tag
                            │
                    ┌───────┴───────┐
                    ▼               ▼
            Backtest simulation   Live signal generation
            (earnings_momentum)   (_check_earnings_momentum_signal)
```

## Detailed Design

### 1. Fundamental_Data_Provider Changes (`fundamental_data_provider.py`)

#### 1a. Real Earnings Surprise via `/analyst-estimates`

Modify `get_historical_fundamentals()`:

- After fetching `/income-statement` (quarterly), add a call to `/analyst-estimates` with `symbol` and `limit=quarters`.
- Build a lookup: `estimates_by_quarter[fiscal_date] = estimated_eps`.
- In the quarterly loop, compute `earnings_surprise = (actual_eps - estimated_eps) / abs(estimated_eps)` when both values exist.
- When estimated_eps is unavailable, fall back to sequential EPS change and set `earnings_surprise_source: "sequential_fallback"`.
- Store `actual_eps` (from income statement) and `estimated_eps` (from analyst estimates) as separate fields.

```python
# New call in get_historical_fundamentals()
analyst_estimates = self._fmp_request("/analyst-estimates", symbol=symbol, limit=quarters)
if analyst_estimates:
    self.fmp_rate_limiter.record_call()

# Build lookup
estimates_by_date = {}
if analyst_estimates:
    for est in analyst_estimates:
        est_date = est.get("date", "")
        est_eps = est.get("estimatedEpsAvg") or est.get("estimatedEps")
        if est_date and est_eps is not None:
            estimates_by_date[est_date] = est_eps

# In quarterly loop, replace surprise computation:
estimated_eps = estimates_by_date.get(date)
if eps is not None and estimated_eps is not None and estimated_eps != 0:
    surprise = (eps - estimated_eps) / abs(estimated_eps)
    surprise_source = "analyst_estimate"
else:
    # Fallback to sequential
    if eps is not None and prev_eps is not None and prev_eps != 0:
        surprise = (eps - prev_eps) / abs(prev_eps)
    surprise_source = "sequential_fallback"
    estimated_eps = prev_eps  # Keep for backward compat
```

API budget: +1 call per symbol per fetch (within 300/min limit).

#### 1b. Insider Trading Endpoint (`get_insider_trading`)

New method:

```python
def get_insider_trading(self, symbol: str, months: int = 6) -> List[Dict[str, Any]]:
    """Fetch insider trading data from FMP /insider-trading endpoint."""
    # Check cache first (TTL: 24h)
    # Call /insider-trading?symbol={symbol}&limit=100
    # Return list of {date, type (buy/sell), shares, price, name, title}

def get_insider_net_purchases(self, symbol: str, lookback_days: int = 90) -> Dict[str, Any]:
    """Aggregate net insider purchases over lookback window."""
    # Calls get_insider_trading, filters by date, sums buys - sells
    # Returns {net_shares, net_value, buy_count, sell_count, last_buy_date}
```

Cache key: `insider_{symbol}`, TTL: 86400s (24h). Stored in `FundamentalDataCache`.

#### 1c. Quarterly Key-Metrics

Modify `get_historical_fundamentals()`:

- Add call to `/key-metrics` with `period=quarter` in addition to the existing annual call.
- Build `quarterly_metrics_by_date` lookup.
- In the quarterly loop, prefer quarterly ROE/D/E over annual when available.
- Tag source: `quality_data_source: "quarterly"` or `"annual_interpolated"`.

```python
quarterly_metrics = self._fmp_request("/key-metrics", symbol=symbol, period="quarter", limit=quarters)
if quarterly_metrics:
    self.fmp_rate_limiter.record_call()

quarterly_metrics_by_date = {}
if quarterly_metrics:
    for m in quarterly_metrics:
        qm_date = m.get("date", "")
        if qm_date:
            quarterly_metrics_by_date[qm_date] = m

# In quarterly loop:
q_metrics = quarterly_metrics_by_date.get(date, {})
roe = q_metrics.get("returnOnEquity") or annual.get("returnOnEquity")
de = q_metrics.get("debtToEquityRatio") or annual.get("debtToEquityRatio")
quality_source = "quarterly" if q_metrics.get("returnOnEquity") else "annual_interpolated"
```

API budget: +1 call per symbol per fetch.

#### 1d. Sector Performance

New method:

```python
def get_sector_performance(self) -> Dict[str, Dict[str, float]]:
    """Fetch sector performance from FMP /stock-price-change or /sector-performance."""
    # Cache key: "sector_performance", TTL: 86400s
    # Returns {sector_name: {1m: pct, 3m: pct, 6m: pct, 1y: pct}}
    # Fallback: compute from sector ETF prices (XLK, XLF, XLE, etc.)
```

### 2. Strategy_Engine Changes (`strategy_engine.py`)

#### 2a. Fix Quality Mean Reversion Simulation

In `_simulate_alpha_edge_with_fundamentals()`, the `quality_mean_reversion` branch:

- Use quarterly ROE/D/E from the new `quality_data_source` field.
- Make RSI threshold configurable (default 45, read from `params.get('rsi_threshold', 45)`).
- Add per-quarter dedup: track `last_qmr_entry_quarter` and skip if same quarter.

```python
elif template_type == 'quality_mean_reversion':
    roe = q.get('roe')
    de = q.get('debt_to_equity')
    rsi_threshold = params.get('rsi_threshold', 45)
    
    # Skip if already entered this quarter
    q_key = q_date[:7]  # YYYY-MM
    if q_key == last_qmr_quarter:
        continue
    
    if roe is not None and roe > params.get('min_roe', 0.15):
        if de is None or de < params.get('max_debt_equity', 0.5):
            # RSI check with configurable threshold
            # ... (existing RSI calculation)
            if rsi < rsi_threshold:
                should_enter = True
                last_qmr_quarter = q_key
```

#### 2b. Fix Sector Rotation Simulation

Replace the price-proxy fallback in `_simulate_alpha_edge_with_fundamentals()`:

- When `template_type == 'sector_rotation'`, call `self._fundamental_data_provider.get_sector_performance()`.
- Rank sectors by 3-month return, enter long on top 3 sector ETFs.
- New dedicated method `_simulate_sector_rotation_with_fundamentals()`.

```python
def _simulate_sector_rotation_with_fundamentals(self, df, params, strategy):
    """Simulate sector rotation using real FMP sector performance data."""
    sector_data = self._fundamental_data_provider.get_sector_performance()
    if not sector_data:
        logger.warning("No sector data from FMP, falling back to price proxy")
        return self._simulate_with_price_proxy('sector_rotation', df, params, strategy)
    
    # Rank by 3-month performance, enter top N
    rebalance_interval = params.get('rebalance_frequency_days', 30)
    top_n = params.get('top_sectors', 3)
    # ... monthly rebalancing logic using sector rankings
```

#### 2c. Fix Dividend Aristocrat Overtrading

In `_simulate_alpha_edge_with_fundamentals()`, the `dividend_aristocrat` branch:

- Track `last_dividend_entry_date` per symbol.
- Enforce 6-month minimum gap between entries.
- Require technical confirmation: pullback >= 5% from 52-week high OR RSI < 40.

```python
elif template_type == 'dividend_aristocrat':
    div_yield = q.get('dividend_yield')
    roe = q.get('roe')
    
    # 6-month cooldown
    if last_div_entry_date and (entry_date - last_div_entry_date).days < 180:
        continue
    
    if div_yield is not None and div_yield > 0.02:
        if roe is None or roe > 0.10:
            # Technical confirmation required
            if entry_idx is not None and entry_idx < len(df):
                high_252 = close.iloc[max(0, entry_idx-252):entry_idx+1].max()
                pullback = (high_252 - close.iloc[entry_idx]) / high_252
                # Also check RSI
                rsi = _calculate_rsi_at(close, entry_idx)
                if pullback >= 0.05 or rsi < 40:
                    should_enter = True
                    last_div_entry_date = entry_date
```

#### 2d. Fix Insider Buying Simulation

Replace `_simulate_insider_buying_trades()` and the insider branch in `_simulate_alpha_edge_with_fundamentals()`:

- Call `self._fundamental_data_provider.get_insider_trading(symbol)`.
- Enter when net insider purchases > threshold in the lookback window.
- Keep volume confirmation from the existing price-proxy simulation.

```python
def _simulate_insider_buying_with_fundamentals(self, df, params, strategy):
    """Simulate insider buying using real FMP insider trading data."""
    symbol = strategy.symbols[0] if strategy and strategy.symbols else None
    if not symbol:
        return []
    
    insider_data = self._fundamental_data_provider.get_insider_trading(symbol)
    if not insider_data:
        return []
    
    # Build date-indexed insider activity
    # Enter when net_purchases > min_net_purchases in lookback window
    # Confirm with volume spike (existing logic)
```

#### 2e. Fix Earnings Momentum Simulation

The existing `earnings_momentum` branch in `_simulate_alpha_edge_with_fundamentals()` already checks `earnings_surprise > 0.05`. With the data fix in 1a, this will now use real analyst estimates instead of sequential EPS change. No simulation logic change needed — the data fix propagates automatically.

### 3. Strategy_Proposer Changes (`strategy_proposer.py`)

#### 3a. Rejection Blacklist

New data structures alongside existing `_zero_trade_blacklist`:

```python
# In __init__:
self._rejection_blacklist: Dict[Tuple[str, str], int] = {}  # (template, symbol) -> consecutive_rejections
self._rejection_blacklist_timestamps: Dict[Tuple[str, str], str] = {}
self._rejection_blacklist_threshold = config.get('rejection_blacklist_threshold', 3)
self._rejection_blacklist_cooldown_days = config.get('rejection_blacklist_cooldown_days', 30)
self._rejection_blacklist_path = "data/rejection_blacklist.json"
```

New methods:

```python
def record_rejection(self, template_name: str, symbol: str) -> None:
    """Increment rejection counter. Called by Autonomous_Manager after activation rejection."""
    key = (template_name, symbol)
    self._rejection_blacklist[key] = self._rejection_blacklist.get(key, 0) + 1
    self._rejection_blacklist_timestamps[key] = datetime.now().isoformat()
    self._save_rejection_blacklist_to_disk()

def reset_rejection(self, template_name: str, symbol: str) -> None:
    """Reset counter on successful activation."""
    key = (template_name, symbol)
    self._rejection_blacklist.pop(key, None)
    self._rejection_blacklist_timestamps.pop(key, None)
    self._save_rejection_blacklist_to_disk()

def is_rejection_blacklisted(self, template_name: str, symbol: str) -> bool:
    """Check if combo is blacklisted (threshold reached and not past cooldown)."""
    key = (template_name, symbol)
    count = self._rejection_blacklist.get(key, 0)
    if count < self._rejection_blacklist_threshold:
        return False
    # Check cooldown
    ts = self._rejection_blacklist_timestamps.get(key)
    if ts:
        age_days = (datetime.now() - datetime.fromisoformat(ts)).days
        if age_days >= self._rejection_blacklist_cooldown_days:
            return False  # Cooldown expired, allow one re-try
    return True
```

Integration in `_score_symbol_for_template()`:

```python
# Add after zero-trade blacklist check:
if self.is_rejection_blacklisted(template.name, symbol):
    return 0.0
```

Persistence: same JSON format as zero-trade blacklist (`_load_rejection_blacklist_from_disk`, `_save_rejection_blacklist_to_disk`).

#### 3b. Improved AE Symbol Scoring

Modify the alpha_edge branch in `_score_symbol_for_template()`:

For Revenue Acceleration:
```python
# Fetch cached quarterly revenue data
quarters = self._get_cached_quarterly_data(symbol)
if quarters and len(quarters) >= 4:
    revenues = [q['revenue'] for q in quarters if q.get('revenue')]
    if revenues:
        cv = np.std(revenues) / np.mean(revenues) if np.mean(revenues) > 0 else 999
        if cv > 0.5:
            alpha_score -= 20  # Inconsistent revenue
        consecutive_growth = sum(1 for i in range(1, len(revenues)) if revenues[i] > revenues[i-1])
        if consecutive_growth >= 3:
            alpha_score += 15  # Strong growth streak
```

For Dividend Aristocrat:
```python
# Check dividend yield and history
fund_data = self._get_cached_fundamental_data(symbol)
if fund_data and fund_data.dividend_yield:
    if fund_data.dividend_yield < 0.015:
        alpha_score -= 25  # Too low yield
    # Check dividend stability from quarterly data
```

For Insider Buying:
```python
# Check recent insider activity
insider_net = self._get_cached_insider_net(symbol)
if insider_net and insider_net.get('buy_count', 0) > 0:
    alpha_score += 15  # Recent insider buying
elif insider_net is not None and insider_net.get('buy_count', 0) == 0:
    alpha_score -= 10  # No insider activity
```

Cache: `_fundamental_scoring_cache` with 24h TTL, populated lazily on first score request per symbol.

#### 3c. Template Disable Check

```python
def _is_template_disabled(self, template: StrategyTemplate) -> Tuple[bool, Optional[str]]:
    """Check if template is disabled due to insufficient data."""
    if template.metadata and template.metadata.get('disabled'):
        return True, template.metadata.get('disable_reason', 'unknown')
    return False, None
```

Integration in `generate_strategies_from_templates()` and `_match_templates_to_symbols()`: skip disabled templates.

### 4. Autonomous_Manager Changes (`autonomous_strategy_manager.py`)

#### 4a. Rejection Tracking

In `_evaluate_and_activate()`, after a strategy is rejected:

```python
if not should_activate:
    # Track rejection for blacklist
    template_name = strategy.metadata.get('template_name', strategy.name) if strategy.metadata else strategy.name
    primary_sym = strategy.symbols[0] if strategy.symbols else 'unknown'
    self.strategy_proposer.record_rejection(template_name, primary_sym)
    # ... existing rejection logging
```

On successful activation:

```python
# Reset rejection counter on success
self.strategy_proposer.reset_rejection(template_name, primary_sym)
```

#### 4b. Disabled Template Logging

In `_propose_strategies()` or at cycle start:

```python
# Log disabled templates once per cycle
for template in all_templates:
    disabled, reason = self.strategy_proposer._is_template_disabled(template)
    if disabled:
        logger.warning(f"Template '{template.name}' is disabled: {reason}")
```

### 5. Configuration Changes (`config/autonomous_trading.yaml`)

```yaml
alpha_edge:
  rejection_blacklist:
    threshold: 3
    cooldown_days: 30
  quality_mean_reversion:
    min_roe: 0.15
    max_debt_equity: 0.5
    rsi_threshold: 45  # NEW: was effectively 50
  dividend_aristocrat:
    min_entry_gap_days: 180  # NEW: 6-month cooldown
    pullback_confirmation_pct: 0.05  # NEW
    rsi_confirmation_threshold: 40  # NEW
  insider_buying:
    min_net_purchases: 3  # NEW: minimum net insider buys
    lookback_days: 90  # NEW
  sector_rotation:
    rebalance_frequency_days: 30
    top_sectors: 3  # NEW
  end_of_month_momentum:
    enabled: true  # Can be set to false to disable
```

## Correctness Properties

### Property 1: Earnings Surprise Computation Correctness
For all quarters where both actual_eps and estimated_eps are non-zero, `earnings_surprise == (actual_eps - estimated_eps) / abs(estimated_eps)`. This is an invariant that must hold regardless of the values.

### Property 2: Insider Net Purchases Aggregation
For any list of insider transactions, `net_shares == sum(buy_shares) - sum(sell_shares)`. This is a metamorphic property: adding a buy transaction increases net_shares by exactly that amount.

### Property 3: Quality Mean Reversion Trade Frequency Cap
For any backtest run of Quality Mean Reversion, `len(trades) <= len(unique_quarters_in_data)`. This is an invariant: at most one trade per quarter.

### Property 4: Sector Ranking Consistency
For any set of sector returns, ranking by 3-month return produces a sorted order where `sector_returns[rank[i]] >= sector_returns[rank[i+1]]` for all i. This is a sort invariant.

### Property 5: Dividend Aristocrat Entry Spacing
For any backtest run of Dividend Aristocrat on a single symbol, for all consecutive trade pairs (t1, t2): `t2.entry_date - t1.entry_date >= 180 days`. This is an invariant.

### Property 6: Rejection Blacklist Persistence Round-Trip
For any rejection blacklist state, `load(save(state)) == state` (excluding expired entries). This is a round-trip property.

### Property 7: Rejection Blacklist Threshold Enforcement
For any (template, symbol) combination with `rejection_count >= threshold` and `age < cooldown_days`, `is_rejection_blacklisted() == True` and `_score_symbol_for_template() == 0.0`. This is an invariant.

### Property 8: Earnings Surprise Source Tagging
For all quarters in the output of `get_historical_fundamentals()`, exactly one of: (a) `earnings_surprise_source == "analyst_estimate"` and `estimated_eps` comes from `/analyst-estimates`, or (b) `earnings_surprise_source == "sequential_fallback"` and `estimated_eps` is the previous quarter's actual EPS. This is a completeness invariant.

### Property 9: No Overlapping Dividend Aristocrat Trades
For any backtest run, there are no two Dividend Aristocrat trades on the same symbol where `t1.exit_date > t2.entry_date`. This is an invariant.

### Property 10: Insider Buying Signal Requires Real Data
After the fix, for any Insider Buying trade in backtest, the trade must have `fundamental_trigger == "insider_buying"` and the insider data source must not be the earnings surprise proxy. This is a metamorphic property: removing insider data should produce zero Insider Buying trades.

## File Changes Summary

| File | Changes |
|------|---------|
| `src/data/fundamental_data_provider.py` | Add `/analyst-estimates` call, `get_insider_trading()`, `get_insider_net_purchases()`, `get_sector_performance()`, quarterly `/key-metrics` call |
| `src/strategy/strategy_engine.py` | Fix QMR simulation (quarterly data, RSI threshold, per-quarter cap), fix Dividend Aristocrat (6-month gap, technical confirmation), fix Insider Buying (real data), fix Sector Rotation (real sector data), update Earnings Momentum (data propagates) |
| `src/strategy/strategy_proposer.py` | Add rejection blacklist (record, reset, check, persist), improve AE symbol scoring (revenue consistency, dividend history, insider activity, earnings recency, ROE availability), add template disable check |
| `src/strategy/autonomous_strategy_manager.py` | Track rejections in `_evaluate_and_activate()`, reset on activation, log disabled templates |
| `config/autonomous_trading.yaml` | Add rejection blacklist config, QMR RSI threshold, Dividend Aristocrat entry gap/confirmation, Insider Buying lookback, Sector Rotation top_sectors, EoM enabled flag |
