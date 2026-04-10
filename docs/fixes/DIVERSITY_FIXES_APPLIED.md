# Strategy Diversity Fixes Applied

## Problem
- Only 27 strategies generated instead of 100 requested
- Only 4 symbols being traded (WMT, GLD, GOLD, GE)
- Only 2 symbols generating signals (GE, GOLD)
- 81 tradeable symbols available but not being utilized

## Root Causes Identified
1. **Diversity constraints too strict**: `max_per_symbol = 2` limited each symbol to only 2 strategies
2. **Proposal count too low**: Config had 50, test requested 100, but only 27 were generated
3. **Greedy matching algorithm**: Ran out of valid (template, symbol) combinations due to strict caps

## Fixes Applied

### 1. Relaxed Diversity Constraints
**File**: `src/strategy/strategy_proposer.py`
**Change**: Increased max strategies per symbol/template from 2 to 5

```python
# Before:
max_per_template = max(2, math.ceil(adjusted_count / max(len(templates_for_cycle), 1)))
max_per_symbol = max(2, math.ceil(adjusted_count / max(len(symbols), 1)))

# After:
max_per_template = max(5, math.ceil(adjusted_count / max(len(templates_for_cycle), 1)))
max_per_symbol = max(5, math.ceil(adjusted_count / max(len(symbols), 1)))
```

**Impact**: Each symbol can now have up to 5 strategies instead of 2, allowing better coverage

### 2. Increased Proposal Count
**File**: `config/autonomous_trading.yaml`
**Change**: Increased proposal count and max active strategies

```yaml
# Before:
proposal_count: 50
max_active_strategies: 100
min_active_strategies: 50

# After:
proposal_count: 150
max_active_strategies: 150
min_active_strategies: 75
```

**Impact**: System will generate 150 proposals per cycle, ensuring better symbol coverage

## Expected Results

### Before Fixes
- 27 proposals generated
- 4 symbols traded
- 2 symbols with signals
- ~5% symbol utilization (4/81)

### After Fixes
- 150 proposals generated
- 50-80 symbols traded (estimated)
- 20-30 symbols with signals (estimated)
- ~60-100% symbol utilization

### Symbol Distribution
With 150 proposals and 81 symbols:
- Average: ~2 strategies per symbol
- Range: 1-5 strategies per symbol
- Coverage: Most symbols will have at least 1 strategy

## Testing

Run the test script to verify:
```bash
python test_strategy_generation.py
```

Expected output:
- Proposals generated: ~150
- DEMO strategies: ~50-100 (after backtest filtering)
- Unique symbols: ~50-80
- Better distribution across all asset classes

## Next Steps

1. **Run test_strategy_generation.py** to verify fixes work
2. **Monitor signal generation** across different asset classes
3. **Check trading activity** to ensure diverse symbol coverage
4. **Adjust proposal_count** if needed (can go higher for even more diversity)

## Files Modified
- `src/strategy/strategy_proposer.py` - Relaxed diversity constraints
- `config/autonomous_trading.yaml` - Increased proposal count
- `test_strategy_generation.py` - Created test script
