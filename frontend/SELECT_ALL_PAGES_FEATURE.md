# Select All Across Pages Feature

## Overview
Updated the "Select All" checkbox functionality to select all strategies across all pages, not just the current page.

## Previous Behavior
- Clicking the header checkbox only selected strategies on the current page
- If you had 100 strategies across 5 pages, only the 20 on the current page would be selected
- Users had to manually go to each page and select strategies

## New Behavior
- Clicking the header checkbox selects **ALL** filtered strategies across **ALL** pages
- If you have 100 strategies across 5 pages, all 100 are selected with one click
- Works with filters - selects all strategies that match current filters

## Implementation

### Before
```typescript
header: ({ table }) => (
  <input
    type="checkbox"
    checked={table.getIsAllPageRowsSelected()}  // Only current page
    onChange={(e) => table.toggleAllPageRowsSelected(!!e.target.checked)}  // Only current page
  />
)
```

### After
```typescript
header: () => {
  const allSelected = filteredActiveStrategies.length > 0 && 
    filteredActiveStrategies.every(s => selectedStrategies.has(s.id));
  
  return (
    <input
      type="checkbox"
      checked={allSelected}  // All strategies
      onChange={(e) => {
        if (e.target.checked) {
          // Select ALL strategies across ALL pages
          setSelectedStrategies(new Set(filteredActiveStrategies.map(s => s.id)));
        } else {
          // Deselect all
          setSelectedStrategies(new Set());
        }
      }}
    />
  );
}
```

## How It Works

### Selection Logic
1. **Check if all selected**: Compares `filteredActiveStrategies` (all strategies matching filters) with `selectedStrategies` Set
2. **Select all**: When checked, adds ALL strategy IDs from `filteredActiveStrategies` to the Set
3. **Deselect all**: When unchecked, clears the Set

### Visual Feedback
- **Checked**: All filtered strategies are selected
- **Unchecked**: No strategies are selected
- **Indeterminate** (future enhancement): Some but not all strategies selected

## Use Cases

### Use Case 1: Select All Active Strategies
1. Navigate to Strategies → Active tab
2. Click header checkbox
3. **Result**: All DEMO, LIVE, and BACKTESTED strategies selected (across all pages)
4. Bulk action buttons appear
5. Can now activate/deactivate/retire all at once

### Use Case 2: Select All Filtered Strategies
1. Navigate to Strategies → Active tab
2. Filter by status: "BACKTESTED"
3. Click header checkbox
4. **Result**: All BACKTESTED strategies selected (across all pages)
5. "Activate Selected" button appears
6. Can activate all BACKTESTED strategies with one click

### Use Case 3: Select All from Specific Template
1. Navigate to Strategies → Active tab
2. Filter by template: "RSI Mean Reversion"
3. Click header checkbox
4. **Result**: All RSI Mean Reversion strategies selected (across all pages)
5. Can manage all strategies from that template

## Benefits

### 1. Efficiency
- **Before**: Select 20 strategies → Next page → Select 20 more → Repeat
- **After**: One click selects all

### 2. Bulk Operations
- Retire all underperforming strategies at once
- Activate all BACKTESTED strategies at once
- Deactivate all DEMO strategies at once

### 3. Filter Integration
- Works seamlessly with all filters
- Select all strategies matching specific criteria
- Example: "Select all BACKTESTED strategies from RSI template"

### 4. Clear Feedback
- Checkbox state reflects actual selection
- Bulk action counter shows total selected
- Example: "127 selected" (across all pages)

## Technical Details

### State Management
```typescript
// Parent component maintains selection
const [selectedStrategies, setSelectedStrategies] = useState<Set<string>>(new Set());

// Header checkbox checks if all filtered strategies are selected
const allSelected = filteredActiveStrategies.length > 0 && 
  filteredActiveStrategies.every(s => selectedStrategies.has(s.id));

// Select all adds all IDs to the Set
setSelectedStrategies(new Set(filteredActiveStrategies.map(s => s.id)));
```

### Performance
- Uses `Set` for O(1) lookup performance
- Efficient even with hundreds of strategies
- No performance impact on pagination

### Pagination Independence
- Selection persists across page changes
- Can select all, then navigate pages to review
- Bulk actions work on all selected, regardless of current page

## Example Scenarios

### Scenario 1: Clean Up All BACKTESTED Strategies
```
1. Filter: Status = "BACKTESTED"
2. Click "Select All" checkbox
3. Result: All 47 BACKTESTED strategies selected
4. Click "Retire Selected"
5. Confirm
6. All 47 strategies retired at once
```

### Scenario 2: Activate All Strategies from Template
```
1. Filter: Template = "MACD Momentum"
2. Filter: Status = "BACKTESTED"
3. Click "Select All" checkbox
4. Result: All 12 BACKTESTED MACD strategies selected
5. Click "Activate Selected"
6. Confirm
7. All 12 strategies activated at once
```

### Scenario 3: Deactivate All DEMO Strategies
```
1. Filter: Status = "DEMO"
2. Click "Select All" checkbox
3. Result: All 23 DEMO strategies selected
4. Click "Deactivate Selected"
5. Confirm
6. All 23 strategies moved to BACKTESTED
```

## User Experience

### Visual Feedback
- **Checkbox checked**: All filtered strategies selected
- **Counter**: "X selected" shows total count
- **Bulk buttons**: Appear immediately when selection > 0

### Clear Intent
- One click = Select everything matching current filters
- Works intuitively with filters
- No surprises - selects exactly what you see (across all pages)

### Undo
- Click checkbox again to deselect all
- Or click "Clear Selection" button
- Or perform action (selection auto-clears)

## Testing Checklist

- [x] TypeScript compilation passes
- [x] Build succeeds
- [ ] Click header checkbox selects all strategies (not just current page)
- [ ] Selection count shows total across all pages
- [ ] Bulk actions work on all selected strategies
- [ ] Navigate to different page - selection persists
- [ ] Filter strategies - select all only selects filtered ones
- [ ] Uncheck header checkbox - all deselected
- [ ] Perform bulk action - selection clears
- [ ] Works with 100+ strategies across multiple pages

## Files Modified

1. **frontend/src/pages/StrategiesNew.tsx**
   - Updated `activeStrategyColumns` select column header
   - Changed from `table.getIsAllPageRowsSelected()` to custom logic
   - Changed from `table.toggleAllPageRowsSelected()` to `setSelectedStrategies()`
   - Now uses `filteredActiveStrategies` instead of current page rows

## Comparison

| Feature | Before | After |
|---------|--------|-------|
| Select scope | Current page only | All pages |
| Max selection | 20 (page size) | Unlimited |
| Filter aware | No | Yes |
| Efficiency | Low (manual per page) | High (one click) |
| Use case | Small datasets | Any size dataset |

## Summary

The "Select All" checkbox now selects all strategies across all pages, making bulk operations much more efficient. Users can:

1. **Select all strategies** with one click (not just current page)
2. **Work with filters** to select specific subsets
3. **Perform bulk actions** on hundreds of strategies at once
4. **Save time** by avoiding manual page-by-page selection

This is especially useful for:
- Cleaning up large numbers of BACKTESTED strategies
- Activating multiple strategies at once
- Retiring underperforming strategies in bulk
- Managing strategies by template or regime

The feature maintains all existing functionality while dramatically improving efficiency for bulk operations.
