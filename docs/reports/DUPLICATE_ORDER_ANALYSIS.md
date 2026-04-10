# Duplicate Order Prevention Analysis

**Date**: 2026-02-21  
**Context**: Investigating why strategies create multiple orders for the same symbol

---

## Current Duplicate Prevention Logic

### What EXISTS ✅

The `_coordinate_signals()` method in `src/core/trading_scheduler.py` (line 478) already implements duplicate prevention:

1. **Checks existing positions** before allowing new signals
2. **Filters signals** if a position already exists for that symbol/direction
3. **Coordinates multiple strategies** trading the same symbol (keeps highest confidence)

**Code Location**: `src/core/trading_scheduler.py:478-620`

**Logic**:
```python
# Check if we already have a position in this symbol/direction
existing_key = (symbol, direction)
if existing_key in existing_positions_map:
    # Skip all signals for this symbol/direction
    logger.info(f"Position duplicate check: filtering {len(signal_list)} new signal(s)")
    continue
```

---

## The Problem: Pending Orders Not Checked ❌

### Root Cause

The duplicate prevention logic checks **existing positions** but NOT **pending/submitted orders**.

**Scenario**:
1. Strategy generates ENTER_LONG signal for SPY at 10:00
2. Order created and submitted to eToro (status: SUBMITTED)
3. Order takes 30-60 seconds to fill
4. Strategy runs again at 10:05 (5 minutes later)
5. No position exists yet (order still pending)
6. **Duplicate prevention FAILS** - new signal allowed
7. Second order created for same symbol
8. Both orders fill → duplicate positions

**Evidence from your system**:
- 29 duplicate OIL orders
- 23 duplicate JPM orders
- All from same strategies running every 5 minutes

---

## Trading Best Practices

### Industry Standard: "One Trade Per Symbol Per Strategy"

**Rule**: A strategy should only have ONE active trade per symbol at a time.

**Definition of "active trade"**:
- Pending order (not yet filled)
- Submitted order (waiting for execution)
- Open position (filled and active)

**Rationale**:
1. **Risk Management**: Prevents over-concentration in one symbol
2. **Capital Efficiency**: Don't tie up capital in duplicate trades
3. **Strategy Intent**: Strategies are designed for one position at a time
4. **Performance Tracking**: Clean attribution (one position = one trade)

### Your System Type: Autonomous Swing Trading

**Characteristics**:
- Signal generation: Every 5 minutes
- Position holding: Hours to days
- Order execution: 30-60 seconds
- Strategy count: 27 active strategies

**Recommended Approach**:
1. **Check pending orders** before allowing new signals
2. **Check open positions** before allowing new signals (already done)
3. **Allow re-entry** only after position is closed
4. **Allow opposite direction** (LONG → SHORT or SHORT → LONG)

---

## Proposed Solution

### Option 1: Check Pending Orders (RECOMMENDED) ✅

**Implementation**:
```python
def _coordinate_signals(self, batch_results, strategy_map, existing_positions, pending_orders):
    # Build map of existing positions (already done)
    existing_positions_map = {}  # (symbol, side) -> [positions]
    
    # NEW: Build map of pending orders
    pending_orders_map = {}  # (strategy_id, symbol, side) -> [orders]
    for order in pending_orders:
        if order.status in [OrderStatus.PENDING, OrderStatus.SUBMITTED]:
            key = (order.strategy_id, order.symbol, order.side.value)
            if key not in pending_orders_map:
                pending_orders_map[key] = []
            pending_orders_map[key].append(order)
    
    # Check both positions AND pending orders
    for (symbol, direction), signal_list in signals_by_symbol_direction.items():
        # Check existing positions (already done)
        if (symbol, direction) in existing_positions_map:
            continue  # Skip
        
        # NEW: Check pending orders for each strategy
        filtered_signals = []
        for strategy_id, signal, strategy_name in signal_list:
            pending_key = (strategy_id, symbol, direction)
            if pending_key in pending_orders_map:
                logger.info(
                    f"Pending order check: {strategy_name} already has pending order for {symbol} {direction}"
                )
                continue  # Skip this strategy's signal
            filtered_signals.append((strategy_id, signal, strategy_name))
        
        # Continue with filtered signals...
```

**Pros**:
- Prevents duplicates from same strategy
- Allows different strategies to trade same symbol (with coordination)
- Minimal code changes
- Industry standard approach

**Cons**:
- Slightly more complex logic
- Need to pass pending orders to coordination method

---

### Option 2: Cooldown Period Per Strategy-Symbol

**Implementation**:
```python
# Track last order time per strategy-symbol
last_order_time = {}  # (strategy_id, symbol) -> timestamp

# Before allowing signal:
key = (strategy_id, symbol)
if key in last_order_time:
    time_since_last = now - last_order_time[key]
    if time_since_last < cooldown_period:  # e.g., 10 minutes
        logger.info(f"Cooldown: {strategy_name} traded {symbol} {time_since_last}s ago")
        continue  # Skip signal
```

