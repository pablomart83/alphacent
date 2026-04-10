# URGENT: Database-eToro Sync Bug Discovered
## CRITICAL - Immediate Action Required

**Date:** February 22, 2026  
**Severity:** 🔴 **CRITICAL**  
**Status:** ⚠️ **ACTIVE BUG** - System is out of sync

---

## Executive Summary

The database is completely out of sync with eToro. What we thought were "0 open GE positions" is actually **5 open GE positions** that the database incorrectly marked as closed.

---

## The Bug

### Database State (WRONG):
```
Symbol: GE
Open Positions: 0
Closed Positions: 5 (marked closed on 2026-02-21 20:12:56)
Pending Orders: 2
```

### eToro Reality (CORRECT):
```
Instrument ID: 1017 (= GE)
Open Positions: 5
- Position 3440004433: 14.31 shares @ $339.88
- Position 3440004445: 13.92 shares @ $339.88
- Position 3440004733: 13.11 shares @ $339.96
- Position 3440004962: 12.56 shares @ $339.96
- Position 3440005220: 11.83 shares @ $339.96
```

### The Mismatch:
- Database stores positions with symbol "GE"
- eToro returns positions with instrument ID "1017"
- Sync process doesn't recognize they're the same
- Database incorrectly marks "GE" positions as closed
- eToro positions remain open but untracked

---

## Impact

### Current Risk:
1. **7 potential GE positions** if pending orders fill (5 existing + 2 pending)
2. **Violates max 3 strategies per symbol** by 133%
3. **Massive position concentration risk**
4. **Duplication prevention completely bypassed**

### Why Duplication Prevention Failed:
```python
# _coordinate_signals() checks database for open positions
existing_positions = query(PositionORM).filter(
    symbol == 'GE',
    closed_at.is_(None)  # Returns 0 positions!
).all()

# But eToro has 5 open positions with symbol='1017'
# System thinks it's safe to create more GE orders
# WRONG!
```

---

## Root Cause

### Symbol Mapping Issue:

**When positions are created:**
- System uses ticker symbol "GE"
- Stored in database as symbol="GE"

**When eToro syncs positions:**
- eToro API returns instrument_id="1017"
- Sync process stores as symbol="1017"
- Doesn't recognize these are the same as "GE"

**Result:**
- Old "GE" positions marked as closed (not found in eToro sync)
- New "1017" positions not recognized as GE
- Database and eToro completely out of sync

---

## Immediate Actions Required

### 1. Cancel Pending GE Orders (URGENT)
```bash
# These 2 orders MUST be cancelled immediately
python scripts/utilities/cancel_all_pending_orders.py
```

Orders to cancel:
- `6d95f336-79d3-4d35-b587-ce77fbd76345` (1631 shares)
- `c31090c2-2844-4297-bb8f-fddc02f9381f` (3000 shares)

**Why:** If these fill, we'll have 7 GE positions (5 existing + 2 new)

### 2. Fix Database Sync (CRITICAL)
The sync process needs to:
1. Map instrument IDs to ticker symbols
2. Update existing positions instead of marking them closed
3. Preserve strategy_id when syncing

### 3. Verify All Positions (URGENT)
Check if other symbols have the same issue:
```bash
python scripts/verify_all_position_sync.py
```

---

## Technical Fix Required

### File: `src/core/order_monitor.py`

**Problem in `sync_positions()` method:**
```python
# Current code:
existing_pos = session.query(PositionORM).filter_by(
    etoro_position_id=pos.etoro_position_id  # ✅ Matches by eToro ID
).first()

if existing_pos:
    # Update existing - but doesn't update symbol!
    existing_pos.current_price = pos.current_price
    # ❌ Missing: existing_pos.symbol = pos.symbol
```

**Fix needed:**
```python
if existing_pos:
    # Update ALL fields including symbol
    existing_pos.symbol = pos.symbol  # ← ADD THIS
    existing_pos.current_price = pos.current_price
    existing_pos.unrealized_pnl = pos.unrealized_pnl
    # ... etc
```

### File: `src/utils/symbol_mapper.py` (NEW)

Need to create a symbol mapper:
```python
INSTRUMENT_ID_TO_SYMBOL = {
    '1017': 'GE',
    '1': 'BTC',  # Bitcoin
    '18': 'ETH',  # Ethereum
    # ... etc
}

def normalize_symbol(symbol_or_id: str) -> str:
    """Convert instrument ID to ticker symbol."""
    return INSTRUMENT_ID_TO_SYMBOL.get(symbol_or_id, symbol_or_id)
```

---

## Verification Steps

After fixes:

1. **Sync positions:**
   ```bash
   python scripts/sync_etoro_positions.py
   ```

2. **Verify GE positions:**
   ```bash
   python scripts/check_ge_duplication_bug.py
   ```

3. **Expected result:**
   ```
   Database:
   - Open GE positions: 5 (updated from eToro)
   - Closed GE positions: 0
   - Pending GE orders: 0 (cancelled)
   
   eToro:
   - GE positions (1017): 5
   ```

4. **Verify duplication prevention:**
   - Run E2E test
   - Should NOT create new GE orders (already have 5, max is 3)
   - Should log: "Symbol limit reached: 5 strategies already trading GE"

---

## Long-term Fix

### Prevent This From Happening Again:

1. **Always use instrument IDs internally**
   - Store positions with eToro instrument ID
   - Map to ticker symbols only for display

2. **Bidirectional symbol mapping**
   - Maintain mapping: ticker ↔ instrument ID
   - Update mapping when new instruments discovered

3. **Sync validation**
   - After sync, verify position counts match
   - Alert if database count != eToro count
   - Log any symbol mismatches

4. **Regular sync audits**
   - Daily check: database positions vs eToro positions
   - Alert on discrepancies
   - Auto-correct minor issues

---

## Testing Plan

1. ✅ Cancel pending GE orders
2. ✅ Fix sync_positions() to update symbol
3. ✅ Create symbol mapper utility
4. ✅ Re-sync all positions
5. ✅ Verify GE shows 5 open positions
6. ✅ Run E2E test - should reject new GE orders
7. ✅ Monitor for 24 hours

---

## Success Criteria

- ✅ Database shows 5 open GE positions (matching eToro)
- ✅ No pending GE orders
- ✅ Duplication prevention blocks new GE orders
- ✅ Symbol mapping works for all instruments
- ✅ Sync process preserves strategy_id
- ✅ No position count mismatches

---

## Priority

🔴 **CRITICAL - STOP ALL TRADING**

Do NOT run autonomous trading until this is fixed. The system will create duplicate positions and violate risk limits.

---

## Files to Create/Modify

1. `src/core/order_monitor.py` - Fix sync_positions()
2. `src/utils/symbol_mapper.py` - NEW - Create symbol mapper
3. `scripts/verify_all_position_sync.py` - NEW - Audit script
4. `scripts/fix_ge_positions.py` - NEW - One-time fix for GE

---

## Estimated Time to Fix

- Cancel orders: 5 minutes
- Fix sync code: 30 minutes
- Create symbol mapper: 1 hour
- Test and verify: 1 hour
- **Total: ~3 hours**

---

## Next Steps

1. **IMMEDIATE:** Cancel the 2 pending GE orders
2. **URGENT:** Fix sync_positions() method
3. **HIGH:** Create symbol mapper
4. **MEDIUM:** Audit all other positions
5. **LOW:** Implement long-term monitoring

