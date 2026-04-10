# Order Delete Feature Implementation

## Summary
Added functionality to permanently delete CANCELLED orders from the database for cleanup purposes.

## Changes Made

### Backend (src/api/routers/orders.py)
1. **DELETE /orders/{order_id}/permanent** - Delete a single CANCELLED order
   - Only allows deletion of orders with CANCELLED status
   - Returns error if order not found or not CANCELLED
   
2. **POST /orders/bulk-delete** - Delete multiple CANCELLED orders
   - Accepts list of order IDs
   - Only deletes CANCELLED orders
   - Returns success/fail counts and lists of deleted/failed order IDs

### Frontend API Client (frontend/src/services/api.ts)
1. **deleteOrderPermanent()** - Call single delete endpoint
2. **bulkDeleteOrders()** - Call bulk delete endpoint

### Frontend UI (frontend/src/pages/OrdersNew.tsx)
1. **handleDeleteOrder()** - Delete single order with confirmation
2. **handleBulkDeleteOrders()** - Delete multiple selected CANCELLED orders
3. **Updated dropdown menu** - Added "Delete Order" option for CANCELLED orders
4. **Updated bulk actions toolbar** - Added "Delete Selected" button

## Usage
- Individual orders: Click the three-dot menu on a CANCELLED order → "Delete Order"
- Bulk delete: Select multiple CANCELLED orders → Click "Delete Selected" button
- Both actions require confirmation before deletion
- Only CANCELLED orders can be deleted (enforced on both frontend and backend)

## Use Cases
- Clean up test orders that were cancelled locally
- Remove orders that were cancelled locally but couldn't be cancelled on eToro
- General database cleanup of old cancelled orders
