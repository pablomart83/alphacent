# Available Symbols in eToro

## Currently Available Symbols

Based on the eToro API response, these symbols are confirmed to work:

### Forex (3)
- **EUR** → EURUSD
- **GBP** → GBPUSD  
- **JPY** → USDJPY

### Cryptocurrencies (2)
- **BTC** → BTCUSD
- **ETH** → ETHUSD

### Stocks (5)
- **AAPL** → Apple
- **GOOGL** → Google
- **MSFT** → Microsoft
- **TSLA** → Tesla
- **AMZN** → Amazon

## Symbols NOT Available

These were in the original mapping but are NOT available in your eToro account:

### Cryptocurrencies
- XRP, LTC, BCH, ADA, DOT, LINK, XLM, DOGE, UNI, MATIC, SOL, AVAX

### Forex
- CHF, AUD, CAD, NZD

### Commodities
- GOLD (XAUUSD)
- SILVER (XAGUSD)
- OIL (OILUSD)
- BRENT (UKOUSD)

## Why Some Symbols Aren't Available

eToro API access depends on:
1. **Account Type**: Demo vs Live accounts have different symbols
2. **Region**: Some symbols are region-restricted
3. **Account Level**: Some symbols require verified accounts
4. **API Limitations**: Not all eToro symbols are available via API

## What Happens When You Try Unavailable Symbols

### Before (with mock data) ❌
```
User adds "SILVER"
→ Shows $150.50 (fake data)
→ User thinks it's real
```

### Now (proper error) ✅
```
User adds "SILVER"
→ HTTP 503 error
→ Message: "Instrument ID not found for XAGUSD"
→ User knows it's not available
```

## How to Add More Symbols

If you have access to more symbols in your eToro account:

1. Check what's available in your account
2. Update `src/utils/symbol_mapper.py`:
```python
SYMBOL_ALIASES: Dict[str, str] = {
    "BTC": "BTCUSD",
    "ETH": "ETHUSD",
    "YOUR_SYMBOL": "ETORO_FORMAT",  # Add here
}
```
3. Restart the backend: `./restart_backend.sh`

## Recommended Symbols to Use

For best results, stick to these confirmed working symbols:

**Crypto:**
- BTC (Bitcoin)
- ETH (Ethereum)

**Forex:**
- EUR (Euro/USD)
- GBP (British Pound/USD)
- JPY (USD/Japanese Yen)

**Stocks:**
- AAPL (Apple)
- GOOGL (Google)
- MSFT (Microsoft)
- TSLA (Tesla)
- AMZN (Amazon)

## Testing Symbol Availability

To test if a symbol is available:

```bash
# Replace SYMBOL with the symbol you want to test
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "http://localhost:8000/api/market-data/SYMBOL?mode=DEMO"

# If available: HTTP 200 with real data
# If not available: HTTP 503 with error message
```

## Summary

✅ **10 symbols confirmed working**
❌ **25+ symbols not available in current account**
✅ **System returns proper errors for unavailable symbols**
✅ **No fake data shown**

---

**Note:** The symbol mapper has been updated to only include confirmed available symbols. This prevents confusion when users try to add symbols that aren't accessible.
