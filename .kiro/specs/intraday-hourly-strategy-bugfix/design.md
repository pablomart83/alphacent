# Intraday/Hourly Strategy Bugfix Design

## Overview

This bugfix implements timeframe-aware thresholds to fix the systematic rejection of intraday and hourly strategies. The current system uses daily-calibrated thresholds (Sharpe 0.9, win rate 45%) that are statistically inappropriate for shorter timeframes. Hourly strategies naturally have lower Sharpe ratios due to more frequent sampling and different return distributions, while intraday strategies show severe walk-forward overfitting when validated with daily thresholds.

The fix introduces a timeframe detection mechanism that adjusts activation, walk-forward validation, signal generation, and retirement thresholds based on the strategy's interval (1H, 15m, 4H, 1D). This preserves the existing crypto/non-crypto threshold separation while adding a timeframe dimension.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug - when strategies with intervals shorter than daily (1H, 15m, 30m) are evaluated using daily-calibrated thresholds
- **Property (P)**: The desired behavior - strategies should be evaluated using thresholds appropriate for their timeframe
- **Preservation**: Existing daily and 4H strategy behavior, crypto/non-crypto threshold separation, and regime-aware adjustments must remain unchanged
- **Timeframe**: The interval at which a strategy operates (1D=daily, 4H=4-hour, 1H=hourly, 15m=15-minute)
- **Sharpe Ratio**: Risk-adjusted return metric that decreases with sampling frequency (hourly Sharpe naturally lower than daily)
- **Walk-Forward Validation**: Out-of-sample testing that splits data into train/test periods to detect overfitting
- **Activation Thresholds**: Minimum performance criteria (Sharpe, win rate, drawdown) required for a strategy to go live
- **Retirement Thresholds**: Performance criteria below which an active strategy is deactivated

## Bug Details

### Fault Condition

The bug manifests when a strategy with an intraday or hourly interval is evaluated for activation, walk-forward validation, signal generation, or retirement. The system fails to detect the strategy's timeframe and applies daily-calibrated thresholds that are statistically too strict for shorter intervals.

**Formal Specification:**
```
FUNCTION isBugCondition(strategy)
  INPUT: strategy of type Strategy
  OUTPUT: boolean
  
  interval = getStrategyInterval(strategy)
  
  RETURN interval IN ['1h', '1H', '15m', '30m', '2h', '2H']
         AND thresholdsUsed(strategy) == dailyThresholds
         AND NOT timeframeAdjustmentApplied(strategy)
END FUNCTION

FUNCTION getStrategyInterval(strategy)
  # Check metadata first (intraday templates)
  IF strategy.metadata.get('interval') EXISTS THEN
    RETURN strategy.metadata['interval']
  
  # Check backtest_results (walk-forward validation)
  IF strategy.backtest_results.metadata.get('interval') EXISTS THEN
    RETURN strategy.backtest_results.metadata['interval']
  
  # Default to daily if not specified
  RETURN '1d'
END FUNCTION
```

### Examples

- **Hourly Strategy Activation**: Strategy with interval='1H', Sharpe=0.75, win_rate=0.72 is rejected with "Sharpe 0.75 < 0.9" despite being strong for hourly timeframe. Expected: Activate with hourly threshold (Sharpe 0.6).

- **Intraday Walk-Forward Overfitting**: Strategy with interval='15m' validated with min_sharpe=0.3, min_win_rate=0.45 produces train_sharpe=2.27, test_sharpe=0.16 (severe overfitting). Expected: Use relaxed intraday thresholds (min_sharpe=0.15, min_win_rate=0.35) to prevent overfitting.

- **1H Signal Generation Failure**: 52 active hourly strategies produce 0 signals consistently. Expected: Generate signals when hourly conditions are met using appropriate indicator calculations.

- **Hourly Strategy Retirement**: Strategy with interval='1H', Sharpe=0.55, 35 trades is retired with "Sharpe 0.55 < 0.2" using daily retirement threshold. Expected: Use hourly retirement threshold (Sharpe 0.15) to avoid premature retirement.

