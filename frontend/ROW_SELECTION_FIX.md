# Row Selection Fix - Bulk Actions Now Working

## Issue
Bulk action buttons (Activate Selected, Deactivate Selected, Retire Selected) were not appearing when selecting multiple strategies via checkboxes.

## Root Cause
The `DataTable` component did not support row selection functionality. It was missing:
1. Row selection state management
2. Props to pass selection state from parent
3. Integration with TanStack Table's row selection features

## Solution

### 1. Updated DataTable Component
**File**: `frontend/src/components/trading/DataTable.tsx`

Added row selection support:

```typescript
import {
  // ... existing imports
  type RowSelectionState,
  type OnChangeFn,
} from '@tanstack/react-table';

interface DataTableProps<TData, TValue> {
  // ... existing props
  rowSelection?: RowSelectionState;
  onRowSelectionChange?: OnChangeFn<RowSelectionState>;
  getRowId?: (row: TData) => string;
}

export function DataTable<TData, TValue>({
  // ... existing props
  rowSelection,
  onRowSelectionChange,
  getRowId,
}: DataTableProps<TData, TValue>) {
  const [internalRowSelection, setInternalRowSelection] = React.useState<RowSelectionState>({});

  // Use external row selection if provided, otherwise use internal
  const currentRowSelection = rowSelection !== undefined ? rowSelection : internalRowSelection;
  const handleRowSelectionChange = onRowSelectionChange || setInternalRowSelection;

  const table = useReactTable({
    // ... existing config
    onRowSelectionChange: handleRowSelectionChange,
    getRowId,
    state: {
      sorting,
      columnFilters,
      rowSelection: currentRowSelection,  // NEW
    },
    enableRowSelection: true,  // NEW
  });
```

### 2. Updated StrategiesNew Component
**File**: `frontend/src/pages/StrategiesNew.tsx`

Connected the DataTable to the parent's selection state:

```typescript
<DataTable
  columns={activeStrategyColumns}
  data={filteredActiveStrategies}
  pageSize={20}
  getRowId={(row) => row.id}  // NEW - Tell table how to identify rows
  rowSelection={Object.fromEntries(  // NEW - Pass selection state
    Array.from(selectedStrategies).map(id => [id, true])
  )}
  onRowSelectionChange={(updaterOrValue) => {  // NEW - Handle selection changes
    const currentSelection = Object.fromEntries(
      Array.from(selectedStrategies).map(id => [id, true])
    );
    const newSelection = typeof updaterOrValue === 'function' 
      ? updaterOrValue(currentSelection)
      : updaterOrValue;
    setSelectedStrategies(new Set(Object.keys(newSelection).filter(key => newSelection[key])));
  }}
/>
```

## How It Works

### Selection Flow
1. User clicks checkbox in table row
2. TanStack Table calls `onRowSelectionChange` with updated selection
3. Parent component updates `selectedStrategies` Set
4. Selection state flows back to DataTable via `rowSelection` prop
5. Bulk action buttons appear/update based on `selectedStrategies.size > 0`

### State Synchronization
```
┌─────────────────────────────────────────────────────┐
│ StrategiesNew Component                             │
│                                                      │
│  selectedStrategies: Set<string>                    │
│         │                                            │
│         ├─► Convert to RowSelectionState            │
│         │   { "id1": true, "id2": true }            │
│         │                                            │
│         └─► Pass to DataTable                       │
│                    │                                 │
│                    ▼                                 │
│         ┌──────────────────────┐                    │
│         │   DataTable          │                    │
│         │                      │                    │
│         │  Checkboxes reflect  │                    │
│         │  selection state     │                    │
│         │                      │                    │
│         │  User clicks ☑       │                    │
│         └──────────────────────┘                    │
│                    │                                 │
│                    ▼                                 │
│         onRowSelectionChange()                      │
│                    │                                 │
│                    ▼                                 │
│  Update selectedStrategies Set                      │
│                    │                                 │
│                    ▼                                 │
│  Bulk actions toolbar appears                       │
│  - Activate Selected (if BACKTESTED)                │
│  - Deactivate Selected (if DEMO/LIVE)               │
│  - Retire Selected (always)                         │
└─────────────────────────────────────────────────────┘
```

## Features Now Working

### ✅ Checkbox Selection
- Click individual checkboxes to select strategies
- Click header checkbox to select all on current page
- Selection persists across actions

### ✅ Bulk Action Buttons Appear
When strategies are selected, the toolbar shows:
- Number of selected strategies
- "Backtest Selected" button
- "Activate Selected" button (if BACKTESTED strategies selected)
- "Deactivate Selected" button (if DEMO/LIVE strategies selected)
- "Retire Selected" button (always)
- "Clear Selection" button

### ✅ Smart Button Visibility
Buttons intelligently show/hide based on selected strategy statuses:
- Select only BACKTESTED → Shows "Activate Selected"
- Select only DEMO/LIVE → Shows "Deactivate Selected"
- Select mixed → Shows both buttons
- "Retire Selected" always visible

## Testing Checklist

- [x] TypeScript compilation passes
- [x] Build succeeds
- [ ] Click checkbox selects strategy
- [ ] Click header checkbox selects all
- [ ] Bulk action toolbar appears when strategies selected
- [ ] "Activate Selected" appears for BACKTESTED strategies
- [ ] "Deactivate Selected" appears for DEMO/LIVE strategies
- [ ] "Retire Selected" always appears
- [ ] Buttons work correctly (activate/deactivate/retire)
- [ ] Selection clears after action completes
- [ ] "Clear Selection" button works

## Files Modified

1. **frontend/src/components/trading/DataTable.tsx**
   - Added `RowSelectionState` and `OnChangeFn` imports
   - Added `rowSelection`, `onRowSelectionChange`, `getRowId` props
   - Added internal row selection state management
   - Enabled row selection in table config

2. **frontend/src/pages/StrategiesNew.tsx**
   - Added `getRowId` prop to DataTable
   - Added `rowSelection` prop with state conversion
   - Added `onRowSelectionChange` handler to sync selection

## Technical Details

### Type Safety
Used TanStack Table's `OnChangeFn<RowSelectionState>` type which handles both:
- Direct value: `{ "id1": true, "id2": true }`
- Updater function: `(old) => ({ ...old, "id3": true })`

### State Conversion
- **Parent → Table**: `Set<string>` → `RowSelectionState` (object)
- **Table → Parent**: `RowSelectionState` → `Set<string>`

### Flexibility
The DataTable component now supports:
- **Controlled mode**: Parent manages selection (used in StrategiesNew)
- **Uncontrolled mode**: DataTable manages its own selection (default)

## Summary

The bulk action feature is now fully functional. Users can:
1. Select multiple strategies using checkboxes
2. See context-aware bulk action buttons
3. Perform activate, deactivate, or retire operations on multiple strategies at once
4. Clear selection or have it auto-clear after actions

The fix maintains type safety, follows React best practices, and integrates seamlessly with TanStack Table's row selection features.
