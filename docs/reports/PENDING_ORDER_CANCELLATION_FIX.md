# Pending Order Cancellation Fix

## Problem
When deleting strategies or cancelling orders from the frontend interface, pending orders were not being properly cancelled on eToro. Additionally, open positions from retired strategies were not being closed, leaving orphaned positions on eToro.

## Root Cause
1. The `retire_strategy()` and `permanently_delete_strategy()` functions were not cancelling pending orders before removing the strategy from the database
2. The `cancel_order()` API endpoint was not properly checking the return value from the eToro API cancellation call
3. Open positions from retired strategies were not being closed, creating "zombie positions"

## Solution

### Strategy Deletion/Retirement
Updated both `retire_strategy()` and `permanently_delete_strategy()` functions to:
1. Query for all pending/submitted orders associated with the strategy
2. Cancel each order via the eToro API (if the order has an eToro order ID)
3. Mark orders as CANCELLED in the local database
4. Mark open positions for closure approval (new workflow)
5. Handle errors gracefully (still mark as cancelled locally even if eToro API fails)

### Order Cancellation from Orders Page
Updated the `cancel_order()` API endpoint to:
1. Properly check the return value from `etoro_client.cancel_order()`
2. Log whether the eToro cancellation succeeded or failed
3. Provide clear feedback messages to the user about the cancellation status
4. Always update local database status even if eToro API fails

### Position Closure Approval Workflow (NEW)
Implemented a new approval workflow for closing positions from retired strategies:
1. When a strategy is retired, open positions are marked with `pending_closure = True`
2. A new "Pending Closures" tab in the Orders page shows these positions
3. Users can review and approve closures individually or in bulk
4. Upon approval, positions are closed via eToro API
5. Provides full visibility and control over position closures

## Files Modified

### Backend

#### 1. `src/models/orm.py`
- Added `pending_closure` (Boolean) field to PositionORM
- Added `closure_reason` (String) field to PositionORM
- Updated `to_dict()` method to include new fields

#### 2. `src/strategy/strategy_engine.py`
- Updated `retire_strategy()` method to:
  - Cancel pending orders before retiring
  - Mark open positions for closure approval
  - Log all actions for debugging

#### 3. `src/api/routers/strategies.py`
- Updated `permanently_delete_strategy()` endpoint to cancel pending orders before deletion

#### 4. `src/api/routers/orders.py`
- Updated `cancel_order()` endpoint to properly handle eToro API response

#### 5. `src/api/routers/account.py` (NEW ENDPOINTS)
- Added `GET /account/positions/pending-closures` - Get positions awaiting closure approval
- Added `POST /account/positions/{position_id}/approve-closure` - Approve single position closure
- Added `POST /account/positions/approve-closures-bulk` - Approve multiple position closures

### Frontend

#### 6. `frontend/src/types/index.ts`
- Added `pending_closure?: boolean` to Position interface
- Added `closure_reason?: string` to Position interface

#### 7. `frontend/src/services/api.ts`
- Added `getPendingClosures()` method
- Added `approvePositionClosure()` method
- Added `approveBulkClosures()` method

#### 8. `frontend/src/pages/OrdersNew.tsx`
- Added new "Pending Closures" tab
- Added state management for pending closures
- Added bulk selection for pending closures
- Added approval handlers (single and bulk)
- Integrated with existing Orders page UI

### Database

#### 9. `migrations/add_pending_closure_fields.py` (NEW)
- Migration script to add new columns to positions table
- Handles SQLite ALTER TABLE operations
- Checks for existing columns before adding

## Behavior

### Strategy Deletion/Retirement
- When a strategy is retired or permanently deleted:
  - All pending/submitted orders are cancelled on eToro
  - All open positions are marked for closure approval
  - Orders without eToro IDs are marked as cancelled locally
  - If eToro API fails, orders/positions are still updated locally
  - All actions are logged for debugging

### Order Cancellation from Orders Page
- When an order is cancelled from the Orders page:
  - If the order has an eToro order ID, it's cancelled via the eToro API
  - The return value is checked to verify cancellation success
  - User receives clear feedback about whether eToro cancellation succeeded
  - Order is always marked as CANCELLED locally, even if eToro API fails

### Position Closure Approval Workflow
- When positions are marked for closure:
  - They appear in the "Pending Closures" tab with full details
  - Users can see: symbol, side, quantity, entry/current price, P&L, strategy, reason
  - Users can select positions individually or all at once
  - Clicking "Close" or "Close Selected" executes market orders on eToro
  - Positions are removed from pending closures after successful closure
  - Clear success/failure feedback is provided

## User Experience

### Orders Page - New "Pending Closures" Tab
- Shows count of pending closures in tab badge
- Table with checkboxes for bulk selection
- Displays all relevant position information
- Shows closure reason (e.g., "Strategy retired: Poor performance")
- Individual "Close" button for each position
- Bulk "Close Selected" button when positions are selected
- Empty state message when no pending closures

## Testing

### Strategy Deletion
1. Create a strategy with pending orders and open positions (outside market hours)
2. Retire the strategy from the frontend
3. Verify pending orders are cancelled on eToro
4. Verify open positions appear in "Pending Closures" tab
5. Check logs to confirm all actions

### Order Cancellation
1. Create pending orders
2. Cancel them from the Orders page "All Orders" tab
3. Verify they're cancelled on eToro
4. Check logs for success/failure messages

### Position Closure Approval
1. Retire a strategy with open positions
2. Navigate to Orders page → "Pending Closures" tab
3. Verify positions are listed with correct information
4. Test individual closure approval
5. Test bulk closure approval
6. Verify positions are closed on eToro
7. Verify positions are removed from pending closures list

### Database Migration
1. Run migration script: `python migrations/add_pending_closure_fields.py`
2. Verify new columns exist in positions table
3. Test that existing positions still work correctly

## Industry Best Practices Alignment

This implementation follows industry best practices for position management:

1. **Risk Management**: Prevents orphaned positions that continue market exposure
2. **Capital Efficiency**: Frees up capital from retired strategies
3. **Audit Trail**: Complete logging of all closure actions
4. **User Control**: Approval workflow gives users visibility and control
5. **Clean State**: Ensures system state matches actual market exposure
6. **Graceful Degradation**: Handles API failures without breaking the system