- **Edge Case - 4H Strategy**: Strategy with interval='4H', Sharpe=0.85 should continue using existing thresholds (no adjustment). Expected: No change in behavior.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Daily strategies (interval='1d' or no interval specified) must continue using existing thresholds (Sharpe 0.9, win rate 45%)
- 4H strategies must continue using existing thresholds (they are working correctly)
- Crypto vs non-crypto threshold separation (min_sharpe_crypto, min_win_rate_crypto) must remain functional
- Regime-aware threshold adjustments (ranging_low_vol, risk_off, direction_aware) must continue working
- Alpha Edge relaxed thresholds (Sharpe 0.2, win rate 35%) must remain unchanged
- Walk-forward validation for daily strategies must use existing thresholds (min_sharpe 0.3, min_win_rate 0.45)
- Signal generation for daily strategies must continue producing signals using existing logic
- Retirement checks for daily strategies must use existing thresholds (Sharpe 0.2, win rate 35%, drawdown 25%)

**Scope:**
All strategies that do NOT have intraday or hourly intervals should be completely unaffected by this fix. This includes:
- Daily strategies (interval='1d' or unspecified)
- 4H strategies (interval='4h' or '4H')
- Weekly or monthly strategies (if any exist)
- All existing regime-aware and asset-class-aware threshold logic

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **Missing Timeframe Detection**: The `evaluate_for_activation` method in `portfolio_manager.py` does not check the strategy's interval before applying thresholds. It reads `min_sharpe` and `min_win_rate` from config without considering timeframe.

2. **Walk-Forward Validation Ignores Timeframe**: The `walk_forward_validate` method in `strategy_engine.py` detects intraday templates to use 1h bars but does not adjust the overfitting detection thresholds. The overfitting check uses a fixed 30% degradation threshold regardless of timeframe.

3. **Signal Generation Interval Mismatch**: The `generate_signals` method may be fetching daily data for hourly strategies, or the indicator calculations are not properly configured for hourly bars, causing zero signals.

4. **Retirement Thresholds Not Timeframe-Aware**: The `check_retirement_triggers` method uses fixed thresholds (Sharpe 0.2, win rate 35%) without considering that hourly strategies naturally have lower Sharpe ratios.

5. **Configuration Schema Missing Timeframe Dimension**: The `config/autonomous_trading.yaml` file has `activation_thresholds` with crypto/non-crypto separation but no timeframe-specific thresholds.

## Correctness Properties

Property 1: Fault Condition - Timeframe-Aware Activation

_For any_ strategy where the interval is intraday or hourly (1H, 15m, 30m, 2H) and the strategy's performance metrics meet the timeframe-appropriate thresholds, the fixed `evaluate_for_activation` function SHALL activate the strategy using adjusted thresholds (hourly: Sharpe 0.6, win rate 40%; intraday: Sharpe 0.4, win rate 38%).

**Validates: Requirements 2.1, 2.4**

Property 2: Fault Condition - Timeframe-Aware Walk-Forward Validation

_For any_ strategy where the interval is intraday or hourly, the fixed `walk_forward_validate` function SHALL apply timeframe-appropriate overfitting detection thresholds (hourly: 40% degradation tolerance; intraday: 50% degradation tolerance) to prevent false overfitting rejections while still catching genuine overfitting.

**Validates: Requirements 2.2**

Property 3: Fault Condition - Timeframe-Aware Signal Generation

_For any_ active strategy where the interval is hourly, the fixed `generate_signals` function SHALL fetch hourly data and calculate indicators on hourly bars, producing signals when hourly conditions are met.

**Validates: Requirements 2.3**

Property 4: Fault Condition - Timeframe-Aware Retirement

_For any_ active strategy where the interval is intraday or hourly, the fixed `check_retirement_triggers` function SHALL apply timeframe-appropriate retirement thresholds (hourly: Sharpe 0.15, win rate 30%; intraday: Sharpe 0.10, win rate 28%) to avoid premature retirement of timeframe-appropriate performers.

**Validates: Requirements 2.5, 2.6**

Property 5: Preservation - Daily Strategy Behavior

