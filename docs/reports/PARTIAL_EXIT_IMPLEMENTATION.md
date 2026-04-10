# Partial Exit Strategy Implementation

## Overview

Implemented partial exit strategy functionality for the AlphaCent trading platform. This feature allows positions to automatically take partial profits at predefined levels while letting the rest of the position run.

## Implementation Date

February 21, 2026

## Changes Made

### 1. Data Model Updates

#### RiskConfig Dataclass (`src/models/dataclasses.py`)
- Added `partial_exit_enabled: bool` field (default: False)
- Added `partial_exit_levels: List[Dict[str, float]]` field with default value `[{"profit_pct": 0.05, "exit_pct": 0.5}]`
- Added `__post_init__` method to initialize default partial exit levels

#### Position Dataclass (`src/models/dataclasses.py`)
- Added `partial_exits: List[Dict[str, Any]]` field to track partial exit history
- Each partial exit record contains:
  - `profit_level`: The profit threshold that triggered the exit
  - `profit_pct`: Actual profit percentage at exit time
  - `exit_pct`: Percentage of position exited
  - `exit_quantity`: Quantity sold
  - `exit_price`: Price at which exit occurred
  - `timestamp`: When the exit was triggered
  - `order_id`: ID of the order created for this exit

### 2. Database Schema Updates

#### RiskConfigORM (`src/models/orm.py`)
- Added `partial_exit_enabled` column (INTEGER, default: 0)
- Added `partial_exit_levels` column (JSON, default: NULL)

#### PositionORM (`src/models/orm.py`)
- Added `partial_exits` column (JSON, default: empty list)
- Updated `to_dict()` method to include `partial_exits` field

### 3. Position Manager Enhancement

#### PositionManager (`src/execution/position_manager.py`)
- Implemented `check_partial_exits(positions: List[Position]) -> List[Order]` method
- Logic:
  1. Checks if partial exits are enabled
  2. Validates partial exit level configuration
  3. For each open position:
     - Calculates current profit percentage
     - Checks each configured profit level
     - Skips levels already triggered (prevents re-triggering)
     - Creates SELL/BUY orders for partial quantities
     - Records exit in position history
     - Updates position quantity
  4. Returns list of orders created

#### Key Features:
- **Profit Calculation**: Handles both LONG and SHORT positions correctly
- **Level Validation**: Validates profit_pct > 0, exit_pct between 0 and 1
- **Re-trigger Prevention**: Tracks triggered levels to avoid duplicate exits
- **Original Quantity Basis**: All exit percentages calculated from original position size
- **Order Creation**: Creates MARKET orders with opposite side of position
- **Error Handling**: Gracefully handles errors, continues processing other positions

### 4. Database Migration

Created `scripts/utilities/migrate_add_partial_exit_fields.py`:
- Adds `partial_exit_enabled` and `partial_exit_levels` to `risk_config` table
- Adds `partial_exits` to `positions` table
- Sets appropriate defaults
- Successfully executed on alphacent.db

### 5. Unit Tests

Added comprehensive test suite in `tests/test_position_manager.py`:

#### Test Coverage:
1. ✅ `test_partial_exits_disabled` - Verifies no action when disabled
2. ✅ `test_partial_exit_no_levels_configured` - Handles missing configuration
3. ✅ `test_partial_exit_profit_threshold_not_met` - Respects profit thresholds
4. ✅ `test_partial_exit_triggered_long_position` - Long position partial exit
5. ✅ `test_partial_exit_triggered_short_position` - Short position partial exit
6. ✅ `test_partial_exit_not_retriggered` - Prevents duplicate exits
7. ✅ `test_partial_exit_multiple_levels` - Handles multiple profit levels
8. ✅ `test_partial_exit_skips_closed_positions` - Ignores closed positions
9. ✅ `test_partial_exit_invalid_level_configuration` - Validates configuration
10. ✅ `test_partial_exit_multiple_positions` - Processes multiple positions
11. ✅ `test_partial_exit_quantity_calculation` - Accurate quantity calculations

**All 21 tests passing** (10 trailing stop tests + 11 partial exit tests)

## Usage Example

```python
from src.models.dataclasses import RiskConfig
from src.execution.position_manager import PositionManager

# Configure partial exits
risk_config = RiskConfig(
    partial_exit_enabled=True,
    partial_exit_levels=[
        {"profit_pct": 0.05, "exit_pct": 0.3},  # At 5% profit, exit 30%
        {"profit_pct": 0.10, "exit_pct": 0.5},  # At 10% profit, exit 50%
    ]
)

# Create position manager
manager = PositionManager(etoro_client, risk_config)

# Check positions for partial exit opportunities
orders = manager.check_partial_exits(open_positions)

# Orders are created and can be submitted to broker
for order in orders:
    order_executor.submit_order(order)
```

## Configuration

### Default Configuration
```json
{
  "partial_exit_enabled": false,
  "partial_exit_levels": [
    {
      "profit_pct": 0.05,  // 5% profit
      "exit_pct": 0.5      // Exit 50% of position
    }
  ]
}
```

### Example Multi-Level Configuration
```json
{
  "partial_exit_enabled": true,
  "partial_exit_levels": [
    {"profit_pct": 0.05, "exit_pct": 0.25},  // 5% profit -> 25% exit
    {"profit_pct": 0.10, "exit_pct": 0.33},  // 10% profit -> 33% exit
    {"profit_pct": 0.20, "exit_pct": 0.50}   // 20% profit -> 50% exit
  ]
}
```

## Integration Points

### Order Execution Flow
1. `PositionManager.check_partial_exits()` creates orders
2. Orders are submitted via `OrderExecutor`
3. When orders fill, `OrderExecutor` updates:
   - Position quantity (reduces by filled amount)
   - Realized P&L (adds profit from partial exit)
   - Position status (closes if quantity reaches 0)

### Position Monitoring
- Should be called periodically (e.g., every 5 seconds) by `OrderMonitor`
- Checks all open positions for partial exit opportunities
- Creates orders automatically when profit thresholds are met

## Benefits

1. **Risk Management**: Lock in profits while maintaining upside potential
2. **Psychological Advantage**: Reduces stress by securing partial gains
3. **Flexibility**: Configurable profit levels and exit percentages
4. **Automation**: No manual intervention required
5. **Tracking**: Complete history of partial exits per position

## Acceptance Criteria Met

✅ Add `partial_exit_enabled` field to RiskConfig (default: False)
✅ Add `partial_exit_levels` field (default: [{"profit_pct": 0.05, "exit_pct": 0.5}])
✅ Extend PositionManager with `check_partial_exits()` method
✅ Calculate exit quantity (position_size * exit_pct)
✅ Create SELL order for partial quantity
✅ Mark position as "partially exited" to avoid re-triggering
✅ Log partial exit
✅ Add partial exit tracking to Position dataclass
✅ Update position P&L calculation to handle partial exits
✅ Add database migration for partial exit tracking
✅ Add unit tests for partial exit logic

## Next Steps

1. Integrate `check_partial_exits()` into `OrderMonitor.run_monitoring_cycle()`
2. Add partial exit configuration to frontend UI (Settings page)
3. Display partial exit history in position details
4. Add metrics tracking for partial exit performance
5. Consider adding dynamic partial exit levels based on volatility

## Notes

- Partial exits are calculated based on the ORIGINAL position size, not the remaining size after previous exits
- This ensures predictable behavior when multiple levels are configured
- The P&L calculation is handled automatically by the existing order execution flow
- Partial exits work for both LONG and SHORT positions
