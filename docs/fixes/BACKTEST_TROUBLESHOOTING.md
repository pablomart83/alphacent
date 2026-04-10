# Backtest Troubleshooting Guide

## Error: 500 Internal Server Error on Backtest

### Possible Causes

1. **Strategy not found in database**
2. **Strategy status is not PROPOSED**
3. **Missing market data for symbols**
4. **Vectorbt import/execution error**
5. **Database connection issue**

### How to Diagnose

#### Step 1: Check Backend Logs
Look at your backend terminal where you ran `python -m src.main`. When you click Backtest, you should see detailed error logs like:

```
ERROR: Backtest failed for {strategy_id}: {error message}
Traceback (most recent call last):
  ...
```

#### Step 2: Check Browser Network Tab
1. Open browser DevTools (F12)
2. Go to Network tab
3. Click Backtest button
4. Find the POST request to `/strategies/{id}/backtest`
5. Click on it and look at the "Response" tab
6. It should show the error message

#### Step 3: Verify Strategy Exists
Check if the strategy exists in the database:

```bash
# If you have sqlite3 installed
sqlite3 data/trading.db "SELECT id, name, status FROM strategies WHERE id='fd5cbe52-05e7-42fa-b04c-2859cf8bd46c';"
```

#### Step 4: Check Strategy Status
The strategy must have status 'PROPOSED' to be backtested. If it's already 'BACKTESTED', you'll get an error.

### Common Issues and Fixes

#### Issue 1: Strategy Already Backtested
**Error:** "Strategy must be PROPOSED to backtest (current status: BACKTESTED)"

**Fix:** The strategy was already backtested. You can only backtest PROPOSED strategies.

#### Issue 2: No Historical Data
**Error:** "No historical data available for {symbol}"

**Fix:** 
- Check if the symbols are valid (AAPL, GOOGL, etc.)
- Ensure market data service is working
- Try with different symbols

#### Issue 3: Vectorbt Not Installed
**Error:** "No module named 'vectorbt'"

**Fix:**
```bash
pip install vectorbt
```

#### Issue 4: Missing Dependencies
**Error:** Various import errors

**Fix:**
```bash
pip install -r requirements.txt
```

### Testing the Backtest System

To test if backtesting works at all, try using the bootstrap command (if dependencies are installed):

```bash
# This will generate and backtest strategies
curl -X POST http://localhost:8000/strategies/bootstrap \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_types": ["momentum"],
    "auto_activate": false,
    "min_sharpe": 1.0
  }'
```

### Next Steps

Please provide:
1. **Backend error logs** from the terminal
2. **Response body** from the Network tab in browser
3. **Strategy details** - what symbols does it have?

This will help identify the exact issue!
