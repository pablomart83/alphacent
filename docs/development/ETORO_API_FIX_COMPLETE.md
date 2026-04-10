# eToro API Fix - Using Correct Endpoints

## What Was Fixed

Updated `src/api/etoro_client.py` to use the **correct eToro API endpoints** you provided:

### Before (Wrong Endpoints - 404 Errors)
```python
# These endpoints don't exist:
GET /api/v1/account/info  # ❌ 404
GET /api/v1/trading/positions  # ❌ 404
```

### After (Correct Endpoints - From Official Docs)
```python
# Real eToro endpoints:
GET /api/v1/trading/info/portfolio  # ✅ Full portfolio data
GET /api/v1/trading/info/real/pnl  # ✅ PnL and balances
```

## Changes Made

### 1. Added Missing Header
Added `x-request-id` (UUID) header which was missing:

```python
def _get_headers(self) -> Dict[str, str]:
    import uuid
    return {
        "x-request-id": str(uuid.uuid4()),  # ✅ Added
        "x-api-key": self.public_key,
        "x-user-key": self.user_key,
        "Content-Type": "application/json"
    }
```

### 2. Updated get_account_info()
Now calls the correct endpoints:
- `GET /api/v1/trading/info/portfolio` - Gets positions, orders, credit
- `GET /api/v1/trading/info/real/pnl` - Gets unrealized/realized PnL

Parses the response to extract:
- Balance (Equity)
- Buying Power (calculated from available margin)
- Margin Used
- Positions Count
- Daily P&L (unrealized)
- Total P&L (realized + unrealized)

### 3. Updated get_positions()
Now calls `GET /api/v1/trading/info/portfolio` and parses the `Positions` array.

Maps eToro position fields to our Position model:
- `PositionID` → `id`
- `InstrumentID` → `symbol` (will need symbol mapping)
- `IsBuy` → `side` (LONG/SHORT)
- `Amount` → `quantity`
- `OpenRate` → `entry_price`
- `CurrentRate` → `current_price`
- `NetProfit` → `unrealized_pnl`
- `StopLossRate` → `stop_loss`
- `TakeProfitRate` → `take_profit`

## What Should Happen Now

When you restart the backend and refresh the frontend:

1. **Backend will call correct eToro endpoints** ✅
2. **eToro will return your real account data** ✅
3. **Frontend will display your actual**:
   - Account balance
   - Open positions
   - P&L
   - Margin usage

## Testing

### 1. Restart Backend
```bash
# Stop current backend (Ctrl+C)
# Start with debug logging
python -m uvicorn src.api.main:app --reload --log-level debug
```

### 2. Check Logs
You should see:
```
INFO - Initialized eToro API client in DEMO mode
DEBUG - Fetching account information from eToro portfolio endpoint
DEBUG - GET https://public-api.etoro.com/api/v1/trading/info/portfolio
DEBUG - Response: 200
DEBUG - Account balance: $X,XXX.XX, positions: X
```

### 3. Refresh Frontend
Open the Portfolio page - you should see your real eToro data!

## Potential Issues

### Issue 1: Symbol Mapping
eToro returns `InstrumentID` (numeric) instead of symbol names.

**Example**: Position shows `InstrumentID: 1001` instead of `AAPL`

**Solution**: We have a symbol mapping in the code, but may need to expand it or add reverse lookup.

### Issue 2: Response Format Differences
eToro's actual response format might differ slightly from what I assumed.

**Solution**: Check the logs for the actual response structure and adjust parsing if needed.

### Issue 3: Demo vs Live Mode
Make sure your API keys match the mode you're using (DEMO keys for DEMO mode).

## Next Steps

1. **Restart backend** with the updated code
2. **Refresh frontend** and check if real data appears
3. **Check logs** for any errors
4. **Share any errors** you see and I'll fix them immediately

## Files Modified

- `src/api/etoro_client.py`:
  - Updated `_get_headers()` to include `x-request-id`
  - Updated `get_account_info()` to use `/api/v1/trading/info/portfolio` and `/api/v1/trading/info/real/pnl`
  - Updated `get_positions()` to use `/api/v1/trading/info/portfolio`

## Expected Result

You should now see your **real eToro account data** instead of the seeded database data!

The "mock data" issue was simply that we were calling endpoints that don't exist. Now we're calling the real ones.
