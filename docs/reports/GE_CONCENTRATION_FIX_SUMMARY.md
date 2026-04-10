
# GE Concentration Issue - Fixes Implemented

**Date**: February 23, 2026

## Summary

Successfully addressed GE strategy concentration issue through:
1. Retired 4 redundant strategies (7 → 3 strategies)
2. Identified P&L calculation issue
3. Verified concentration limit configuration
4. Documented safeguard implementations

---

## 1. Strategies Retired

### Duplicate Strategy
- **BB Upper Band Short Ranging GE BB(15,1.5) V41** (ID: c95a6c38...)
  - Reason: Exact duplicate name

### Redundant RSI Strategies (Kept V10 only)
- **RSI Overbought Short Ranging GE V26** (ID: 13149bf4...)
- **RSI Overbought Short Ranging GE V34** (ID: 84f2ab6e...)
- **RSI Overbought Short Ranging GE V43** (ID: f0b0b7e5...)

### Result
- GE concentration: 36.8% → 20.0%
- Still slightly above 15% target but much improved
- Remaining strategies:
  1. RSI Overbought Short Ranging GE V10
  2. BB Upper Band Short Ranging GE BB(15,1.5) V41
  3. BB Upper Band Short Ranging GE BB(20,2.0) V37

---

## 2. P&L Calculation Issue

### Problem Identified
All closed GE positions show:
- Realized P&L: 0 or None
- Entry price == Current price
- No P&L calculation on close

### Root Causes (Suspected)
1. current_price not updated from eToro on position close
2. P&L calculation not triggered on close event
3. Positions closed immediately after opening (test data)

### Recommendation
Review position close handler in:
- `src/execution/position_manager.py`
- `src/core/order_monitor.py`

Ensure:
1. Fetch final price from eToro before closing
2. Calculate realized P&L: (exit_price - entry_price) / entry_price
3. Update position.realized_pnl field
4. Update position.current_price to exit price

---

## 3. Concentration Limits Configuration

### Current Settings
```python
# src/models/dataclasses.py
max_symbol_exposure_pct: float = 0.15  # 15% max
max_strategies_per_symbol: int = 3     # 3 strategies max
```

### Enforcement Locations
1. **Risk Manager** (`src/risk/risk_manager.py`)
   - Checks during signal validation
   - Prevents orders if limits exceeded

2. **Trading Scheduler** (`src/core/trading_scheduler.py`)
   - Filters signals during coordination
   - Hardcoded MAX_STRATEGIES_PER_SYMBOL = 3

3. **Strategy Activation** (NEW - needs implementation)
   - Should check before activating strategy
   - Prevent activation if would exceed limits

### Current Concentration Status
After retirement:
- GE: 3 strategies (20.0%) - ⚠️ Still above 15%
- GOLD: 2 strategies (13.3%) - ✅ OK
- GER40: 2 strategies (13.3%) - ✅ OK
- COST: 2 strategies (13.3%) - ✅ OK

---

## 4. Safeguards Implemented/Recommended

### ✅ Implemented
1. **Duplicate Detection in Retirement Script**
   - Identifies strategies with identical names
   - Automatically retires duplicates

2. **Concentration Monitoring**
   - Script to analyze symbol concentration
   - Alerts when limits exceeded

### 📋 Recommended (Not Yet Implemented)

#### A. Pre-Activation Concentration Check
**Location**: `src/strategy/strategy_engine.py` - `activate_strategy()`

**Implementation**: Add check before activating:
```python
# Count active strategies for each symbol
for symbol in strategy.symbols:
    active_count = count_active_strategies_for_symbol(symbol)
    if active_count >= max_strategies_per_symbol:
        raise ValueError(f"Cannot activate: {symbol} limit reached")
```

#### B. Duplicate Name Detection
**Location**: `src/strategy/autonomous_strategy_manager.py`

**Implementation**: Before activation, check for duplicate names:
```python
if strategy_name_exists(strategy.name):
    logger.warning(f"Duplicate name: {strategy.name}")
    # Either skip or append unique suffix
```

#### C. Signal Generation Pause Mechanism
**Options**:
1. Environment variable: `SIGNAL_GENERATION_PAUSED=true`
2. Database flag in system_state table
3. Scheduler pause command

**Use Case**: Pause signal generation during:
- System maintenance
- Strategy analysis
- Database migrations
- Emergency situations

---

## 5. Next Steps

### Immediate (This Week)
1. ✅ Retire redundant GE strategies - DONE
2. ⚠️ Consider retiring 1 more GE strategy to reach 15% target
3. 🔴 Fix P&L calculation on position close
4. 🔴 Implement pre-activation concentration check

### Short-Term (This Month)
1. Add duplicate name detection to strategy proposer
2. Implement signal generation pause mechanism
3. Add unit tests for concentration limits
4. Monitor remaining GE strategies for signal activity

### Medium-Term (Next Quarter)
1. Implement portfolio-level optimization
2. Add strategy correlation analysis
3. Improve backtest-to-live performance tracking
4. Add automated concentration rebalancing

---

## 6. Monitoring

### Daily Checks
- Run `python scripts/analyze_ge_strategy_concentration_simple.py`
- Check for new duplicate strategies
- Monitor signal generation activity

### Weekly Reviews
- Review symbol concentration across all symbols
- Check for strategies with 0 signals in 7+ days
- Verify P&L calculations are working

### Monthly Audits
- Full portfolio concentration analysis
- Strategy performance vs backtest comparison
- Duplicate detection audit

---

## Files Modified
1. `scripts/fix_ge_concentration_issue.py` - Retirement script
2. `scripts/analyze_ge_strategy_concentration_simple.py` - Analysis tool
3. `GE_CONCENTRATION_ANALYSIS_FEB_23_2026.md` - Detailed analysis
4. Database: 4 strategies retired

## Files to Modify (Recommended)
1. `src/strategy/strategy_engine.py` - Add concentration check
2. `src/strategy/autonomous_strategy_manager.py` - Add duplicate detection
3. `src/execution/position_manager.py` - Fix P&L calculation

---

**Report Generated**: February 23, 2026
**Status**: Partial Fix Implemented, Additional Work Recommended
