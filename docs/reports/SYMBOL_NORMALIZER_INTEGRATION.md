# Symbol Normalizer - How It Works Automatically

**Date:** February 22, 2026  
**Status:** ✅ **FULLY INTEGRATED**

---

## Overview

The symbol normalizer is now **fully automatic** across the entire trading system. Every place that handles symbols now normalizes them automatically, ensuring consistency.

---

## How It Works

### The Utility (src/utils/symbol_normalizer.py)

```python
from src.utils.symbol_normalizer import normalize_symbol

# Handles all variations automatically:
normalize_symbol("GE")        → "GE"
normalize_symbol("1017")      → "GE"
normalize_symbol("ID_1017")   → "GE"
normalize_symbol(1017)        → "GE"
```

### Integration Points (All Automatic)

## 1. ✅ Order Creation (src/execution/order_executor.py)

**When:** Every time an order is created from a signal

**What happens:**
```python
def execute_signal(self, signal, ...):
    # Automatically normalizes the signal's symbol
    normalized_symbol = normalize_symbol(signal.symbol)
    
    # Order is created with normalized symbol
    order = Order(
        symbol=normalized_symbol,  # Always normalized
        ...
    )
```

**Result:** All orders are created with normalized symbols (e.g., "GE", never "ID_1017")

---

## 2. ✅ Position Sync (src/api/etoro_client.py)

**When:** Every time positions are synced from eToro (every 5 minutes, or after order fills)

**What happens:**
```python
def get_positions(self):
    # Gets instrument_id from eToro (e.g., 1017)
    instrument_id = int(item.get("InstrumentID"))  # Keep as int
    
    # Automatically maps to normalized symbol
    symbol = INSTRUMENT_ID_TO_SYMBOL.get(instrument_id, f"ID_{instrument_id}")
    
    # Position is created with normalized symbol
    position = Position(symbol=symbol, ...)  # "GE", not "ID_1017"
```

**Result:** All positions synced from eToro have normalized symbols

---

## 3. ✅ Duplication Check (src/core/trading_scheduler.py)

**When:** Every trading cycle, before creating new orders

**What happens:**
```python
def _coordinate_signals(self, ...):
    # Automatically normalizes position symbols
    for pos in existing_positions:
        normalized_symbol = normalize_symbol(pos.symbol)
        existing_positions_map[(normalized_symbol, side)] = pos
    
    # Automatically normalizes order symbols
    for order in pending_orders:
        normalized_symbol = normalize_symbol(order.symbol)
        pending_orders_map[(strategy_id, normalized_symbol, side)] = order
    
    # Automatically normalizes signal symbols
    for signal in signals:
        normalized_symbol = normalize_symbol(signal.symbol)
        signals_by_symbol[(normalized_symbol, direction)] = signal
```

**Result:** Duplication check compares normalized symbols, so "GE" matches "ID_1017"

---

## 4. ✅ Position Sync Update (src/core/order_monitor.py)

**When:** Every time positions are synced and updated in database

**What happens:**
```python
def sync_positions(self, force: bool = False):
    if existing_pos:
        # Automatically updates symbol to normalized version
        existing_pos.symbol = pos.symbol  # pos.symbol is already normalized
        existing_pos.current_price = pos.current_price
        ...
```

**Result:** Database positions are updated with normalized symbols

---

## Complete Flow Example

Let's trace a signal for "GE" through the entire system:

### Step 1: Signal Generated
```python
signal = TradingSignal(
    symbol="GE",  # Strategy generates signal with "GE"
    action=SignalAction.ENTER_LONG,
    ...
)
```

### Step 2: Order Created (Automatic Normalization)
```python
# In order_executor.py
normalized_symbol = normalize_symbol("GE")  # → "GE"

order = Order(
    symbol="GE",  # Normalized symbol stored
    ...
)
```

### Step 3: Order Submitted to eToro
```python
# eToro receives order with symbol="GE"
# eToro internally uses instrument_id=1017
```

### Step 4: Order Fills, Becomes Position
```python
# eToro position has instrument_id=1017
```

