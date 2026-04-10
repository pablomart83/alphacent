# eToro API Endpoints - Official Documentation

## Base URLs

### Production (Live Trading)
```
https://public-api.etoro.com
```

### Public Data (No Authentication Required)
```
https://www.etoro.com
```

## Authentication

eToro uses **header-based authentication** (not token-based like our current implementation).

### Required Headers
```
x-request-id: <UUID>        # Unique request ID
x-api-key: <PUBLIC_KEY>     # Your Public API Key
x-user-key: <USER_KEY>      # Your User Key
```

### Important Notes
- **No separate authentication endpoint** - credentials are sent with each request
- **No token refresh needed** - keys are long-lived
- Keys are generated from eToro Settings > Trading > API Key Management

## Available Endpoints

### 1. Account & Portfolio

**Get Watchlists**
```
GET https://public-api.etoro.com/api/v1/watchlists
Headers:
  x-request-id: <UUID>
  x-api-key: <PUBLIC_KEY>
  x-user-key: <USER_KEY>
```

### 2. Market Data

**Search Instruments**
```
GET https://www.etoro.com/api/search/v1/instruments
Query Parameters:
  - prefix: Search query (e.g., "AAPL")
  - startIndex: First result index (default: 0)
  - instrumentsCount: Number of results (default: 5)
  - format: "json"
```

**Get Instrument Details**
```
GET https://www.etoro.com/sapi/instrumentsmetadata/V1.1/instruments/{instrumentId}
```

**Get Instrument Price**
```
GET https://www.etoro.com/sapi/trade-real/rates/{instrumentId}
Response:
{
  "Rate": {
    "InstrumentID": 1234,
    "Ask": 150.25,
    "Bid": 150.20,
    "LastExecution": 150.22,
    "Date": "2026-02-14T15:30:00Z"
  }
}
```

**Get Historical Candles**
```
GET https://www.etoro.com/sapi/candles/candles/desc.json/{period}/{candlesNumber}/{instrumentId}
Parameters:
  - period: OneMinute, FiveMinutes, TenMinutes, FifteenMinutes, OneHour, OneDay, OneWeek
  - candlesNumber: Number of candles to return (e.g., 30)
  - instrumentId: eToro instrument ID
```

### 3. Trading

**Open Market Order (by Amount)**
```
POST https://public-api.etoro.com/api/v1/trading/execution/market-open-orders/by-amount
Headers:
  x-request-id: <UUID>
  x-api-key: <PUBLIC_KEY>
  x-user-key: <USER_KEY>
Body:
{
  "instrumentId": 1234,
  "amount": 1000.00,
  "leverage": 1,
  "stopLoss": 145.00,
  "takeProfit": 160.00
}
```

### 4. Social Trading

**Search Investors**
```
GET https://www.etoro.com/sapi/rankings/rankings/
Query Parameters:
  - period: CurrMonth, OneMonthAgo, CurrQuarter, CurrYear, etc.
  - blocked: false
  - istestaccount: false
  - optin: true
  - gainmin: Minimum gain percentage
  - gainmax: Maximum gain percentage
  - copiersmin: Minimum number of copiers
  - sort: Sort field (prefix with '-' for descending)
```

**Get Investor Stats**
```
GET https://www.etoro.com/sapi/rankings/cid/{userCid}/rankings
Query Parameters:
  - period: CurrMonth, OneMonthAgo, etc.
```

## Key Differences from Our Implementation

### Current Implementation (Incorrect)
```python
# Authentication endpoint (doesn't exist)
POST https://api-demo.etoro.com/v1/auth/login

# Token-based auth (not used by eToro)
Authorization: Bearer <token>
```

### Correct Implementation
```python
# No authentication endpoint needed
# Header-based auth on every request
x-api-key: <PUBLIC_KEY>
x-user-key: <USER_KEY>
x-request-id: <UUID>
```

## What Needs to Change

### 1. Remove Authentication Flow
- Remove `authenticate()` method
- Remove `AuthToken` class
- Remove token refresh logic

### 2. Update Request Headers
```python
def _get_headers(self) -> Dict[str, str]:
    return {
        "x-request-id": str(uuid.uuid4()),
        "x-api-key": self.public_key,
        "x-user-key": self.user_key,
        "Content-Type": "application/json"
    }
```

### 3. Update Base URLs
```python
# For authenticated endpoints (trading, portfolio)
BASE_URL = "https://public-api.etoro.com"

# For public data (market data, search)
PUBLIC_URL = "https://www.etoro.com"
```

### 4. Update Endpoint Paths

**Account Info** - Not directly available, need to use portfolio/positions
**Positions** - Not directly available in public API docs
**Market Data** - Use `/sapi/trade-real/rates/{instrumentId}`
**Historical Data** - Use `/sapi/candles/candles/desc.json/{period}/{candlesNumber}/{instrumentId}`
**Orders** - Use `/api/v1/trading/execution/market-open-orders/by-amount`

## Important Notes

### Demo vs Live
- The API documentation doesn't show separate demo/live URLs
- Both use `https://public-api.etoro.com`
- Demo vs Live is likely determined by the API keys used

### Account & Position Data
- The public API docs don't show explicit `/account` or `/positions` endpoints
- These may be available but not documented publicly
- Alternative: Use watchlists and portfolio endpoints

### Rate Limiting
- Not explicitly documented
- Implement conservative rate limiting (e.g., 1 request/second)
- Monitor for 429 responses

## Next Steps

1. Update `EToroAPIClient` class to use header-based auth
2. Remove token/authentication logic
3. Update base URLs
4. Update endpoint paths
5. Test with real credentials
6. Handle missing account/position endpoints gracefully

## References

- Official API Portal: https://api-portal.etoro.com/
- Authentication Guide: https://etoro-6fc30280.mintlify.app/getting-started/authentication
- OpenAPI Spec: https://www.etoro.com/app/openapi.yaml

