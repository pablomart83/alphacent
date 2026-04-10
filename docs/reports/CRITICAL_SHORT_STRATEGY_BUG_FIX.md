# CRITICAL BUG FIX: SHORT Strategies Generating LONG Signals

## Issue Discovered
During Task 12.1 E2E testing, discovered that "RSI Overbought Short Ranging GE V7" was generating ENTER_LONG signals instead of ENTER_SHORT signals, despite the strategy name clearly indicating it should be shorting.

## Root Cause Analysis

### Problem 1: Metadata Not Persisted
The `StrategyEngine._save_strategy()` and `_orm_to_strategy()` methods were NOT saving/loading the `strategy.metadata` field, which contains the critical `direction` field that determines if a strategy should go LONG or SHORT.

**Code Location:** `src/strategy/strategy_engine.py`
- Line 469-530: `_save_strategy()` - missing `strategy_metadata` assignment
- Line 553-575: `_orm_to_strategy()` - missing `metadata` field in Strategy construction

### Problem 2: Signal Generation Logic
The signal generation code checks `strategy.metadata.get('direction') == 'short'` to determine signal direction, but since metadata was never persisted, all strategies defaulted to LONG.

**Code Location:** `src/strategy/strategy_engine.py`
- Line 3719-3723: Checks metadata direction
- Line 3815-3822: Sets SignalAction based on direction

## Fixes Applied

### 1. Fixed Strategy Engine Persistence (src/strategy/strategy_engine.py)

**_save_strategy() method:**
```python
# Added to UPDATE path (line ~498):
existing.strategy_metadata = strategy.metadata if strategy.metadata else {}

# Added to CREATE path (line ~519):
strategy_metadata=strategy.metadata if strategy.metadata else {},
```

**_orm_to_strategy() method:**
```python
# Added to Strategy construction (line ~572):
metadata=orm.strategy_metadata if orm.strategy_metadata else {},
```

### 2. Created Migration Script (migrations/fix_short_strategy_direction.py)

Migrated 110 existing SHORT strategies in the database to have `direction='short'` in their metadata.

**Results:**
- Total strategies checked: 110
- Updated: 110
- Already correct: 0

## Verification

Before fix:
```python
Strategy: RSI Overbought Short Ranging GE V7
Metadata: {}
Direction: None
# Would generate: ENTER_LONG (WRONG!)
```

After fix:
```python
Strategy: RSI Overbought Short Ranging GE V7
Metadata: {'direction': 'short'}
Direction: short
# Will generate: ENTER_SHORT (CORRECT!)
```

## Impact

### Affected Strategies
All 110 strategies with "Short" in their name were affected:
- RSI Overbought Short strategies
- Stochastic Overbought Short strategies
- Ultra Short EMA Momentum strategies
- BB Upper Band Short strategies
- RSI Bollinger Combo Short strategies

### Trading Impact
**CRITICAL:** Any SHORT strategies that were activated before this fix were placing LONG orders when they should have been placing SHORT orders. This is a complete reversal of the intended trading direction.

### Historical Trades
Need to review all historical trades from SHORT strategies to assess:
1. How many trades were placed in the wrong direction
2. P&L impact of the incorrect direction
3. Whether any positions are currently open that should be closed

## Testing

### Manual Test
```bash
# Run E2E test again to verify SHORT strategies now generate SHORT signals
source venv/bin/activate && python scripts/e2e_trade_execution_test.py
```

### Expected Behavior
When "RSI Overbought Short Ranging GE V7" detects RSI > 75 (overbought):
- ✅ Should generate: ENTER_SHORT signal
- ❌ Was generating: ENTER_LONG signal (before fix)

## Recommendations

1. **Immediate:** Retire all currently active SHORT strategies and re-activate them to ensure they load the corrected metadata
2. **Review:** Audit all historical trades from SHORT strategies for incorrect direction
3. **Monitor:** Watch SHORT strategy performance closely over next few days
4. **Test:** Add integration test to verify SHORT strategies generate SHORT signals

## Files Modified

1. `src/strategy/strategy_engine.py` - Fixed metadata persistence
2. `migrations/fix_short_strategy_direction.py` - Migration script
3. `CRITICAL_SHORT_STRATEGY_BUG_FIX.md` - This document

## Date
2026-02-22

## Severity
🔴 CRITICAL - Complete reversal of trading direction for 110 strategies