### Step 5: Position Synced (Automatic Normalization)
```python
# In etoro_client.py
instrument_id = 1017  # From eToro
symbol = INSTRUMENT_ID_TO_SYMBOL.get(1017)  # → "GE"

position = Position(
    symbol="GE",  # Normalized symbol stored
    ...
)
```

### Step 6: Database Updated
```python
# In order_monitor.py
existing_pos.symbol = "GE"  # Normalized symbol stored in DB
```

### Step 7: Next Cycle - Duplication Check (Automatic Normalization)
```python
# In trading_scheduler.py
# New signal comes in for "GE"
normalized_signal_symbol = normalize_symbol("GE")  # → "GE"

# Check existing positions
for pos in positions:
    normalized_pos_symbol = normalize_symbol(pos.symbol)  # "GE" → "GE"
    
# Compare: "GE" == "GE" ✅ MATCH!
# Duplication prevention blocks the new order
```

---

## What If Something Goes Wrong?

### Scenario: Position somehow gets stored as "ID_1017"

Even if a position is stored with the wrong symbol, the duplication check still works:

```python
# Database has position with symbol="ID_1017" (wrong)
# New signal comes in with symbol="GE"

# Duplication check:
normalized_pos_symbol = normalize_symbol("ID_1017")  # → "GE"
normalized_signal_symbol = normalize_symbol("GE")    # → "GE"

# Compare: "GE" == "GE" ✅ MATCH!
# Duplication prevention still works!
```

---

## Monitoring

### Automatic Detection of Unmapped Symbols

If a symbol can't be normalized (not in the mapping), it gets the `ID_` prefix:

```python
# Unknown instrument ID 9999
symbol = INSTRUMENT_ID_TO_SYMBOL.get(9999, f"ID_9999")  # → "ID_9999"
```

This makes it easy to detect mapping failures:

```python
# Daily audit job
bad_symbols = session.query(PositionORM).filter(
    PositionORM.symbol.like('ID_%')
).all()

if bad_symbols:
    alert(f"Found {len(bad_symbols)} positions with unmapped symbols")
```

---

## Testing

### Unit Tests

```python
def test_symbol_normalization():
    """Test all symbol variations normalize correctly."""
    assert normalize_symbol("GE") == "GE"
    assert normalize_symbol("1017") == "GE"
    assert normalize_symbol("ID_1017") == "GE"
    assert normalize_symbol(1017) == "GE"

def test_duplication_with_mixed_symbols():
    """Test duplication prevention works with mixed symbols."""
    # Create position with symbol="ID_1017"
    pos = PositionORM(symbol="ID_1017", ...)
    
    # Create signal with symbol="GE"
    signal = TradingSignal(symbol="GE", ...)
    
    # Duplication check should match them
    assert normalize_symbol(pos.symbol) == normalize_symbol(signal.symbol)
```

### Integration Tests

```python
def test_end_to_end_symbol_consistency():
    """Test symbol stays consistent through entire flow."""
    # 1. Create signal with symbol="GE"
    signal = TradingSignal(symbol="GE", ...)
    
    # 2. Execute order
    order = order_executor.execute_signal(signal, ...)
    assert order.symbol == "GE"  # Normalized
    
    # 3. Simulate order fill on eToro (instrument_id=1017)
    # 4. Sync positions
    positions = order_monitor.sync_positions(force=True)
    
    # 5. Check database
    db_position = session.query(PositionORM).filter_by(
        etoro_position_id=order.etoro_order_id
    ).first()
    assert db_position.symbol == "GE"  # Still normalized
    
    # 6. Create another signal for "GE"
    signal2 = TradingSignal(symbol="GE", ...)
    
    # 7. Duplication check should block it
    coordinated = scheduler._coordinate_signals(...)
    assert signal2 not in coordinated  # Blocked!
```

---

## Summary

The symbol normalizer is **fully automatic** and integrated at every critical point:

1. ✅ **Order creation** - normalizes before creating order
2. ✅ **Position sync** - normalizes when syncing from eToro
3. ✅ **Duplication check** - normalizes when comparing symbols
4. ✅ **Database updates** - normalizes when updating positions

**You don't need to do anything** - the system automatically ensures symbol consistency everywhere.

**Result:** No more duplication bugs due to symbol mismatches. "GE", "1017", and "ID_1017" are all treated as the same symbol.
