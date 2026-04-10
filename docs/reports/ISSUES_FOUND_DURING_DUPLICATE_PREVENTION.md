# Issues Found During Duplicate Prevention Implementation

**Date**: 2026-02-21  
**Context**: Issues discovered while implementing task 6.5.9

---

## Issue 1: Test Data in EXTERNAL_POSITION_STRATEGY_IDS (HIGH PRIORITY)

### Problem

The `EXTERNAL_POSITION_STRATEGY_IDS` set in `src/risk/risk_manager.py` contains test data that should have been cleaned up:

```python
EXTERNAL_POSITION_STRATEGY_IDS = {
    "etoro_position",
    "strategy_1",  # ⚠️ TEST DATA - should be removed
}
```

### Impact

1. **Production Data Pollution**: `strategy_1` appears to be test data that's being treated as an external position
2. **Filtering Issues**: Any orders or positions with `strategy_id = "strategy_1"` are:
   - Skipped in signal coordination
   - Excluded from risk calculations
   - Excluded from autonomous position management
   - Not counted in portfolio metrics

3. **Test Confusion**: Unit tests had to avoid using `strategy_1` as a test ID because it's filtered out

### Evidence

From the DUPLICATE_ORDER_ANALYSIS.md:
- Task 6.5.2 mentioned cleaning up "fake test positions (strategy_1, strategy_2, strategy_3)"
- These were supposed to be removed but `strategy_1` remains in the EXTERNAL_POSITION_STRATEGY_IDS

### Recommended Fix

**Option 1: Remove from EXTERNAL_POSITION_STRATEGY_IDS (RECOMMENDED)**
```python
EXTERNAL_POSITION_STRATEGY_IDS = {
    "etoro_position",  # Only keep legitimate external positions
}
```

**Option 2: Clean up database and keep the filter**
If `strategy_1` positions/orders still exist in the database:
1. Query and remove all positions with `strategy_id = "strategy_1"`
2. Query and remove all orders with `strategy_id = "strategy_1"`
3. Then remove from EXTERNAL_POSITION_STRATEGY_IDS

### Files Affected

The EXTERNAL_POSITION_STRATEGY_IDS is used in:
- `src/risk/risk_manager.py` (multiple locations)
- `src/core/trading_scheduler.py` (_coordinate_signals)
- `scripts/diagnostics/check_db_positions.py`
- `scripts/diagnostics/verify_position_data.py`
- `scripts/e2e_trade_execution_test.py`
- `tests/manual/test_concentration_limits.py`
- `scripts/utilities/close_large_position.py`

---

## Issue 2: Potential Database Cleanup Needed

### Problem

Based on the DUPLICATE_ORDER_ANALYSIS.md, there may still be test data in the database:
- Test positions: `strategy_1`, `strategy_2`, `strategy_3`
- Old manual/vibe_coding orders
- 123 BACKTESTED strategies that won't be used

### Recommended Action

Run a database audit to check for:

```sql
-- Check for test strategy positions
SELECT COUNT(*) FROM positions WHERE strategy_id IN ('strategy_1', 'strategy_2', 'strategy_3');

-- Check for test strategy orders
SELECT COUNT(*) FROM orders WHERE strategy_id IN ('strategy_1', 'strategy_2', 'strategy_3');

-- Check for old vibe_coding orders
SELECT COUNT(*) FROM orders WHERE strategy_id = 'vibe_coding';

-- Check for BACKTESTED strategies that should be retired
SELECT COUNT(*) FROM strategies WHERE status = 'BACKTESTED';
```

If any exist, create a cleanup script to remove them.

---

## Issue 3: Inconsistent Strategy ID Naming Convention

### Problem

The codebase uses inconsistent strategy ID formats:
- External positions: `"etoro_position"` (snake_case)
- Test data: `"strategy_1"`, `"strategy_2"` (snake_case with number)
- Autonomous strategies: UUIDs or generated IDs

### Recommendation

Establish a clear naming convention:
- **External positions**: `"etoro_position"`, `"manual_trade"` (snake_case, descriptive)
- **Autonomous strategies**: UUIDs (e.g., `"550e8400-e29b-41d4-a716-446655440000"`)
- **Test data**: Prefix with `"test_"` (e.g., `"test_strategy_auto"`) to make it obvious

This would prevent test data from being confused with production data.

---

## Issue 4: No Database Constraint for Duplicate Orders

### Problem

While the code now prevents duplicate orders, there's no database-level safeguard. If the code logic fails or is bypassed, duplicates could still occur.

### Recommendation

Add a unique partial index to the orders table:

```sql
CREATE UNIQUE INDEX idx_active_orders_per_strategy_symbol 
ON orders (strategy_id, symbol, side) 
WHERE status IN ('PENDING', 'SUBMITTED');
```

This provides a fail-safe at the database level.

**Benefits**:
- Prevents duplicates even if code logic fails
- Database will reject duplicate inserts with a clear error
- No performance impact (partial index only on active orders)

**Implementation**:
Create a migration script: `scripts/utilities/migrate_add_unique_order_constraint.py`

---

## Issue 5: Missing Monitoring for Duplicate Detection

### Problem

There's no monitoring to detect if duplicates somehow still occur.

### Recommendation

Add a monitoring check in the MonitoringService or create a diagnostic script:

```python
def check_for_duplicate_orders(self):
    """Check for duplicate pending orders and alert."""
    from sqlalchemy import func
    
    duplicates = self.session.query(
        OrderORM.strategy_id,
        OrderORM.symbol,
        OrderORM.side,
        func.count(OrderORM.id).label('count')
    ).filter(
        OrderORM.status.in_([OrderStatus.PENDING, OrderStatus.SUBMITTED])
    ).group_by(
        OrderORM.strategy_id,
        OrderORM.symbol,
        OrderORM.side
    ).having(
        func.count(OrderORM.id) > 1
    ).all()
    
    if duplicates:
        logger.error(f"DUPLICATE ORDERS DETECTED: {len(duplicates)} groups")
        for dup in duplicates:
            logger.error(f"  {dup.strategy_id} - {dup.symbol} {dup.side}: {dup.count} orders")
        # Send alert to monitoring system
```

---

## Priority Ranking

1. **HIGH**: Issue 1 - Remove `strategy_1` from EXTERNAL_POSITION_STRATEGY_IDS
2. **HIGH**: Issue 2 - Clean up test data from database
3. **MEDIUM**: Issue 4 - Add database unique constraint
4. **MEDIUM**: Issue 5 - Add duplicate detection monitoring
5. **LOW**: Issue 3 - Establish naming convention (documentation)

---

## Recommended Next Steps

1. **Immediate**: Check if `strategy_1` positions/orders exist in database
   ```bash
   python scripts/diagnostics/check_db_positions.py
   ```

2. **If they exist**: Run cleanup script to remove them
   ```python
   # Create: scripts/utilities/cleanup_test_data.py
   ```

3. **Then**: Remove `strategy_1` from EXTERNAL_POSITION_STRATEGY_IDS

4. **Optional**: Add database unique constraint for extra safety

5. **Optional**: Add monitoring for duplicate detection

---

## Conclusion

The main issue is **test data pollution** in the EXTERNAL_POSITION_STRATEGY_IDS set. This should be cleaned up to ensure the system only filters legitimate external positions (like eToro-synced positions) and not test data.

The duplicate prevention implementation is solid, but these cleanup tasks would improve the overall system health and prevent future confusion.
