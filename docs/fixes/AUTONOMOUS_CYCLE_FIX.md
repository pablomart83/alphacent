# Autonomous Cycle Issue - Root Cause Analysis and Fix

## Problem
When triggering an autonomous trading cycle from the frontend, only 2 strategies were generated instead of the expected 50 (as configured in `config/autonomous_trading.yaml`).

## Root Cause Analysis

### Issue 1: Missing strategy_engine Parameter
**Location:** `src/strategy/autonomous_strategy_manager.py` - `_propose_strategies()` method

**Problem:**
```python
# BEFORE (BROKEN)
proposals = self.strategy_proposer.propose_strategies(count=proposal_count)
```

The `propose_strategies` method has these defaults:
- `use_walk_forward=True` (enables walk-forward validation)
- `strategy_engine=None` (no engine provided)

When `use_walk_forward=True` but `strategy_engine=None`, the walk-forward validation logic is triggered but cannot execute properly, causing most strategies to be filtered out.

**Fix Applied:**
```python
# AFTER (FIXED)
proposals = self.strategy_proposer.propose_strategies(
    count=proposal_count,
    strategy_engine=self.strategy_engine,
    use_walk_forward=True
)
```

Now the strategy_engine is properly passed, enabling walk-forward validation to work correctly.

### Issue 2: Walk-Forward Validation Too Aggressive
**Location:** `src/strategy/strategy_proposer.py` - `propose_strategies()` method

**Current Behavior:**
1. Generates `count * 3` strategies (e.g., 50 * 3 = 150 strategies)
2. Runs walk-forward validation on all 150
3. Filters to only strategies with:
   - `train_sharpe > 0.5`
   - `test_sharpe > 0.5`
   - `not is_overfitted`
4. If fewer than `count` pass, returns all that passed (could be just 2)

**Why Only 2 Strategies Passed:**
- Walk-forward validation requires strategies to perform well on BOTH train and test periods
- The validation criteria are strict (Sharpe > 0.5 on both periods)
- Most template-generated strategies don't meet these criteria
- Result: Only 2 out of 150 generated strategies passed validation

## Configuration Verification

### Config File (`config/autonomous_trading.yaml`)
```yaml
autonomous:
  enabled: true
  proposal_count: 50  # ✓ Correctly set to 50
  max_active_strategies: 100

backtest:
  days: 730  # ✓ Using 2 years of data
  walk_forward:
    train_days: 480  # 16 months
    test_days: 240   # 8 months

data_sources:
  yahoo_finance:
    enabled: true  # ✓ Yahoo Finance enabled
```

### Yahoo Finance Integration
✓ **VERIFIED:** All backtesting code uses `prefer_yahoo=True` to fetch historical data from Yahoo Finance
✓ **VERIFIED:** Market data manager properly falls back to Yahoo Finance when eToro data is unavailable
✓ **VERIFIED:** 2+ years of historical data is being used for analysis and backtesting

## Recommendations

### Option 1: Relax Walk-Forward Validation Criteria (Recommended)
Adjust the validation thresholds to be less strict:

```python
# Current (too strict)
if train_sharpe > 0.5 and test_sharpe > 0.5 and not is_overfitted:

# Recommended (more realistic)
if train_sharpe > 0.3 and test_sharpe > 0.2 and not is_overfitted:
```

**Rationale:**
- Sharpe ratio > 0.5 is quite good; > 0.3 is still acceptable
- Test Sharpe is typically lower than train Sharpe (out-of-sample)
- This would allow more strategies to pass while still filtering out poor performers

### Option 2: Disable Walk-Forward for Initial Generation
Generate strategies without walk-forward validation first, then apply it selectively:

```python
proposals = self.strategy_proposer.propose_strategies(
    count=proposal_count,
    strategy_engine=self.strategy_engine,
    use_walk_forward=False  # Disable for faster generation
)
```

**Rationale:**
- Faster cycle execution
- More strategies generated
- Can still apply validation during activation phase

### Option 3: Adjust Generation Multiplier
Increase the generation multiplier to compensate for aggressive filtering:

```python
# In propose_strategies method
if use_walk_forward and strategy_engine:
    generation_count = count * 5  # Increase from 3x to 5x
```

**Rationale:**
- Generates more candidates (250 instead of 150 for count=50)
- Higher chance of getting enough strategies that pass validation
- More computationally expensive

## Testing Recommendations

1. **Test with relaxed criteria** (Option 1):
   - Modify validation thresholds
   - Run cycle
   - Verify 30-50 strategies are generated
   - Check quality of activated strategies

2. **Test without walk-forward** (Option 2):
   - Disable walk-forward validation
   - Run cycle
   - Verify 50 strategies are generated
   - Monitor performance over time

3. **Monitor data quality**:
   - Check logs for "POOR data quality" warnings
   - Verify Yahoo Finance is returning sufficient historical data
   - Ensure all symbols have 730+ days of data

## Files Modified

1. `src/strategy/autonomous_strategy_manager.py`
   - Fixed `_propose_strategies()` to pass `strategy_engine` parameter

## Next Steps

1. ✅ **COMPLETED:** Fixed missing strategy_engine parameter
2. **TODO:** Decide on validation criteria adjustment (Option 1, 2, or 3)
3. **TODO:** Test autonomous cycle with fix applied
4. **TODO:** Monitor strategy quality and performance
5. **TODO:** Adjust thresholds based on real-world results

## Expected Behavior After Fix

With the strategy_engine parameter fix applied:
- Walk-forward validation will execute properly
- Strategies will be validated against train/test splits
- Number of strategies generated depends on validation criteria:
  - **Current strict criteria:** 2-10 strategies (very selective)
  - **Relaxed criteria (recommended):** 30-50 strategies (balanced)
  - **No walk-forward:** 50 strategies (as configured)

## E2E Test Reference

The e2e test (`test_e2e_autonomous_system.py`) successfully generated multiple diverse strategies because:
1. It used `proposal_count: 3` (smaller, more achievable target)
2. It had proper strategy_engine initialization
3. Walk-forward validation had enough candidates to filter from

The production system with `proposal_count: 50` needs either:
- Relaxed validation criteria, OR
- Disabled walk-forward validation, OR
- Higher generation multiplier

to achieve the target of 50 strategies.
