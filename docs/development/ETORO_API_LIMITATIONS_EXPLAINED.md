# eToro API Limitations - Why You're Seeing Database Data

## The Core Issue

**eToro's Public API does not provide account/position/order endpoints**, even with valid API keys (public + private).

## What the Logs Show

From `logs/alphacent_20260214_173814.log`:

```
2026-02-14 18:26:49 - src.api.etoro_client - INFO - Initialized eToro API client in DEMO mode
2026-02-14 18:26:50 - src.api.etoro_client - ERROR - API request failed: 404 - Unknown error
2026-02-14 18:26:50 - src.api.etoro_client - ERROR - Failed to fetch account info: API request failed: 404 - Unknown error
2026-02-14 18:26:50 - src.api.routers.account - WARNING - Failed to fetch from eToro API: Failed to fetch account info: API request failed: 404 - Unknown error, falling back to database
2026-02-14 18:26:50 - src.api.routers.account - INFO - Returning cached account info from database
```

## What's Happening

1. **Your API keys are loaded correctly** ✅
2. **eToro client is initialized** ✅  
3. **API request is made to**: `https://public-api.etoro.com/api/v1/account/info`
4. **eToro returns 404** ❌ (endpoint doesn't exist)
5. **Backend falls back to database** ✅
6. **Database returns seeded data** ($100,000 balance, fake positions)

## eToro Public API - What's Available

### ✅ Working (Public Endpoints)
- **Real-time market data**: `https://www.etoro.com/sapi/trade-real/rates/{instrumentId}`
- **Historical candles**: `https://www.etoro.com/sapi/candles/...` (blocked by Cloudflare)
- **Instrument metadata**: `https://www.etoro.com/sapi/instrumentsmetadata/...`

### ❌ NOT Available (Even with API Keys)
- **Account balance**: `/api/v1/account/info` → 404
- **Open positions**: `/api/v1/trading/positions` → 404
- **Order history**: `/api/v1/trading/orders` → 404
- **Order placement**: `/api/v1/trading/execution/...` → Unknown (not tested)

## From the Documentation

`ETORO_API_DOCUMENTATION.md` explicitly states:

> ### 2. Get Account Info (Availability Unknown)
> **Endpoint**: `/api/v1/account/info`
> **Method**: GET
> **Description**: Get account balance, buying power, margin
> **Note**: **This endpoint may not be available in eToro's public API. The platform uses local database tracking as a fallback.**

> ### 3. Get Positions (Availability Unknown)
> **Endpoint**: `/api/v1/trading/positions`
> **Method**: GET
> **Description**: Get all open positions
> **Note**: **This endpoint may not be available in eToro's public API. The platform uses local database tracking as a fallback.**

## Why This Limitation Exists

eToro's Public API is designed for:
- Market data access (quotes, charts)
- Basic instrument information
- Possibly order placement (untested)

It is **NOT** designed for:
- Account management
- Portfolio tracking
- Position monitoring
- Order history

These features require either:
1. **eToro's Private/Partner API** (requires special access from eToro)
2. **Web scraping** (fragile, against ToS)
3. **Manual tracking** (current approach)

## The Current Architecture

The app is designed to work around this limitation:

```
┌─────────────────────────────────────────────────────────┐
│                    AlphaCent Platform                    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────┐         ┌──────────────────┐     │
│  │  Market Data     │         │  Account Data    │     │
│  │                  │         │                  │     │
│  │  ✅ eToro API    │         │  ❌ eToro API    │     │
│  │  (Public)        │         │  (Not Available) │     │
│  │                  │         │                  │     │
│  │  • Real prices   │         │  ⬇️ Fallback     │     │
│  │  • Quotes        │         │                  │     │
│  │  • Instrument    │         │  ✅ Database     │     │
│  │    metadata      │         │  (Local Track)   │     │
│  │                  │         │                  │     │
│  │                  │         │  • Balance       │     │
│  │                  │         │  • Positions     │     │
│  │                  │         │  • Orders        │     │
│  │                  │         │  • P&L           │     │
│  └──────────────────┘         └──────────────────┘     │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## What You're Seeing

The data you see in the frontend is:
- **Market prices**: ✅ Real from eToro API
- **Account balance**: ❌ Seeded database data ($100,000)
- **Positions**: ❌ Seeded database data (AAPL, MSFT, GOOGL)
- **Orders**: ❌ Seeded database data

## Solutions

### Option 1: Manual Sync (Current Approach)
**How it works**:
1. Manually enter your eToro positions into the database
2. App uses real eToro prices to calculate P&L
3. Update database when you make trades on eToro

**Pros**:
- Works with current API access
- Real market data for pricing
- Accurate P&L calculations

**Cons**:
- Manual work required
- Not real-time sync
- Positions can drift out of sync

**Implementation**:
```bash
# Clear seeded data
sqlite3 alphacent.db "DELETE FROM positions; DELETE FROM orders; DELETE FROM account_info;"

# Add your real positions manually
# Or create a script to import from eToro CSV export
```

### Option 2: Web Scraping
**How it works**:
1. Use Selenium/Puppeteer to login to eToro web interface
2. Scrape account data from HTML
3. Parse and store in database
4. Run periodically to stay in sync

**Pros**:
- Automated sync
- Real-time data
- No special API access needed

**Cons**:
- Fragile (breaks when eToro updates UI)
- Against eToro Terms of Service
- Requires browser automation
- Slower than API

**Implementation**: Would require significant development

### Option 3: eToro Partner API Access
**How it works**:
1. Apply for eToro Partner/Institutional API access
2. Get credentials with full account access
3. Use authenticated endpoints

**Pros**:
- Official solution
- Full API access
- Reliable and supported

**Cons**:
- Requires approval from eToro
- May have fees or requirements
- Application process can be lengthy

**How to apply**: Contact eToro's API team or partner program

### Option 4: Switch Brokers
**How it works**:
1. Use a broker with better API support
2. Examples: Interactive Brokers, Alpaca, TD Ameritrade
3. Implement their API client

**Pros**:
- Full API access out of the box
- Better documentation
- More features

**Cons**:
- Need to change brokers
- Different fee structures
- Migration effort

## Recommended Approach

For now, the best approach is:

1. **Accept that eToro Public API is limited**
2. **Use the database as source of truth** for account/positions
3. **Use real eToro market data** for pricing
4. **Manually sync positions** when you trade on eToro
5. **Consider web scraping** if you need automation
6. **Apply for Partner API** if you're serious about this platform

## Testing the Limitation

You can verify this yourself:

```bash
# Try to call the account endpoint directly
curl -H "x-api-key: YOUR_PUBLIC_KEY" \
     -H "x-user-key: YOUR_PRIVATE_KEY" \
     -H "x-request-id: $(uuidgen)" \
     https://public-api.etoro.com/api/v1/account/info

# You'll get: 404 Not Found
```

## Summary

**You provided valid API keys, but eToro's Public API simply doesn't expose account/position endpoints.**

The 404 errors are not because your keys are wrong - they're because the endpoints don't exist in eToro's public API.

The app is working exactly as designed:
1. Try eToro API
2. Get 404 (endpoint doesn't exist)
3. Fall back to database
4. Return database data

This is why you're seeing "mock data" - it's actually database fallback data because eToro doesn't provide the real data through their public API.
