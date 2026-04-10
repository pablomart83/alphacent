# Duplicate Order Root Cause Analysis

**Date**: 2026-02-21  
**Test**: Task 6.6 E2E Trade Execution Test  
**Status**: 🔴 TWO ROOT CAUSES IDENTIFIED

---

## Problem Summary

Two critical issues are preventing the duplicate order prevention from working:

1. **Symbol Mismatch**: Orders use our symbol (`DOGE`) but positions use eToro's internal ID (`100043`)
2. **No SHORT Strategies Generated**: All strategies are LONG-only despite having SHORT templates available

### Evidence

From the E2E test, we see 7 DOGE orders from the same strategy:

```
Orders from DEMO strategies (last 2h): 15
- 7c233ba5-2d2… | BUY 1926.7800240000001 DOGE | status=FILLED
- 8540c9cd-6f9… | BUY 1916.66072 DOGE | status=FILLED
- a4800e61-fd2… | BUY 1906.5945080000001 DOGE | status=FILLED
- 50460d98-a2a… | BUY 1906.5945080000001 DOGE | status=FILLED
- cc08fdf2-fba… | BUY 1721.42500007632 DOGE | status=FILLED
- 786b1612-075… | BUY 1704.03860007632 DOGE | status=FILLED
- 9b5213e0-f82… | BUY 1704.03860007632 DOGE | status=FILLED
```

All from strategy: `SMA Trend Momentum DOGE V14` (ID: `184c111d-3b20-4716-b22a-17d8737edccf`)

### Database Investigation

**Orders table** (symbol = `DOGE`):
```
DOGE Orders:
  9b5213e0-f82... | 184c111d-3b2... | FILLED | 2026-02-21 20:30:00
  786b1612-075... | 184c111d-3b2... | FILLED | 2026-02-21 20:29:05
  cc08fdf2-fba... | 184c111d-3b2... | FILLED | 2026-02-21 20:24:02
  50460d98-a2a... | 184c111d-3b2... | FILLED | 2026-02-21 20:19:34
  a4800e61-fd2... | 184c111d-3b2... | FILLED | 2026-02-21 20:19:15
  8540c9cd-6f9... | 184c111d-3b2... | FILLED | 2026-02-21 20:18:07
  7c233ba5-2d2... | 184c111d-3b2... | FILLED | 2026-02-21 20:16:18
```

