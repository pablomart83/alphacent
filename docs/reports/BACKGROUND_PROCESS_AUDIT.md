# Background Process Audit & eToro API Optimization

**Date**: 2026-02-21  
**Issue**: Backend crashes due to excessive eToro API calls and inefficient background processes

## Critical Findings

### 1. **Excessive eToro API Calls** 🔴 CRITICAL

**Problem**: We're hitting eToro's API for EVERY order status check, EVERY 5 seconds.

**Current Flow** (src/core/order_monitor.py):
```python
# Line 193: Called EVERY 5 seconds for EVERY submitted order
status_data = self.etoro_client.get_order_status(order.etoro_order_id)
```

**Impact**:
- With 56 orders in SUBMITTED state → 56 API calls every 5 seconds
- That's **672 API calls per minute** just for order monitoring
- eToro API likely rate-limiting or timing out
- Backend hangs waiting for responses

**Solution**: Use database as cache, only query eToro when necessary

---

### 2. **Background Process Schedule**

**Fast Cycle** (Every 5 seconds):
- ✅ Order monitoring (process_pending_orders)
- ✅ Order status checks (check_submitted_orders) ← **TOO AGGRESSIVE**
- ✅ Position sync (sync_positions) ← **TOO AGGRESSIVE**
- ✅ Trailing stop checks

**Slow Cycle** (Every 300 seconds = 5 minutes):
- ✅ Signal generation (fetches years of market data)
- ✅ Risk validation
- ✅ Order execution

**Problems**:
1. Order status checks every 5s is overkill - orders don't fill that fast
2. Position sync every 5s hammers eToro API unnecessarily
3. No caching strategy for order/position data

---

### 3. **Database vs eToro API Usage**

**Current State**: ❌ Database is write-only
- Orders saved to DB but never read from it
- Positions synced to DB but always fetched from eToro
- No caching layer

**What Should Happen**: ✅ Database as source of truth
- Read orders from DB (updated periodically from eToro)
- Read positions from DB (synced less frequently)
- Only query eToro for:
  - New order submission
  - Periodic status updates (every 30-60s, not 5s)
  - Critical operations (close position, modify SL/TP)

---

## Recommended Optimizations

### Priority 1: Reduce Order Monitoring Frequency ⚡

**Change**: Check order status every 30 seconds instead of 5 seconds

**Rationale**:
- Orders typically take 10-60 seconds to fill
- 5-second checks provide minimal benefit
- Reduces API calls by 83% (from 12/min to 2/min per order)

**Implementation**:
```python
# src/core/trading_scheduler.py
def __init__(self):
    self.fast_cycle_interval = 5  # Keep for trailing stops
    self.order_check_interval = 30  # New: separate interval for orders
    self._last_order_check = 0
```

---

### Priority 2: Implement Database-First Order Queries 🗄️

**Change**: Read orders from database, update from eToro periodically

**Current** (every API call):
```python
# ❌ Always queries eToro
status_data = self.etoro_client.get_order_status(order.etoro_order_id)
```

**Proposed** (database-first):
```python
# ✅ Read from database
session = db.get_session()
orders = session.query(OrderORM).filter(
    OrderORM.status == OrderStatus.SUBMITTED
).all()

# Only update from eToro every 30s
if time.time() - self._last_etoro_sync > 30:
    self._sync_orders_from_etoro(orders)
```

---

### Priority 3: Reduce Position Sync Frequency 📊

**Change**: Sync positions every 60 seconds instead of 5 seconds

**Rationale**:
- Position prices update in real-time on eToro's side
- We don't need second-by-second accuracy for autonomous trading
- Our strategies run every 5 minutes anyway
- Reduces API calls by 92%

**Implementation**:
```python
# src/core/trading_scheduler.py
async def _run_trading_cycle(self):
    # Fast path: Order monitoring (every 30s)
    if now - self._last_order_check >= self.order_check_interval:
        self._order_monitor.check_submitted_orders()
        self._last_order_check = now
    
    # Medium path: Position sync (every 60s)
    if now - self._last_position_sync >= 60:
        self._order_monitor.sync_positions()
        self._last_position_sync = now
    
    # Slow path: Signal generation (every 300s)
    if now - self._last_signal_check >= self.signal_check_interval:
        # ... signal generation ...
```

