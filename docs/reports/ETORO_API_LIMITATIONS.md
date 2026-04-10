# eToro API Limitations

## Order Cancellation

### Issue
The eToro public API does not support programmatic order cancellation. When attempting to cancel an order via the API, you'll receive a 404 "Route not found" error.

### Current Behavior
When you cancel an order through the AlphaCent platform:
1. ✅ The system attempts to cancel via eToro API
2. ❌ eToro API returns 404 (endpoint not available)
3. ✅ The order is marked as CANCELLED in the local database
4. ✅ The order will not be processed further by AlphaCent
5. ⚠️ The order remains active on eToro platform

### Manual Cancellation Required
To actually cancel the order on eToro, you must:
1. Log into your eToro account at https://www.etoro.com
2. Navigate to your Portfolio
3. Find the pending order
4. Click "Cancel" to manually cancel it

### Why This Happens
eToro's public API has limited functionality and doesn't expose order cancellation endpoints. This is a known limitation of their API, not a bug in AlphaCent.

### Workaround
The system correctly marks orders as cancelled locally, preventing AlphaCent from processing them further. However, you need to manually cancel them on eToro to:
- Free up margin/buying power
- Prevent the order from executing if market conditions are met
- Keep your eToro account in sync with AlphaCent

### Future Improvements
Possible solutions:
1. **Web Scraping**: Use browser automation to cancel orders (complex, fragile)
2. **eToro Partnership**: Request API access with full order management
3. **User Notifications**: Send alerts when manual cancellation is needed
4. **Batch Cancellation Guide**: Provide step-by-step instructions for bulk cancellation

### Related Endpoints
The following eToro API endpoints are also not available:
- Order cancellation: `/api/v1/trading/orders/{id}` (DELETE)
- Order modification: `/api/v1/trading/orders/{id}` (PUT/PATCH)
- Some order status checks

### Recommendation
**Best Practice**: When retiring strategies or cancelling orders:
1. Use AlphaCent to mark orders as cancelled (prevents further processing)
2. Immediately log into eToro and manually cancel the orders
3. Verify cancellation on both platforms

This ensures your trading state is consistent across both systems.

## Position Closure

### Status
Position closure via API **IS SUPPORTED** ✅

The eToro API does support closing positions programmatically, which is why the "Pending Closures" workflow works correctly for positions.

## Summary

| Operation | API Support | AlphaCent Behavior |
|-----------|-------------|-------------------|
| Place Order | ✅ Supported | Works correctly |
| Check Order Status | ⚠️ Limited | Uses local tracking |
| Cancel Order | ❌ Not Supported | Marks cancelled locally, manual action required |
| Close Position | ✅ Supported | Works correctly |
| Modify Position (SL/TP) | ✅ Supported | Works correctly |

---

**Last Updated**: February 22, 2026
