# eToro Demo Account - Allowed Instruments

## Summary

eToro demo accounts have restrictions on which instruments can be traded. This document lists tested instruments and their availability.

## ✅ ALLOWED STOCKS (13 tested)

### Tech Giants
- **AAPL** - Apple Inc.
- **MSFT** - Microsoft Corporation
- **GOOGL** - Alphabet Inc. (Google)
- **AMZN** - Amazon.com Inc.
- **TSLA** - Tesla Inc.
- **AMD** - Advanced Micro Devices Inc.
- **NFLX** - Netflix Inc.

### Other Sectors
- **DIS** - The Walt Disney Company
- **BA** - The Boeing Company
- **JPM** - JPMorgan Chase & Co.
- **WMT** - Walmart Inc.

### ETFs
- **SPY** - SPDR S&P 500 ETF Trust
- **QQQ** - Invesco QQQ Trust (Nasdaq-100)

## ❌ BLOCKED INSTRUMENTS

### Blocked Stocks (Error 714: "instrument is flagged untradable")
- **META** - Meta Platforms Inc. (Facebook)
- **NVDA** - NVIDIA Corporation
- **V** - Visa Inc.
- **IWM** - iShares Russell 2000 ETF

### Cryptocurrencies (Error 746: "opening position is disallowed")
- **BTC** - Bitcoin
- **ETH** - Ethereum
- **XRP** - Ripple
- **LTC** - Litecoin
- **BCH** - Bitcoin Cash
- **ADA** - Cardano
- **DOT** - Polkadot
- **LINK** - Chainlink
- **XLM** - Stellar
- **DOGE** - Dogecoin

## Error Codes

### Error 714
**Message:** "Error opening position- instrument(ID) is flagged untradable"

**Meaning:** The instrument exists in eToro's system but is marked as untradable in demo accounts. This typically applies to:
- Certain high-profile stocks (META, NVDA, V)
- Some ETFs (IWM)

**Solution:** These instruments may be available in LIVE accounts but are restricted in DEMO.

### Error 746
**Message:** "opening position is disallowed for Buy positions of this instrument"

**Meaning:** The instrument category is completely blocked in demo accounts. This applies to:
- All cryptocurrencies

**Solution:** Switch to LIVE mode to trade cryptocurrencies (if supported by eToro).

## Implementation

The system now includes pre-flight checks:

### Crypto Blocking (src/api/etoro_client.py)
```python
crypto_symbols = ["BTC", "ETH", "XRP", "LTC", "BCH", "ADA", "DOT", "LINK", "XLM", "DOGE"]
if self.mode == TradingMode.DEMO and symbol in crypto_symbols:
    raise EToroAPIError(
        f"Cryptocurrency trading is not available in DEMO mode. "
        f"{symbol} orders will be rejected by eToro (error 746). "
        f"Please switch to LIVE mode to trade cryptocurrencies."
    )
```

### Error 714 Handling
Currently, error 714 is caught by the order monitor after submission. Orders are marked as FAILED with the error message.

## Recommendations

### For Users
1. **Stick to major stocks** like AAPL, MSFT, GOOGL, AMZN, TSLA for demo trading
2. **Avoid crypto** in demo mode - it's completely blocked
3. **Test carefully** with new symbols - some popular stocks (META, NVDA) are blocked
4. **Use LIVE mode** if you need to trade blocked instruments

### For Developers
1. **Add error 714 pre-flight check** similar to crypto blocking
2. **Maintain allowlist** of known working symbols
3. **Cache instrument availability** to avoid repeated API calls
4. **Provide clear error messages** when instruments are blocked

## Testing Methodology

Each instrument was tested by:
1. Placing a $10 market order
2. Waiting 2 seconds
3. Checking order status for error codes
4. Recording success or failure with error details

## Future Enhancements

1. **Instrument Validation API**
   - Add endpoint to check if symbol is tradeable before order placement
   - Cache results to improve performance

2. **Smart Symbol Suggestions**
   - Frontend autocomplete with only allowed symbols
   - Filter out blocked instruments in demo mode

3. **Error 714 Pre-flight Check**
   - Maintain list of known blocked symbols
   - Block orders before submission like crypto check

4. **Dynamic Instrument Discovery**
   - Query eToro API for available instruments
   - Update allowlist automatically

## Notes

- This list is based on testing as of February 2026
- eToro may change instrument availability without notice
- Some instruments may be temporarily unavailable due to market conditions
- LIVE accounts may have different restrictions
