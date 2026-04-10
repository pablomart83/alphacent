# Vibe Coding Fix - Testing Guide

## What Was Fixed

### Problem
1. When entering "buy 1 unit of BTC", the system was:
   - Converting 1 unit → $10 (default)
   - Then converting $10 → $412,075 (10 × BTC price)
   - Order failed due to insufficient balance

2. When entering "buy $50 of BTC", the system was:
   - Receiving $50
   - Then converting $50 → $2,060,375 (50 × BTC price)
   - Order failed due to insufficient balance

### Root Cause
The order placement API had faulty logic that assumed any quantity < 100 was in units and tried to convert it to dollars. This was wrong because:
- Dollar amounts like $10, $50 are < 100
- The conversion was happening AFTER vibe coding already set the correct amount

### Solution
1. **Removed faulty conversion in order API** (`src/api/routers/orders.py`)
   - Deleted the `if request.quantity < 100` logic
   - Order API now expects quantities to already be in dollars

2. **Added proper unit conversion in LLM service** (`src/llm/llm_service.py`)
   - Detects unit/share patterns (e.g., "1 unit", "10 shares")
   - Fetches current market price
   - Converts units to dollars BEFORE sending to order API
   - Dollar amounts pass through unchanged

## How It Works Now

### Example 1: "buy 1 unit of BTC"
```
1. User enters: "buy 1 unit of BTC"
2. Regex detects: "1 unit"
3. LLM translates: symbol = "BTC"
4. System fetches: BTC price = $41,207.50
5. Calculates: 1 × $41,207.50 = $41,207.50
6. Sends to API: quantity = $41,207.50
7. Order placed: BUY $41,207.50 of BTC
```

### Example 2: "buy $50 of BTC"
```
1. User enters: "buy $50 of BTC"
2. Regex detects: "$50"
3. LLM translates: symbol = "BTC"
4. Uses directly: $50 (no conversion)
5. Sends to API: quantity = $50
6. Order placed: BUY $50 of BTC
```

### Example 3: "buy 10 shares of AAPL"
```
1. User enters: "buy 10 shares of AAPL"
2. Regex detects: "10 shares"
3. LLM translates: symbol = "AAPL"
4. System fetches: AAPL price = $255.61
5. Calculates: 10 × $255.61 = $2,556.10
6. Sends to API: quantity = $2,556.10
7. Order placed: BUY $2,556.10 of AAPL
```

## Testing Instructions

### 1. Restart the backend server
The changes require a server restart to take effect:

```bash
# Stop the current server (Ctrl+C in the terminal running it)
# Or kill the process
pkill -f "uvicorn src.api.app:app"

# Start the server again
source venv/bin/activate
python -m uvicorn src.api.app:app --reload --log-level debug
```

### 2. Test via Vibe Coding UI

Try these commands in the Vibe Coding interface:

1. **Test dollar amount**: `buy $50 of BTC`
   - Expected: Order for $50 of BTC
   - Check logs: Should see "Quantity: $50.00"

2. **Test single unit**: `buy 1 unit of BTC`
   - Expected: Order for ~$41,000 of BTC (current BTC price)
   - Check logs: Should see "Converted 1.0 units of BTC to $41207.50"

3. **Test multiple shares**: `buy 10 shares of AAPL`
   - Expected: Order for ~$2,556 of AAPL (10 × AAPL price)
   - Check logs: Should see "Converted 10.0 units of AAPL to $2556.10"

### 3. Check the logs

Watch the server logs for these key messages:

```
# For unit conversion:
INFO - Converted 1.0 units of BTC to $41207.50 at price $41207.50

# For dollar amounts:
INFO - Translated vibe code: buy $50 of BTC -> ENTER_LONG BTC $50.0

# Order placement (no more wrong conversion):
INFO - Placing BUY order for BTC in DEMO mode
INFO - Executing signal: ENTER_LONG BTC (size: 50.0)
```

### 4. Verify in database

Check that orders have correct amounts:

```bash
sqlite3 alphacent.db "SELECT symbol, side, quantity, status FROM orders ORDER BY submitted_at DESC LIMIT 5;"
```

Expected results:
- `BTC|BUY|50.0|SUBMITTED` (for $50 order)
- `BTC|BUY|41207.5|SUBMITTED` (for 1 unit order)
- `AAPL|BUY|2556.1|SUBMITTED` (for 10 shares order)

## What Changed in Code

### File: `src/api/routers/orders.py`

**REMOVED** (lines 295-313):
```python
# Check if quantity looks like units (very small for crypto/stocks)
# If quantity < 100 and symbol is crypto or stock, assume it's units and convert
if request.quantity < 100:
    try:
        # Get current market price to convert units to dollars
        market_data = etoro_client.get_market_data(request.symbol)
        position_size_dollars = request.quantity * market_data.close
        logger.info(
            f"Converted {request.quantity} units of {request.symbol} "
            f"to ${position_size_dollars:.2f} at price ${market_data.close:.2f}"
        )
    except Exception as e:
        logger.warning(f"Failed to get market price for {request.symbol}, assuming quantity is in dollars: {e}")
        position_size_dollars = request.quantity
```

**REPLACED WITH**:
```python
# eToro API expects dollar amounts, not units/shares
# The quantity field should already be in dollars from vibe coding or frontend
position_size_dollars = request.quantity
```

### File: `src/llm/llm_service.py`

**ADDED** unit conversion logic in `translate_vibe_code()` method:
```python
# Check if user specified units/shares
import re
unit_pattern = r'(\d+(?:\.\d+)?)\s*(unit|share|coin)s?'
unit_match = re.search(unit_pattern, natural_language, re.IGNORECASE)

# ... (LLM processing)

elif unit_match:
    # User specified units/shares - need to convert to dollars
    num_units = float(unit_match.group(1))
    
    # Get current market price to convert
    etoro_client = EToroAPIClient(...)
    market_data = etoro_client.get_market_data(command.symbol)
    dollar_amount = num_units * market_data.close
    
    # Enforce minimum of $10
    if dollar_amount < 10.0:
        dollar_amount = 10.0
    
    command.quantity = dollar_amount
```

## Troubleshooting

### Issue: Orders still failing with large amounts

**Check**: Make sure the server was restarted after the code changes.

```bash
# Check if the old code is still running
grep "Check if quantity looks like units" src/api/routers/orders.py
# Should return nothing (line was removed)

# Restart server
pkill -f uvicorn
source venv/bin/activate
python -m uvicorn src.api.app:app --reload --log-level debug
```

### Issue: "Cannot convert units to dollars (no credentials)"

**Solution**: Make sure eToro credentials are configured:

```bash
# Check credentials
ls -la .etoro_credentials_*

# If missing, configure them through the UI or manually
```

### Issue: Minimum order validation failing

**Check**: eToro requires minimum $10 orders. The fix includes:
- Dollar amounts < $10 are adjusted to $10
- Unit conversions that result in < $10 are adjusted to $10

## Summary

✅ **Fixed**: Order API no longer does faulty unit-to-dollar conversion  
✅ **Fixed**: LLM service properly converts units to dollars  
✅ **Fixed**: Dollar amounts pass through unchanged  
✅ **Fixed**: All orders now use correct dollar amounts  

The system now correctly handles:
- Dollar amounts: `$50`, `$1000` → used directly
- Units: `1 unit`, `10 shares` → converted to dollars using market price
- Minimum validation: All amounts meet eToro's $10 minimum
