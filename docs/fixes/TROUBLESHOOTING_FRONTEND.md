# Troubleshooting Frontend Market Data

## Issue
Frontend not showing real eToro data even though backend is working correctly.

## Backend Verification ✅

The backend is working perfectly:

```bash
# Test EURUSD
curl -b cookies.txt "http://localhost:8000/market-data/EURUSD?mode=DEMO"
# Returns: price: 1.18734, source: "ETORO" ✅

# Test AAPL
curl -b cookies.txt "http://localhost:8000/market-data/AAPL?mode=DEMO"
# Returns: price: 255.61, source: "ETORO" ✅

# Test BTCUSD
curl -b cookies.txt "http://localhost:8000/market-data/BTCUSD?mode=DEMO"
# Returns: Real Bitcoin price, source: "ETORO" ✅
```

## Likely Causes

### 1. Browser Cache
The browser may have cached:
- Old JavaScript files
- Old localStorage data with old watchlist
- Old API responses

### 2. LocalStorage Watchlist
The old watchlist `['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'BTC']` may be stored in localStorage, overriding the new default `['EURUSD', 'BTCUSD', 'AAPL', 'MSFT', 'GOOGL']`.

### 3. Session/Cookie Issues
The frontend may not have a valid session cookie.

## Solutions

### Solution 1: Hard Refresh Browser (Recommended)
1. Open the browser at `http://localhost:5173`
2. Press `Cmd+Shift+R` (Mac) or `Ctrl+Shift+R` (Windows/Linux)
3. This clears the cache and reloads

### Solution 2: Clear LocalStorage
1. Open browser DevTools (F12 or Cmd+Option+I)
2. Go to "Application" tab (Chrome) or "Storage" tab (Firefox)
3. Find "Local Storage" → `http://localhost:5173`
4. Delete the key `alphacent_watchlist`
5. Refresh the page

### Solution 3: Clear All Site Data
1. Open browser DevTools (F12)
2. Go to "Application" tab
3. Click "Clear site data" button
4. Refresh the page
5. Login again with `admin` / `admin123`

### Solution 4: Incognito/Private Window
1. Open a new Incognito/Private window
2. Navigate to `http://localhost:5173`
3. Login with `admin` / `admin123`
4. Check if real data appears

### Solution 5: Check Browser Console
1. Open browser DevTools (F12)
2. Go to "Console" tab
3. Look for any errors (red text)
4. Look for network requests to `/market-data/`
5. Check if requests include `?mode=DEMO`

### Solution 6: Check Network Tab
1. Open browser DevTools (F12)
2. Go to "Network" tab
3. Refresh the page
4. Look for requests to `/market-data/EURUSD?mode=DEMO`
5. Click on the request
6. Check the "Response" tab
7. Verify it shows `"source": "ETORO"`

## Expected Behavior

### What You Should See:

**Market Data Section:**
- Symbol: EURUSD
- Price: ~$1.18734 (real eToro price)
- Change: $0.00 (0.00%)
- Volume: 0
- Badge: "✓ Live eToro Data" (green)

**Other Symbols:**
- BTCUSD: Real Bitcoin price
- AAPL: ~$255.61
- MSFT: Real price
- GOOGL: Real price

### What You Might See (If Not Working):

**Old Mock Data:**
- Symbol: AAPL
- Price: $150.50 (fake price)
- Change: $2.50 (1.69%)
- Volume: 1,000,000
- Badge: "⚠ Mock Data" (yellow) or no badge

## Debugging Steps

### Step 1: Verify Backend
```bash
# Login
curl -c cookies.txt -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Test EURUSD
curl -b cookies.txt "http://localhost:8000/market-data/EURUSD?mode=DEMO" | python3 -m json.tool
```

**Expected:** `"source": "ETORO"` and real price

### Step 2: Check Frontend Request
1. Open browser DevTools → Network tab
2. Refresh page
3. Filter by "market-data"
4. Check if requests include `?mode=DEMO`
5. Check response body for `"source": "ETORO"`

### Step 3: Check Console Errors
1. Open browser DevTools → Console tab
2. Look for red errors
3. Common issues:
   - CORS errors
   - 401 Unauthorized (need to login)
   - Network errors

### Step 4: Verify API Client
Open browser console and run:
```javascript
// Check if apiClient is loaded
console.log(window.apiClient);

// Manually test API call
fetch('http://localhost:8000/market-data/EURUSD?mode=DEMO', {
  credentials: 'include'
}).then(r => r.json()).then(console.log);
```

**Expected:** Should return real eToro data

## Quick Fix Script

Run this in the browser console to force update:

```javascript
// Clear old watchlist
localStorage.removeItem('alphacent_watchlist');

// Set new watchlist
localStorage.setItem('alphacent_watchlist', JSON.stringify(['EURUSD', 'BTCUSD', 'AAPL', 'MSFT', 'GOOGL']));

// Reload page
location.reload();
```

## Still Not Working?

### Check These:

1. **Is the backend running?**
   ```bash
   curl http://localhost:8000/health
   # Should return: {"status":"healthy","service":"alphacent-backend"}
   ```

2. **Is the frontend dev server running?**
   ```bash
   curl http://localhost:5173
   # Should return HTML
   ```

3. **Are you logged in?**
   - Check if you see the Dashboard
   - If not, go to login page and login with `admin` / `admin123`

4. **Check browser compatibility**
   - Use Chrome, Firefox, or Safari
   - Make sure JavaScript is enabled
   - Disable browser extensions that might block requests

5. **Check CORS**
   - Backend should allow `http://localhost:5173`
   - Check backend logs for CORS errors

## Manual Test

If all else fails, manually test the API:

1. Open `http://localhost:5173`
2. Login with `admin` / `admin123`
3. Open browser console (F12)
4. Run this code:

```javascript
// Import the API client (if not already available)
import { apiClient } from './services/api';

// Test getting a quote
apiClient.getQuote('EURUSD', 'DEMO')
  .then(data => {
    console.log('Market Data:', data);
    console.log('Source:', data.source);
    console.log('Price:', data.price);
  })
  .catch(err => console.error('Error:', err));
```

**Expected Output:**
```
Market Data: {symbol: "EURUSD", price: 1.18734, source: "ETORO", ...}
Source: ETORO
Price: 1.18734
```

## Contact

If none of these solutions work, please provide:
1. Screenshot of browser console (F12 → Console tab)
2. Screenshot of network tab showing `/market-data/` requests
3. Browser and version (e.g., Chrome 120)
4. Any error messages

## Summary

The backend is working perfectly and returning real eToro data. The issue is likely browser caching or localStorage. Try:
1. Hard refresh (Cmd+Shift+R)
2. Clear localStorage
3. Use incognito window
4. Check browser console for errors
