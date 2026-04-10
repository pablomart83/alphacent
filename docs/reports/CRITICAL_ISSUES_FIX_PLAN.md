2E test again
2. Verify no duplicate orders created
3. Verify fundamental filter pass rate 60-80%
4. Verify Alpha Edge strategies generated
5. Monitor for 24 hours before production deployment

---

## Success Criteria

- ✅ No duplicate orders for same symbol (max 3 strategies per symbol)
- ✅ Fundamental filter pass rate 60-80%
- ✅ Alpha Edge strategies represent 40% of active strategies
- ✅ All E2E tests pass consistently
- ✅ Production readiness score >95/100
0-day TTL instead of 24h)

### Implementation
- Upgrade FMP subscription
- Update fallback logic in `src/data/fundamental_data_provider.py`
- Increase cache TTL in config

---

## Priority Order

1. 🔴 **CRITICAL** - Issue #1: Fix order duplication bug (immediate)
2. 🔴 **CRITICAL** - Issue #2: Fix fundamental filter (immediate)
3. 🟡 **HIGH** - Issue #3: Add Alpha Edge strategies (1-2 days)
4. 🟡 **MEDIUM** - Issue #4: Upgrade FMP tier (optional, can work around)

---

## Testing Plan

After fixes:
1. Run Eals.extend(additional_proposals)
```

---

## Issue #4: FMP API Free Tier Limitations (MEDIUM)

### Problem
- FMP free tier returns 404 for earnings calendar
- FMP free tier returns 402 (Payment Required) for some fundamental data
- Fallback to Alpha Vantage working but not comprehensive

### Fix Required
1. **Upgrade to FMP paid tier** ($15/month for 750 calls/day)
2. **Improve Alpha Vantage fallback** coverage
3. **Add Yahoo Finance** as additional fallback for fundamental data
4. **Cache more aggressively** (3for p in proposals 
    if p.metadata.get('strategy_category') == 'alpha_edge'
]

if len(alpha_edge_proposals) < MIN_ALPHA_EDGE_STRATEGIES:
    logger.warning(
        f"Only {len(alpha_edge_proposals)} Alpha Edge strategies proposed, "
        f"generating more to meet minimum of {MIN_ALPHA_EDGE_STRATEGIES}"
    )
    # Generate additional Alpha Edge strategies
    additional_proposals = self._generate_alpha_edge_strategies(
        count=MIN_ALPHA_EDGE_STRATEGIES - len(alpha_edge_proposals)
    )
    proposed only template-based technical strategies. Alpha Edge strategies were not proposed in this cycle.

### Fix Required
1. **Ensure Alpha Edge templates are included** in proposal generation
2. **Set minimum Alpha Edge strategy count** (e.g., 2 out of 10)
3. **Increase proposal count** to ensure diverse coverage

### Implementation
Update `src/strategy/autonomous_strategy_manager.py`:
```python
# In propose_strategies():
# After generating proposals, ensure Alpha Edge representation

alpha_edge_proposals = [
    p ks when data is unavailable
- Add strategy-type-aware P/E thresholds
- Log which checks passed/failed/skipped

---

## Issue #3: Missing Alpha Edge Strategies (HIGH)

### Problem
- Current distribution: 100% template-based, 0% alpha edge
- Target distribution: 60% template, 40% alpha edge
- Missing strategies:
  - Earnings Momentum (small-cap post-earnings drift)
  - Sector Rotation (regime-based ETF rotation)
  - Quality Mean Reversion (high-quality oversold stocks)

### Root Cause
The autonomous cycle generat
Update `config/autonomous_trading.yaml`:
```yaml
alpha_edge:
  fundamental_filters:
    enabled: true
    min_checks_passed: 3  # Changed from 4
    treat_missing_as_neutral: true  # New flag
    checks:
      profitable: true
      growing: true
      reasonable_valuation: true
      no_dilution: true
      insider_buying: true
    valuation_thresholds:
      momentum: null  # Skip P/E check
      growth: 60
      value: 25
      default: 30
```

Update `src/strategy/fundamental_filter.py`:
- Add logic to skip chec available: 142 times
   - P/E ratio data not available: 142 times

2. **Too strict thresholds**:
   - P/E < 30 may be too strict for growth stocks
   - Treating "data not available" as failure

### Fix Required
1. **Reduce required checks**: 4/5 → 3/5
2. **Soft failures**: Treat "data not available" as neutral (don't count against pass rate)
3. **Adjust P/E thresholds by strategy type**:
   - Momentum strategies: Skip P/E check
   - Growth strategies: P/E < 60
   - Value strategies: P/E < 25

### Implementationpending orders for {symbol}, "
            f"filtering {len(signal_list)} new signal(s)"
        )
        continue  # Skip all signals for this symbol
```

---

## Issue #2: Fundamental Filter Too Strict (CRITICAL)

### Problem
- Fundamental filter requires 4/5 checks to pass
- Current pass rate: **0.0%** (162 symbols filtered, 0 passed)
- Blocking ALL signals from execution

### Root Cause
1. **Data unavailability** (FMP free tier limitations):
   - Revenue growth data not available: 162 times
   - EPS data not) + 1

# Filter signals that would exceed symbol limit
MAX_STRATEGIES_PER_SYMBOL = 3  # From risk config
for (symbol, direction), signal_list in signals_by_symbol_direction.items():
    current_count = orders_per_symbol.get(symbol, 0)
    if current_count >= MAX_STRATEGIES_PER_SYMBOL:
        logger.warning(
            f"Symbol limit reached: {current_count} ng**:
   - Alert when multiple strategies target same symbol
   - Dashboard showing orders per symbol

### Implementation
```python
# In _coordinate_signals(), after checking pending orders per strategy:

# Check symbol-level limits (across all strategies)
orders_per_symbol = {}  # symbol -> count of pending orders
for order in pending_orders:
    if order.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED]:
        symbol = order.symbol
        orders_per_symbol[symbol] = orders_per_symbol.get(symbol, 0es to create orders for the same symbol
- ❌ Doesn't enforce max strategies per symbol limit (configured as 3)

### Fix Required
1. **Add symbol-level duplicate check** in `_coordinate_signals()`:
   - Count total pending orders per symbol (across all strategies)
   - Enforce `max_strategies_per_symbol` limit (default: 3)
   - Log when limit is reached

2. **Clean up existing duplicate orders**:
   - Cancel the 2 stuck SUBMITTED orders for GE
   - They've been pending since Feb 22 and won't fill

3. **Add monitori - 1631 shares
  2. RSI Overbought Short Ranging GE V1 (DEMO) - 3000 shares
- 5 closed GE positions (old, from eToro sync)

eToro:
- 0 GE positions (live)
```

### Root Cause
The `_coordinate_signals()` method checks pending orders by `(strategy_id, symbol, side)`, which:
- ✅ Prevents duplicates within the same strategy
- ❌ Allows different strategiFollow-up

**Date:** February 22, 2026  
**Status:** 🔴 CRITICAL - Requires immediate fixes before production

---

## Issue #1: Order Duplication Bug (CRITICAL)

### Problem
The E2E test created duplicate pending orders for GE:
- 2 existing SUBMITTED orders for GE (from different strategies)
- E2E test created a 3rd order for GE
- Duplication prevention failed to catch this

### Current State
```
Database:
- 0 open GE positions
- 2 pending/submitted GE orders:
  1. RSI Overbought Short Ranging GE V27 (RETIRED)# Critical Issues Fix Plan
## Production Readiness Task 12.1 