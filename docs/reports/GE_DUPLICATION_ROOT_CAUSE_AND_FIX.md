# GE Duplication Bug - Root Cause Analysis & Complete Fix

**Date:** February 22, 2026  
**Status:** 🔴 **CRITICAL - REQUIRES IMMEDIATE SPEC**

---

## Current Situation

**8 pending orders totaling $18,472.93:**
- 4 GE orders (instrument 1017): $9,733.95
- 1 COST order (instrument 1461): $3,750.88
- 1 DJ30 order (instrument 29): $2,014.82
- 1 VOO order (instrument 4238): $1,055.39
- 1 PLTR order (instrument 7991): $1,918.89

**Cannot cancel via API:** eToro's cancel order endpoint returns 404 (doesn't exist or not available in demo mode)

**Strategy retired:** The GE strategy has been retired to prevent more orders

---

## Root Cause: Symbol Normalization Inconsistency

### The Bug Flow

1. **Strategy generates signal** with `symbol='GE'`
2. **Order created** with `symbol='GE'` → stored in database
3. **Order submitted to eToro** with instrument_id=1017
4. **Order fills** → becomes position on eToro
5. **Position sync runs:**
   - Gets position from eToro with `instrument_id=1017`
   - Code was converting to string: `instrument_id = str(1017)` = `"1017"`
   - Lookup fails: `INSTRUMENT_ID_TO_SYMBOL.get("1017")` returns None (key is int 1017, not string)
   - Fallback: stores position as `symbol='ID_1017'`
