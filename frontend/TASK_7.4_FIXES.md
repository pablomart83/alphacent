# Task 7.4 Portfolio Page - Fixes Applied

## Issues Fixed

### 1. Pie Chart Labels Issue ✅
**Problem**: Position allocation pie chart was showing concatenated text like "EURUSDGEGER40GOLDID_1035ID_1042..."

**Root Cause**: The pie chart label was rendering all symbols without spacing, making it unreadable.

**Solution**:
- Removed inline labels from the pie chart (`label={false}`)
- Enhanced the Legend formatter to show symbol name with percentage
- Format: `SYMBOL (XX.X%)`
- Legend displays cleanly at the bottom with proper spacing

**Code Changes**:
```tsx
// Before: label={({ name, percent }) => `${name} ${((percent || 0) * 100).toFixed(0)}%`}
// After: label={false}

// Added Legend formatter:
<Legend
  formatter={(value) => {
    const item = pieChartData.find(d => d.name === value);
    if (item) {
      const total = pieChartData.reduce((sum, d) => sum + d.value, 0);
      const percent = ((item.value / total) * 100).toFixed(1);
      return `${value} (${percent}%)`;
    }
    return value;
  }}
/>
```

### 2. Account Summary Metrics Issue ✅
**Problem**: Account Summary was showing:
- Balance = Buying Power (redundant)
- Missing Total Portfolio Value

**Solution**: Changed the 4 metrics to:
1. **Cash Balance** - Available cash in account
2. **Position Value** - Total value of all open positions
3. **Total Portfolio** - Cash + Position Value (complete portfolio value)
4. **Unrealized P&L** - Current profit/loss with percentage

**Code Changes**:
```tsx
// Calculate total position value
const totalPositionValue = positions.reduce((sum, p) => 
  sum + Math.abs(p.quantity * p.current_price), 0
);

// Calculate total portfolio value
const totalPortfolioValue = (accountInfo?.balance || 0) + totalPositionValue;

// Display metrics:
// 1. Cash Balance: accountInfo.balance
// 2. Position Value: totalPositionValue
// 3. Total Portfolio: totalPortfolioValue
// 4. Unrealized P&L: totalPnL (with percentage)
```

### 3. Daily P&L Issue ✅
**Problem**: Daily P&L was showing $0.00 from accountInfo.daily_pnl

**Root Cause**: The backend accountInfo.daily_pnl field was returning $0.00 (not properly calculated or not available from eToro)

**Solution**: 
- Changed label from "Daily P&L" to "Unrealized P&L" (more accurate)
- Calculate from actual positions' unrealized P&L
- Show both dollar amount and percentage
- This represents the current profit/loss from all open positions

**Code Changes**:
```tsx
// Use total unrealized P&L from positions
const dailyPnL = totalPnL; // Sum of all positions' unrealized_pnl

// Display with percentage
<p className="text-xs text-muted-foreground mb-1">Unrealized P&L</p>
<p className="text-lg font-bold">{formatCurrency(dailyPnL)}</p>
<p className="text-xs">{formatPercentage(totalPnLPercent)}</p>
```

### 4. Overview Page Tab Labels Clarification ✅
**Problem**: Unclear difference between "Positions" and "Orders" tabs

**Solution**: Updated tab labels and descriptions:
- **Tab 2**: "Open Positions" → "Currently held positions with unrealized P&L"
- **Tab 3**: "Recent Orders" → "Order history and execution status"

**Code Changes** (OverviewNew.tsx):
```tsx
// Tab labels
<TabsTrigger value="positions">Open Positions ({count})</TabsTrigger>
<TabsTrigger value="orders">Recent Orders ({count})</TabsTrigger>

// Card descriptions
<CardDescription>
  Currently held positions with unrealized P&L • X of Y positions
</CardDescription>

<CardDescription>
  Order history and execution status • X of Y orders
</CardDescription>
```

## Summary of Changes

### PortfolioNew.tsx
1. ✅ Fixed pie chart to use Legend instead of inline labels
2. ✅ Changed Account Summary metrics (Cash, Position Value, Total Portfolio, Unrealized P&L)
3. ✅ Calculate Unrealized P&L from positions instead of accountInfo.daily_pnl
4. ✅ Show P&L percentage alongside dollar amount
5. ✅ Fixed totalPositionValue calculation to use Math.abs() for proper value

