# Symbol Mapping Visual Guide

## Before vs After

### Before (Not Working) ❌
```
Frontend Dashboard:
┌─────────────────────────────┐
│ Market Data                 │
├─────────────────────────────┤
│ Symbol: BTC                 │  ← User sees "BTC"
│ Price: Loading...           │  ← No data!
└─────────────────────────────┘
         ↓
    API Request: GET /api/market-data/BTC
         ↓
    Backend: "BTC not found in eToro"  ← Backend doesn't understand "BTC"
         ↓
    ❌ No data returned
```

### After (Working) ✅
```
Frontend Dashboard:
┌─────────────────────────────┐
│ Market Data                 │
├─────────────────────────────┤
│ Symbol: BTC                 │  ← User sees "BTC"
│ Price: $50,500.00          │  ← Real eToro data! ✅
│ Change: +2.5%              │
└─────────────────────────────┘
         ↓
    API Request: GET /api/market-data/BTC
         ↓
    Backend Symbol Mapper: BTC → BTCUSD  ← Auto-converts!
         ↓
    eToro API: Fetch BTCUSD data
         ↓
    ✅ Real market data returned
```

## Data Flow Diagram

```
┌──────────────┐
│   Frontend   │
│  (React UI)  │
└──────┬───────┘
       │ User types "BTC"
       │
       ↓
┌──────────────────────────────┐
│  API Request                 │
│  GET /api/market-data/BTC    │
└──────┬───────────────────────┘
       │
       ↓
┌──────────────────────────────┐
│  Symbol Mapper               │
│  normalize_symbol("BTC")     │
│  → "BTCUSD"                  │
└──────┬───────────────────────┘
       │
       ↓
┌──────────────────────────────┐
│  Market Data Manager         │
│  get_quote("BTCUSD")         │
└──────┬───────────────────────┘
       │
       ↓
┌──────────────────────────────┐
│  eToro API Client            │
│  Fetch real BTCUSD data      │
└──────┬───────────────────────┘
       │
       ↓
┌──────────────────────────────┐
│  Response                    │
│  {                           │
│    symbol: "BTCUSD",         │
│    price: 50500.00,          │
│    change: 2.5,              │
│    ...                       │
│  }                           │
└──────┬───────────────────────┘
       │
       ↓
┌──────────────────────────────┐
│  Frontend Display            │
│  Shows real Bitcoin price    │
└──────────────────────────────┘
```

## Symbol Mapping Examples

### Cryptocurrencies
```
User Types    →    Backend Uses    →    eToro API
─────────────────────────────────────────────────
BTC           →    BTCUSD          →    ✅ Real data
ETH           →    ETHUSD          →    ✅ Real data
DOGE          →    DOGEUSD         →    ✅ Real data
```

### Forex
```
User Types    →    Backend Uses    →    eToro API
─────────────────────────────────────────────────
EUR           →    EURUSD          →    ✅ Real data
GBP           →    GBPUSD          →    ✅ Real data
JPY           →    USDJPY          →    ✅ Real data
```

### Commodities
```
User Types    →    Backend Uses    →    eToro API
─────────────────────────────────────────────────
GOLD          →    XAUUSD          →    ✅ Real data
SILVER        →    XAGUSD          →    ✅ Real data
OIL           →    OILUSD          →    ✅ Real data
```

### Stocks (Unchanged)
```
User Types    →    Backend Uses    →    eToro API
─────────────────────────────────────────────────
AAPL          →    AAPL            →    ✅ Real data
MSFT          →    MSFT            →    ✅ Real data
GOOGL         →    GOOGL           →    ✅ Real data
```

## Frontend Component Changes

### Default Watchlist
```typescript
// Before ❌
const DEFAULT_WATCHLIST = ['EURUSD', 'BTCUSD', 'AAPL', 'MSFT', 'GOOGL'];
//                          ^^^^^^   ^^^^^^
//                          Not user-friendly

// After ✅
const DEFAULT_WATCHLIST = ['EUR', 'BTC', 'AAPL', 'MSFT', 'GOOGL'];
//                          ^^^   ^^^
//                          User-friendly!
```

### Input Placeholder
```typescript
// Before ❌
placeholder="Add symbol (e.g., AAPL)"

// After ✅
placeholder="Add symbol (e.g., BTC, ETH, AAPL)"
//                              ^^^  ^^^
//                              Shows crypto examples!
```

## User Experience

### Adding Symbols

```
┌─────────────────────────────────────┐
│ Add Symbol: [BTC          ] [Add]  │  ← User types "BTC"
└─────────────────────────────────────┘
         ↓
    Backend validates and normalizes
         ↓
┌─────────────────────────────────────┐
│ Symbol  │ Price      │ Change       │
├─────────┼────────────┼──────────────┤
│ BTC     │ $50,500.00 │ +2.5% ✅     │  ← Real data appears!
└─────────┴────────────┴──────────────┘
```

### Case Insensitive

```
User Input    →    Normalized    →    Result
────────────────────────────────────────────
BTC           →    BTCUSD        →    ✅ Works
btc           →    BTCUSD        →    ✅ Works
Btc           →    BTCUSD        →    ✅ Works
 BTC          →    BTCUSD        →    ✅ Works (trimmed)
```

## API Endpoints

### Get Quote
```bash
# User-friendly format ✅
curl http://localhost:8000/api/market-data/BTC

# eToro format (still works) ✅
curl http://localhost:8000/api/market-data/BTCUSD

# Both return the same data!
```

### Get Symbol Aliases
```bash
curl http://localhost:8000/api/market-data/symbol-aliases

# Returns:
{
  "aliases": {
    "BTC": "BTCUSD",
    "ETH": "ETHUSD",
    ...
  },
  "count": 25
}
```

## Testing Visualization

```
┌─────────────────────────────────────┐
│ Test Suite                          │
├─────────────────────────────────────┤
│ ✅ Symbol normalization (11 tests)  │
│ ✅ Integration tests (6 tests)      │
│ ✅ E2E verification                 │
│ ✅ No breaking changes              │
└─────────────────────────────────────┘
         ↓
    All 17 tests passing! 🎉
```

## Quick Reference

### For Users
```
Type This    Get This
─────────────────────
BTC      →   Bitcoin price
ETH      →   Ethereum price
GOLD     →   Gold price
EUR      →   Euro/USD rate
AAPL     →   Apple stock price
```

### For Developers
```python
# Backend
from src.utils.symbol_mapper import normalize_symbol
etoro_symbol = normalize_symbol("BTC")  # Returns "BTCUSD"
```

```typescript
// Frontend
const data = await api.getQuote('BTC');  // Just works!
```

---

**Visual Summary:** The symbol mapping system seamlessly converts user-friendly symbols to eToro format, enabling real market data to display correctly in the frontend.