6. **Next trading cycle:**
   - Duplication check queries: `WHERE symbol='GE' AND closed_at IS NULL`
   - Finds 0 positions (they're stored as 'ID_1017')
   - Thinks it's safe to create more GE orders
   - Creates duplicate order!

### Why This Is Critical

- **Violates risk limits:** Max 3 strategies per symbol, but system allows unlimited
- **Capital concentration:** All capital can end up in one symbol
- **Cascading failures:** Affects ALL symbols, not just GE
- **Silent failure:** No errors logged, system thinks it's working correctly

---

## What We've Fixed So Far

### ✅ 1. Instrument ID Type Conversion (src/api/etoro_client.py)

**Before:**
```python
instrument_id = str(item.get("InstrumentID", ""))  # String!
symbol = INSTRUMENT_ID_TO_SYMBOL.get(instrument_id, str(instrument_id))  # Lookup fails
```

**After:**
```python
instrument_id = int(instrument_id_raw) if instrument_id_raw else 0  # Keep as int
symbol = INSTRUMENT_ID_TO_SYMBOL.get(instrument_id, f"ID_{instrument_id}")  # Lookup works
```

### ✅ 2. Position Sync Symbol Update (src/core/order_monitor.py)

**Before:**
```python
if existing_pos:
    existing_pos.current_price = pos.current_price
    # ❌ Missing: symbol update
```

**After:**
```python
if existing_pos:
    existing_pos.symbol = pos.symbol  # ✅ Now syncs symbol
    existing_pos.current_price = pos.current_price
```

### ✅ 3. Symbol Normalizer Utility (src/utils/symbol_normalizer.py)

Created centralized symbol normalization:
- `normalize_symbol("GE")` → "GE"
- `normalize_symbol("1017")` → "GE"
- `normalize_symbol("ID_1017")` → "GE"
- `get_symbol_variations("GE")` → ["GE", "1017", "ID_1017"]

### ✅ 4. Duplication Check Normalization (src/core/trading_scheduler.py)

**Before:**
```python
key = (pos.symbol, pos.side.value)  # Uses raw symbol
```

**After:**
```python
normalized_symbol = normalize_symbol(pos.symbol)  # Normalize first
key = (normalized_symbol, pos.side.value)
```

### ✅ 5. Retired Problematic Strategy

Retired "RSI Overbought Short Ranging GE V1" to prevent more orders.

---

## What Still Needs Fixing

### ❌ 1. Pending Orders Cannot Be Cancelled

**Problem:** eToro's cancel order API endpoint doesn't exist or isn't available in demo mode.

**Impact:** 8 pending orders ($18,472.93) are stuck until they fill or expire.

**Options:**
1. **Manual cancellation:** Cancel through eToro web interface
2. **Wait for expiration:** Orders may expire after 24-48 hours
3. **Let them fill:** Accept the positions and manage them

**Recommendation:** Manual cancellation through eToro web interface immediately.

### ❌ 2. Existing Positions with Wrong Symbols

**Problem:** Database has positions with `symbol='ID_1017'` instead of `'GE'`.

**Impact:** Historical data is inconsistent, queries may miss positions.

**Fix needed:**
```sql
UPDATE positions 
SET symbol = 'GE' 
WHERE symbol IN ('ID_1017', '1017') 
AND closed_at IS NOT NULL;
```

### ❌ 3. Order Creation Doesn't Normalize Symbols

**Problem:** Orders are created with whatever symbol the signal has.

**Impact:** If a signal somehow has `symbol='ID_1017'`, order will be created with that.

**Fix needed:** Normalize symbol in `order_executor.py` before creating order:
```python
from src.utils.symbol_normalizer import normalize_symbol

def execute_signal(self, signal, ...):
    # Normalize symbol before creating order
    normalized_symbol = normalize_symbol(signal.symbol)
    
    order = Order(
        symbol=normalized_symbol,  # Use normalized symbol
        ...
    )
```

### ❌ 4. No Validation That Sync Worked

**Problem:** Position sync can fail silently, leaving database out of sync.

**Impact:** Duplication prevention relies on accurate database state.

**Fix needed:** Add sync validation:
```python
def sync_positions(self, force: bool = False) -> dict:
    # ... sync logic ...
    
    # Validate sync worked
    db_count = session.query(PositionORM).filter_by(closed_at=None).count()
    etoro_count = len(positions)
    
    if db_count != etoro_count:
        logger.error(
            f"Position sync validation FAILED: "
            f"DB has {db_count} positions, eToro has {etoro_count}"
        )
        # Alert or take corrective action
```

### ❌ 5. No Monitoring for Symbol Mismatches

**Problem:** We don't detect when symbols are inconsistent.

**Impact:** Bug can recur without detection.

**Fix needed:** Daily audit job:
```python
# Check for ID_* symbols (indicates mapping failure)
bad_symbols = session.query(PositionORM).filter(
    PositionORM.symbol.like('ID_%')
).all()

if bad_symbols:
    logger.error(f"Found {len(bad_symbols)} positions with unmapped symbols")
```

---

## Immediate Actions Required

### 1. Cancel Pending Orders (MANUAL)

**You must manually cancel these orders through eToro web interface:**

1. Log into eToro demo account
2. Go to Portfolio → Orders
3. Cancel these 8 orders:
   - 329867741 (GE, $2,550.60)
   - 330024276 (GE, $2,550.60)
   - 329875346 (COST, $3,750.88)
   - 329984174 (GE, $3,000.70)
   - 329867718 (GE, $1,631.05)
   - 329867717 (DJ30, $2,014.82)
   - 329867716 (VOO, $1,055.39)
   - 330024225 (PLTR, $1,918.89)

### 2. Fix Historical Position Symbols

Run this script:
```bash
python scripts/fix_historical_position_symbols.py
```

### 3. Add Order Symbol Normalization

Update `src/execution/order_executor.py` to normalize symbols before creating orders.

### 4. Add Sync Validation

Update `src/core/order_monitor.py` to validate sync results.

### 5. Create Monitoring

Add daily audit job to detect symbol mismatches.

---

## Testing Plan

### 1. Unit Tests

```python
def test_symbol_normalization():
    assert normalize_symbol("GE") == "GE"
    assert normalize_symbol("1017") == "GE"
    assert normalize_symbol("ID_1017") == "GE"
    assert normalize_symbol(1017) == "GE"

def test_duplication_prevention_with_mixed_symbols():
    # Create position with symbol='ID_1017'
    # Create signal with symbol='GE'
    # Verify duplication prevention blocks it
```

### 2. Integration Tests

```python
def test_full_cycle_symbol_consistency():
    # 1. Create signal with symbol='GE'
    # 2. Execute order
    # 3. Simulate order fill
    # 4. Sync positions from eToro
    # 5. Verify position has symbol='GE' (not 'ID_1017')
    # 6. Create another signal for 'GE'
    # 7. Verify duplication prevention blocks it
```

### 3. E2E Test

```python
def test_no_duplicates_across_cycles():
    # Run 10 trading cycles
    # Verify no duplicate positions created
    # Verify all symbols are normalized
```

---

## Long-Term Prevention

### 1. Centralized Symbol Management

All symbol operations should go through `symbol_normalizer.py`:
- Creating orders
- Querying positions
- Syncing from eToro
- Displaying in UI

### 2. Database Constraints

Add check constraint:
```sql
ALTER TABLE positions 
ADD CONSTRAINT check_symbol_format 
CHECK (symbol NOT LIKE 'ID_%');
```

### 3. Monitoring Dashboard

Add metrics:
- Position count: DB vs eToro
- Symbol mismatches detected
- Duplication prevention blocks
- Orders created per symbol

### 4. Alerting

Alert on:
- DB position count != eToro position count
- Any position with symbol like 'ID_%'
- More than 3 strategies trading same symbol
- Duplication prevention triggered

---

## Success Criteria

- ✅ All 8 pending orders cancelled
- ✅ All historical positions have normalized symbols
- ✅ Order creation normalizes symbols
- ✅ Position sync validates results
- ✅ Monitoring detects symbol mismatches
- ✅ Unit tests pass
- ✅ Integration tests pass
- ✅ E2E test runs 10 cycles with no duplicates
- ✅ No positions with symbol like 'ID_%'
- ✅ DB position count == eToro position count

---

## Estimated Time

- Manual order cancellation: 10 minutes
- Fix historical symbols: 30 minutes
- Add order normalization: 1 hour
- Add sync validation: 1 hour
- Add monitoring: 2 hours
- Write tests: 3 hours
- **Total: ~8 hours**

---

## Priority

🔴 **CRITICAL - CREATE SPEC IMMEDIATELY**

This bug affects the entire trading system, not just GE. Every symbol is at risk of duplication. We need a comprehensive spec to:

1. Fix all remaining issues
2. Add proper testing
3. Add monitoring
4. Prevent recurrence

**Recommended:** Create spec "symbol-normalization-and-duplication-fix" with full requirements, design, and tasks.
