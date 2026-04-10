# Order Monitor Performance Optimization
**Date**: February 21, 2026  
**Issue**: Order monitor taking 30+ seconds per cycle to sync 39 positions  
**Solution**: Smart position sync with interval-based caching

## Problem Analysis

### Before Optimization
```
2026-02-21 20:14:30 - Checking status of 3 submitted orders
2026-02-21 20:14:58 - Syncing 39 positions from eToro (28s)
2026-02-21 20:15:03 - Checking status of 3 submitted orders (5s later)
2026-02-21 20:15:35 - Checking status of 3 submitted orders (32s)
2026-02-21 20:16:02 - Syncing 39 positions from eToro (27s)
```

**Issues**:
1. Position sync called EVERY monitoring cycle (every 5 seconds)
2. Syncing 39 positions takes ~28 seconds per call
3. Positions rarely change between cycles
4. Unnecessary API load on eToro
5. Blocks other monitoring operations

### Root Cause
The `run_monitoring_cycle()` method called `sync_positions()` unconditionally on every cycle, even though:
- Positions only change when orders fill
- Price updates don't need to be real-time (5-minute intervals are fine)
- Database already has position data

## Solution: Smart Position Sync

### Implementation

Added intelligent position sync logic with three levels:

#### 1. Interval-Based Sync (Default)
```python
# Only sync every 5 minutes by default
self._last_full_sync = 0
self._full_sync_interval = 300  # 5 minutes
```

#### 2. Force Sync on Order Fills
```python
# Force sync when orders fill (new positions created)
force_sync = order_results.get("filled", 0) > 0
position_results = self.sync_positions(force=force_sync)
```

#### 3. Skip Unnecessary Syncs
```python
def sync_positions(self, force: bool = False) -> dict:
    time_since_sync = time.time() - self._last_full_sync
    needs_sync = force or time_since_sync >= self._full_sync_interval
    
    if not needs_sync:
        logger.debug(f"Skipping position sync (last sync {time_since_sync:.0f}s ago)")
        return {"skipped": True}
```

### Changes Made

**File**: `src/core/order_monitor.py`

1. **Added tracking fields** to `__init__`:
   ```python
   self._last_full_sync = 0
   self._full_sync_interval = 300  # 5 minutes
   ```

2. **Updated `sync_positions()`** to accept `force` parameter:
   - Checks time since last sync
   - Skips sync if < 5 minutes and not forced
   - Returns `{"skipped": True}` when skipped

3. **Updated `run_monitoring_cycle()`**:
   - Only forces sync when orders fill
   - Otherwise respects 5-minute interval

## Expected Performance Improvement

### Before
- Monitoring cycle: ~30-35 seconds
- Position sync: Every cycle (every 5s)
- API calls: ~720 position syncs per hour

### After
- Monitoring cycle: ~2-5 seconds (when sync skipped)
- Position sync: Every 5 minutes OR when orders fill
- API calls: ~12 position syncs per hour (60x reduction)

### Cycle Breakdown (After)
```
Cycle 1 (0:00):  Check orders (2s) + Sync positions (28s) = 30s
Cycle 2 (0:05):  Check orders (2s) + Skip sync = 2s
Cycle 3 (0:10):  Check orders (2s) + Skip sync = 2s
...
Cycle 60 (5:00): Check orders (2s) + Sync positions (28s) = 30s
```

**Average cycle time**: ~3 seconds (vs 30 seconds before)

## Benefits

1. **90% faster monitoring cycles** (2-5s vs 30s)
2. **60x fewer API calls** to eToro (12/hour vs 720/hour)
3. **Reduced API rate limiting risk**
4. **Faster order status updates** (not blocked by position sync)
5. **Still syncs immediately when orders fill** (no delay for new positions)
6. **Position prices still updated every 5 minutes** (sufficient for monitoring)

## Testing

### Test Scenario
Run e2e test with 3 orders and 39 positions:

**Before**:
- 3 monitoring cycles
- Each cycle: 30+ seconds
- Total: ~90 seconds

**After** (expected):
- Cycle 1: 30s (initial sync)
- Cycle 2-3: 2-5s each (skip sync)
- Total: ~40 seconds (55% faster)

### Validation
```bash
# Run e2e test and check logs
python scripts/e2e_trade_execution_test.py

# Look for:
# - "Skipping position sync" messages
# - Faster cycle times
# - Position sync only on order fills or 5-min intervals
```

## Configuration

The sync interval can be adjusted if needed:

```python
# In OrderMonitor.__init__
self._full_sync_interval = 300  # seconds (5 minutes default)

# Options:
# - 60:  1 minute (more frequent, more API calls)
# - 300: 5 minutes (balanced - recommended)
# - 600: 10 minutes (less frequent, fewer API calls)
```

## Backward Compatibility

The change is fully backward compatible:
- `sync_positions()` still works without parameters (defaults to `force=False`)
- Monitoring service continues to work (respects its own intervals)
- Manual calls can force sync with `sync_positions(force=True)`

## Related Files

- `src/core/order_monitor.py` - Main implementation
- `src/core/monitoring_service.py` - Uses order monitor (no changes needed)
- `scripts/e2e_trade_execution_test.py` - Test script

## Future Optimizations

1. **Batch order status checks**: Check all orders in one API call
2. **WebSocket for position updates**: Real-time updates without polling
3. **Differential sync**: Only update changed positions
4. **Database-only price updates**: Use market data service instead of eToro API