---

### Priority 4: Batch API Calls 📦

**Change**: Batch multiple order status checks into single API call

**Current**:
```python
# ❌ N API calls for N orders
for order in submitted_orders:
    status = self.etoro_client.get_order_status(order.etoro_order_id)
```

**Proposed**:
```python
# ✅ 1 API call for all orders
order_ids = [o.etoro_order_id for o in submitted_orders]
statuses = self.etoro_client.get_orders_batch(order_ids)  # New method
```

**Note**: Need to check if eToro API supports batch queries

---

### Priority 5: Smart Caching with TTL ⏱️

**Change**: Cache eToro responses with time-to-live

**Implementation**:
```python
class OrderMonitor:
    def __init__(self):
        self._order_cache = {}  # order_id -> (status, timestamp)
        self._cache_ttl = 30  # seconds
    
    def get_order_status(self, order_id: str):
        # Check cache first
        if order_id in self._order_cache:
            status, timestamp = self._order_cache[order_id]
            if time.time() - timestamp < self._cache_ttl:
                return status
        
        # Cache miss or expired - query eToro
        status = self.etoro_client.get_order_status(order_id)
        self._order_cache[order_id] = (status, time.time())
        return status
```

---

## Expected Impact

### Before Optimization:
- **Order checks**: 56 orders × 12 checks/min = **672 API calls/min**
- **Position syncs**: 1 sync × 12 times/min = **12 API calls/min**
- **Total**: ~684 API calls/min during active trading
- **Result**: Backend hangs, timeouts, crashes

### After Optimization:
- **Order checks**: 56 orders × 2 checks/min = **112 API calls/min** (-83%)
- **Position syncs**: 1 sync/min = **1 API call/min** (-92%)
- **Total**: ~113 API calls/min during active trading
- **Reduction**: **83% fewer API calls**
- **Result**: Stable backend, no timeouts

---

## Implementation Plan

### Phase 1: Quick Wins (30 minutes)
1. ✅ Change order check interval from 5s to 30s
2. ✅ Change position sync interval from 5s to 60s
3. ✅ Test with current 7 pending orders

### Phase 2: Database-First (1-2 hours)
1. ✅ Modify order_monitor to read from database
2. ✅ Add periodic eToro sync (every 30s)
3. ✅ Update position queries to use database
4. ✅ Test with multiple orders

### Phase 3: Advanced Caching (2-3 hours)
1. ✅ Implement TTL cache for order statuses
2. ✅ Add batch API call support (if eToro supports it)
3. ✅ Add cache invalidation on order state changes
4. ✅ Performance testing

---

## Trading System Considerations

### What Frequency Do We Actually Need?

**Order Monitoring**:
- Market orders: Fill in 1-10 seconds
- Limit orders: Fill in minutes to hours
- **Recommendation**: 30-second checks are sufficient

**Position Sync**:
- Prices update continuously on eToro
- Our strategies run every 5 minutes
- Trailing stops need current prices
- **Recommendation**: 60-second syncs for prices, 5-second checks for trailing stops (using cached data)

**Signal Generation**:
- Fetches years of historical data
- Computationally expensive
- **Current**: 5 minutes is appropriate

---

## Monitoring Commands

After implementing optimizations, monitor with:

```bash
# Check API call frequency
tail -f backend.log | grep "get_order_status\|get_positions"

# Count API calls per minute
tail -f backend.log | grep "get_order_status" | prl -c

# Monitor order processing
tail -f backend.log | grep "Order monitoring\|Position sync"
```

---

## Next Steps

1. **Immediate**: Implement Phase 1 (interval changes)
2. **Short-term**: Implement Phase 2 (database-first)
3. **Medium-term**: Implement Phase 3 (caching)
4. **Long-term**: Consider WebSocket connection to eToro for real-time updates (if available)
