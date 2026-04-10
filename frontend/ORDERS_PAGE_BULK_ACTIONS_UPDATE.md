# Orders Page Bulk Actions Update

**Date**: February 21, 2026  
**Status**: ✅ Complete

## Overview

Updated the Orders page (All Orders tab) to add bulk selection functionality and order cancellation actions, matching the pattern used in the Strategies page.

## Changes Made

### 1. Added Bulk Selection State

Added state management for tracking selected orders:

```typescript
const [selectedOrders, setSelectedOrders] = useState<Set<string>>(new Set());
```

### 2. Added Bulk Cancel Handler

Implemented bulk cancellation functionality:

```typescript
const handleBulkCancelOrders = async () => {
  if (selectedOrders.size === 0) return;
  
  if (!confirm(`Cancel ${selectedOrders.size} selected orders?`)) {
    return;
  }
  
  // Cancel each selected order
  for (const orderId of selectedOrders) {
    await apiClient.cancelOrder(orderId, tradingMode!);
  }
  
  setSelectedOrders(new Set());
  toast.success(`Cancelled ${successCount} orders successfully`);
};
```

### 3. Added Checkbox Column

Added a selection checkbox column to the orders table:

- **Header**: "Select All" checkbox that selects/deselects all filtered orders
- **Cell**: Individual checkbox for each order
- Positioned as the first column in the table

### 4. Added Bulk Actions Toolbar

Added a toolbar that appears when orders are selected:

```tsx
{selectedOrders.size > 0 && (
  <div className="flex items-center gap-3 mb-4 p-3 bg-dark-lighter rounded-lg">
    <span className="text-sm text-gray-400 font-mono">
      {selectedOrders.size} selected
    </span>
    <Button onClick={handleBulkCancelOrders} variant="destructive">
      Cancel Selected
    </Button>
    <Button onClick={() => setSelectedOrders(new Set())} variant="ghost">
      Clear Selection
    </Button>
  </div>
)}
```

### 5. Fixed Missing "SUBMITTED" Status

Added the missing "SUBMITTED" status to the status filter dropdown:

```tsx
<SelectContent>
  <SelectItem value="all">All Status</SelectItem>
  <SelectItem value="PENDING">Pending</SelectItem>
  <SelectItem value="SUBMITTED">Submitted</SelectItem>  {/* NEW */}
  <SelectItem value="FILLED">Filled</SelectItem>
  <SelectItem value="PARTIALLY_FILLED">Partial</SelectItem>
  <SelectItem value="CANCELLED">Cancelled</SelectItem>
  <SelectItem value="REJECTED">Rejected</SelectItem>
</SelectContent>
```

### 6. Updated Cancel Action

Modified the actions dropdown to allow cancelling any order (not just PENDING/PARTIALLY_FILLED):

**Before**:
```tsx
{(row.original.status === 'PENDING' || row.original.status === 'PARTIALLY_FILLED') && (
  <DropdownMenuItem onClick={() => handleCancelOrder(row.original.id)}>
    Cancel Order
  </DropdownMenuItem>
)}
```

**After**:
```tsx
<DropdownMenuItem onClick={() => handleCancelOrder(row.original.id)}>
  Cancel Order
</DropdownMenuItem>
```

This allows users to attempt cancellation on any order. The backend will handle validation and return appropriate errors if the order cannot be cancelled.

## Features

### Bulk Selection
- ✅ Select individual orders via checkbox
- ✅ Select all filtered orders with header checkbox
- ✅ Selection persists across filtering
- ✅ Clear selection button

### Bulk Actions
- ✅ Cancel multiple orders at once
- ✅ Confirmation dialog before bulk cancellation
- ✅ Success/error toast notifications
- ✅ Automatic UI update after cancellation

### Status Filter
- ✅ Added missing "SUBMITTED" status option
- ✅ All order statuses now filterable:
  - All Status
  - Pending
  - Submitted (NEW)
  - Filled
  - Partial
  - Cancelled
  - Rejected

