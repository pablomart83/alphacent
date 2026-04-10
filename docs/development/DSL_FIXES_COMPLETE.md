# DSL Fixes Complete ✅

**Date**: 2026-02-18

## Issues Fixed

### 1. STDDEV Indicator Key Mismatch ✅

**Problem**: 
- DSL expected indicator key: `STDDEV_20`
- Indicator library returned: `STDDEV`
- Result: Strategies using STDDEV failed with "Missing indicators: STDDEV_20"

**Root Cause**:
The `_get_standardized_key()` method in `indicator_library.py` didn't include `STDDEV` in the list of indicators that get the `_{period}` suffix.

**Fix**:
```python
# Before
if indicator_upper in ['SMA', 'EMA', 'RSI', 'ATR', 'VOLUME_MA', 'SUPPORT_RESISTANCE', 'STOCH', 'ADX']:

# After  
if indicator_upper in ['SMA', 'EMA', 'RSI', 'ATR', 'VOLUME_MA', 'SUPPORT_RESISTANCE', 'STOCH', 'ADX', 'STDDEV']:
```

**File**: `src/strategy/indicator_library.py` line 99

**Test Result**: ✅ PASS
- STDDEV now returns key `STDDEV_20`
- DSL parsing works: `(CLOSE - SMA(20)) / STDDEV(20) < -1.2`
- Generated code: `(((data['close'] - indicators['SMA_20']) / indicators['STDDEV_20']) < (-1.2))`

---

### 2. Bollinger Band Semantic Validation Too Strict ✅

**Problem**:
- Semantic validation rejected: `CLOSE > BB_UPPER(20, 2)` as entry condition
- Error: "Bollinger upper band entry should use < (price below upper band), not >"
- This rejected valid breakout strategies (e.g., Bollinger Squeeze)

**Root Cause**:
The semantic validation assumed:
- Lower band = always entry (mean reversion only)
- Upper band = always exit (mean reversion only)

But there are TWO valid strategy types:
1. **Mean Reversion**: Enter when price < lower band, exit when price > upper band
2. **Breakout**: Enter when price > upper band, exit when price < lower band

**Fix**:
Removed overly strict validation that rejected breakout strategies. Now allows:
- `CLOSE > BB_UPPER` (breakout entry - valid)
- `CLOSE < BB_LOWER` (mean reversion entry - valid)
- Band width checks: `(BB_UPPER - BB_LOWER) < ATR * 4` (squeeze detection - valid)

**File**: `src/strategy/strategy_engine.py` lines 2901-2930

**Test Result**: ✅ PASS
- Bollinger Squeeze strategy now passes validation
- Breakout strategies now allowed
- Mean reversion strategies still work

---

## Impact

### Before Fixes
- **5 strategies filtered out** due to DSL errors
- Z-Score Mean Reversion: 0 trades (STDDEV error)
- Bollinger Squeeze: 0 trades (semantic validation error)

### After Fixes
- **STDDEV strategies will generate trades**
- **Bollinger Squeeze strategies will generate trades**
- **More strategy diversity** (both mean reversion and breakout)

---

## Test Results

All tests passed:

```
✅ PASS: STDDEV Key Fix
✅ PASS: STDDEV DSL Parsing  
✅ PASS: Bollinger Squeeze Validation

🎉 ALL TESTS PASSED!
```

**Test file**: `test_dsl_fixes.py`

---

## Next Steps

1. ✅ Fixes applied and tested
2. ⏭️ Re-run extended backtest to see improved results
3. ⏭️ Expect more strategies to pass filtering (STDDEV and Bollinger Squeeze)

---

## Technical Details

### STDDEV Fix
- **Location**: `src/strategy/indicator_library.py:99`
- **Change**: Added `'STDDEV'` to indicator list
- **Impact**: All STDDEV-based strategies now work

### Semantic Validation Fix
- **Location**: `src/strategy/strategy_engine.py:2901-2930`
- **Change**: Removed strict Bollinger Band validation
- **Impact**: Breakout strategies now allowed

---

## Conclusion

Both DSL issues are now fixed:
1. ✅ STDDEV indicator key mismatch resolved
2. ✅ Bollinger Band semantic validation relaxed to allow breakout strategies

The system is now more robust and supports a wider variety of trading strategies.
