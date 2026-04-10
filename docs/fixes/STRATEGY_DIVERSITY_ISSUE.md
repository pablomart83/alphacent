# Strategy Diversity Issue

## Current Status
- **Total templates**: 47 available
- **Total tradeable symbols**: 81 (stocks, ETFs, forex, indices, commodities, crypto)
- **Strategies generated per cycle**: Only 27 (requested 100)
- **Active DEMO strategies**: 15
- **Symbols being traded**: Only 4 (WMT, GLD, GOLD, GE)

## Root Cause
The autonomous cycle is only generating 27 proposals instead of the requested 100, and those proposals are concentrated on just a few symbols.

### Why Only 4 Symbols Generate Signals?
1. **Only 15 DEMO strategies active** (after autonomous cycle)
2. **Those 15 strategies only cover 4 symbols**: WMT (5), GLD (4), GOLD (4), GE (2)
3. **Only GE and GOLD have current market conditions** that trigger entry rules

### Why Only 27 Proposals Instead of 100?
Possible reasons:
1. **Template filtering** - Some templates may be filtered out based on market regime
2. **Symbol analysis failures** - Some symbols may fail market analysis
3. **Diversity constraints** - System limits strategies per symbol to prevent over-concentration

## Diversity Constraints
The `_match_templates_to_symbols` method enforces:
```python
max_per_symbol = max(2, ceil(adjusted_count / len(symbols)))
# With 100 proposals and 81 symbols: max_per_symbol = 2
```

This means each symbol can only appear in 2 strategies maximum.

## Solutions

### Option 1: Increase Proposal Count (Quick Fix)
Increase the proposal count in autonomous cycle to generate more strategies:
```python
# In autonomous_trading.yaml or e2e test
proposal_count: 200  # Instead of 100
```

### Option 2: Relax Diversity Constraints
Modify `_match_templates_to_symbols` to allow more strategies per symbol:
```python
max_per_symbol = max(5, ceil(adjusted_count / len(symbols)))  # Allow 5 per symbol
```

### Option 3: Ensure All Proposals Are Generated
Debug why only 27/100 proposals are being created:
- Check template filtering logic
- Check symbol analysis success rate
- Check if there are errors during strategy generation

### Option 4: Run Multiple Cycles
Instead of one big cycle, run multiple smaller cycles to build up diversity over time.

## Recommended Action
1. **Debug the 27/100 issue first** - Find out why only 27 proposals are generated
2. **Increase max_per_symbol to 5** - Allow more strategies per symbol
3. **Increase proposal_count to 200** - Generate more proposals per cycle
4. **Monitor signal generation** - Ensure strategies across all asset classes generate signals

## Expected Outcome
With these changes, you should see:
- 100+ proposals generated per cycle
- 50+ strategies activated in DEMO
- Signals across 20-30 different symbols
- Trading in stocks, ETFs, forex, indices, commodities, AND crypto
