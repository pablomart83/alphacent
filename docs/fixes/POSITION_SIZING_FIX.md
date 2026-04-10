# Position Sizing Fix - Strategy Allocation Implementation

## Date: 2026-02-20

## Critical Issues Identified

### 1. Position Sizes Growing Exponentially
**Problem**: Orders were $50K, $36K, $25K, etc. on a $400K account
- This is 12.5%, 9%, 6.25% of total balance per order
- Far too large for a 1% allocated strategy

**Root Cause**: `RiskManager.calculate_position_size()` was calculating based on TOTAL account balance, completely ignoring the strategy's `allocation_percent`.

### 2. Fixed 1% Allocation Not Used
**Problem**: Strategies had `allocation_percent = 1.0%` in database, but this was never used in position sizing calculations.

**Root Cause**: The `validate_signal()` method didn't accept or pass `strategy_allocation_pct` to `calculate_position_size()`.

### 3. Only 2 Symbols Trading
**Problem**: All orders were for NVDA and NKE only
- 21 DEMO strategies active
- Only 2 strategies generating signals

**Root Cause**: Market conditions - only "Ultra Short EMA Momentum" strategies for NVDA and NKE met their entry criteria. This is actually correct behavior (strategies should only trade when conditions are met).

---

## Solution Implemented

### 1. Updated `RiskManager.calculate_position_size()`

**File**: `src/risk/risk_manager.py`

**Changes**:
- Added `strategy_allocation_pct` parameter (default: 1.0%)
- Calculate strategy's allocated capital: `account.balance * (strategy_allocation_pct / 100.0)`
- Track strategy-specific exposure (positions from this strategy only)
- Calculate position size as percentage of STRATEGY'S allocated capital (not total balance)
- Scale from 20% to 100% of strategy allocation based on signal confidence

**Key Logic**:
```python
# Calculate strategy's allocated capital
strategy_allocated_capital = account.balance * (strategy_allocation_pct / 100.0)

# Calculate current exposure for THIS strategy
strategy_current_exposure = sum(
    self._get_position_value(pos)
    for pos in positions 
    if pos.closed_at is None
    and pos.strategy_id == signal.strategy_id
)

# Calculate remaining capital for this strategy
strategy_remaining_capital = strategy_allocated_capital - strategy_current_exposure

# Position size as percentage of strategy's allocated capital
# Scale from 20% (low confidence) to 100% (high confidence)
position_pct = 0.20 + (0.80 * confidence_factor)
position_size = strategy_allocated_capital * position_pct
```

### 2. Updated `RiskManager.validate_signal()`

**File**: `src/risk/risk_manager.py`

**Changes**:
- Added `strategy_allocation_pct` parameter (default: 1.0%)
- Pass `strategy_allocation_pct` to `calculate_position_size()`
- Log allocation percentage in validation message

### 3. Updated Trading Scheduler

**File**: `src/core/trading_scheduler.py`

**Changes**:
- Pass `strategy.allocation_percent` to `validate_signal()`

```python
validation_result = self._risk_manager.validate_signal(
    signal=signal,
    account=account_info,
    positions=position_dataclasses,
    strategy_allocation_pct=strategy.allocation_percent  # NEW
)
```

### 4. Updated E2E Test Script

**File**: `scripts/e2e_trade_execution_test.py`

**Changes**:
- Pass `strategy.allocation_percent` to `validate_signal()` in both test scenarios

---

## Expected Behavior After Fix

### Position Sizing Example:
- **Account Balance**: $400,000
- **Strategy Allocation**: 1.0%
- **Strategy Allocated Capital**: $4,000 (1% of $400K)
- **Signal Confidence**: 0.80 (80%)
- **Position Percentage**: 84% (20% + 80% * 80%)
- **Position Size**: $3,360 (84% of $4,000)

### Multiple Positions:
- Strategy can open multiple positions up to its $4,000 allocation
- Each position sized based on confidence (20%-100% of remaining allocation)
- Once $4,000 is used, no more positions until some close

### Multiple Strategies:
- Each 1% strategy gets $4,000 to work with
- 25 strategies @ 1% each = $100,000 total allocated (25% of portfolio)
- Remaining 75% stays as cash buffer

---

## Benefits

### 1. Proper Risk Management
- Each strategy limited to its allocated capital
- No single strategy can blow up the account
- Portfolio-level risk control maintained

### 2. Scalable Architecture
- Can activate many strategies (100+ at 1% each)
- Each operates independently within its allocation
- Total exposure controlled at portfolio level

### 3. Confidence-Based Sizing
- High confidence signals (80-100%) use more of allocation
- Low confidence signals (20-40%) use less
- Automatic position sizing optimization

### 4. Strategy Isolation
- Each strategy's exposure tracked separately
- One strategy's losses don't affect others' capital
- Clear attribution of P&L to strategies

---

## Testing

### Before Fix:
```
Order: NVDA $50,086.55 (12.5% of $400K account)
Order: NVDA $36,062.36 (9.0% of $400K account)
Order: NVDA $25,964.91 (6.5% of $400K account)
```

### After Fix (Expected):
```
Order: NVDA $3,200 (80% of $4K allocation, 0.8% of account)
Order: NVDA $640 (20% of $4K allocation, 0.16% of account)
Total: $3,840 (96% of $4K allocation, 0.96% of account)
```

---

## Files Modified

1. `src/risk/risk_manager.py`
   - `calculate_position_size()` - Added strategy allocation logic
   - `validate_signal()` - Added strategy_allocation_pct parameter

2. `src/core/trading_scheduler.py`
   - Pass `strategy.allocation_percent` to `validate_signal()`

3. `scripts/e2e_trade_execution_test.py`
   - Pass `strategy.allocation_percent` to `validate_signal()` in tests

---

## Future Enhancements

### Smart Allocation (Not Implemented Yet)
The current 1% fixed allocation works, but could be smarter:

1. **Performance-Based Allocation**
   - High Sharpe strategies get more allocation
   - Poor performers get less
   - Dynamic rebalancing based on results

2. **Volatility-Adjusted Allocation**
   - High volatility strategies get less capital
   - Low volatility strategies get more
   - Risk-parity approach

3. **Correlation-Based Allocation**
   - Uncorrelated strategies get more allocation
   - Highly correlated strategies share allocation
   - Portfolio diversification optimization

4. **Market Regime Adaptation**
   - Bull market: increase allocations
   - Bear market: decrease allocations
   - High VIX: reduce all allocations

These enhancements can be added to `PortfolioManager.auto_activate_strategy()` in the future.

---

## Status: ✅ READY FOR TESTING

Run the e2e test to verify position sizes are now correct:
```bash
source venv/bin/activate
python scripts/e2e_trade_execution_test.py
```

Expected: Position sizes should be ~$800-$4,000 (20%-100% of $4K allocation) instead of $20K-$50K.
