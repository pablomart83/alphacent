
# Fix for Duplicate Order Bug - February 23, 2026

## Changes Required

### 1. Update Position-Aware Pre-Filtering (src/strategy/strategy_engine.py)

Current logic (line ~3590):
```python
# Build set of normalized symbols with open positions (excluding external positions)
for pos in open_positions:
    # Skip external positions (eToro sync, manual trades)
    if pos.strategy_id in EXTERNAL_POSITION_STRATEGY_IDS:
        continue
    
    normalized_symbol = normalize_symbol(pos.symbol)
    symbols_to_skip.add(normalized_symbol)
```

**PROBLEM**: This skips ALL strategies for a symbol if ANY strategy has a position.

**FIX**: Change to strategy-specific filtering:
```python
# Build dict of (strategy_id, symbol) tuples with open positions
strategy_symbol_positions = set()
for pos in open_positions:
    # Skip external positions (eToro sync, manual trades)
    if pos.strategy_id in EXTERNAL_POSITION_STRATEGY_IDS:
        continue
    
    normalized_symbol = normalize_symbol(pos.symbol)
    strategy_symbol_positions.add((pos.strategy_id, normalized_symbol))

if strategy_symbol_positions:
    logger.info(
        f"Pre-filtering: Found {len(strategy_symbol_positions)} strategy-symbol combinations with existing positions."
    )
```

Then update the skip check (line ~3623):
```python
# Check if THIS strategy already has a position in this symbol
strategy_symbol_key = (strategy.id, normalized_symbol)
if strategy_symbol_key in strategy_symbol_positions:
    logger.info(
        f"Skipping signal generation for {symbol} by strategy {strategy.name}: "
        f"existing position found for this strategy-symbol combination."
    )
    continue
```

### 2. Add Order Deduplication Check (src/execution/order_executor.py)

Add before order execution:
```python
def _check_duplicate_order(self, strategy_id: str, symbol: str, side: str) -> bool:
    """Check if a similar order was placed recently (within 1 hour)."""
    from datetime import datetime, timedelta, timezone
    from src.models.database import get_database
    from src.models.orm import OrderORM
    
    db = get_database()
    session = db.get_session()
    
    try:
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_orders = session.query(OrderORM).filter(
            OrderORM.strategy_id == strategy_id,
            OrderORM.symbol == symbol,
            OrderORM.side == side,
            OrderORM.submitted_at > one_hour_ago
        ).count()
        
        if recent_orders > 0:
            logger.warning(
                f"Duplicate order detected: {strategy_id} already has {recent_orders} "
                f"{side} orders for {symbol} in the last hour. Skipping."
            )
            return True
        
        return False
    finally:
        session.close()
```

### 3. Add Strategy Cooldown Period (config/autonomous_trading.yaml)

Add new configuration:
```yaml
strategy_cooldown:
  enabled: true
  cooldown_hours: 24  # Prevent same strategy from trading same symbol within 24 hours
  apply_to_same_direction_only: true  # Only prevent same direction (LONG/SHORT)
```

### 4. Add Position Check in Order Executor (final safety net)

Before submitting order:
```python
def _check_existing_position(self, strategy_id: str, symbol: str) -> bool:
    """Check if strategy already has an open position in this symbol."""
    from src.models.database import get_database
    from src.models.orm import PositionORM
    
    db = get_database()
    session = db.get_session()
    
    try:
        open_position = session.query(PositionORM).filter(
            PositionORM.strategy_id == strategy_id,
            PositionORM.symbol == symbol,
            PositionORM.closed_at.is_(None)
        ).first()
        
        if open_position:
            logger.warning(
                f"Position already exists: {strategy_id} has open position in {symbol}. "
                f"Skipping order execution."
            )
            return True
        
        return False
    finally:
        session.close()
```

## Testing

After applying fixes, verify:
1. Run E2E test again
2. Check that only 1 order per strategy per symbol is created
3. Verify position-aware filtering logs show strategy-specific filtering
4. Confirm no duplicate orders in database

## Expected Impact

- ✅ Eliminate duplicate orders from same strategy
- ✅ Reduce unnecessary API calls
- ✅ Improve system reliability
- ✅ Prevent over-concentration in single symbols