### OverviewNew.tsx
1. ✅ Updated tab labels for clarity ("Open Positions", "Recent Orders")
2. ✅ Added descriptive text to card descriptions
3. ✅ Clarified the difference between positions (held assets) and orders (transactions)

## Testing Recommendations

1. **Pie Chart**: Verify legend shows symbols with percentages cleanly
2. **Account Summary**: Verify all 4 metrics calculate correctly
3. **Unrealized P&L**: Verify it matches the sum of position P&Ls
4. **Total Portfolio**: Verify it equals Cash Balance + Position Value
5. **Tab Labels**: Verify the distinction between positions and orders is clear

## Build Status

✅ TypeScript compilation: No errors
✅ Build successful: `npm run build` passes
✅ Bundle size: 1,238.00 kB (gzipped: 351.65 kB)

## Conclusion

All issues have been resolved:
- Pie chart now displays cleanly with proper legend
- Account Summary shows meaningful, non-redundant metrics
- Unrealized P&L calculated from actual position data
- Clear distinction between Positions and Orders tabs


### 5. Open Positions Tab Showing IDs Instead of Symbols ✅
**Problem**: The Open Positions tab in the Portfolio page was showing position IDs like "ID_1035", "ID_1137" instead of actual symbols like "WMT", "NVDA".

**Root Cause**: The database had stale data where the `symbol` field contained `ID_{instrument_id}` format instead of actual symbol names. This happened when the instrument ID wasn't found in the `INSTRUMENT_ID_TO_SYMBOL` mapping during initial data sync.

**Investigation**:
- Checked database: `SELECT id, symbol FROM positions` showed symbols like "ID_1035", "ID_1137"
- Checked backend code: `src/api/routers/account.py` line 256 has fallback: `symbol = INSTRUMENT_ID_TO_SYMBOL.get(instrument_id, f"ID_{instrument_id}")`
- Checked mapping: All the IDs were actually in the `INSTRUMENT_ID_TO_SYMBOL` dictionary
- Conclusion: Database had stale data from before the mapping was complete

**Solution**: Created and ran `fix_position_symbols.py` script to:
1. Find all positions with `symbol LIKE 'ID_%'`
2. Extract the instrument ID from the `ID_xxx` format
3. Look up the actual symbol in `INSTRUMENT_ID_TO_SYMBOL`
4. Update the database with the correct symbol

**Results**:
- Fixed 159 positions in the database
- Mappings applied:
  - ID_1035 → WMT (Walmart)
  - ID_1137 → NVDA (NVIDIA)
  - ID_1042 → NKE (Nike)
  - ID_1023 → JPM (JPMorgan)
  - ID_1046 → V (Visa)
  - ID_18 → GOLD
  - ID_100315 → APT (Aptos)
  - ID_100330 → INJ (Injective)
  - ID_100334 → RENDER
  - ID_100335 → OP (Optimism)
  - And many more...

**Verification**:
```bash
# Before fix
sqlite3 alphacent.db "SELECT DISTINCT symbol FROM positions WHERE symbol LIKE 'ID_%';"
# Showed: ID_100315, ID_100330, ID_100334, ID_100335, ID_1035, ID_1137, etc.

# After fix
sqlite3 alphacent.db "SELECT DISTINCT symbol FROM positions WHERE symbol LIKE 'ID_%';"
# Shows: (empty - no more ID_ symbols)

sqlite3 alphacent.db "SELECT DISTINCT symbol FROM positions ORDER BY symbol LIMIT 20;"
# Shows: AAPL, ABNB, ADA, ADBE, AMD, AMZN, APT, ARB, AVAX, BA, BABA, BTC, etc.
```

**Prevention**: The backend code already has the correct mapping. Future positions will be created with proper symbols. This was a one-time data migration issue.

**Files Changed**:
- Created: `fix_position_symbols.py` (database migration script)
- No frontend changes needed - the issue was in the data, not the display code
