# FMP API Optimization - Deferred Fundamental Filtering

## Problem
FMP API calls were happening too early in the trading cycle, causing:
- 88% of signal generation time (21s out of 23.8s) spent on fundamental filtering
- 4 API calls per symbol × all strategy symbols = massive API usage
- API calls made even for symbols that never generate signals
- Rate limit exhaustion (250 calls/day)

## Root Cause
Fundamental filtering was applied BEFORE signal generation:
```
Strategy symbols (e.g., 20 symbols)
  ↓
Fundamental filter ALL symbols (20 × 4 = 80 API calls)
  ↓
Generate signals only for passed symbols
  ↓
Result: API calls wasted on symbols with no signals
```

## Solution
Move fundamental filtering AFTER signal generation:
```
Strategy symbols (e.g., 20 symbols)
  ↓
Generate signals for all symbols (no API calls)
  ↓
Fundamental filter ONLY symbols with signals (e.g., 2-3 symbols × 4 = 8-12 API calls)
  ↓
Result: 85-90% reduction in API calls
```

## Implementation Changes

### File: `src/strategy/strategy_engine.py`

**Before (lines 3220-3280):**
- Fundamental filter applied to ALL strategy symbols upfront
- `passed_symbols = fundamental_filter.get_passed_symbols(symbols_to_trade, strategy_type)`
- Signal generation only for passed symbols

**After:**
1. **Initialization phase (lines 3220-3250):** Initialize fundamental filter but don't use it yet
2. **Signal generation phase:** Generate signals for ALL symbols (no API calls)
3. **Post-signal filtering phase (lines 3430-3460):** Apply fundamental filter ONLY to symbols with actual signals

## Performance Impact

### Before Optimization:
- 20 symbols in strategy
- 20 symbols × 4 API calls = 80 API calls
- Time: ~21 seconds (2.7-3.7s per symbol due to rate limits)
- Signals generated: 2-3
- **Wasted API calls: 68-72 (85-90%)**

### After Optimization:
- 20 symbols in strategy
- Generate signals: 2-3 symbols have signals
- 2-3 symbols × 4 API calls = 8-12 API calls
- Time: ~2-3 seconds
- **API call reduction: 85-90%**
- **Time reduction: 85-90%**

## Benefits

1. **Massive API savings:** Only call FMP for symbols that actually have trading signals
2. **Faster signal generation:** 21s → 2-3s (7-10x faster)
3. **Rate limit preservation:** 80 calls → 8-12 calls per strategy run
4. **Better scalability:** Can run more strategies without hitting rate limits
5. **Same filtering quality:** All signals still pass through fundamental filter

## Cache Effectiveness

The 24-hour cache becomes much more effective:
- **Before:** Cache hit rate low because filtering all symbols every run
- **After:** Cache hit rate high because only filtering symbols with signals (same symbols tend to generate signals repeatedly)

## Testing

Run the E2E test to verify:
```bash
pytest tests/test_e2e_alpha_edge.py::TestAlphaEdgeE2E::test_comprehensive_e2e_trade_execution -v -s
```

Expected results:
- Signal generation time: 23.8s → ~3-5s
- FMP API calls: Reduced by 85-90%
- All signals still pass fundamental filter
- No change in signal quality

## Notes

- Fundamental filtering still happens - just deferred until we know which symbols need it
- Signals that fail fundamental filter are rejected (same behavior as before)
- API usage is logged after filtering for monitoring
- Cache is still used (24-hour TTL)
