# EXTERNAL_POSITION_STRATEGY_IDS - Complete Explanation

**Date**: 2026-02-21  
**Purpose**: Document what EXTERNAL_POSITION_STRATEGY_IDS is and how it's used

---

## What Is It?

`EXTERNAL_POSITION_STRATEGY_IDS` is a set of strategy IDs that identify positions that are **NOT managed by the autonomous trading system**. These are positions that exist in your eToro account but were created outside of AlphaCent.

### Current Value:
```python
EXTERNAL_POSITION_STRATEGY_IDS = {
    "etoro_position",
}
```

---

## What Does "etoro_position: 299" Mean?

This means there are **299 position records** in your database with `strategy_id = "etoro_position"`. These are:

- **179 OPEN positions** - Currently active in your eToro account
- **120 CLOSED positions** - Historical positions that have been closed

### Sample Data:
```
Symbol: BTC  | Qty: $9,997.55  | Entry: $69,667.92 | Side: LONG | Closed: Yes
Symbol: WMT  | Qty: $48,335.96 | Entry: $334.01    | Side: LONG | Closed: Yes
Symbol: WMT  | Qty: $48,335.81 | Entry: $335.34    | Side: LONG | Closed: Yes
```

**Key Point**: For eToro positions, the `quantity` field stores the **dollar amount invested**, not the number of units. This is different from autonomous positions where `quantity` = number of units.

---

## Where Do These Positions Come From?

These positions are **synced from your eToro account** by the position sync service. They could be:

1. **Manual trades** you placed directly on eToro
2. **Copy trading positions** from eToro's social trading
3. **Positions from other eToro features** (Smart Portfolios, etc.)
4. **Historical positions** from before AlphaCent was implemented

They are stored in your database so AlphaCent can:
- Display them in the UI
- Track your total portfolio value
- Avoid conflicts with autonomous trading

---

## How Is EXTERNAL_POSITION_STRATEGY_IDS Used?

The set is used to **exclude external positions** from autonomous trading logic. Here are the specific use cases:

### 1. Position Value Calculation (`_get_position_value`)

**Purpose**: Calculate dollar value differently for external vs autonomous positions

```python
if pos.strategy_id in EXTERNAL_POSITION_STRATEGY_IDS:
    # eToro positions: quantity IS the dollar amount invested
    return pos.quantity
else:
    # Autonomous positions: quantity is in units
    return pos.quantity * pos.current_price
```

**Why**: eToro API returns invested amount, not unit quantity, so we store it differently.

---

### 2. Filter Autonomous Positions (`_filter_autonomous_positions`)

**Purpose**: Get only positions managed by autonomous strategies

```python
return [
    pos for pos in positions
    if pos.strategy_id not in EXTERNAL_POSITION_STRATEGY_IDS
    and pos.closed_at is None
]
```

**Used in**:
- Risk calculations
- Portfolio allocation
- Strategy performance tracking

**Why**: We don't want to include manual eToro trades in autonomous strategy metrics.

---

### 3. Symbol Exposure Calculation

**Purpose**: Calculate how much capital is allocated to each symbol

```python
for pos in positions:
    if pos.symbol == symbol and pos.closed_at is None:
        if pos.strategy_id not in EXTERNAL_POSITION_STRATEGY_IDS:
            existing_position_value += self._get_position_value(pos)
```

**Why**: When checking if we can open a new position in SPY, we only count autonomous positions, not your manual SPY trades.

---

### 4. Signal Coordination (`_coordinate_signals`)

**Purpose**: Prevent duplicate signals for same symbol

```python
for pos in existing_positions:
    # Skip external positions (eToro sync, manual trades)
    if pos.strategy_id in EXTERNAL_POSITION_STRATEGY_IDS:
        continue
```

**Why**: If you manually bought AAPL on eToro, we don't want that to block autonomous strategies from trading AAPL.

---

### 5. Pending Order Filtering

**Purpose**: Check for duplicate pending orders

```python
if order.strategy_id in EXTERNAL_POSITION_STRATEGY_IDS:
    continue  # Skip external strategy orders
```

**Why**: External orders (if any) shouldn't block autonomous trading.

---

## Why Is This Important?

### Without EXTERNAL_POSITION_STRATEGY_IDS:

❌ Manual eToro trades would be counted as autonomous positions  
❌ Risk calculations would be wrong  
❌ Portfolio allocation would be incorrect  
❌ Strategy performance metrics would be polluted  
❌ Autonomous system might avoid symbols you're manually trading  

### With EXTERNAL_POSITION_STRATEGY_IDS:

✅ Clear separation between autonomous and manual trading  
✅ Accurate risk calculations for autonomous system  
✅ Correct portfolio allocation  
✅ Clean strategy performance metrics  
✅ Autonomous system can trade any symbol independently  

---

## Real-World Example

**Scenario**: You have:
- 179 open positions synced from eToro (manual trades, copy trading, etc.)
- 10 open positions from autonomous strategies

**What happens**:

1. **Risk Manager** calculates risk:
   - Only counts the 10 autonomous positions
   - Ignores the 179 eToro positions
   - This ensures autonomous system stays within its risk limits

2. **Signal Coordination** checks for duplicates:
   - If autonomous strategy wants to buy AAPL
   - And you already manually own AAPL on eToro
   - The autonomous system will still allow the trade (separate positions)

3. **Position Value** calculation:
   - eToro positions: Uses `quantity` directly (dollar amount)
   - Autonomous positions: Calculates `quantity * current_price`

4. **Performance Tracking**:
   - Autonomous strategy returns only include autonomous positions
   - Your manual eToro trades don't affect strategy metrics

---

## Summary

**EXTERNAL_POSITION_STRATEGY_IDS** is a critical configuration that:

1. **Identifies** positions not managed by autonomous trading
2. **Separates** manual/external trades from autonomous trades
3. **Ensures** accurate risk calculations and metrics
4. **Prevents** conflicts between manual and autonomous trading

**Current State**:
- ✅ Only contains `"etoro_position"` (legitimate external positions)
- ✅ 299 total positions (179 open, 120 closed)
- ✅ Test data has been cleaned up
- ✅ Working correctly

**Bottom Line**: This is a **necessary and correctly configured** feature that allows AlphaCent to coexist with your manual eToro trading activity.