_For any_ strategy where the interval is daily ('1d') or unspecified, the fixed functions SHALL produce exactly the same activation, validation, signal generation, and retirement behavior as the original functions, preserving all existing thresholds and logic.

**Validates: Requirements 3.1, 3.2, 3.7**

Property 6: Preservation - 4H Strategy Behavior

_For any_ strategy where the interval is 4H ('4h' or '4H'), the fixed functions SHALL produce exactly the same behavior as the original functions, with no timeframe adjustments applied.

**Validates: Requirements 3.3**

Property 7: Preservation - Crypto Threshold Separation

_For any_ strategy where the primary symbol is crypto (BTC, ETH, etc.), the fixed functions SHALL continue using `min_sharpe_crypto` and `min_win_rate_crypto` thresholds, with timeframe adjustments applied on top of the crypto base thresholds.

**Validates: Requirements 3.5**

Property 8: Preservation - Regime-Aware Adjustments

_For any_ strategy evaluated in a specific market regime (ranging_low_vol, risk_off, etc.), the fixed functions SHALL continue applying regime-aware threshold adjustments, with timeframe adjustments applied independently.

**Validates: Requirements 3.4**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File 1**: `src/strategy/portfolio_manager.py`

**Function**: `evaluate_for_activation`

**Specific Changes**:
1. **Add Timeframe Detection**: After loading base thresholds from config, detect the strategy's interval by checking `strategy.metadata.get('interval')` and `strategy.backtest_results.metadata.get('interval')` if available.

2. **Apply Timeframe Multipliers**: If interval is hourly (1H, 2H), multiply base Sharpe threshold by 0.67 and reduce win rate threshold by 5 percentage points. If interval is intraday (15m, 30m), multiply base Sharpe threshold by 0.44 and reduce win rate threshold by 7 percentage points.

3. **Preserve Crypto Logic**: Apply timeframe adjustments AFTER crypto threshold selection, so crypto hourly strategies use `min_sharpe_crypto * 0.67`.

4. **Log Timeframe Adjustment**: Add logging to show when timeframe adjustment is applied: "Hourly strategy: Adjusted thresholds - Sharpe>0.6 (from 0.9), WinRate>40% (from 45%)".

5. **Handle Missing Interval**: If interval is not specified, default to '1d' (daily) and use existing thresholds.

**File 2**: `src/strategy/strategy_engine.py`

**Function**: `walk_forward_validate`

**Specific Changes**:
1. **Adjust Overfitting Detection**: After calculating performance degradation, check the strategy's interval. If hourly, use 40% degradation threshold instead of 30%. If intraday, use 50% threshold.

2. **Update Overfitting Logic**: Change the overfitting check from `test_sharpe < train_sharpe * 0.3` to use a timeframe-aware threshold: `test_sharpe < train_sharpe * degradation_threshold`.

3. **Log Timeframe-Aware Validation**: Add logging: "Hourly strategy: Using 40% degradation threshold for overfitting detection (vs 30% for daily)".

**File 3**: `src/strategy/strategy_engine.py`

**Function**: `generate_signals`

**Specific Changes**:
1. **Detect Strategy Interval**: At the start of signal generation, check `strategy.metadata.get('interval')` to determine the data interval to fetch.

2. **Pass Interval to Data Fetch**: When calling `self.market_data.get_historical_data()`, pass the detected interval instead of defaulting to '1d'.

3. **Verify Indicator Calculations**: Ensure that indicators are calculated on the correct timeframe bars (hourly bars for hourly strategies).

4. **Log Interval Usage**: Add logging: "Generating signals for hourly strategy using 1h bars".

**File 4**: `src/strategy/portfolio_manager.py`

**Function**: `check_retirement_triggers`

**Specific Changes**:
1. **Add Timeframe Detection**: At the start of the function, detect the strategy's interval using the same logic as activation.

2. **Apply Timeframe Multipliers to Retirement Thresholds**: If hourly, use Sharpe threshold 0.15 (vs 0.2 for daily). If intraday, use Sharpe threshold 0.10. Adjust win rate thresholds similarly (hourly: 30%, intraday: 28%).

