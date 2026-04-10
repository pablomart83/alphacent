# Symbol Concentration & Signal Coordination Improvements

## Problem Statement

The autonomous trading system was creating excessive concentration risk by allowing multiple strategies to trade the same symbols simultaneously:

- **NVDA**: 42 orders from 9 strategies = $216K total exposure
- **NKE**: 42 orders from 9 strategies = $338K total exposure
- **WMT**: 1 order from 1 strategy = $79K

This created several issues:
1. **Concentration risk** - too much capital in single assets
2. **Redundancy** - multiple strategies doing the same thing
3. **Correlation risk** - all positions move together
4. **Capital inefficiency** - many small positions instead of fewer larger ones

## Solutions Implemented

### 1. Symbol Concentration Limits (RiskManager)

Added two new risk parameters to `RiskConfig`:

```python
max_symbol_exposure_pct: float = 0.15  # 15% max exposure per symbol
max_strategies_per_symbol: int = 3     # Max 3 strategies per symbol
```

Implemented `check_symbol_concentration()` method that:
- Calculates total exposure to each symbol across all strategies
- Blocks new positions if symbol exposure would exceed 15% of portfolio
- Blocks new positions if more than 3 strategies already hold the symbol
- Provides clear rejection reasons for debugging

**Example:**
```
Account balance: $256,167
Max symbol exposure: $38,425 (15%)

Test: ENTER_LONG NVDA $51,233
Result: ❌ REJECTED
Reason: Symbol concentration limit - NVDA exposure would be $51,233 (max $38,425)
```

### 2. Signal Coordination (TradingScheduler)

Added `_coordinate_signals()` method that:
- Groups signals by symbol
- When multiple strategies want to trade the same symbol:
  - Keeps only the highest-confidence signal
  - Filters out lower-confidence redundant signals
  - Logs which signals were filtered and why

**Example:**
```
Signal coordination: 3 strategies want to trade NVDA
  ✅ Kept: Ultra Short EMA Momentum NVDA V31 (confidence=0.80)
  ❌ Filtered: MACD RSI Momentum NVDA V15 (confidence=0.65)
  ❌ Filtered: Breakout Strategy NVDA V22 (confidence=0.55)
```

### 3. Integration into Validation Pipeline

The symbol concentration check is now part of the standard validation flow:

```
Signal → Calculate Position Size → Check Position Limits → 
Check Exposure Limits → Check Symbol Concentration → Execute
```

All checks must pass for a signal to be executed.

## Files Modified

1. **src/models/dataclasses.py**
   - Added `max_symbol_exposure_pct` to RiskConfig
   - Added `max_strategies_per_symbol` to RiskConfig

2. **src/risk/risk_manager.py**
   - Added `check_symbol_concentration()` method
   - Integrated check into `validate_signal()` flow

3. **src/core/trading_scheduler.py**
   - Added `_coordinate_signals()` method
   - Integrated coordination into `_run_trading_cycle()`
   - Signals are now coordinated before validation/execution

## Testing Results

```bash
$ python test_concentration_limits.py

Risk Configuration:
  Max symbol exposure: 15.0%
  Max strategies per symbol: 3

Test 1: Small Position
  ENTER_LONG NVDA $5,000
  Result: ✅ VALID

Test 2: Large Position Exceeding Limit
  ENTER_LONG NVDA $51,233
  Result: ❌ REJECTED
  Reason: Symbol concentration limit exceeded

Test 3: Multiple Strategies per Symbol
  NVDA: 9 strategies (exceeds limit of 3)
  Signal coordination will filter to highest-confidence
```

## Expected Behavior Changes

### Before:
- 9 strategies all trading NVDA simultaneously
- Each strategy places small orders independently
- Total NVDA exposure: $216K (84% of portfolio!)
- High correlation risk, capital inefficiency

### After:
- Signal coordination filters to 1 best signal per symbol
- Symbol concentration limit caps exposure at 15% per symbol
- Max 3 strategies can hold same symbol simultaneously
- Better diversification, lower correlation risk

## Configuration

Default limits can be adjusted in risk configuration:

```python
# Conservative (default)
max_symbol_exposure_pct = 0.15  # 15%
max_strategies_per_symbol = 3

# Moderate
max_symbol_exposure_pct = 0.20  # 20%
max_strategies_per_symbol = 5

# Aggressive
max_symbol_exposure_pct = 0.25  # 25%
max_strategies_per_symbol = 10
```

## Benefits

1. **Reduced Concentration Risk**
   - No single symbol can dominate the portfolio
   - Forced diversification across assets

2. **Better Capital Efficiency**
   - One larger position instead of many tiny ones
   - Lower transaction costs
   - Easier to manage

3. **Lower Correlation Risk**
   - Prevents multiple correlated positions
   - Better risk-adjusted returns

4. **Clearer Strategy Performance**
   - Each strategy gets fair chance to prove itself
   - No confusion from overlapping positions

5. **Improved Risk Management**
   - Clear, enforceable limits
   - Transparent rejection reasons
   - Easy to audit and adjust

## Future Enhancements

Potential improvements for future iterations:

1. **Sector Concentration Limits**
   - Track exposure by sector (tech, retail, etc.)
   - Prevent over-concentration in correlated sectors

2. **Correlation-Aware Portfolio Construction**
   - Calculate correlation between positions
   - Limit total correlated exposure

3. **Dynamic Limits Based on Volatility**
   - Tighter limits for high-volatility assets
   - Looser limits for stable assets

4. **Strategy Retirement Based on Redundancy**
   - Automatically retire strategies that are too similar
   - Keep only the best-performing unique strategies

## Monitoring

Key metrics to monitor:

- Symbol exposure distribution (should be more balanced)
- Number of filtered signals (indicates coordination working)
- Rejection reasons (track concentration limit hits)
- Strategy diversity (number of unique symbols traded)

## Conclusion

These improvements significantly enhance the risk management capabilities of the autonomous trading system by preventing excessive concentration in single symbols and eliminating redundant signals from multiple strategies. The system now enforces clear, configurable limits while maintaining flexibility for different risk profiles.
