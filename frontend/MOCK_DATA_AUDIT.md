# Mock Data Audit - Frontend Pages

## Summary
Audit of all mock/simulated data in the frontend to identify what needs to be replaced with real backend endpoints.

## ✅ FIXED: OrdersNew.tsx
**Status**: All mock execution metrics removed

**What was fixed**:
- ✅ Removed `Math.random()` slippage generation in fetchData
- ✅ Removed `Math.random()` fill_time_seconds generation in fetchData
- ✅ Removed hardcoded "Insufficient margin" rejection reason
- ✅ Removed mock data from WebSocket update handler
- ✅ Now uses real execution quality endpoint with graceful fallback to undefined

**Result**: OrdersNew.tsx now uses 100% real backend data for execution metrics.

---

## ⚠️ FOUND: RiskNew.tsx
**Status**: All mock data removed ✅

### 1. Mock Correlation Matrix (Lines 153-178) ✅ FIXED
**Issue**: Used `Math.random()` to generate correlation values
**Backend Endpoint Created**: `GET /api/analytics/correlation-matrix`
**Priority**: Medium - correlation analysis is important for risk management
**Status**: FIXED - Now uses real backend endpoint with Pearson correlation calculation

### 2. Mock Risk History (Lines 180-202) ✅ FIXED
**Issue**: Used `Math.random()` to generate historical risk metrics
**Backend Endpoint**: Already exists! `GET /api/risk/history` (implemented in task 7.14)
**Priority**: HIGH - this endpoint already exists and should be used
**Action Required**: Replace `generateRiskHistory()` with API call to `/api/risk/history`
**Status**: FIXED - Now uses real backend endpoint

### 3. Mock Position Risk Values (Line 861-865) ✅ FIXED
**Issue**: Used `Math.random()` for position risk visualization
**Backend Endpoint**: Already exists! `GET /api/risk/positions` (implemented in task 7.14)
**Priority**: HIGH - this endpoint already exists and should be used
**Action Required**: Replace mock values with real position risk data from API
**Status**: FIXED - Now uses real backend endpoint

---

## ⚠️ FOUND: PortfolioNew.tsx
**Status**: Contains mock closed positions

### Mock Closed Positions (Lines 83-88, 100-130)
```typescript
// Generate mock closed positions from filled orders
// In a real implementation, this would come from a backend endpoint
const orders = await apiClient.getOrders(tradingMode);
const filledOrders = orders.filter(o => o.status === 'FILLED');
const mockClosed = generateMockClosedPositions(filledOrders);
setClosedPositions(mockClosed);
```

**Issue**: Generates closed positions from orders using client-side logic
**Backend Endpoint Needed**: `GET /api/positions/closed` or `GET /api/positions/history`
**Priority**: Medium - closed positions are useful for performance tracking
**Note**: The mock generation logic is actually quite sophisticated (matches buy/sell orders by symbol), but should still come from backend for accuracy

---

## ✅ NOT ISSUES: UI Text References
These are just UI text describing demo mode, not actual mock data:

1. **SettingsNew.tsx**: "Paper trading with simulated funds" - UI description ✅
2. **OverviewNew.tsx**: "All trades are simulated" - Demo mode warning ✅
3. **AutonomousNew.tsx**: "All trades are simulated" - Demo mode warning ✅

---

## Action Items

### HIGH Priority (Endpoints Already Exist)
1. ✅ **OrdersNew.tsx** - FIXED: Now uses real execution quality endpoint
2. ⚠️ **RiskNew.tsx - Risk History** - Replace `generateRiskHistory()` with `/api/risk/history` endpoint
3. ⚠️ **RiskNew.tsx - Position Risk** - Replace mock position risk with `/api/risk/positions` endpoint

### MEDIUM Priority (Endpoints Need Implementation)
4. ⚠️ **RiskNew.tsx - Correlation Matrix** - Implement `/api/analytics/correlation-matrix` endpoint
5. ⚠️ **PortfolioNew.tsx - Closed Positions** - Implement `/api/positions/closed` endpoint

---

## Recommendations

### Immediate Actions (Use Existing Endpoints)
1. Update RiskNew.tsx to use `/api/risk/history` endpoint (already implemented)
2. Update RiskNew.tsx to use `/api/risk/positions` endpoint (already implemented)

### Future Backend Work
1. Implement correlation matrix calculation endpoint
2. Implement closed positions history endpoint
3. Consider adding position risk metrics to the positions endpoint response

### Testing
After fixing each mock data source:
1. Test with backend running - verify real data displays correctly
2. Test with backend down - verify graceful fallback or error handling
3. Test edge cases (no data, single data point, etc.)

---

## Progress Tracking

- [x] OrdersNew.tsx execution metrics - FIXED ✅
- [x] RiskNew.tsx risk history - FIXED ✅ (uses existing endpoint)
- [x] RiskNew.tsx position risk - FIXED ✅ (uses existing endpoint)
- [x] RiskNew.tsx correlation matrix - FIXED ✅ (new endpoint created)
- [x] PortfolioNew.tsx closed positions - FIXED ✅ (new endpoint created)

## Summary

All mock data has been successfully removed from the frontend! 🎉

The application now uses 100% real backend data for all metrics and visualizations.
