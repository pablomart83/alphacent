# Monitoring Background Process - Updated Behavior

## Overview
The background monitoring process that reviews strategies and identifies issues will now work with the updated retirement logic.

## What Changed

### Before (Old Behavior)
When monitoring detected issues or when running the e2e test:
- ALL non-RETIRED strategies were retired
- This included LIVE strategies actively generating signals
- Every cycle started from scratch with no continuity

### After (New Behavior)
When monitoring or running cycles:
- Only inactive strategies are retired (PROPOSED, BACKTESTED, DEMO, INVALID)
- LIVE strategies generating signals are preserved
- Continuity maintained for successful strategies

## Monitoring Process Flow

```
Background Monitor:
├── Check system health
├── Review strategy performance
├── Identify issues
└── Trigger cycle if needed
    ├── Step 0: Cleanup inactive strategies
    │   └── Retire: PROPOSED, BACKTESTED, DEMO, INVALID
    │   └── Keep: LIVE strategies
    ├── Step 1-4: Generate and activate new strategies
    └── Step 5-6: Performance-based retirement
        └── Retire LIVE strategies only if underperforming
```

## When Strategies Are Retired

### Cleanup Phase (Step 0)
Strategies retired automatically:
- **PROPOSED**: Never backtested
- **BACKTESTED**: Never activated
- **DEMO**: Testing mode only
- **INVALID**: Failed validation

### Performance Phase (Step 5-6)
LIVE strategies retired only if:
- Sharpe ratio < 0.5 (after 30+ trades)
- Max drawdown > 15%
- Win rate < 40% (after 50+ trades)
- Other performance triggers

## Benefits for Monitoring

1. **Continuity**: Successful strategies continue generating signals across cycles
2. **Better Metrics**: Can track long-term performance of LIVE strategies
3. **Reduced Churn**: Less disruption to active trading
4. **Cleaner Database**: Old inactive strategies are cleaned up
5. **Resource Efficiency**: Focus on strategies that are actually trading

## Running the Monitor

The monitor can now safely run cycles without losing active strategies:

```bash
# Activate virtual environment
source venv/bin/activate

# Run the e2e test (now preserves LIVE strategies)
python scripts/e2e_trade_execution_test.py

# Or verify the fix first
python verify_retirement_fix.py

# Or test the retirement logic
python test_retirement_logic.py
```

## Frontend Integration

When triggering cycles from the frontend:
- Same behavior as e2e test
- LIVE strategies are preserved
- Cleanup count shown in UI
- WebSocket updates include cleanup statistics

## Example Cycle Output

```
================================================================================
Starting autonomous strategy cycle
================================================================================

[STEP 0] Cleaning up non-activated and DEMO strategies...
  Found 8 inactive strategies to retire
    Retiring: Old Momentum Strategy (status: DEMO)
    Retiring: Failed Backtest Strategy (status: BACKTESTED)
    Retiring: Invalid Rules Strategy (status: INVALID)
    ...
  ✓ Cleaned up 8 inactive strategies (kept 5 LIVE strategies)

[STEP 1] Proposing new strategies...
  [1/10] Proposed: New Momentum Strategy (symbols: AAPL, MSFT)
  ...

[STEP 2] Backtesting proposed strategies...
  ...

[STEP 3-4] Evaluating and activating high performers...
  ✓ Activated 3 new strategies in DEMO mode

[STEP 5-6] Checking retirement triggers...
  ✓ All 5 LIVE strategies performing well
  (No performance-based retirements needed)

================================================================================
Autonomous strategy cycle completed
Duration: 1847.3 seconds
Strategies cleaned: 8
Proposals generated: 10
Proposals backtested: 10
Strategies activated: 3
Strategies retired: 0
================================================================================
```

## Monitoring Best Practices

1. **Check LIVE Strategy Count**: Monitor how many LIVE strategies are active
2. **Review Cleanup Stats**: Track how many inactive strategies are cleaned per cycle
3. **Watch Performance Metrics**: Ensure LIVE strategies maintain good performance
4. **Alert on Zero LIVE**: If all LIVE strategies are retired, investigate why
5. **Balance Portfolio**: Aim for 5-10 LIVE strategies for diversification

## Troubleshooting

### If all LIVE strategies are retired:
- Check performance metrics (Sharpe, drawdown, win rate)
- Review market conditions (regime change?)
- Check if retirement thresholds are too strict
- Verify strategies are generating signals

### If too many inactive strategies accumulate:
- Cycle will clean them up automatically
- Can manually trigger cycle from frontend
- Check why strategies aren't being activated

### If no new strategies are activated:
- Check backtest results (meeting thresholds?)
- Review market data quality
- Verify strategy templates are working
- Check activation thresholds in config
