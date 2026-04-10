# eToro API Integration Documentation

## Overview

This document describes the eToro API integration structure for the AlphaCent trading platform. The integration uses eToro's Public API with header-based authentication.

## Authentication

eToro uses **header-based authentication**, not token-based authentication.

### Required Headers

```python
{
    "x-request-id": "<unique-request-id>",  # UUID for each request
    "x-api-key": "<public-api-key>",        # Your eToro public API key
    "x-user-key": "<user-api-key>",         # Your eToro user API key
    "Content-Type": "application/json"
}
```

### No Token Management Required

Unlike traditional OAuth or JWT-based APIs, eToro does not use authentication tokens that need to be refreshed. The API keys are included in every request header.

## Base URLs

- **Authenticated Endpoints**: `https://public-api.etoro.com`
- **Public Data Endpoints**: `https://www.etoro.com`

## Rate Limiting

The platform implements conservative rate limiting to avoid 429 (Too Many Requests) errors:

- **Rate**: 1 request per second
- **Implementation**: Enforced before each API call
- **Retry Strategy**: Exponential backoff with configurable max retries

## Public Endpoints (No Authentication Required)

These endpoints are available without authentication and use the `https://www.etoro.com` base URL.

### 1. Real-Time Market Data

**Endpoint**: `/sapi/trade-real/rates/{instrumentId}`

**Method**: GET

**Description**: Get current bid/ask prices for an instrument

**Example**:
```
GET https://www.etoro.com/sapi/trade-real/rates/1001
```

**Response**:
```json
{
  "Rate": {
    "Ask": 150.25,
    "Bid": 150.20,
    "Date": "2024-02-14T10:30:00Z"
  }
}
```

### 2. Historical Candle Data

**Endpoint**: `/sapi/candles/candles/desc.json/{period}/{count}/{instrumentId}`

**Method**: GET

**Description**: Get historical OHLC candle data

**Parameters**:
- `period`: OneMinute, FiveMinutes, TenMinutes, FifteenMinutes, OneHour, OneDay, OneWeek
- `count`: Number of candles to retrieve (e.g., 100)
- `instrumentId`: eToro instrument ID

**Example**:
```
GET https://www.etoro.com/sapi/candles/candles/desc.json/OneDay/100/1001
```

**Response**:
```json
{
  "Candles": [
    {
      "FromDate": "2024-02-14T00:00:00Z",
      "Open": 149.50,
      "High": 151.00,
      "Low": 149.00,
      "Close": 150.25
    }
  ]
}
```

### 3. Instrument Metadata

**Endpoint**: `/sapi/instrumentsmetadata/V1.1/instruments/{instrumentId}`

**Method**: GET

**Description**: Get instrument details (name, type, exchange, etc.)

**Example**:
```
GET https://www.etoro.com/sapi/instrumentsmetadata/V1.1/instruments/1001
```

**Response**:
```json
{
  "InstrumentID": 1001,
  "Symbol": "AAPL",
  "InstrumentDisplayName": "Apple Inc.",
  "InstrumentTypeID": 1,
  "ExchangeID": 1
}
```

### 4. Instrument Search (May Not Be Available)

**Endpoint**: `/sapi/trade-data-real/instruments/search`

**Method**: GET

**Description**: Search for instruments by name or symbol

**Note**: This endpoint may not be publicly available. The platform falls back to local instrument ID mapping.

## Authenticated Endpoints (Require API Keys)

These endpoints require authentication headers and use the `https://public-api.etoro.com` base URL.

### 1. Place Market Order

**Endpoint**: `/api/v1/trading/execution/market-open-orders/by-amount`

**Method**: POST

**Description**: Place a market order by amount (in account currency)

**Request Body**:
```json
{
  "InstrumentID": 1001,
  "Amount": 1000.00,
  "IsBuy": true,
  "Leverage": 1,
  "OrderType": "MARKET"
}
```

**Response**:
```json
{
  "OrderID": "abc123",
  "Status": "PENDING"
}
```

### 2. Get Account Info (Availability Unknown)

**Endpoint**: `/api/v1/account/info`

**Method**: GET

**Description**: Get account balance, buying power, margin

**Note**: This endpoint may not be available in eToro's public API. The platform uses local database tracking as a fallback.

### 3. Get Positions (Availability Unknown)

**Endpoint**: `/api/v1/trading/positions`

**Method**: GET

**Description**: Get all open positions

**Note**: This endpoint may not be available in eToro's public API. The platform uses local database tracking as a fallback.

### 4. Get Order Status (Availability Unknown)

**Endpoint**: `/api/v1/trading/orders/{orderId}`

**Method**: GET

**Description**: Get status of a specific order

**Note**: This endpoint may not be available in eToro's public API. The platform uses local database tracking as a fallback.

### 5. Cancel Order (Availability Unknown)

**Endpoint**: `/api/v1/trading/orders/{orderId}`

**Method**: DELETE

**Description**: Cancel a pending order

**Note**: This endpoint may not be available in eToro's public API.

### 6. Close Position (Availability Unknown)

**Endpoint**: `/api/v1/trading/positions/{positionId}/close`

**Method**: POST

**Description**: Close an open position

