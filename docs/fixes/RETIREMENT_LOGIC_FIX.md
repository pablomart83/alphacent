# Strategy Retirement Logic Fix

## Problem
Previously, every time the autonomous cycle ran (either from the e2e test or triggered from the frontend), ALL non-RETIRED strategies were retired, including DEMO and LIVE strategies that were actively generating trading signals.

This meant that successful strategies generating real signals would be retired and replaced with new untested strategies on every cycle.

## Solution
Modified the retirement logic to be more selective:

### Strategies that ARE retired (cleaned up):
- **PROPOSED**: Not yet backtested
- **BACKTESTED**: Not yet activated
- **INVALID**: Failed validation

### Strategies that are KEPT:
- **DEMO**: Actively generating signals in demo account (these are active!)
- **LIVE**: Actively generating signals in live account (these are the money-makers!)
- **RETIRED**: Already retired (no change needed)

## Key Understanding

**DEMO ≠ Testing Mode**
- DEMO status means the strategy is ACTIVE and generating signals
- It's trading in a demo account (not live money)
- These strategies should be preserved just like LIVE strategies

**Status Hierarchy:**
1. PROPOSED → not yet tested
2. BACKTESTED → tested but not activated
3. DEMO → activated in demo account (ACTIVE!)
4. LIVE → activated in live account (ACTIVE!)
5. RETIRED → no longer active

## Changes Made

### 1. E2E Test Script (`scripts/e2e_trade_execution_test.py`)
- Modified `step1_retire_all_strategies()` to only retire non-activated strategies
- Now retires: PROPOSED, BACKTESTED, INVALID
- Keeps: DEMO and LIVE (both are actively generating signals)

### 2. Autonomous Strategy Manager (`src/strategy/autonomous_strategy_manager.py`)
- Added new `_cleanup_inactive_strategies()` method
- Integrated cleanup as Step 0 in the cycle (before proposing new strategies)
- Added `strategies_cleaned` counter to cycle statistics
- Updated WebSocket broadcasts to include cleanup count
- Updated logging to show cleanup results

### 3. API Endpoint (`src/api/routers/strategies.py`)
- Updated cycle completion message to include cleanup count
- Frontend will now see: "X strategies cleaned, Y proposed, Z activated, W retired"

## Benefits

1. **Preserves Working Strategies**: DEMO and LIVE strategies generating signals are kept
2. **Cleaner Database**: Removes old PROPOSED, BACKTESTED, and INVALID strategies
3. **Better Resource Usage**: Focuses on strategies that are actually trading
4. **Consistent Behavior**: Same logic applies whether cycle is triggered from:
   - E2E test script
   - Frontend UI
   - Scheduled autonomous cycle

## Testing

Run the test script to see which strategies would be affected:
```bash
source venv/bin/activate
python test_retirement_logic.py
```

Run the e2e test to verify the full cycle:
```bash
source venv/bin/activate
python scripts/e2e_trade_execution_test.py
```

## Example Output

Before (OLD logic):
```
Retiring ALL 15 non-RETIRED strategies
  - Strategy A (LIVE) ❌ Should keep!
  - Strategy B (DEMO) ❌ Should keep!
  - Strategy C (PROPOSED) ✓ OK to retire
  ...
```

After (NEW logic):
```
Retiring 5 inactive strategies (keeping 10 DEMO/LIVE strategies)
  - Strategy C (PROPOSED) ✓ Retired
  - Strategy D (BACKTESTED) ✓ Retired
  - Strategy E (INVALID) ✓ Retired
  ...
Keeping active strategies:
  - Strategy A (LIVE) ✓ Kept - generating signals!
  - Strategy B (DEMO) ✓ Kept - generating signals!
  ...
```

## Cycle Flow

```
Autonomous Cycle:
├── Step 0: Cleanup (NEW!)
│   └── Retire: PROPOSED, BACKTESTED, INVALID
│   └── Keep: DEMO and LIVE strategies
├── Step 1: Propose new strategies
├── Step 2: Backtest proposals
├── Step 3-4: Evaluate and activate high performers
└── Step 5-6: Check retirement triggers for active strategies
    └── Retire DEMO/LIVE strategies only if underperforming
```

## Notes

- The retirement check in Step 5-6 still applies to DEMO and LIVE strategies
- Active strategies can still be retired if they fail performance checks (low Sharpe, high drawdown, etc.)
- This change only affects the cleanup phase, not the performance-based retirement
- DEMO strategies are just as important as LIVE - they're both actively trading!