**Pros**:
- Simple to implement
- Prevents rapid-fire orders
- Works even if order status tracking fails

**Cons**:
- Arbitrary cooldown period
- Might miss legitimate re-entry opportunities
- Doesn't address root cause

---

### Option 3: Strategy State Tracking

**Implementation**:
```python
# Add state to Strategy dataclass
class Strategy:
    active_trades: Dict[str, str]  # symbol -> order_id or position_id
    
# Before generating signals:
if symbol in strategy.active_trades:
    logger.info(f"{strategy.name} already has active trade for {symbol}")
    continue  # Don't generate signal
```

**Pros**:
- Clean separation of concerns
- Strategy "knows" what it's trading
- Easy to query strategy state

**Cons**:
- Requires database schema changes
- More complex state management
- Need to update state on order fill/close

---

## Recommendation: Option 1 (Check Pending Orders)

**Why**:
1. **Industry standard** - this is how professional trading systems work
2. **Minimal changes** - just extend existing coordination logic
3. **Preserves flexibility** - different strategies can still trade same symbol
4. **Addresses root cause** - checks both positions AND pending orders

**Implementation Steps**:
1. Update `_coordinate_signals()` to accept `pending_orders` parameter
2. Build `pending_orders_map` by (strategy_id, symbol, side)
3. Filter signals if strategy already has pending order for that symbol/side
4. Log filtered signals for visibility
5. Test with multiple strategies generating signals for same symbol

**Estimated Time**: 2-3 hours

---

## Additional Safeguards

### 1. Database Unique Constraint

Add unique constraint to prevent duplicate orders at database level:

```sql
CREATE UNIQUE INDEX idx_active_orders_per_strategy_symbol 
ON orders (strategy_id, symbol, side) 
WHERE status IN ('PENDING', 'SUBMITTED');
```

**Pros**: Fail-safe if logic fails  
**Cons**: Requires migration, might cause errors

---

### 2. Order Deduplication in OrderExecutor

Add check in `OrderExecutor.execute_signal()`:

```python
def execute_signal(self, signal, position_size, stop_loss_pct, take_profit_pct):
    # Check for existing pending orders
    existing_orders = self.db.query(OrderORM).filter(
        OrderORM.strategy_id == signal.strategy_id,
        OrderORM.symbol == signal.symbol,
        OrderORM.status.in_([OrderStatus.PENDING, OrderStatus.SUBMITTED])
    ).all()
    
    if existing_orders:
        logger.warning(f"Duplicate order prevented: {signal.strategy_id} already has pending order for {signal.symbol}")
        return None  # Don't create order
```

**Pros**: Last line of defense  
**Cons**: Happens after signal validation (wasted work)

---

### 3. Monitoring & Alerts

Add monitoring to detect duplicates:

```python
# In OrderMonitor
def check_for_duplicates(self):
    duplicates = self.db.query(OrderORM).filter(
        OrderORM.status.in_([OrderStatus.PENDING, OrderStatus.SUBMITTED])
    ).group_by(
        OrderORM.strategy_id, OrderORM.symbol, OrderORM.side
    ).having(
        func.count(OrderORM.id) > 1
    ).all()
    
    if duplicates:
        logger.error(f"DUPLICATE ORDERS DETECTED: {len(duplicates)} groups")
        # Send alert
```

**Pros**: Early detection  
**Cons**: Reactive, not preventive

---

## Testing Plan

### 1. Unit Tests
- Test `_coordinate_signals()` with pending orders
- Test filtering logic for same strategy
- Test allowing different strategies

### 2. Integration Tests
- Run 2 strategies trading same symbol
- Verify only 1 order created per strategy
- Verify coordination keeps highest confidence

### 3. E2E Tests
- Run full trading cycle with 27 strategies
- Monitor for duplicate orders
- Verify no duplicates in database

---

## Conclusion

**Current State**: Duplicate prevention EXISTS but only checks positions, not pending orders.

**Problem**: Strategies generate signals every 5 minutes, creating duplicate orders before previous orders fill.

**Solution**: Extend `_coordinate_signals()` to check pending orders per strategy-symbol-side.

**Priority**: HIGH - This is causing the 56 duplicate orders that crashed your backend.

**Estimated Time**: 2-3 hours to implement + 1-2 hours to test.

**Next Steps**:
1. Add task to spec (Phase 6.5.9 or new Phase 6.6)
2. Implement pending order check in `_coordinate_signals()`
3. Add database unique constraint as safeguard
4. Add monitoring for duplicate detection
5. Test with full trading cycle

---

**Status**: Analysis complete, ready for implementation.
