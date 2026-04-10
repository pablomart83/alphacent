# Fix for Strategy Symbol Assignment

## Problem
All strategies are assigned the same list of symbols (e.g., ["SPY", "QQQ", "DIA"]), and the backtest only uses the first symbol. This means:
- All strategies trade SPY
- No symbol diversity
- Identical results across all strategies

## Solution
Distribute symbols across strategies to create diversity.

## Implementation
Modify `generate_strategies_from_templates` in `strategy_proposer.py` to assign different symbols to different strategies:

```python
# In generate_strategies_from_templates method:
for i in range(count):
    # Select template (cycle through available templates)
    template = templates[i % len(templates)]
    
    # ASSIGN DIFFERENT SYMBOL TO EACH STRATEGY FOR DIVERSITY
    # Cycle through available symbols
    strategy_symbol = [symbols[i % len(symbols)]]  # Single symbol per strategy
    
    # ... rest of the code ...
    
    strategy = self._generate_strategy_with_params(
        template=template,
        symbols=strategy_symbol,  # Use single symbol
        params=validated_params,
        variation_number=i
    )
```

This way:
- Strategy 0 gets ["SPY"]
- Strategy 1 gets ["QQQ"]
- Strategy 2 gets ["DIA"]
- Strategy 3 gets ["SPY"] (cycles back)
- etc.

This creates symbol diversity and ensures different strategies trade different instruments.