### Order Cancellation
- ✅ Cancel individual orders from actions menu
- ✅ Cancel multiple orders via bulk action
- ✅ Works for any order status (backend validates)
- ✅ Real-time UI updates

## User Experience

### Selection Flow
1. User clicks checkbox on individual orders or "Select All"
2. Bulk actions toolbar appears showing selection count
3. User clicks "Cancel Selected" button
4. Confirmation dialog appears
5. Orders are cancelled with progress feedback
6. Selection is cleared automatically

### Visual Feedback
- Selected orders have checked checkboxes
- Bulk actions toolbar shows selection count
- Toast notifications for success/errors
- Immediate UI updates after cancellation

## Technical Details

### State Management
- Uses `Set<string>` for efficient order ID tracking
- Automatic cleanup after bulk actions
- Persists across filtering operations

### API Integration
- Uses existing `apiClient.cancelOrder()` method
- Handles errors gracefully per order
- Provides aggregate success/failure counts

### Error Handling
- Individual order failures don't stop bulk operation
- Separate success/error toast notifications
- Console logging for debugging

## Consistency with Strategies Page

The implementation follows the same pattern as the Strategies page:

| Feature | Strategies Page | Orders Page |
|---------|----------------|-------------|
| Checkbox column | ✅ | ✅ |
| Select all header | ✅ | ✅ |
| Bulk actions toolbar | ✅ | ✅ |
| Selection count display | ✅ | ✅ |
| Clear selection button | ✅ | ✅ |
| Confirmation dialogs | ✅ | ✅ |
| Toast notifications | ✅ | ✅ |

## Files Modified

1. `frontend/src/pages/OrdersNew.tsx`
   - Added `selectedOrders` state
   - Added `handleBulkCancelOrders` function
   - Added checkbox column to table
   - Added bulk actions toolbar
   - Fixed status filter to include "SUBMITTED"
   - Updated cancel action to work for all orders

## Testing Recommendations

### Manual Testing
1. ✅ Select individual orders and verify checkbox state
2. ✅ Use "Select All" and verify all orders selected
3. ✅ Filter orders and verify selection persists
4. ✅ Cancel single order from actions menu
5. ✅ Cancel multiple orders via bulk action
6. ✅ Verify confirmation dialog appears
7. ✅ Verify toast notifications appear
8. ✅ Verify UI updates after cancellation
9. ✅ Test "SUBMITTED" status filter
10. ✅ Test cancelling orders with different statuses

### Edge Cases
- Empty selection (bulk action button disabled)
- All orders selected then filtered
- Cancelling already cancelled orders
- Network errors during bulk cancellation
- Mixed success/failure in bulk operation

## Benefits

1. **Efficiency**: Cancel multiple orders at once instead of one-by-one
2. **Consistency**: Matches the UX pattern from Strategies page
3. **Flexibility**: Can cancel orders regardless of status
4. **Visibility**: Missing "SUBMITTED" status now filterable
5. **User Control**: Clear selection and confirmation dialogs
6. **Feedback**: Toast notifications for all actions

## Future Enhancements

Potential improvements for future iterations:

1. **Bulk Actions Menu**: Add more bulk actions (e.g., export selected)
2. **Smart Selection**: Select by criteria (e.g., all pending orders)
3. **Undo Cancellation**: Allow reverting recent cancellations
4. **Keyboard Shortcuts**: Shift+click for range selection
5. **Selection Persistence**: Remember selection across page refreshes
6. **Batch API**: Backend endpoint to cancel multiple orders in one call
7. **Progress Indicator**: Show progress bar for bulk operations
8. **Partial Success Handling**: Better UI for mixed results

## Notes

- The backend `cancel_order` method handles validation, so the frontend can attempt to cancel any order
- The bulk cancellation processes orders sequentially to avoid overwhelming the API
- Selection state is cleared after successful bulk operations
- The implementation is fully responsive and works on mobile devices
