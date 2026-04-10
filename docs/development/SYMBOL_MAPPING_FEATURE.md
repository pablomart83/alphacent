# Symbol Mapping Feature

## Overview

The AlphaCent Trading Platform now includes a symbol alias/mapping system that allows users to use friendly, intuitive symbols (like "BTC") which automatically map to eToro's naming convention (like "BTCUSD").

## Problem Solved

Previously, users had to know eToro's specific symbol format (e.g., "BTCUSD" instead of "BTC"), which was not user-friendly and caused issues with the frontend not displaying real market data.

## Solution

A symbol mapper utility that:
- Automatically converts user-friendly symbols to eToro format
- Works transparently in both the API and market data manager
- Supports cryptocurrencies, forex pairs, and commodities
- Allows dynamic addition of custom aliases

## Supported Aliases

### Cryptocurrencies
- BTC → BTCUSD
- ETH → ETHUSD
- XRP → XRPUSD
- LTC → LTCUSD
- BCH → BCHUSD
- ADA → ADAUSD
- DOT → DOTUSD
- LINK → LINKUSD
- XLM → XLMUSD
- DOGE → DOGEUSD
- UNI → UNIUSD
- MATIC → MATICUSD
- SOL → SOLUSD
- AVAX → AVAXUSD

### Forex Pairs
- EUR → EURUSD
- GBP → GBPUSD
- JPY → USDJPY
- CHF → USDCHF
- AUD → AUDUSD
- CAD → USDCAD
- NZD → NZDUSD

### Commodities
- GOLD → XAUUSD
- SILVER → XAGUSD
- OIL → OILUSD
- BRENT → UKOUSD

## Usage

### Backend (Python)

```python
from src.utils.symbol_mapper import normalize_symbol, get_display_symbol

# Convert user input to eToro format
etoro_symbol = normalize_symbol("BTC")  # Returns "BTCUSD"

# Convert eToro format back to user-friendly
display_symbol = get_display_symbol("BTCUSD")  # Returns "BTC"

# Add custom alias
from src.utils.symbol_mapper import add_alias
add_alias("MYTOKEN", "MYTOKENUSD")
```

### API Endpoints

All market data endpoints now support both formats:

```bash
# Using user-friendly symbol
GET /api/market-data/BTC

# Using eToro format (still works)
GET /api/market-data/BTCUSD

# Get list of all available aliases
GET /api/market-data/symbol-aliases
```

### Frontend (TypeScript/React)

Users can now type "BTC" in the UI and it will automatically work:

```typescript
// Both of these will work
const btcData = await api.getQuote('BTC');
const btcData = await api.getQuote('BTCUSD');
```

## Implementation Details

### Files Modified
1. `src/utils/symbol_mapper.py` - New utility module with mapping logic
2. `src/data/market_data_manager.py` - Integrated symbol normalization
3. `src/api/routers/market_data.py` - Added normalization to API endpoints

### Key Features
- **Case-insensitive**: "btc", "BTC", "Btc" all work
- **Whitespace handling**: " BTC " is automatically trimmed
- **Pass-through**: Stock symbols like "AAPL" pass through unchanged
- **Bidirectional**: Convert both ways (user → eToro and eToro → user)
- **Extensible**: Easy to add new aliases at runtime

## Testing

Comprehensive test suite in `tests/test_symbol_mapper.py`:
- 11 test cases covering all functionality
- All tests passing ✅

Run tests:
```bash
source venv/bin/activate
python -m pytest tests/test_symbol_mapper.py -v
```

## Benefits

1. **Better UX**: Users can type intuitive symbols like "BTC" instead of "BTCUSD"
2. **Fixes frontend issue**: Market data now displays correctly for instruments
3. **Backward compatible**: eToro format still works
4. **Flexible**: Easy to add more aliases as needed
5. **Transparent**: Works automatically without frontend changes

## Next Steps

To use this feature:
1. Frontend can continue using simple symbols like "BTC"
2. Backend automatically handles the conversion
3. Real eToro market data will now display correctly
4. Optional: Frontend can call `/api/market-data/symbol-aliases` to show users available shortcuts
