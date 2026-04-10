# Historical Data Lookback Period Fix

## Problem
The system was only fetching 59-90 days of historical data despite having access to years of data through Yahoo Finance and the configuration being set to use 730 days (2 years).

## Root Cause
Multiple hardcoded `timedelta(days=90)` values in the codebase that were not reading from the configuration file.

## Changes Made

### 1. `src/strategy/strategy_proposer.py`
- **`analyze_market_conditions()` method (line ~77)**:
  - Changed from hardcoded 90 days to reading from config
  - Now uses `config['backtest']['days']` (730 days = 2 years)
  - Added logging to show how many days are being requested
  
- **Data quality thresholds updated**:
  - EXCELLENT: 600+ days (~2 years) - was 60+ days
  - GOOD: 365-599 days (~1 year) - was 45-59 days
  - FAIR: 180-364 days (~6 months) - was 30-44 days
  - POOR: <180 days - was <30 days

### 2. `src/strategy/market_analyzer.py`
- **`detect_sub_regime()` method (line ~914)**:
  - Changed from hardcoded 90 days to reading from config
  - Now uses `config['backtest']['days']` (730 days = 2 years)
  - Added logging to show how many days are being requested
  
- **Data quality thresholds updated** (same as above):
  - EXCELLENT: 600+ days
  - GOOD: 365-599 days
  - FAIR: 180-364 days
  - POOR: <180 days

### 3. `src/strategy/strategy_engine.py`
- **`validate_strategy_signals()` method (line ~1465)**:
  - Changed from 90 days to 180 days (6 months)
  - This is a quick validation, so 180 days is reasonable
  - Updated error messages to reflect 180 days
  
- **`_validate_signal_overlap()` method (line ~1818)**:
  - Changed from 90 days to 180 days (6 months)
  - Updated minimum data requirement from 30 to 90 days

## Configuration
The system now properly reads from `config/autonomous_trading.yaml`:

```yaml
backtest:
  days: 730  # 2 years of data
  warmup_days: 250
  min_trades: 50
  walk_forward:
    train_days: 480  # 16 months
    test_days: 240   # 8 months
```

## Expected Results
After these changes, you should see in the logs:
- "Using 730 days of historical data for market regime analysis"
- "Using 730 days of historical data for sub-regime detection"
- Data quality should now be "excellent" or "good" instead of "good" (59 days)
- Market analysis will be based on 2 years of data instead of 90 days

## Data Sources
- **Yahoo Finance**: Primary source, provides unlimited years of daily data
- **Alpha Vantage**: Secondary source for pre-calculated indicators (25 calls/day limit)
- **FRED**: Macro indicators (VIX, rates) - unlimited calls

The system will now fetch the full 730 days from Yahoo Finance, providing much more robust market regime detection and strategy analysis.
