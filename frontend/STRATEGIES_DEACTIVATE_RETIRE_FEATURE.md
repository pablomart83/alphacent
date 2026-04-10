# Strategies Page - Activate, Deactivate & Retire Feature

## Overview
Added the ability to select strategies in the Active tab and change their status to "Activate" (for BACKTESTED strategies), "Deactivate" (for DEMO/LIVE strategies), or "Retire" (for any strategy) with full database integration.

## Changes Made

### 1. Updated Active Strategies Filter
**Location**: `frontend/src/pages/StrategiesNew.tsx`

Now includes BACKTESTED strategies in the Active tab so users can see and activate them:

```typescript
const activeStrategies = useMemo(() => 
  strategies.filter(s => s.status === 'DEMO' || s.status === 'LIVE' || s.status === 'BACKTESTED'),
  [strategies]
);
```

### 2. Added Bulk Activate Handler
```typescript
const handleBulkActivate = async () => {
  if (selectedStrategies.size === 0) return;
  
  if (!confirm(`Activate ${selectedStrategies.size} selected strategies? They will start generating signals.`)) {
    return;
  }

  let successCount = 0;
  let failCount = 0;

  for (const strategyId of selectedStrategies) {
    try {
      await apiClient.activateStrategy(strategyId, tradingMode!);
      successCount++;
    } catch (err) {
      console.error(`Failed to activate strategy ${strategyId}:`, err);
      failCount++;
    }
  }

  setSelectedStrategies(new Set());
  await fetchStrategies();
  
  toast.success(`Activated ${successCount} strategies${failCount > 0 ? `, ${failCount} failed` : ''}`);
};
```

### 3. Added Individual Activate Handler
```typescript
const handleActivate = async (strategyId: string) => {
  if (!confirm('Activate this strategy? It will start generating signals.')) {
    return;
  }

  try {
    await apiClient.activateStrategy(strategyId, tradingMode!);
    await fetchStrategies();
    toast.success('Strategy activated successfully');
  } catch (error) {
    console.error('Failed to activate strategy:', error);
    toast.error('Failed to activate strategy');
  }
};
```

### 4. Updated Dropdown Menu Actions (Conditional)
The dropdown menu now shows different options based on strategy status:

**For BACKTESTED strategies:**
```typescript
<DropdownMenuItem 
  onClick={() => handleActivate(row.original.id)}
  className="text-accent-green"
>
  <PlayCircle className="mr-2 h-4 w-4" />
  Activate
</DropdownMenuItem>
```

**For DEMO/LIVE strategies:**
```typescript
<DropdownMenuItem 
  onClick={() => handleDeactivate(row.original.id)}
  className="text-yellow-500"
>
  <Pause className="mr-2 h-4 w-4" />
  Deactivate
</DropdownMenuItem>
```

### 5. Updated Bulk Actions UI (Conditional)
Added smart bulk actions that show based on selected strategies:

```typescript
// Check what types of strategies are selected
const selectedStrategiesInfo = useMemo(() => {
  const selectedList = Array.from(selectedStrategies)
    .map(id => strategies.find(s => s.id === id))
    .filter(Boolean) as Strategy[];
  
  const hasBacktested = selectedList.some(s => s.status === 'BACKTESTED');
  const hasActive = selectedList.some(s => s.status === 'DEMO' || s.status === 'LIVE');
  
  return { hasBacktested, hasActive };
}, [selectedStrategies, strategies]);

// Show Activate button only if BACKTESTED strategies are selected
{selectedStrategiesInfo.hasBacktested && (
  <Button onClick={handleBulkActivate}>
    <PlayCircle className="h-4 w-4 mr-2" />
    Activate Selected
  </Button>
)}

// Show Deactivate button only if DEMO/LIVE strategies are selected
{selectedStrategiesInfo.hasActive && (
  <Button onClick={handleBulkDeactivate}>
    <Pause className="h-4 w-4 mr-2" />
    Deactivate Selected
  </Button>
)}
```

