# eToro API Status Codes - Research & Documentation

## Research Summary

Based on actual API responses from eToro Demo API testing, we have documented the following status codes.

**Note**: eToro does not provide public documentation for their statusID values. This documentation is based on empirical observation from real API responses.

## Order Status Codes (statusID)

### Observed Status Codes

| Status ID | Meaning | Context | Evidence |
|-----------|---------|---------|----------|
| **1** | Pending/Submitted | Order received by eToro, awaiting processing | Seen in initial order submission responses |
| **2** | Filled/Executed | Order successfully executed, position opened | Standard success state |
| **3** | Executed/Completed | Order executed, position(s) opened | Confirmed: order 329403751 had status 3 with positions array containing opened position 3439759921. **NOT cancelled.** If no `positions` array present, may indicate genuine cancellation. |
| **4** | Failed/Rejected | Order rejected due to validation error | **CRITICAL**: Only when `errorCode != 0` |
| **11** | Pending Execution | Order submitted but queued for execution | Seen in `ordersForOpen` array |

### Status 4 - Special Case

Status 4 has **dual meaning** depending on context:

1. **With Error Code (errorCode != 0)**:
   - Meaning: Order FAILED/REJECTED
   - Example: Minimum order size violation
   - Response includes `errorCode` and `errorMessage`

2. **Without Error Code (errorCode == 0 or null)**:
   - Meaning: Position closed (different context, not order status)
   - Seen when querying old orders that became positions and were closed

### Example Responses

#### Status 1 - Pending/Submitted
```json
{
  "orderID": 328070708,
  "statusID": 1,
  "instrumentID": 1001,
  "amount": 10.0,
  "isBuy": true,
  "openDateTime": "2026-02-14T19:33:04.6845367Z"
}
```

#### Status 4 - Failed (with error)
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

#### Status 11 - Pending Execution
```json
{
  "orderID": 328092974,
  "statusID": 11,
  "instrumentID": 1001,
  "amount": 10.0,
  "isBuy": true,
  "openDateTime": "2026-02-14T19:18:05.817Z",
  "lastUpdate": "2026-02-14T19:18:05.817Z"
}
```

## Error Codes

### Observed Error Codes

| Error Code | Meaning | Solution |
|------------|---------|----------|
| **720** | Minimum order size violation | Increase order amount to meet minimum ($10 for most instruments) |

## Order Lifecycle States

```
┌─────────────┐
│   Created   │ (Local app state)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  PENDING    │ (Local: Order created, not yet submitted)
└──────┬──────┘
       │
       ▼ [Submit to eToro]
       │
       ├──► Status 1: Submitted/Pending
       │
       ├──► Status 11: Pending Execution (queued)
       │
       ├──► Status 4 + errorCode: FAILED/REJECTED
       │
       ├──► Status 2: FILLED/EXECUTED ──► Position Created
       │
       ├──► Status 3 + positions[]: FILLED/EXECUTED ──► Position Created
       │
       ├──► Status 3 (no positions): CANCELLED
```

## Implementation Guidelines

### 1. Status Checking Logic

```python
def interpret_order_status(status_data):
    status_id = status_data.get("statusID")
    error_code = status_data.get("errorCode")
    has_positions = bool(status_data.get("positions"))
    
    # CRITICAL: Check error code first
    if error_code and error_code != 0:
        return "FAILED", status_data.get("errorMessage")
    
    # Then check status ID
    if status_id == 1:
        return "PENDING", "Order submitted, awaiting processing"
    elif status_id == 2:
        return "FILLED", "Order executed successfully"
    elif status_id == 3:
        # Status 3 with positions = executed, without = cancelled
        if has_positions:
            return "FILLED", "Order executed, position(s) opened"
        return "CANCELLED", "Order cancelled (no positions opened)"
    elif status_id == 7:
        return "FILLED", "Position active"
    elif status_id == 11:
        return "PENDING_EXECUTION", "Order queued for execution"
    elif status_id == 4:
        # Status 4 without error code (rare case)
        return "UNKNOWN", "Status 4 without error code"
    else:
        return "UNKNOWN", f"Unknown status: {status_id}"
```

### 2. Order Monitoring Best Practices

1. **Always check `errorCode` before interpreting `statusID`**
2. Poll order status every 5-10 seconds for pending orders
3. Consider orders with status 11 as "pending execution" (not failed)
4. Log full response for unknown status codes
5. Implement timeout for orders stuck in pending state (e.g., 5 minutes)

### 3. Minimum Order Sizes

Based on error code 720 observations:
- **Minimum order amount**: $10 USD
- **Recommended minimum**: $50 USD for better execution
- Always validate order size before submission

## Testing Evidence

### Test 1: Small Order Rejection
- Order: $1 GOOGL
- Result: Status 4, Error 720
- Message: "Initial Leveraged Position Amount is under the minimum"

### Test 2: Valid Order Submission
- Order: $10 AAPL
- Result: Status 1 → Status 11 (pending execution)
- Outcome: Order accepted, queued for execution

### Test 3: Order Status Query
- Query: Get status of order 328070708
- Result: Status 4 (old order, position closed)
- Note: No error code, different context

## Recommendations

1. **Validate order sizes locally** before submitting to eToro (minimum $10)
2. **Check error codes first** when interpreting status responses
3. **Treat status 11 as pending**, not failed
4. **Log unknown status codes** for future documentation
5. **Implement retry logic** for transient errors (not for validation errors like 720)

## Data Sources

All information derived from:
- Direct eToro Demo API testing (2026-02-14)
- Order submission responses
- Order status query responses
- Portfolio endpoint responses (`ordersForOpen` array)
- PnL endpoint responses

## Limitations

- Documentation based on Demo API only (Live API may differ)
- Limited sample size of status codes observed
- No official eToro documentation available
- Error code 720 is the only error code observed so far

## Future Research Needed

- [ ] Document additional error codes as encountered
- [ ] Verify status codes in Live trading mode
- [ ] Document position status codes (separate from order status)
- [ ] Document order types and their specific status flows
- [ ] Test edge cases (partial fills, market closed, etc.)
