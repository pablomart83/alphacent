#!/usr/bin/env python3
"""
Fix Duplicate Order Bug - February 23, 2026

Root Cause Analysis:
- Trading scheduler runs every 5 minutes (300 seconds)
- Position-aware pre-filtering is NOT working correctly
- Same strategy is creating multiple orders for the same symbol
- 8 orders for JPM from "RSI Midrange Momentum JPM V34" in 2 hours
- 8 orders for GE from "RSI Overbought Short Ranging GE V10" in 2 hours

The Fix:
1. Update position-aware filtering to check by STRATEGY + SYMBOL, not just SYMBOL
2. Add order deduplication check before execution
3. Add strategy-level cooldown period (prevent same strategy from trading same symbol within X hours)
"""

import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

def analyze_issue():
    """Analyze the duplicate order issue."""
    print("="*80)
    print("DUPLICATE ORDER BUG ANALYSIS")
    print("="*80)
    
    print("\n🔴 CRITICAL BUG IDENTIFIED:")
    print("   - Same strategy creating multiple orders for same symbol")
    print("   - JPM: 8 orders from 'RSI Midrange Momentum JPM V34' in 2 hours")
    print("   - GE: 8 orders from 'RSI Overbought Short Ranging GE V10' in 2 hours")
    
    print("\n📊 ROOT CAUSE:")
    print("   1. Trading scheduler runs every 5 minutes")
    print("   2. Position-aware pre-filtering checks SYMBOL only, not STRATEGY+SYMBOL")
    print("   3. No order deduplication check before execution")
    print("   4. No strategy-level cooldown period")
    
    print("\n🔧 THE FIX:")
    print("   1. Update pre-filtering to check by STRATEGY + SYMBOL")
    print("   2. Add order deduplication check (prevent duplicate orders within 1 hour)")
    print("   3. Add strategy cooldown (prevent same strategy from trading same symbol within 24 hours)")
    print("   4. Add position check in order executor (final safety net)")


def create_fix_patch():
    """Create a patch file with the fix."""
    print("\n" + "="*80)
    print("CREATING FIX PATCH")
    print("="*80)
    
    patch_content = """
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
    \"\"\"Check if a similar order was placed recently (within 1 hour).\"\"\"
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
    \"\"\"Check if strategy already has an open position in this symbol.\"\"\"
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
"""
    
    patch_file = Path("DUPLICATE_ORDER_BUG_FIX_PATCH.md")
    with open(patch_file, 'w') as f:
        f.write(patch_content)
    
    print(f"✅ Fix patch created: {patch_file}")
    print("\nNext steps:")
    print("1. Review the patch file")
    print("2. Apply the changes to the codebase")
    print("3. Run E2E test to verify fix")
    print("4. Monitor for 24 hours to ensure no regressions")


def main():
    """Main entry point."""
    analyze_issue()
    create_fix_patch()
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print("\n✅ Analysis complete")
    print("✅ Fix patch created: DUPLICATE_ORDER_BUG_FIX_PATCH.md")
    print("\n🔴 CRITICAL: This bug must be fixed before production deployment!")
    print("   Without this fix, the system will create duplicate orders every 5 minutes,")
    print("   leading to over-concentration and potential losses.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