3. **Adjust Average Loss Check**: For intraday strategies, relax the 3x stop-loss threshold to 4x to account for higher intraday volatility.

4. **Log Timeframe Adjustment**: Add logging: "Hourly strategy: Using retirement threshold Sharpe>0.15 (vs 0.2 for daily)".

**File 5**: `config/autonomous_trading.yaml` (Optional Enhancement)

**Section**: `activation_thresholds`

**Specific Changes**:
1. **Add Timeframe Multipliers**: Add optional config keys `hourly_sharpe_multiplier: 0.67`, `intraday_sharpe_multiplier: 0.44`, `hourly_win_rate_adjustment: -0.05`, `intraday_win_rate_adjustment: -0.07`.

2. **Document Timeframe Logic**: Add comments explaining that these multipliers are applied to base thresholds (including crypto thresholds) when strategies have hourly or intraday intervals.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Fault Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Create test strategies with hourly and intraday intervals, run them through activation, walk-forward validation, signal generation, and retirement checks on the UNFIXED code. Observe failures and log rejection reasons.

**Test Cases**:
1. **Hourly Activation Test**: Create strategy with interval='1H', Sharpe=0.75, win_rate=0.72. Run through `evaluate_for_activation`. Expected failure: "Sharpe 0.75 < 0.9" (will fail on unfixed code).

2. **Intraday Walk-Forward Test**: Create strategy with interval='15m', run through `walk_forward_validate` with train_sharpe=2.0, test_sharpe=0.8. Expected failure: Marked as overfitted despite 40% degradation being acceptable for intraday (will fail on unfixed code).

3. **Hourly Signal Generation Test**: Create active hourly strategy, run through `generate_signals`. Expected failure: 0 signals produced due to daily data being fetched instead of hourly (will fail on unfixed code).

4. **Hourly Retirement Test**: Create active hourly strategy with Sharpe=0.18, 35 trades. Run through `check_retirement_triggers`. Expected failure: Retired with "Sharpe 0.18 < 0.2" despite being acceptable for hourly (will fail on unfixed code).

**Expected Counterexamples**:
- Hourly strategies with Sharpe 0.6-0.8 are rejected at activation
- Intraday strategies with 40-50% performance degradation are marked as overfitted
- Hourly strategies produce zero signals when they should produce signals
- Hourly strategies with Sharpe 0.15-0.19 are prematurely retired
- Possible causes: Missing timeframe detection, fixed thresholds in code, interval not passed to data fetch

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed functions produce the expected behavior.

