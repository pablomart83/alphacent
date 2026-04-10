# Strategy Retirement Logic Improvements

## Overview
Implemented improved strategy retirement logic as specified in Task 2 of the System Readiness Improvements spec. The new logic provides fairer evaluation of strategies before retirement, preventing premature retirement during normal drawdown periods.

## Changes Implemented

### 1. Configuration (Task 2.1)
Added `retirement_logic` section to `config/autonomous_trading.yaml`:
```yaml
retirement_logic:
  min_live_trades_before_evaluation: 20
  rolling_window_days: 60
  consecutive_failures_required: 3
  probation_period_days: 30
```

### 2. Database Schema (Task 2.2)
Added three new fields to the `strategies` table:
- `retirement_evaluation_history` (JSON): Tracks all retirement evaluation attempts with timestamps, results, and metrics
- `live_trade_count` (INTEGER): Counts the number of live trades executed by the strategy
- `last_retirement_evaluation` (DATETIME): Timestamp of the last retirement evaluation

Added one new field to the `strategy_retirements` table:
- `final_drawdown` (FLOAT): Records the final drawdown at retirement

### 3. Improved Retirement Logic (Task 2.3)

#### Minimum Live Trades Requirement
- Strategies must have at least 20 live trades (configurable) before retirement evaluation
- Prevents premature retirement of new strategies with insufficient data

#### Probation Period
- New strategies have a 30-day probation period (configurable) after activation
- No retirement evaluation during probation period
- Allows strategies time to establish performance track record

#### Consecutive Failures Requirement
- Strategies must fail 3 consecutive evaluations (configurable) before retirement
- Prevents retirement due to temporary performance dips
- Evaluation history is tracked and stored

#### Rolling Window Metrics
- Evaluations use rolling 60-day metrics (configurable) instead of point-in-time
- More stable and representative of recent performance
- Note: Current implementation uses overall performance metrics; future enhancement will calculate metrics from trades within the rolling window

#### Detailed Logging
- Each evaluation records:
  - Timestamp
  - Pass/fail status
  - Specific failure reasons
  - All key metrics (Sharpe, drawdown, win rate, return, trade count)
- Retirement records include detailed reason with metrics
- Evaluation history limited to last 10 evaluations to prevent unbounded growth

### 4. Retirement Triggers
The following triggers are evaluated (all must fail for 3 consecutive evaluations):
1. Sharpe ratio < 0.5
2. Maximum drawdown > 15%
3. Win rate < 40%
4. Negative total return

### 5. Live Trade Count Tracking
- Automatically incremented when orders are filled in `OrderExecutor.handle_fill()`
- Persisted to database for accurate tracking
- Used to enforce minimum trade count requirement

### 6. Migration Script
Created `scripts/utilities/migrate_add_retirement_fields.py` to add new fields to existing databases:
- Adds `retirement_evaluation_history`, `live_trade_count`, `last_retirement_evaluation` to strategies table
- Adds `final_drawdown` to strategy_retirements table
- Safe to run multiple times (checks if columns exist)

## Testing

### Unit Tests (`tests/test_strategy_retirement.py`)
Comprehensive test coverage for:
- Minimum trade count requirement
- Probation period logic
- Consecutive failures requirement
- Evaluation history tracking
- Individual retirement triggers
- Configuration loading

### Integration Tests (`tests/test_retirement_integration.py`)
End-to-end tests for:
- Full retirement flow (3 consecutive failures)
- Recovery from failures (passing evaluation resets count)
- Configuration loading and application

All 19 tests pass successfully.

## Usage

### Automatic Evaluation
The `check_retirement_triggers()` method should be called periodically (e.g., daily) for each active strategy:

```python
strategy_engine = StrategyEngine(...)
for strategy in active_strategies:
    reason = strategy_engine.check_retirement_triggers(strategy.id)
    if reason:
        # Strategy should be retired
        strategy_engine.retire_strategy(strategy.id, reason)
```

### Manual Retirement
Strategies can still be manually retired:

```python
strategy_engine.retire_strategy(
    strategy_id="strategy-123",
    reason="Manual retirement by user"
)
```

### Viewing Evaluation History
Evaluation history is available in the strategy object:

```python
strategy = strategy_engine.get_strategy("strategy-123")
for evaluation in strategy.retirement_evaluation_history:
    print(f"Timestamp: {evaluation['timestamp']}")
    print(f"Passed: {evaluation['passed']}")
    print(f"Reasons: {evaluation['failure_reasons']}")
    print(f"Metrics: {evaluation['metrics']}")
```

## Configuration Options

All retirement logic parameters are configurable in `config/autonomous_trading.yaml`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_live_trades_before_evaluation` | 20 | Minimum live trades before retirement evaluation |
| `rolling_window_days` | 60 | Days of historical data for rolling metrics |
| `consecutive_failures_required` | 3 | Number of consecutive failures before retirement |
| `probation_period_days` | 30 | Days after activation before evaluation begins |

## Benefits

1. **Fairer Evaluation**: Strategies aren't retired during normal drawdown periods
2. **Statistical Significance**: Minimum trade count ensures sufficient data
3. **Stability**: Consecutive failures requirement prevents knee-jerk reactions
4. **Transparency**: Detailed logging and history tracking
5. **Flexibility**: All parameters are configurable
6. **Recovery**: Strategies can recover from temporary poor performance

## Future Enhancements

1. **True Rolling Window Metrics**: Calculate metrics from trades within the rolling window period (currently uses overall metrics)
2. **Adaptive Thresholds**: Adjust retirement thresholds based on market regime
3. **Performance Trend Analysis**: Consider performance trajectory, not just absolute values
4. **Strategy Rehabilitation**: Allow retired strategies to be reactivated after improvements

## Files Modified

- `config/autonomous_trading.yaml` - Added retirement_logic configuration
- `src/models/orm.py` - Added new fields to StrategyORM and StrategyRetirementORM
- `src/models/dataclasses.py` - Added new fields to Strategy dataclass
- `src/strategy/strategy_engine.py` - Improved check_retirement_triggers() and retire_strategy() methods
- `src/execution/order_executor.py` - Added live_trade_count increment on order fill

## Files Created

- `tests/test_strategy_retirement.py` - Unit tests for retirement logic
- `tests/test_retirement_integration.py` - Integration tests
- `scripts/utilities/migrate_add_retirement_fields.py` - Database migration script
- `STRATEGY_RETIREMENT_IMPROVEMENTS.md` - This documentation

## Migration Instructions

1. Run the migration script to add new database fields:
   ```bash
   python scripts/utilities/migrate_add_retirement_fields.py
   ```

2. Restart the trading system to load new configuration

3. Existing strategies will start with `live_trade_count=0` and empty `retirement_evaluation_history`

4. Strategies will be evaluated according to the new logic on the next evaluation cycle