**Positions table** (symbol = `100043` - eToro's internal ID):
```
All Positions for strategy 184c111d-3b2...: 2
  6267d945-2c6... | 100043 | OPEN | Qty: 19165.560916 | Entry: $0.0995
  afe11f72-000... | 100043 | OPEN | Qty: 17126.03015 | Entry: $0.0995
```

---

## Root Cause

### Symbol Mismatch

1. **Orders** are created with our symbol: `DOGE`
2. **Positions** are created with eToro's symbol: `100043`
3. **Duplicate prevention** checks: `position.symbol == signal.symbol`
4. **Result**: `100043 != DOGE` → duplicate prevention fails

### Code Location

**File**: `src/core/order_monitor.py`  
**Method**: `check_submitted_orders()`  
**Line**: ~476

```python
new_pos = PositionORM(
    id=str(uuid.uuid4()),
    strategy_id=order.strategy_id,  # ✅ Correct
    symbol=etoro_pos.symbol,        # ❌ BUG: Uses eToro's symbol (100043)
    side=etoro_pos.side,
    quantity=etoro_pos.quantity,
    ...
)
```

**Should be**:
```python
new_pos = PositionORM(
    id=str(uuid.uuid4()),
    strategy_id=order.strategy_id,
    symbol=order.symbol,            # ✅ FIX: Use order's symbol (DOGE)
    side=etoro_pos.side,
    quantity=etoro_pos.quantity,
    ...
)
```

---

## Why This Happens

### Order Creation Flow

1. **Signal generation**: Creates signal with `symbol='DOGE'`
2. **Order execution**: Creates order with `symbol='DOGE'`
3. **Order submission**: Submits to eToro with `symbol='DOGE'`
4. **eToro response**: Returns position with `symbol='100043'` (internal ID)
5. **Position creation**: Uses eToro's symbol `100043` instead of order's symbol `DOGE`

### Duplicate Prevention Flow

1. **Next signal cycle**: Strategy generates signal for `DOGE`
2. **Coordination check**: Queries positions with `symbol='DOGE'`
3. **Database query**: `SELECT * FROM positions WHERE symbol='DOGE' AND closed_at IS NULL`
4. **Result**: 0 positions found (because positions have `symbol='100043'`)
5. **Duplicate prevention**: FAILS - allows duplicate order

---

## Impact

### Severity: HIGH

- **Duplicate orders**: Multiple orders for same symbol from same strategy
- **Capital inefficiency**: Over-concentration in single symbol
- **Risk management**: Exceeds intended position sizes
- **Performance tracking**: Incorrect attribution (multiple positions per strategy)

### Affected Symbols

Any symbol where eToro uses internal IDs:
- `DOGE` → `100043`
- Potentially other crypto and CFDs

---

## Solution

### Fix 1: Use Order Symbol in Position Creation (RECOMMENDED)

**File**: `src/core/order_monitor.py`  
**Method**: `check_submitted_orders()`  
**Change**: Line ~476

```python
# BEFORE
symbol=etoro_pos.symbol,  # Uses eToro's internal ID

# AFTER
symbol=order.symbol,      # Uses our consistent symbol
```

**Rationale**:
- Orders and positions use same symbol
- Duplicate prevention works correctly
- Consistent symbol across entire system
- No changes needed to duplicate prevention logic

### Fix 2: Update Existing Positions (Data Migration)

**File**: `scripts/utilities/fix_position_symbols.py` (new)

```python
"""
Fix position symbols to match order symbols.

Updates all positions where symbol is an eToro internal ID (numeric)
to use the corresponding order's symbol.
"""

from src.models.database import get_database
from src.models.orm import PositionORM, OrderORM

db = get_database()
session = db.get_session()

try:
    # Find positions with numeric symbols (eToro internal IDs)
    positions = session.query(PositionORM).filter(
        PositionORM.symbol.regexp_match(r'^\d+$')
    ).all()
    
    print(f"Found {len(positions)} positions with numeric symbols")
    
    for pos in positions:
        # Find the order that created this position
        order = session.query(OrderORM).filter(
            OrderORM.strategy_id == pos.strategy_id,
            OrderORM.etoro_order_id.isnot(None)
        ).order_by(OrderORM.submitted_at.desc()).first()
        
        if order:
            old_symbol = pos.symbol
            pos.symbol = order.symbol
            print(f"  Updated position {pos.id[:12]}... symbol: {old_symbol} → {order.symbol}")
    
    session.commit()
    print(f"✅ Updated {len(positions)} positions")

except Exception as e:
    session.rollback()
    print(f"❌ Error: {e}")
finally:
    session.close()
```

---

## Testing Plan

### 1. Unit Test

**File**: `tests/test_position_symbol_consistency.py` (new)

```python
def test_position_uses_order_symbol_not_etoro_symbol():
    """Verify positions are created with order symbol, not eToro symbol."""
    # Create order with symbol='DOGE'
    order = create_test_order(symbol='DOGE')
    
    # Simulate eToro response with internal ID
    etoro_pos = create_etoro_position(symbol='100043')
    
    # Create position from order
    position = create_position_from_order(order, etoro_pos)
    
    # Assert position uses order's symbol, not eToro's
    assert position.symbol == 'DOGE'
    assert position.symbol != '100043'
```

### 2. Integration Test

Run E2E test again after fix:
```bash
python scripts/e2e_trade_execution_test.py
```

**Expected result**:
- First cycle: 7 signals → 7 orders → 7 positions
- Second cycle: 0 signals (duplicate prevention works)
- No duplicate orders for same strategy-symbol

### 3. Production Verification

After deployment:
1. Monitor logs for "Position duplicate check" messages
2. Verify no duplicate orders created
3. Check database: `SELECT strategy_id, symbol, COUNT(*) FROM positions WHERE closed_at IS NULL GROUP BY strategy_id, symbol HAVING COUNT(*) > 1`
4. Should return 0 rows

---

## Acceptance Criteria

✅ Positions created with order's symbol (not eToro's internal ID)  
✅ Duplicate prevention works correctly  
✅ No duplicate orders for same strategy-symbol  
✅ Existing positions migrated to correct symbols  
✅ E2E test passes without duplicates  

---

## Priority

**CRITICAL** - This is the root cause of the duplicate order issue that's been creating multiple orders for DOGE and other symbols.

**Estimated Fix Time**: 30 minutes (code change + testing)  
**Estimated Migration Time**: 10 minutes (data fix)

---

## Next Steps

1. ✅ Root cause identified
2. ⏳ Apply fix to `order_monitor.py`
3. ⏳ Create data migration script
4. ⏳ Run unit tests
5. ⏳ Run E2E test
6. ⏳ Deploy to production
7. ⏳ Monitor for 24 hours

---

**Status**: Ready for implementation


---

## Issue 2: No SHORT Strategies Generated

### Problem

Despite having 9 SHORT strategy templates (templates 43-51), NO SHORT strategies are being generated. All 10 DEMO strategies have `Direction: UNKNOWN` and all orders are BUY orders.

### Evidence

**From database query**:
```
DEMO Strategies: 10

RSI Mild Oversold PLTR V6
  Direction: UNKNOWN
  Entry conditions: ['RSI(14) > 30 AND RSI(14) < 45']...

SMA Trend Momentum DOGE V14
  Direction: UNKNOWN
  Entry conditions: ['CLOSE > SMA(20) AND RSI(14) > 45 AND RSI(14) < 65']...

... (all 10 strategies have Direction: UNKNOWN)
```