**Pseudocode:**
```
FOR ALL strategy WHERE isBugCondition(strategy) DO
  interval = getStrategyInterval(strategy)
  
  # Test activation
  IF interval IN ['1h', '1H', '2h', '2H'] THEN
    adjusted_sharpe_threshold = base_sharpe * 0.67
    adjusted_wr_threshold = base_wr - 0.05
  ELSE IF interval IN ['15m', '30m'] THEN
    adjusted_sharpe_threshold = base_sharpe * 0.44
    adjusted_wr_threshold = base_wr - 0.07
  END IF
  
  result = evaluate_for_activation_fixed(strategy)
  ASSERT result uses adjusted_sharpe_threshold
  ASSERT result uses adjusted_wr_threshold
  
  # Test walk-forward validation
  wf_result = walk_forward_validate_fixed(strategy)
  IF interval IN ['1h', '1H', '2h', '2H'] THEN
    ASSERT wf_result uses 40% degradation threshold
  ELSE IF interval IN ['15m', '30m'] THEN
    ASSERT wf_result uses 50% degradation threshold
  END IF
  
  # Test signal generation
  signals = generate_signals_fixed(strategy)
  ASSERT data fetched with interval parameter
  ASSERT indicators calculated on correct timeframe
  
  # Test retirement
  retirement_reason = check_retirement_triggers_fixed(strategy)
  IF interval IN ['1h', '1H', '2h', '2H'] THEN
    ASSERT uses Sharpe threshold 0.15
    ASSERT uses win rate threshold 0.30
  ELSE IF interval IN ['15m', '30m'] THEN
    ASSERT uses Sharpe threshold 0.10
    ASSERT uses win rate threshold 0.28
  END IF
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed functions produce the same result as the original functions.

**Pseudocode:**
```
FOR ALL strategy WHERE NOT isBugCondition(strategy) DO
  # Daily and 4H strategies should be unchanged
  interval = getStrategyInterval(strategy)
  
  IF interval IN ['1d', '4h', '4H', NULL] THEN
    # Test activation
    result_original = evaluate_for_activation_original(strategy)
    result_fixed = evaluate_for_activation_fixed(strategy)
    ASSERT result_original == result_fixed
    
    # Test walk-forward validation
    wf_original = walk_forward_validate_original(strategy)
    wf_fixed = walk_forward_validate_fixed(strategy)
    ASSERT wf_original.is_overfitted == wf_fixed.is_overfitted
    
    # Test signal generation
    signals_original = generate_signals_original(strategy)
    signals_fixed = generate_signals_fixed(strategy)
    ASSERT len(signals_original) == len(signals_fixed)
    
    # Test retirement
    retire_original = check_retirement_triggers_original(strategy)
    retire_fixed = check_retirement_triggers_fixed(strategy)
    ASSERT retire_original == retire_fixed
  END IF
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain (different intervals, Sharpe ratios, win rates)
- It catches edge cases that manual unit tests might miss (e.g., interval='1D' vs '1d', missing interval)
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for daily and 4H strategies, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Daily Strategy Activation Preservation**: Create 100 random daily strategies with varying Sharpe/win rates. Run through activation on unfixed code, record results. Run through fixed code, verify identical results.

2. **4H Strategy Preservation**: Create 50 random 4H strategies. Verify activation, validation, signal generation, and retirement produce identical results on unfixed vs fixed code.

3. **Crypto Threshold Preservation**: Create crypto strategies (BTC, ETH) with daily and hourly intervals. Verify that crypto thresholds are still used, with timeframe adjustments applied on top for hourly.

4. **Regime-Aware Preservation**: Create strategies in ranging_low_vol regime. Verify that regime adjustments are still applied, with timeframe adjustments applied independently.

### Unit Tests

- Test timeframe detection logic with various interval formats ('1h', '1H', '15m', '30m', '1d', '4h', None)
- Test threshold calculation for each timeframe (hourly, intraday, daily)
- Test that crypto thresholds are preserved and adjusted correctly for hourly crypto strategies
- Test edge cases: missing interval (defaults to daily), invalid interval (defaults to daily)
- Test activation with hourly strategy meeting hourly thresholds but not daily thresholds
- Test walk-forward validation with intraday strategy showing 45% degradation (acceptable for intraday, not for daily)
- Test retirement with hourly strategy at Sharpe 0.17 (acceptable for hourly, not for daily)

### Property-Based Tests

- Generate random strategies with random intervals, Sharpe ratios, and win rates. Verify that:
  - Hourly strategies use hourly thresholds
  - Intraday strategies use intraday thresholds
  - Daily strategies use daily thresholds
  - Crypto strategies use crypto base thresholds with timeframe adjustments
- Generate random daily strategies and verify activation results are identical between unfixed and fixed code
- Generate random 4H strategies and verify all operations produce identical results
- Generate random market contexts (VIX levels, regimes) and verify regime adjustments work correctly with timeframe adjustments

### Integration Tests

- Test full activation flow: hourly strategy with Sharpe 0.7 should activate (currently rejects)
- Test full walk-forward flow: intraday strategy with 45% degradation should pass (currently fails)
- Test full signal generation flow: 52 active hourly strategies should produce signals (currently produces 0)
- Test full retirement flow: hourly strategy with Sharpe 0.18 should not retire (currently retires)
- Test crypto hourly strategy: should use crypto base threshold (0.3) * hourly multiplier (0.67) = 0.2 Sharpe threshold
- Test regime-aware hourly strategy: should apply both regime adjustment and timeframe adjustment