### 6. Updated Status Filter
Added BACKTESTED to the status filter dropdown:

```typescript
<SelectContent>
  <SelectItem value="all">All Statuses</SelectItem>
  <SelectItem value="BACKTESTED">Backtested</SelectItem>
  <SelectItem value="DEMO">Demo</SelectItem>
  <SelectItem value="LIVE">Live</SelectItem>
</SelectContent>
```

## Functionality Differences

### Activate
- **Status Change**: BACKTESTED → DEMO (or LIVE depending on mode)
- **Effect**: Strategy starts generating signals again
- **Reversible**: Yes, can be deactivated
- **Use Case**: Reactivate a previously deactivated strategy
- **Color**: Green (success)
- **Icon**: PlayCircle (▶)

### Deactivate
- **Status Change**: DEMO/LIVE → BACKTESTED
- **Effect**: Strategy stops generating signals but remains in database
- **Reversible**: Yes, can be reactivated
- **Use Case**: Temporarily pause a strategy without losing it
- **Color**: Yellow (warning)
- **Icon**: Pause (⏸)

### Retire
- **Status Change**: Any → RETIRED (or deleted)
- **Effect**: Strategy is permanently removed or marked as retired
- **Reversible**: No, permanent action
- **Use Case**: Permanently remove underperforming or unwanted strategies
- **Color**: Red (destructive)
- **Icon**: Trash (🗑)

## Database Integration

### API Endpoints Used
All three actions are fully integrated with the backend database:

1. **Activate**: `POST /api/strategies/{strategy_id}/activate?mode={mode}`
   - Backend: `src/api/routers/strategies.py` → `activate_strategy()`
   - Engine: `src/strategy/strategy_engine.py` → `activate_strategy()`
   - Updates strategy status to DEMO/LIVE in database
   - Adds to active strategies cache
   - Broadcasts WebSocket update

2. **Deactivate**: `POST /api/strategies/{strategy_id}/deactivate?mode={mode}`
   - Backend: `src/api/routers/strategies.py` → `deactivate_strategy()`
   - Engine: `src/strategy/strategy_engine.py` → `deactivate_strategy()`
   - Updates strategy status to BACKTESTED in database
   - Removes from active strategies cache
   - Broadcasts WebSocket update

3. **Retire**: `DELETE /api/strategies/{strategy_id}?mode={mode}`
   - Backend: `src/api/routers/strategies.py` → `retire_strategy()`
   - Engine: `src/strategy/strategy_engine.py` → `retire_strategy()`
   - Marks strategy as RETIRED or deletes from database
   - Removes from active strategies cache
   - Broadcasts WebSocket update

### Database Tables Affected
- **strategies** table: Status field updated
- **strategy_proposals** table: Related proposals may be affected
- **active_strategies** cache: Strategy added/removed from memory

## User Experience

### Active Tab Now Shows
- DEMO strategies (actively trading)
- LIVE strategies (actively trading)
- BACKTESTED strategies (ready to activate)

### Selection Flow
1. User navigates to Strategies page → Active tab
2. User sees all DEMO, LIVE, and BACKTESTED strategies
3. User selects one or more strategies using checkboxes
4. Bulk action toolbar appears showing:
   - Number of selected strategies
   - "Backtest Selected" button
   - "Activate Selected" button (if BACKTESTED strategies selected)
   - "Deactivate Selected" button (if DEMO/LIVE strategies selected)
   - "Retire Selected" button
   - "Clear Selection" button

### Individual Action Flow
1. User clicks the three-dot menu (⋮) on any strategy row
2. Dropdown menu shows:
   - View Details
   - Backtest
   - ---
   - **Activate** (green) - if status is BACKTESTED
   - **Deactivate** (yellow) - if status is DEMO/LIVE
   - Retire (red)