**Note**: This endpoint may not be available in eToro's public API.

### 7. Social Insights (Availability Unknown)

**Endpoint**: `/api/v1/social/insights/{symbol}`

**Method**: GET

**Description**: Get social sentiment and trending data

**Note**: This endpoint may not be available in eToro's public API.

### 8. Smart Portfolios (Availability Unknown)

**Endpoint**: `/api/v1/smart-portfolios`

**Method**: GET

**Description**: Get list of available Smart Portfolios

**Note**: This endpoint may not be available in eToro's public API.

## Instrument ID Mapping

eToro uses numeric instrument IDs instead of symbols. The platform maintains a local mapping:

### Forex
- EURUSD: 1
- GBPUSD: 2
- USDJPY: 3
- AUDUSD: 4
- USDCAD: 5
- USDCHF: 6

### Cryptocurrencies
- BTCUSD: 100
- ETHUSD: 101
- LTCUSD: 102
- XRPUSD: 103
- BCHUSD: 104
- ADAUSD: 105
- DOTUSD: 106
- LINKUSD: 107

### US Stocks
- AAPL: 1001
- GOOGL: 1002
- MSFT: 1003
- TSLA: 1004
- AMZN: 1005
- META: 1006
- NVDA: 1007
- NFLX: 1008
- AMD: 1009
- INTC: 1010
- BABA: 1011
- DIS: 1012
- BA: 1013
- JPM: 1014
- V: 1015
- MA: 1016
- WMT: 1017
- PG: 1018
- JNJ: 1019
- UNH: 1020

### ETFs
- SPY: 2001
- QQQ: 2002
- IWM: 2003
- DIA: 2004
- VTI: 2005
- VOO: 2006
- GLD: 2007
- SLV: 2008

### Symbol Aliases

The platform supports common aliases:
- BTC → BTCUSD
- ETH → ETHUSD
- LTC → LTCUSD
- XRP → XRPUSD
- BCH → BCHUSD
- ADA → ADAUSD
- DOT → DOTUSD
- LINK → LINKUSD
- EUR → EURUSD
- GBP → GBPUSD
- JPY → USDJPY
- AUD → AUDUSD
- CAD → USDCAD
- CHF → USDCHF

## Local Database Fallback

For endpoints that may not be available in eToro's public API, the platform implements local database tracking:

### Account Information
- Tracked locally based on order fills and position updates
- Updated when orders are filled
- Calculated from position values and realized P&L

### Positions
- Tracked locally when orders are filled
- Updated with current market prices
- Closed when close orders are executed

### Orders
- Tracked locally when submitted
- Status updated based on eToro responses
- Historical record maintained for reporting

### Performance Metrics
- Calculated locally from position and order history
- Includes returns, Sharpe ratio, drawdown, win rate
- Attributed to specific strategies

## Error Handling

The platform implements comprehensive error handling:

### HTTP Status Codes
- **200**: Success
- **400**: Bad Request (invalid parameters)
- **401**: Unauthorized (invalid API keys)
- **403**: Forbidden (insufficient permissions)
- **404**: Not Found (invalid endpoint or instrument ID)
- **429**: Too Many Requests (rate limit exceeded)
- **500**: Internal Server Error (eToro API issue)
- **502/503/504**: Service Unavailable (eToro API down)

### Retry Strategy
- Automatic retry with exponential backoff for 429, 500, 502, 503, 504
- No retry for 400, 401, 403, 404 (client errors)
- Configurable max retries (default: 3)

### Logging
- All API requests logged with method, URL, parameters
- All API responses logged with status code and data
- Errors logged with full context for debugging
- Rate limiting events logged for monitoring

## Testing with Real Credentials

To test the eToro API integration:

1. **Obtain API Keys**: Get your public key and user key from eToro's developer portal
2. **Configure Credentials**: Add keys to Settings page in the platform
3. **Test Connection**: Use the connection status endpoint to verify authentication
4. **Test Market Data**: Fetch real-time quotes for known instruments (AAPL, BTC, etc.)
5. **Test Historical Data**: Fetch candle data for backtesting
6. **Test Order Placement**: Place a small test order in Demo mode
7. **Monitor Logs**: Check backend logs for detailed API interaction information

## Known Limitations

1. **Instrument Discovery**: No public search endpoint - must use local mapping or metadata endpoint
2. **Account Data**: Account info endpoint may not be available - using local tracking
3. **Position Data**: Positions endpoint may not be available - using local tracking
4. **Order Status**: Order status endpoint may not be available - using local tracking
5. **Social Features**: Social insights endpoint may not be available
6. **Smart Portfolios**: Smart Portfolios endpoint may not be available
7. **Volume Data**: Not provided in real-time or historical endpoints
8. **Order Types**: Limited to market orders via public API

## Future Enhancements

1. **Instrument Discovery**: Implement web scraping or manual discovery of new instrument IDs
2. **WebSocket Support**: Add real-time streaming for market data (if available)
3. **Advanced Orders**: Support limit, stop-loss, take-profit orders (if available)
4. **Portfolio Sync**: Periodic sync with eToro account (if endpoints become available)
5. **Social Features**: Integrate social trading features (if endpoints become available)
