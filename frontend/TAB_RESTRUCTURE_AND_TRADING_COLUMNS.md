# Tab Restructure and Trading Activity Columns - Implementation Summary

## Overview
Restructured the Strategies page tabs from "Active/Retired" to "Active/Backtested" and added trading activity columns to the Active tab.

## Changes Made

### 1. Tab Restructure
- **Removed**: "Retired" tab (retired strategies are permanently deleted)
- **Added**: "Backtested" tab for strategies ready to be activated
- **Updated**: "Active" tab now only shows DEMO/LIVE strategies (actively trading)

### 2. Strategy Filtering
- `activeStrategies`: Filters strategies with status DEMO or LIVE
- `backtestedStrategies`: Filters strategies with status BACKTESTED
- Both lists are independently filtered by search, template, regime, and source

### 3. New Columns in Active Tab
Added three new columns to show trading activity:

#### Trades Column
- **Field**: `performance_metrics.total_trades`
- **Display**: Number of trades executed
- **Format**: Right-aligned, monospace font
- **Default**: Shows 0 if no trades

#### P&L Column
- **Field**: `performance_metrics.total_pnl`
- **Display**: Total profit/loss in currency
- **Format**: Right-aligned, monospace font, color-coded (green for positive, red for negative)
- **Default**: Shows "N/A" if no data

#### Last Order Date Column
- **Field**: `last_order_date` (new field on Strategy)
- **Display**: Date of last order execution
- **Format**: Localized date string, monospace font
- **Default**: Shows "Never" if no orders

### 4. Type Updates
Updated `frontend/src/types/index.ts`:

```typescript
export interface PerformanceMetrics {
  // ... existing fields
  total_pnl?: number;  // NEW: Total profit/loss
}

export interface Strategy {
  // ... existing fields
  last_order_date?: string;  // NEW: Last order execution date
}
```

### 5. Summary Metrics
- Updated "Total Retired" metric to "Total Backtested"
- Shows count of backtested strategies ready for activation

### 6. Bulk Actions
Both tabs support bulk actions with proper filtering:
- **Active Tab**: Activate (for BACKTESTED), Deactivate (for DEMO/LIVE), Retire, Backtest
- **Backtested Tab**: Activate, Re-Backtest, Retire

### 7. Select All Behavior
- Selecting "all" in Active tab selects all filtered active strategies across all pages
- Selecting "all" in Backtested tab selects all filtered backtested strategies across all pages

## Backend Requirements

The frontend expects the backend to return these fields:

1. **`performance_metrics.total_pnl`**: Total profit/loss for the strategy
2. **`last_order_date`**: ISO timestamp of the last order execution

If these fields are not provided by the backend, the UI will gracefully show:
- "N/A" for missing P&L
- "Never" for missing last order date
- 0 for missing trade count

## Build Status
✅ TypeScript compilation successful
✅ Vite build successful
✅ No runtime errors

## Testing Recommendations

1. **Verify Backend Data**: Ensure backend returns `total_pnl` and `last_order_date` fields
2. **Test Tab Switching**: Verify strategies appear in correct tabs based on status
3. **Test New Columns**: Verify trading activity columns display correctly
4. **Test Bulk Actions**: Verify bulk actions work correctly in both tabs
5. **Test Select All**: Verify "select all" selects strategies across all pages

## Files Modified
- `frontend/src/pages/StrategiesNew.tsx` - Main implementation
- `frontend/src/types/index.ts` - Type definitions

## Next Steps
- Backend team should ensure `total_pnl` and `last_order_date` are included in strategy responses
- Test with real data to verify column formatting and display
- Consider adding sorting by these new columns
