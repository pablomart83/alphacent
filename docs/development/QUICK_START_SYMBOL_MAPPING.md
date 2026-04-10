# Quick Start: Symbol Mapping

## TL;DR

Users can now type **"BTC"** instead of **"BTCUSD"** everywhere in the platform. The backend automatically handles the conversion.

## For Frontend Developers

No changes needed! Just use friendly symbols:

```typescript
// ✅ This now works
const btcData = await api.getQuote('BTC');
const ethData = await api.getQuote('ETH');
const goldData = await api.getQuote('GOLD');

// ✅ Old format still works
const btcData = await api.getQuote('BTCUSD');
```

## For Backend Developers

Import and use the mapper when needed:

```python
from src.utils.symbol_mapper import normalize_symbol

# Convert user input to eToro format
etoro_symbol = normalize_symbol("BTC")  # Returns "BTCUSD"
```

## Supported Shortcuts

| User Types | Backend Uses |
|------------|--------------|
| BTC        | BTCUSD       |
| ETH        | ETHUSD       |
| DOGE       | DOGEUSD      |
| EUR        | EURUSD       |
| GOLD       | XAUUSD       |
| AAPL       | AAPL (unchanged) |

[See full list in SYMBOL_MAPPING_FEATURE.md]

## API Endpoints

### Get Quote (supports both formats)
```bash
GET /api/market-data/BTC
GET /api/market-data/BTCUSD  # Still works
```

### Get Available Aliases
```bash
GET /api/market-data/symbol-aliases
```

Response:
```json
{
  "aliases": {
    "BTC": "BTCUSD",
    "ETH": "ETHUSD",
    ...
  },
  "count": 25
}
```

## Testing

```bash
# Run tests
source venv/bin/activate
python -m pytest tests/test_symbol_mapper.py -v

# Run demo
python examples/symbol_mapping_example.py
```

## Add Custom Aliases

```python
from src.utils.symbol_mapper import add_alias

# Add at runtime
add_alias("MYTOKEN", "MYTOKENUSD")

# Now works
normalize_symbol("MYTOKEN")  # Returns "MYTOKENUSD"
```

## That's It!

The feature works transparently. Users get a better experience, and you don't need to change existing code.

---

**Questions?** See `SYMBOL_MAPPING_FEATURE.md` for complete documentation.
