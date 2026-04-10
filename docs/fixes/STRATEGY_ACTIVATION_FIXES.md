# Strategy Activation Fixes - Option C Implementation

## Problem Analysis

The system was not generating trades because:

1. **Limited Active Strategies**: Only 2 DEMO strategies active (both for WMT with same conditions)
2. **Strict Activation Criteria**: Win rate threshold of 45% was too high - only 16/99 strategies passed
3. **Aggressive Walk-Forward Filtering**: 88% of strategies were rejected during walk-forward validation
4. **Current Market Conditions**: The 2 active strategies required specific MACD crossover conditions not met today

## Root Causes Identified

### 1. Walk-Forward Validation Issues

**Problem**: Walk-forward validation was rejecting 72% of proposed strategies (13 out of 18)

**Root Causes**:
- **Sharpe threshold too high**: Required Sharpe > 0.5 on both train AND test periods
- **Overfitting detection too strict**: Test Sharpe had to be >= 50% of train Sharpe
- **Test period challenges**: 240-day test period may not generate enough trades for mean-reversion strategies

### 2. Activation Threshold Issues

**Problem**: Only 10 out of 99 BACKTESTED strategies met activation criteria

**Breakdown**:
- 16/99 pass win rate >= 45%
- 33/99 pass Sharpe >= 0.3
- 99/99 pass drawdown < 20%
- 86/99 pass trades >= 3
- **Only 10 pass ALL criteria**

The 45% win rate threshold was the main bottleneck.

## Fixes Implemented

### Fix 1: Relaxed Win Rate Threshold
**File**: `src/strategy/portfolio_manager.py`
**Change**: Lowered base win rate threshold from 45% to 40%

```python
# Before
base_win_rate_threshold = 0.45

# After  
base_win_rate_threshold = 0.40  # Lowered from 0.45 to 0.40
```

**Impact**: This allows 15 strategies instead of 10 to pass activation criteria (50% increase)

### Fix 2: Relaxed Walk-Forward Sharpe Threshold
**File**: `src/strategy/strategy_proposer.py`
**Change**: Lowered Sharpe requirement from 0.5 to 0.3 for both train and test periods

```python
# Before
if train_sharpe > 0.5 and test_sharpe > 0.5 and not is_overfitted:

# After
# Require Sharpe > 0.3 on train AND test periods (RELAXED from 0.5)
# This allows more strategies through while still filtering poor performers
if train_sharpe > 0.3 and test_sharpe > 0.3 and not is_overfitted:
```

**Impact**: More strategies will pass walk-forward validation while still maintaining quality standards

### Fix 3: Relaxed Overfitting Detection
**File**: `src/strategy/strategy_engine.py`
**Change**: Lowered overfitting threshold from 50% to 30%

```python
# Before
is_overfitted = (
    test_sharpe < 0 or
    (train_sharpe > 0 and test_sharpe < train_sharpe * 0.5)  # 50% threshold
)

# After
# RELAXED: Consider overfitted only if test Sharpe < 0 or < 30% of train Sharpe
# (was 50%, too strict for strategies with few trades in test period)
is_overfitted = (
    test_sharpe < 0 or
    (train_sharpe > 0 and test_sharpe < train_sharpe * 0.3)  # 30% threshold
)
```

**Impact**: Strategies with moderate performance degradation will no longer be rejected as overfitted

### Fix 4: Added MOMENTUM Strategy Type
**File**: `src/strategy/strategy_templates.py`
**Change**: Added missing MOMENTUM enum value

```python
class StrategyType(str, Enum):
    """Strategy type classifications."""
    MEAN_REVERSION = "mean_reversion"
    TREND_FOLLOWING = "trend_following"
    VOLATILITY = "volatility"
    BREAKOUT = "breakout"
    MOMENTUM = "momentum"  # Added
```

**Impact**: Fixes AttributeError that was preventing strategy generation

## Expected Outcomes

### Immediate Benefits:
1. **More strategies will pass walk-forward validation** - Expect 30-40% pass rate instead of 28%
2. **More strategies will be activated** - Expect 15-20 active DEMO strategies instead of 2
3. **Better symbol diversity** - Strategies across multiple symbols, not just WMT
4. **Higher signal generation** - More strategies = more opportunities to generate trading signals

### Quality Safeguards Still in Place:
- Sharpe ratio must still be positive and >= 0.3
- Max drawdown must be < 20%
- Minimum 3 trades required
- Risk/reward ratio >= 1.2:1 for stop-loss strategies
- Walk-forward validation still prevents overfitting

## Testing

Run the activation script to apply these changes:

```bash
source venv/bin/activate
python scripts/activate_more_strategies.py
```

This will:
1. Run an autonomous cycle with 50 proposals
2. Apply the relaxed thresholds
3. Activate eligible strategies
4. Report the results

## Monitoring

After activation, monitor:
1. Number of active DEMO strategies
2. Symbol diversity across strategies
3. Daily signal generation rate
4. Strategy performance metrics

## Next Steps

1. Run the activation script
2. Monitor signal generation over next 24-48 hours
3. If still insufficient signals, consider:
   - Further relaxing win rate to 38%
   - Increasing test period to 365 days
   - Adding more strategy templates for current market regime
