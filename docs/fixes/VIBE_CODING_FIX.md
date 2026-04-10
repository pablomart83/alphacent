# Vibe Coding Order Placement Fix

## Issues Fixed

### 1. Missing `strategy_id` Field (422 Error)
The backend `/orders` endpoint requires a `strategy_id` field, but the frontend wasn't sending it.

**Fixed in**: `frontend/src/services/api.ts`
- Added `strategy_id: 'manual_vibe_coding'` to the order payload in `executeVibeCommand()`
- Updated `placeOrder()` method to accept optional `strategy_id` parameter (defaults to `'manual_order'`)
- Fixed the query parameter format to use `?mode=${mode}` instead of sending mode in the body

### 2. Authentication Required (401 Error)
The order placement requires authentication. You need to log in first.

## How to Use Vibe Coding Now

1. **Log in first** using the Login page with your credentials
2. **Navigate to Trading** page
3. **Use Vibe Coding** to place orders with natural language

## Example Commands

- "buy 10 shares of Apple"
- "sell some Bitcoin"
- "go long on Tesla with 5 shares"
- "short 100 shares of SPY"
- "buy MSFT at $350"

## Technical Details

### Backend Requirements (from `src/api/routers/orders.py`)
```python
class PlaceOrderRequest(BaseModel):
    strategy_id: str  # REQUIRED
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
```

### Frontend Changes
```typescript
// Before (missing strategy_id)
{
  symbol: command.symbol,
  side: 'BUY',
  type: 'MARKET',
  quantity: 1,
  mode: 'DEMO'
}

// After (includes strategy_id)
{
  strategy_id: 'manual_vibe_coding',
  symbol: command.symbol,
  side: 'BUY',
  order_type: 'MARKET',
  quantity: 1
}
```

## Next Steps

1. Restart your frontend dev server if it's running
2. Log in to the application
3. Try placing an order via Vibe Coding
4. The order should now be placed successfully and saved to the database
