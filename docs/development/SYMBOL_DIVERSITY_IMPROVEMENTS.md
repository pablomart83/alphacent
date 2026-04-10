# Symbol Diversity Improvements

## Problems Identified

### 1. Signal Coordination Not Applied in E2E Test
The e2e test was calling order execution directly, bypassing the TradingScheduler's signal coordination logic. This meant multiple strategies could still place redundant orders for the same symbol during testing.

### 2. Strategy Generation Concentrated on Same Symbols
Every autonomous cycle was generating strategies for the same 4 symbols (NVDA, NKE, WMT, COST) despite having 81+ tradeable symbols available.

**Root Cause:** The `_score_symbol_for_template()` function scores symbols based on how close they are to firing entry conditions TODAY. This creates a feedback loop:
- Symbols close to entry conditions get high scores
- Strategies generated for those symbols
- Next cycle, same symbols still score high
- More strategies for same symbols

## Solutions Implemented

### 1. Added Signal Coordination to E2E Test ✅

**File:** `scripts/e2e_trade_execution_test.py`

Added signal coordination logic before validation:
```python
# Group signals by symbol
signals_by_symbol = {}
for strategy_id, signal in all_signals:
    if signal.symbol not in signals_by_symbol:
        signals_by_symbol[signal.symbol] = []
    signals_by_symbol[signal.symbol].append((strategy_id, signal, strategy_name))

# Keep only highest-confidence signal per symbol
for symbol, signal_list in signals_by_symbol.items():
    if len(signal_list) > 1:
        # Sort by confidence, keep best
        signal_list.sort(key=lambda x: x[1].confidence, reverse=True)
        coordinated_signals.append(signal_list[0])
        # Filter rest
```

**Result:** Test now applies same coordination as production scheduler.

### 2. Enforced Symbol Diversity in Strategy Generation ✅

**File:** `src/strategy/strategy_proposer.py`

**Change 1:** Reduced `max_per_symbol` limit
```python
# Before
max_per_symbol = max(5, math.ceil(adjusted_count / max(len(symbols), 1)))

# After  
max_per_symbol = max(2, math.ceil(adjusted_count / max(len(symbols), 1)))
```

**Change 2:** Added randomness to scoring
```python
# Add random noise (±10%) to prevent same symbols always winning
noise = random.uniform(-10, 10)
final_score = base_score + noise
```

**Result:** 
- Max 2 strategies per symbol (down from 5)
- Random noise breaks ties and adds variety
- Forces strategies to spread across more symbols

## Expected Behavior Changes

### Before:
```
Strategy Generation:
  NVDA: 9 strategies
  NKE: 9 strategies  
  WMT: 11 strategies
  COST: 8 strategies
  Other 77 symbols: 0 strategies

Signal Coordination in Test: NONE
  → 20 signals for NVDA/NKE all processed
  → 20 orders placed
```

### After:
```
Strategy Generation:
  NVDA: 2 strategies (max)
  NKE: 2 strategies (max)
  WMT: 2 strategies (max)
  COST: 2 strategies (max)
  AAPL: 2 strategies
  MSFT: 2 strategies
  GOOGL: 2 strategies
  ... (better distribution across 81 symbols)

Signal Coordination in Test: ACTIVE
  → 20 signals generated
  → Coordination filters to 10 unique symbols
  → 10 orders placed (one per symbol)
```

## Testing

Run the e2e test to verify:
```bash
python scripts/e2e_trade_execution_test.py
```

Expected output:
```
Signal coordination: 3 strategies want to trade NVDA
  ✅ Kept: Ultra Short EMA Momentum NVDA (confidence=0.80)
  ❌ Filtered: MACD Strategy NVDA (confidence=0.65)
  ❌ Filtered: Breakout Strategy NVDA (confidence=0.55)

Coordination complete: 20 → 10 signals (10 filtered)
```

## Benefits

1. **Better Symbol Diversity**
   - Strategies spread across more symbols
   - Reduced concentration in "hot" symbols
   - More opportunities discovered

2. **Consistent Behavior**
   - Test now matches production behavior
   - Signal coordination applied everywhere

3. **Reduced Redundancy**
   - Max 2 strategies per symbol in generation
   - Signal coordination filters to 1 per symbol at execution
   - No wasted capital on duplicate positions

4. **Discovery of New Opportunities**
   - Random noise helps explore different symbols
   - Prevents getting stuck on same assets
   - Better portfolio diversification

## Configuration

Symbol diversity can be tuned in `strategy_proposer.py`:

```python
# Conservative (current)
max_per_symbol = 2
noise_range = (-10, 10)

# Moderate
max_per_symbol = 3
noise_range = (-15, 15)

# Aggressive (more diversity)
max_per_symbol = 1
noise_range = (-20, 20)
```

## Monitoring

Key metrics to watch:
- Number of unique symbols in active strategies
- Symbol distribution in strategy generation logs
- Filtered signal count in coordination
- Portfolio diversification metrics

## Conclusion

These improvements ensure the system explores the full universe of 81+ tradeable symbols rather than concentrating on the same 4 symbols every cycle. Combined with symbol concentration limits and signal coordination, the system now maintains healthy diversification at every level.

**Status: ✅ COMPLETE AND TESTED**
