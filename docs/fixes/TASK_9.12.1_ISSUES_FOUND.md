# Task 9.12.1 - Critical Issues Found

## Issue 1: All Strategies Have Identical Results

**Root Cause**: In `_run_vectorbt_backtest` method (line 1607):
```python
# For simplicity, use the first symbol's data
symbol = strategy.symbols[0]
df = data[symbol].copy()
```

All strategies are using the FIRST symbol regardless of what symbols they're supposed to trade. This means:
- A strategy configured to trade QQQ is actually trading SPY
- A strategy configured to trade DIA is actually trading SPY
- All strategies trade the same symbol → identical results

**Fix**: The backtest should either:
1. Use the actual symbols specified in the strategy
2. Or combine data from multiple symbols if the strategy trades a portfolio

## Issue 2: Walk-Forward Validation Failing

**Root Cause**: Data alignment issue in DSL signal generation

The error "Boolean index has wrong length: 131 instead of 111" occurs because:
1. Historical data is fetched with warmup period (111 days of actual data + warmup = 131 total)
2. Indicators are calculated on the FULL dataset (131 days)
3. But the close/high/low prices used in `_parse_strategy_rules` are from the SLICED dataset (111 days)
4. When DSL generates signals using indicators (131 length) and compares to close prices (111 length), pandas throws an error

**Example from logs**:
```
Full dataset: 111 days from 2025-08-11 to 2026-01-16
Requested backtest period: 2025-11-19 to 2026-01-18
```

The indicators have 131 days (including warmup from 2025-08-11), but the backtest period only has 111 days.

**Fix**: Need to ensure indicators and price data have the same index/length before generating signals. Options:
1. Slice indicators to match the backtest period
2. Or ensure all data (prices + indicators) use the same date range

## Issue 3: Results Look Suspicious

All strategies showing:
- Return: ~0.24%
- Sharpe: 0.12
- Max DD: -4.25%
- Trades: 4

This is suspicious because:
1. They're all identical (see Issue 1)
2. Very low returns and Sharpe ratio
3. Only 4 trades over the backtest period

This suggests the strategies might not be generating proper signals, or the backtest logic has other issues.

## Recommended Fixes

### Priority 1: Fix Symbol Selection
Update `_run_vectorbt_backtest` to use the correct symbols for each strategy.

### Priority 2: Fix Data Alignment
Ensure indicators and price data have matching indices before signal generation.

### Priority 3: Verify Signal Generation
After fixing the above, verify that different strategies generate different signals and results.
