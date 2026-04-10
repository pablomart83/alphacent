# GOOGL Order Analysis

## Order Details
- **Order ID**: af01b6f5-d352-41dc-a68d-0b0cd3242ca9
- **eToro Order ID**: 328122289
- **Symbol**: GOOGL
- **Side**: BUY
- **Amount**: $1.00
- **Status in DB**: SUBMITTED
- **Submitted**: 2026-02-14 19:35:35

## eToro Response

```json
{
  "orderID": 328122289,
  "statusID": 4,
  "errorCode": 720,
  "errorMessage": "Error opening position - Initial Leveraged Position Amount is under the minimum defined Leveraged Amount in the system. leveraged InitialPositionAmount: 1.00 MinimumPositionAmount: 10 (Dollars)",
  "instrumentID": 1002,
  "amount": 1.0,
  "units": 0.0
}
```

## Root Cause

**The order was REJECTED by eToro because $1 is below the minimum order size.**

eToro requires:
- **Minimum order size: $10**
- Your order: $1

## Status Code 4 Meaning

Status 4 has TWO meanings depending on context:
1. **With error code (errorCode != 0)**: Order FAILED/REJECTED
2. **Without error code**: Position closed (different context)

## Fix Applied

Updated `src/core/order_monitor.py` to:
1. Check for `errorCode` field in order status response
2. If `errorCode` exists and is not 0, mark order as FAILED
3. Log the error message for debugging

## Recommendation

**Increase minimum order size to $10 or more** to meet eToro's requirements.

The app should validate order sizes before submission:
- Minimum: $10
- Recommended: $50+ for better execution

## Summary

✅ Orders ARE being submitted to eToro
✅ eToro IS receiving and processing orders
❌ Small orders ($1-$9) are being REJECTED
✅ Order monitoring now detects and handles rejections

The integration is working correctly - eToro is just enforcing minimum order sizes.