### Confirmation Dialogs
- **Activate**: "Activate X selected strategies? They will start generating signals."
- **Deactivate**: "Deactivate X selected strategies? They will be moved to BACKTESTED status and stop generating signals."
- **Retire**: "Retire X selected strategies? This action cannot be undone and will permanently remove them."

### Toast Notifications
- Success: "Activated X strategies", "Deactivated X strategies", or "Retired X strategies"
- Partial success: "Activated X strategies, Y failed"
- Error: "Failed to activate strategy", "Failed to deactivate strategy", or "Failed to retire strategy"

## Visual Design

### Color Coding
- **Activate button**: Green (`text-accent-green`, `border-accent-green/30`, `hover:bg-accent-green/10`)
- **Deactivate button**: Yellow (`text-yellow-500`, `border-yellow-500/30`, `hover:bg-yellow-500/10`)
- **Retire button**: Red (`variant="destructive"`, `text-accent-red`)

### Icons
- **Activate**: PlayCircle icon (▶)
- **Deactivate**: Pause icon (⏸)
- **Retire**: Trash icon (🗑)

## Smart Bulk Actions

The bulk action buttons are context-aware:
- If you select only BACKTESTED strategies → Shows "Activate Selected"
- If you select only DEMO/LIVE strategies → Shows "Deactivate Selected"
- If you select a mix → Shows both "Activate Selected" and "Deactivate Selected"
- "Retire Selected" always shows (works for any status)

## Testing Checklist

- [x] TypeScript compilation passes
- [ ] BACKTESTED strategies appear in Active tab
- [ ] Bulk activate works with BACKTESTED strategies
- [ ] Bulk deactivate works with DEMO/LIVE strategies
- [ ] Bulk retire works with any strategies
- [ ] Individual activate works from dropdown (BACKTESTED only)
- [ ] Individual deactivate works from dropdown (DEMO/LIVE only)
- [ ] Individual retire works from dropdown (any status)
- [ ] Dropdown shows correct action based on strategy status
- [ ] Bulk actions show/hide based on selected strategies
- [ ] Confirmation dialogs appear correctly
- [ ] Toast notifications show success/error messages
- [ ] Database updates correctly (status changes)
- [ ] WebSocket broadcasts strategy updates
- [ ] Strategies refresh after action completes
- [ ] Selection clears after bulk action
- [ ] Error handling works for failed operations
- [ ] Status filter includes BACKTESTED option

## Files Modified

1. **frontend/src/pages/StrategiesNew.tsx**
   - Updated `activeStrategies` filter to include BACKTESTED
   - Added `handleBulkActivate()` function
   - Added `handleActivate()` function
   - Added `selectedStrategiesInfo` computed property
   - Updated bulk actions UI with conditional buttons
   - Updated dropdown menu with conditional actions
   - Added BACKTESTED to status filter
   - Imported PlayCircle icon

## Backend Integration Verified

✅ **API Client**: `frontend/src/services/api.ts`
- `activateStrategy()` method exists
- `deactivateStrategy()` method exists
- `retireStrategy()` method exists

✅ **Backend Endpoint**: `src/api/routers/strategies.py`
- `POST /{strategy_id}/activate` endpoint exists
- `POST /{strategy_id}/deactivate` endpoint exists
- `DELETE /{strategy_id}` endpoint exists

✅ **Strategy Engine**: `src/strategy/strategy_engine.py`
- `activate_strategy()` method exists
- `deactivate_strategy()` method exists
- `retire_strategy()` method exists
- Database updates implemented
- WebSocket broadcasts implemented

## Summary

The Strategies page now provides users with three distinct options for managing strategies:

1. **Activate** - Start generating signals (for BACKTESTED strategies)
2. **Deactivate** - Temporarily pause strategies (for DEMO/LIVE strategies)
3. **Retire** - Permanently remove strategies (for any status)

All actions are available as:
- Bulk operations (select multiple strategies)
- Individual operations (dropdown menu per strategy)

