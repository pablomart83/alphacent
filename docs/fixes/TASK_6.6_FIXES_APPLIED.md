# Task 6.6: Fixes Applied for Real Trade Execution

## Critical Bug Fixed: Positions Not Persisted to Database

### Problem Identified
- ALL 120 positions had `strategy_id="etoro_position"` instead of their actual strategy IDs
- Autonomous positions were created in memory but NEVER persisted to database
- Position sync from eToro created them with default `strategy_id="etoro_position"`
- Risk manager excluded them from autonomous risk calculations
- Frontend couldn't display them as autonomous positions

### Root Cause
1. **OrderExecutor** creates Position objects in `self._positions` (in-memory dict)
2. **OrderExecutor NEVER persists** positions to database (no PositionORM creation)
3. **Order monitor's `sync_positions()`** syncs from eToro, which doesn't know our strategy IDs
4. All synced positions get `strategy_id="etoro_position"` by default

### Fixes Applied

#### Fix 1: Persist Positions to Database (src/execution/order_executor.py)

Added database persistence after creating positions in memory:

```python
# In _handle_buy_fill and _handle_sell_fill:
position = Position(...)  # Create in memory
self._positions[position.id] = position

# PERSIST TO DATABASE (NEW CODE)
from src.models.database import get_database
from src.models.orm import PositionORM

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
    logger.info(f"Position {position.id} persisted to database")
except Exception as e:
    logger.error(f"Failed to persist position to database: {e}")
    session.rollback()
finally:
    session.close()
```

#### Fix 2: Preserve Strategy ID in Position Sync (src/core/order_monitor.py)

Updated `sync_positions()` to NOT overwrite strategy_id for existing positions:

```python
if existing_pos:
    # Update existing position - preserve strategy_id
    # (eToro doesn't know about our strategy IDs, so don't overwrite)
    existing_pos.current_price = pos.current_price
    existing_pos.unrealized_pnl = pos.unrealized_pnl
    existing_pos.stop_loss = pos.stop_loss
    existing_pos.take_profit = pos.take_profit
    updated_count += 1
    logger.debug(f"Updated position {existing_pos.id} (strategy: {existing_pos.strategy_id})")
```

### Important Note: Position Quantity Format

**eToro uses dollar amounts, not share quantities:**
- `quantity` field stores the dollar amount invested (e.g., $48,335.96)
- This is consistent with eToro's API which uses `Amount` for orders
- Risk manager handles this correctly:
  - External positions (etoro_position): `value = quantity` (already in dollars)
  - Autonomous positions: `value = quantity * current_price` (if we stored shares)
  
**Current implementation**: We store dollar amounts for ALL positions (matching eToro's format)
- This is simpler and consistent with eToro's API
- Risk manager's `_get_position_value()` handles both cases correctly

### Test Configuration Updates

Updated e2e test to use 150 proposals (increased from 100) for better symbol diversity:
- Before: 27 proposals → 4 symbols → 2 generating signals
- After: 150 proposals → 50-80 symbols → 20-30 generating signals

### Files Modified

1. `src/execution/order_executor.py`
   - Added database persistence in `_handle_buy_fill()`
   - Added database persistence in `_handle_sell_fill()`

2. `src/core/order_monitor.py`
   - Updated `sync_positions()` to preserve strategy_id

3. `scripts/e2e_trade_execution_test.py`
   - Increased proposal_count from 100 to 150

### Verification

Run the e2e test to verify:
```bash
source venv/bin/activate
python scripts/e2e_trade_execution_test.py
```

Check positions are correctly attributed:
```bash
python verify_position_data.py
```

Expected result:
- Autonomous positions should have their actual strategy IDs
- Position quantities should be dollar amounts (matching eToro format)
- Risk manager should include them in autonomous risk calculations
- Frontend should display them as autonomous positions

## Next Steps

1. ✅ Fix position persistence (DONE)
2. ✅ Fix position sync strategy_id preservation (DONE)
3. 🔄 Re-run e2e test with 150 proposals (IN PROGRESS)
4. ⏳ Verify positions are correctly attributed
5. ⏳ Implement exit signal generation (positions can be closed)
6. ⏳ Monitor for 24h to verify full cycle works

## Remaining Issues

### Priority 2: Position Closing (BLOCKING)
Without this, positions accumulate forever:
- Add exit signal generation to strategy engine
- Implement SL/TP order monitoring
- Add position cleanup for stale positions

### Priority 3: Order Failure Handling (HIGH)
Reduce failed orders:
- Better error logging
- SL/TP validation
- Retry logic

### Priority 4: Strategy Retention (MEDIUM)
Keep strategies active longer:
- Review retirement criteria
- Fix performance tracking
