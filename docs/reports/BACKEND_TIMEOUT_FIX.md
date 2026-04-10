# Backend Timeout Issue - Diagnosis and Fix

## Problem Summary

1. **Frontend timeout**: StrategiesNew.tsx timing out after 30 seconds when fetching strategies
2. **Backend hanging**: Backend server not responding to any requests
3. **Duplicate orders**: 29 duplicate OIL orders and 23 duplicate JPM orders in database
4. **Runaway process**: Multiprocessing worker consuming 45% CPU

## Root Causes

### 1. Order Monitor Blocking Startup
- Backend startup is blocked by order monitor checking 56 submitted orders
- eToro API is rate-limiting or timing out when checking order status
- This blocks the entire FastAPI application from starting

### 2. Duplicate Order Generation
- Two strategies creating duplicate orders:
  - Strategy `d144126f-e1c0-44ee-8fe1-f4dc15b0b594`: 28 OIL orders
  - Strategy `d8fc2ed8-a849-4e43-9e24-f97f16b3d183`: 23 JPM orders
- Likely caused by signal generation loop not checking for existing pending orders

### 3. Runaway Multiprocessing Worker
- Process PID 21149 was consuming 45.7% CPU
- Likely stuck in signal generation or order submission loop
- Killed manually

## Immediate Fixes Applied

1. ✅ Killed runaway multiprocessing worker (PID 21149)
2. ✅ Restarted backend server

## Required Fixes

### Fix 1: Make Order Monitor Non-Blocking on Startup

**File**: `src/core/trading_scheduler.py` or `src/api/app.py`

**Problem**: Order monitor runs synchronously during startup, blocking the server

**Solution**: Run order monitor in background thread/task after server starts

```python
# In src/api/app.py startup event
@app.on_event("startup")
async def startup_event():
    # ... existing startup code ...
    
    # Start trading scheduler in background (non-blocking)
    asyncio.create_task(trading_scheduler.start_async())
    
    logger.info("AlphaCent Backend Service started successfully")
```

### Fix 2: Add Duplicate Order Prevention

**File**: `src/core/signal_processor.py` or `src/execution/order_executor.py`

**Problem**: Strategies submitting duplicate orders for same symbol/side

**Solution**: Check for existing pending orders before creating new ones

```python
def should_create_order(strategy_id: str, symbol: str, side: OrderSide, session: Session) -> bool:
    """Check if order should be created (no duplicate pending orders)."""
    existing_pending = session.query(OrderORM).filter(
        OrderORM.strategy_id == strategy_id,
        OrderORM.symbol == symbol,
        OrderORM.side == side,
        OrderORM.status.in_([OrderStatus.PENDING, OrderStatus.SUBMITTED])
    ).first()
    
    if existing_pending:
        logger.warning(
            f"Skipping order creation - pending order already exists: "
            f"strategy={strategy_id}, symbol={symbol}, side={side}"
        )
        return False
    
    return True
```

### Fix 3: Add Order Monitor Timeout

**File**: `src/core/order_monitor.py`

**Problem**: Order monitor can hang indefinitely when checking eToro API

**Solution**: Add timeout to eToro API calls and batch processing

```python
async def check_submitted_orders_with_timeout(self, timeout: int = 30):
    """Check submitted orders with timeout."""
    try:
        await asyncio.wait_for(
            self.check_submitted_orders(),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.warning(f"Order status check timed out after {timeout}s")
    except Exception as e:
        logger.error(f"Error checking orders: {e}")
```

### Fix 4: Clean Up Duplicate Orders

**Immediate action needed**:

```sql
-- Cancel duplicate orders (keep only the first one for each strategy/symbol/side)
DELETE FROM orders 
WHERE id NOT IN (
    SELECT MIN(id) 
    FROM orders 
    WHERE status IN ('SUBMITTED', 'PENDING')
    GROUP BY strategy_id, symbol, side
)
AND status IN ('SUBMITTED', 'PENDING');
```

### Fix 5: Add Rate Limiting to Signal Generation

**File**: `src/core/trading_scheduler.py`

**Problem**: Signal generation can run too frequently, creating duplicate orders

**Solution**: Add cooldown period per strategy

```python
class TradingScheduler:
    def __init__(self):
        self.last_signal_time: Dict[str, datetime] = {}
        self.signal_cooldown = 60  # seconds
    
    def can_generate_signals(self, strategy_id: str) -> bool:
        """Check if enough time has passed since last signal generation."""
        last_time = self.last_signal_time.get(strategy_id)
        if last_time is None:
            return True
        
        elapsed = (datetime.now() - last_time).total_seconds()
        return elapsed >= self.signal_cooldown
```

## Testing Plan

1. Clean up duplicate orders in database
2. Restart backend with fixes
3. Monitor for duplicate order creation
4. Test frontend strategies page load time
5. Verify order monitor doesn't block startup

## Prevention

1. Add monitoring for duplicate orders
2. Add alerts when order count exceeds threshold
3. Add circuit breaker for eToro API calls
4. Implement proper async/await for all I/O operations
5. Add health check that doesn't depend on external APIs