The UI is smart and context-aware:
- Shows only relevant actions based on strategy status
- Bulk actions adapt to the types of strategies selected
- Clear visual distinction with color coding and icons

All actions are fully integrated with the backend database and include proper error handling, confirmation dialogs, and user feedback via toast notifications.

## Changes Made

### 1. Added Bulk Deactivate Handler
**Location**: `frontend/src/pages/StrategiesNew.tsx`

```typescript
const handleBulkDeactivate = async () => {
  if (selectedStrategies.size === 0) return;
  
  if (!confirm(`Deactivate ${selectedStrategies.size} selected strategies? They will be moved to BACKTESTED status and stop generating signals.`)) {
    return;
  }

  let successCount = 0;
  let failCount = 0;

  for (const strategyId of selectedStrategies) {
    try {
      await apiClient.deactivateStrategy(strategyId, tradingMode!);
      successCount++;
    } catch (err) {
      console.error(`Failed to deactivate strategy ${strategyId}:`, err);
      failCount++;
    }
  }

  setSelectedStrategies(new Set());
  await fetchStrategies();
  
  toast.success(`Deactivated ${successCount} strategies${failCount > 0 ? `, ${failCount} failed` : ''}`);
};
```

### 2. Added Individual Deactivate Handler
```typescript
const handleDeactivate = async (strategyId: string) => {
  if (!confirm('Deactivate this strategy? It will be moved to BACKTESTED status and stop generating signals.')) {
    return;
  }

  try {
    await apiClient.deactivateStrategy(strategyId, tradingMode!);
    await fetchStrategies();
    toast.success('Strategy deactivated successfully');
  } catch (error) {
    console.error('Failed to deactivate strategy:', error);
    toast.error('Failed to deactivate strategy');
  }
};
```

### 3. Updated Dropdown Menu Actions
Added "Deactivate" option to the individual strategy actions dropdown:

```typescript
<DropdownMenuItem 
  onClick={() => handleDeactivate(row.original.id)}
  className="text-yellow-500"
>
  <Pause className="mr-2 h-4 w-4" />
  Deactivate
</DropdownMenuItem>
<DropdownMenuItem 
  onClick={() => handleRetire(row.original.id)}
  className="text-accent-red"
>
  <Trash2 className="mr-2 h-4 w-4" />
  Retire
</DropdownMenuItem>
```

### 4. Updated Bulk Actions UI
Added "Deactivate Selected" button to the bulk actions toolbar:

```typescript
<Button
  onClick={handleBulkDeactivate}
  variant="outline"
  size="sm"
  className="text-yellow-500 border-yellow-500/30 hover:bg-yellow-500/10"
>
  <Pause className="h-4 w-4 mr-2" />
  Deactivate Selected
</Button>
<Button
  onClick={handleBulkRetire}
  variant="destructive"
  size="sm"
>
  <Trash2 className="h-4 w-4 mr-2" />
  Retire Selected
</Button>
```

## Functionality Differences

### Deactivate
- **Status Change**: DEMO/LIVE → BACKTESTED
- **Effect**: Strategy stops generating signals but remains in the database
- **Reversible**: Yes, can be reactivated later
- **Use Case**: Temporarily pause a strategy without losing it
- **Color**: Yellow (warning)
- **Icon**: Pause

### Retire
- **Status Change**: Any → RETIRED (or deleted)
- **Effect**: Strategy is permanently removed or marked as retired
- **Reversible**: No, permanent action
- **Use Case**: Permanently remove underperforming or unwanted strategies
- **Color**: Red (destructive)
- **Icon**: Trash

## Database Integration

### API Endpoints Used
Both actions are fully integrated with the backend database:

1. **Deactivate**: `POST /api/strategies/{strategy_id}/deactivate?mode={mode}`
   - Backend: `src/api/routers/strategies.py` → `deactivate_strategy()`
   - Engine: `src/strategy/strategy_engine.py` → `deactivate_strategy()`
   - Updates strategy status to BACKTESTED in database
   - Removes from active strategies cache
   - Broadcasts WebSocket update

