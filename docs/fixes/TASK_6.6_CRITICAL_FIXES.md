# Task 6.6: Critical Fixes for Real Trade Execution

## Test Results Summary

✅ **ACCEPTANCE CRITERIA MET**: At least 1 autonomous order placed and visible in the database.

However, there are **critical bugs** that need fixing:

## Issues Found

### 1. Positions Not Persisted to Database (CRITICAL)
**Problem**: ALL 120 positions have `strategy_id="etoro_position"` instead of their actual strategy IDs
- Autonomous positions are created in memory but NEVER persisted to database
- Position sync from eToro creates them with default `strategy_id="etoro_position"`
- Risk manager excludes them from autonomous risk calculations
- Frontend can't display them as autonomous positions

**Root Cause**: 
- OrderExecutor creates Position objects in `self._positions` (in-memory dict)
- OrderExecutor NEVER persists positions to database (no PositionORM creation)
- Order monitor's `sync_positions()` syncs from eToro, which doesn't know our strategy IDs
- All synced positions get `strategy_id="etoro_position"` by default

**Fix Required**:
```python
# In OrderExecutor._handle_buy_fill and _handle_sell_fill:
# After creating position in memory, persist to database

from src.models.database import get_database
from src.models.orm import PositionORM

position = Position(...)  # Create in memory
self._positions[position.id] = position

# PERSIST TO DATABASE
db = get_database()
session = db.get_session()
try:
    position_orm = PositionORM(
        id=position.id,
        strategy_id=position.strategy_id,  # Preserve actual strategy ID
        symbol=position.symbol,
        side=position.side,
        quantity=position.quantity,
        entry_price=position.entry_price,
        current_price=position.current_price,
        unrealized_pnl=position.unrealized_pnl,
        realized_pnl=position.realized_pnl,
        opened_at=position.opened_at,
        etoro_position_id=position.etoro_position_id,
        stop_loss=position.stop_loss,
        take_profit=position.take_profit,
        closed_at=position.closed_at
    )
    session.add(position_orm)
    session.commit()
finally:
    session.close()
```

**Additional Fix**: Update `sync_positions()` to preserve strategy_id for existing positions:
```python
# In order_monitor.py sync_positions():
if existing_pos:
    # DON'T overwrite strategy_id - preserve it
    existing_pos.current_price = pos.current_price
    existing_pos.unrealized_pnl = pos.unrealized_pnl
    # ... update other fields but NOT strategy_id
```

### 2. Position Accumulation (CRITICAL)
**Problem**: 120 open positions accumulated, none are being closed
- Positions are opened but exit signals aren't triggering
- Stop-loss and take-profit orders may not be working

**Root Cause**: Multiple possible causes:
1. Exit conditions in DSL rules are too restrictive
2. Stop-loss/take-profit orders aren't being monitored
3. Order monitor isn't processing SL/TP fills
4. Position sync from eToro isn't working

**Fix Required**:
1. Verify SL/TP orders are actually submitted to eToro
2. Add position monitoring to check SL/TP status
3. Implement exit signal generation (currently only entry signals are generated)
4. Add position cleanup for stale positions

### 3. Order Failure Rate (HIGH)
**Problem**: Many orders are FAILED or CANCELLED
- 108 orders in 24h, many failed
- Suggests eToro API rejections or validation issues

**Possible Causes**:
1. Stop-loss/take-profit rates are invalid (too close to entry price)
2. Symbol not tradeable in DEMO mode
3. Market closed when order submitted
4. Insufficient balance (though this should be caught by risk manager)

**Fix Required**:
1. Add better error logging for eToro API rejections
2. Validate SL/TP rates before submission (min distance from entry)
3. Improve market hours checking
4. Add retry logic for transient failures

### 4. No DEMO Strategies Remain
**Problem**: All DEMO strategies were retired or transitioned
- Test generated 4 DEMO strategies, but 0 remain
- Suggests strategies are being auto-retired too aggressively

**Fix Required**:
1. Check retirement criteria - may be too strict
2. Verify performance tracking is accurate
3. Ensure strategies aren't retired due to position quantity bug

## Recommended Fix Priority

### Priority 1: Position Quantity Fix (BLOCKING)
This breaks everything downstream:
- Risk management calculations are wrong
- P&L calculations are wrong
- Position limits don't work correctly
- Frontend displays wrong data

**Files to Fix**:
- `src/execution/order_executor.py` - Convert dollar amount to shares in `_handle_buy_fill` and `_handle_sell_fill`
- `src/risk/risk_manager.py` - Update `_get_position_value` to handle both quantity types
- `src/models/dataclasses.py` - Add documentation clarifying quantity is in shares

### Priority 2: Position Closing (BLOCKING)
Without this, positions accumulate forever:
- Add exit signal generation to strategy engine
- Implement SL/TP order monitoring
- Add position cleanup for stale positions

**Files to Fix**:
- `src/strategy/strategy_engine.py` - Add exit signal generation
- `src/core/order_monitor.py` - Monitor SL/TP orders
- `src/execution/order_executor.py` - Handle SL/TP fills

### Priority 3: Order Failure Handling (HIGH)
Reduce failed orders:
- Better error logging
- SL/TP validation
- Retry logic

**Files to Fix**:
- `src/execution/order_executor.py` - Add SL/TP validation
- `src/api/etoro_client.py` - Better error messages

### Priority 4: Strategy Retention (MEDIUM)
Keep strategies active longer:
- Review retirement criteria
- Fix performance tracking

**Files to Fix**:
- `src/strategy/autonomous_strategy_manager.py` - Adjust retirement thresholds

## Next Steps

1. **Fix Position Quantity Bug** - This is blocking everything else
2. **Re-run E2E Test** - Verify positions are tracked correctly
3. **Implement Exit Signals** - Ensure positions can be closed
4. **Monitor for 24h** - Verify full cycle works (entry → hold → exit)
5. **Fix Remaining Issues** - Order failures, strategy retention

## Test Command

```bash
source venv/bin/activate
python scripts/e2e_trade_execution_test.py
```

## Verification Queries

```python
# Check position quantities are reasonable
from src.models.database import get_database
from src.models.orm import PositionORM

db = get_database()
session = db.get_session()

positions = session.query(PositionORM).filter(PositionORM.closed_at.is_(None)).all()
for p in positions[:10]:
    value = p.quantity * p.entry_price
    print(f"{p.symbol}: qty={p.quantity:.2f} @ ${p.entry_price:.2f} = ${value:.2f}")
    # Should show reasonable values like:
    # WMT: qty=144.56 @ $335.34 = $48,485.00
    # NOT: qty=48335.96 @ $335.34 = $16,210,000.00
```
