# Tradeable Instruments Implementation

## Summary

Implemented a comprehensive system to restrict trading to verified tradeable instruments in eToro demo accounts. The system now blocks orders for crypto, untradeable stocks (META, NVDA, V, IWM), and unknown symbols before they reach the eToro API.

## Changes Made

### 1. New Module: Tradeable Instruments Configuration
**File:** `src/core/tradeable_instruments.py`

Centralized configuration for tradeable instruments:
- **DEMO_ALLOWED_STOCKS**: 13 verified tradeable stocks (AAPL, MSFT, GOOGL, AMZN, TSLA, AMD, NFLX, DIS, BA, JPM, WMT, SPY, QQQ)
- **DEMO_BLOCKED_STOCKS**: 4 stocks blocked in demo (META, NVDA, V, IWM)
- **CRYPTO_SYMBOLS**: 10 cryptocurrencies (BTC, ETH, XRP, LTC, BCH, ADA, DOT, LINK, XLM, DOGE)
- **LIVE_ALLOWED_STOCKS**: All stocks (demo allowed + demo blocked)

Functions:
- `get_tradeable_symbols(mode)` - Get list of tradeable symbols
- `is_tradeable(symbol, mode)` - Check if symbol is tradeable
- `get_blocked_reason(symbol, mode)` - Get reason why symbol is blocked
- `get_default_watchlist(mode)` - Get recommended watchlist

### 2. Updated eToro Client
**File:** `src/api/etoro_client.py`

Modified `place_order()` method to:
- Check if instrument is tradeable before submission
- Block crypto orders with error 746 message
- Block untradeable stocks with error 714 message
- Block unknown symbols with helpful message
- Provide clear error messages for each case

### 3. New API Endpoint
**File:** `src/api/routers/market_data.py`

Added `/market-data/tradeable-symbols` endpoint:
- Returns list of tradeable symbols for given mode
- Returns default watchlist recommendations
- Used by frontend to populate symbol suggestions

### 4. Updated Frontend Component
**File:** `frontend/src/components/ManualOrderEntry.tsx`

Enhanced with:
- Auto-complete dropdown for symbol input
- Fetches tradeable symbols from API based on mode
- Shows only verified tradeable symbols
- Displays available symbols in help text
- Updates when trading mode changes

## Error Messages

### Cryptocurrency (Error 746)
```
Cannot place order for BTC: Cryptocurrency trading is not available in DEMO mode. 
Please use one of the verified tradeable instruments.
```

### Blocked Stock (Error 714)
```
Cannot place order for META: META is flagged as untradable in DEMO mode (error 714). 
Please use one of the verified tradeable instruments.
```

### Unknown Symbol
```
Cannot place order for XYZ: XYZ is not in the list of verified tradeable instruments. 
Please use one of the verified tradeable instruments.
```

## Testing

All tests passing:

### Backend Tests
```bash
python test_tradeable_instruments.py
✅ All tradeable instrument functions working correctly

python test_order_blocking.py
✅ AAPL: Order accepted
✅ BTC: Blocked with correct message
✅ META: Blocked with correct message
✅ NVDA: Blocked with correct message
✅ XYZ: Blocked with correct message
```

### Frontend Build
```bash
cd frontend && npm run build
✓ built in 958ms
```

## Verified Tradeable Symbols (DEMO Mode)

### Tech Stocks (7)
- AAPL - Apple Inc.
- MSFT - Microsoft Corporation
- GOOGL - Alphabet Inc.
- AMZN - Amazon.com Inc.
- TSLA - Tesla Inc.
- AMD - Advanced Micro Devices
- NFLX - Netflix Inc.

### Other Sectors (4)
- DIS - The Walt Disney Company
- BA - The Boeing Company
- JPM - JPMorgan Chase & Co.
- WMT - Walmart Inc.

### ETFs (2)
- SPY - SPDR S&P 500 ETF Trust
- QQQ - Invesco QQQ Trust (Nasdaq-100)

## Default Watchlist

### DEMO Mode
AAPL, MSFT, GOOGL, AMZN, TSLA, SPY, QQQ

### LIVE Mode
AAPL, MSFT, GOOGL, AMZN, TSLA, NVDA, META, SPY, QQQ

## User Experience Improvements

1. **Immediate Feedback**: Orders are blocked before submission, saving API calls and time
2. **Clear Error Messages**: Users understand exactly why their order was rejected
3. **Symbol Suggestions**: Auto-complete helps users find tradeable symbols
4. **Mode-Aware**: Symbol list updates when switching between DEMO and LIVE modes
5. **Visible Constraints**: Help text shows all available symbols

## Integration Points

### Order Placement
- Manual Order Entry component
- Vibe Coding (via order executor)
- Strategy Engine (when generating strategies)
- Direct API calls

### Market Data
- Dashboard watchlists
- Market data component
- Strategy research
- Symbol search

## Future Enhancements

1. **Dynamic Discovery**: Query eToro API for available instruments
2. **Caching**: Cache tradeable symbols to reduce API calls
3. **Admin Interface**: Allow admins to update tradeable symbols list
4. **Instrument Details**: Show more info about each symbol (sector, market cap, etc.)
5. **Smart Suggestions**: Recommend similar tradeable alternatives when blocked symbol is entered

## Files Modified

1. `src/core/tradeable_instruments.py` (new)
2. `src/api/etoro_client.py`
3. `src/api/routers/market_data.py`
4. `frontend/src/components/ManualOrderEntry.tsx`

## Files Created

1. `test_tradeable_instruments.py`
2. `test_order_blocking.py`
3. `ETORO_DEMO_ALLOWED_INSTRUMENTS.md`
4. `TRADEABLE_INSTRUMENTS_IMPLEMENTATION.md`