2. **Retire**: `DELETE /api/strategies/{strategy_id}?mode={mode}`
   - Backend: `src/api/routers/strategies.py` → `retire_strategy()`
   - Engine: `src/strategy/strategy_engine.py` → `retire_strategy()`
   - Marks strategy as RETIRED or deletes from database
   - Removes from active strategies cache
   - Broadcasts WebSocket update

### Database Tables Affected
- **strategies** table: Status field updated
- **strategy_proposals** table: Related proposals may be affected
- **active_strategies** cache: Strategy removed from memory

## User Experience

### Selection Flow
1. User navigates to Strategies page → Active tab
2. User selects one or more strategies using checkboxes
3. Bulk action toolbar appears showing:
   - Number of selected strategies
   - "Backtest Selected" button
   - "Deactivate Selected" button (NEW)
   - "Retire Selected" button
   - "Clear Selection" button

### Individual Action Flow
1. User clicks the three-dot menu (⋮) on any strategy row
2. Dropdown menu shows:
   - View Details
   - Backtest
   - ---
   - Deactivate (NEW - yellow)
   - Retire (red)

### Confirmation Dialogs
- **Deactivate**: "Deactivate X selected strategies? They will be moved to BACKTESTED status and stop generating signals."
- **Retire**: "Retire X selected strategies? This action cannot be undone and will permanently remove them."

### Toast Notifications
- Success: "Deactivated X strategies" or "Retired X strategies"
- Partial success: "Deactivated X strategies, Y failed"
- Error: "Failed to deactivate strategy" or "Failed to retire strategy"

## Visual Design

### Color Coding
- **Deactivate button**: Yellow (`text-yellow-500`, `border-yellow-500/30`, `hover:bg-yellow-500/10`)
- **Retire button**: Red (`variant="destructive"`, `text-accent-red`)

### Icons
- **Deactivate**: Pause icon (⏸)
- **Retire**: Trash icon (🗑)

## Testing Checklist

- [x] TypeScript compilation passes
- [ ] Bulk deactivate works with multiple strategies
- [ ] Bulk retire works with multiple strategies
- [ ] Individual deactivate works from dropdown
- [ ] Individual retire works from dropdown
- [ ] Confirmation dialogs appear correctly
- [ ] Toast notifications show success/error messages
- [ ] Database updates correctly (status changes)
- [ ] WebSocket broadcasts strategy updates
- [ ] Strategies refresh after action completes
- [ ] Selection clears after bulk action
- [ ] Error handling works for failed operations

## Files Modified

1. **frontend/src/pages/StrategiesNew.tsx**
   - Added `handleBulkDeactivate()` function
   - Added `handleDeactivate()` function
   - Updated bulk actions UI
   - Updated dropdown menu actions
   - Enhanced confirmation messages

## Backend Integration Verified

✅ **API Client**: `frontend/src/services/api.ts`
- `deactivateStrategy()` method exists
- `retireStrategy()` method exists

✅ **Backend Endpoint**: `src/api/routers/strategies.py`
- `POST /{strategy_id}/deactivate` endpoint exists
- `DELETE /{strategy_id}` endpoint exists

✅ **Strategy Engine**: `src/strategy/strategy_engine.py`
- `deactivate_strategy()` method exists
- `retire_strategy()` method exists
- Database updates implemented
- WebSocket broadcasts implemented

## Summary

The Strategies page now provides users with two distinct options for managing active strategies:

1. **Deactivate** - Temporarily pause strategies (reversible)
2. **Retire** - Permanently remove strategies (irreversible)

Both actions are available as:
- Bulk operations (select multiple strategies)
- Individual operations (dropdown menu per strategy)

All actions are fully integrated with the backend database and include proper error handling, confirmation dialogs, and user feedback via toast notifications.