**From E2E test orders**:
```
All 15 orders are BUY orders:
- BUY 3112.4908080000005 PLTR
- BUY 1926.7800240000001 DOGE
- BUY 1630.352328 SPY
- BUY 1916.66072 DOGE
... (all BUY, no SELL)
```

### Root Cause

SHORT strategy templates (43-51) are ONLY assigned to TRENDING_DOWN market regimes:

```python
# Template 43: RSI Overbought Short
templates.append(StrategyTemplate(
    name="RSI Overbought Short",
    description="Short when RSI indicates extreme overbought conditions",
    strategy_type=StrategyType.MEAN_REVERSION,
    market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK],  # ❌ Only downtrends
    ...
    metadata={"direction": "short"}
))
```

**Current market regime**: Likely RANGING or TRENDING_UP (not TRENDING_DOWN)

**Result**: No SHORT templates are eligible for the current market regime, so no SHORT strategies are generated.

### Why This Matters

1. **Diversification**: All strategies are directionally correlated (all LONG)
2. **Risk**: Cannot profit from or hedge against market declines
3. **Opportunity**: Missing 50% of trading opportunities (downside moves)
4. **Portfolio Balance**: Unbalanced exposure (100% long bias)

### Solution Options

#### Option 1: Add SHORT Templates for All Regimes (RECOMMENDED)

Add SHORT versions of existing LONG templates that work in all regimes:

```python
# Example: RSI Overbought Short for RANGING markets
templates.append(StrategyTemplate(
    name="RSI Overbought Short Ranging",
    description="Short when RSI overbought in ranging markets",
    strategy_type=StrategyType.MEAN_REVERSION,
    market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL],  # ✅ Works in ranging
    entry_conditions=[
        "RSI(14) > 70"  # Overbought
    ],
    exit_conditions=[
        "RSI(14) < 30"  # Cover on oversold
    ],
    required_indicators=["RSI"],
    default_parameters={
        "rsi_period": 14,
        "overbought_threshold": 70,
        "oversold_threshold": 30,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.04,
    },
    expected_trade_frequency="2-4 trades/month",
    expected_holding_period="3-7 days",
    risk_reward_ratio=2.0,
    metadata={"direction": "short"}
))
```

**Add SHORT versions for**:
- RSI Overbought Short (RANGING, RANGING_LOW_VOL)
- Bollinger Upper Band Short (RANGING, RANGING_LOW_VOL)
- SMA Breakdown Short (RANGING, TRENDING_UP_WEAK)
- MACD Bearish Short (RANGING, TRENDING_UP_WEAK)
- Stochastic Overbought Short (RANGING, RANGING_LOW_VOL)

#### Option 2: Make Existing Templates Bidirectional

Modify existing templates to generate both LONG and SHORT signals based on conditions:

```python
# Example: RSI Mean Reversion (bidirectional)
templates.append(StrategyTemplate(
    name="RSI Mean Reversion Bidirectional",
    description="Long when oversold, Short when overbought",
    strategy_type=StrategyType.MEAN_REVERSION,
    market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL],
    entry_conditions=[
        "RSI(14) < 30 OR RSI(14) > 70"  # Both directions
    ],
    exit_conditions=[
        "RSI(14) > 50 AND RSI(14) < 50"  # Exit at neutral
    ],
    required_indicators=["RSI"],
    default_parameters={
        "rsi_period": 14,
        "oversold_threshold": 30,
        "overbought_threshold": 70,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.04,
    },
    expected_trade_frequency="4-8 trades/month",
    expected_holding_period="3-7 days",
    risk_reward_ratio=2.0,
    metadata={"direction": "both"}  # ✅ Bidirectional
))
```

#### Option 3: Adjust Market Regime Detection

If the market is actually in a downtrend but not being detected, fix the market regime analyzer to correctly identify TRENDING_DOWN conditions.

---

## Combined Impact

### Current State
- **Symbol mismatch**: Duplicate prevention fails → 7 DOGE orders from same strategy
- **No SHORT strategies**: 100% long bias → missing 50% of opportunities
- **Result**: Over-concentrated, unbalanced portfolio with duplicate positions

### After Fixes
- **Symbol consistency**: Duplicate prevention works → 1 order per strategy-symbol
- **Balanced strategies**: 50/50 LONG/SHORT mix → diversified exposure
- **Result**: Balanced, diversified portfolio with proper risk management

---

## Priority

**CRITICAL** - Both issues must be fixed:

1. **Issue 1 (Symbol Mismatch)**: Immediate fix (30 min) - prevents duplicates
2. **Issue 2 (No SHORT Strategies)**: High priority (2-3 hours) - enables balanced portfolio

---

## Next Steps

1. ✅ Root causes identified
2. ⏳ Fix symbol mismatch in `order_monitor.py`
3. ⏳ Add SHORT templates for RANGING/TRENDING_UP regimes
4. ⏳ Run E2E test to verify both fixes
5. ⏳ Deploy to production
6. ⏳ Monitor for 24 hours

---

**Status**: Ready for implementation
