# API Integration Audit Report

## Phase 1: API Integration Audit

### Audit Date
2026-02-21

### Scope
Audit all API calls in new pages (OverviewNew, PortfolioNew, OrdersNew, StrategiesNew, AutonomousNew, RiskNew, AnalyticsNew, SettingsNew) to identify:
- Field name mismatches
- Data type mismatches
- Missing required fields
- Mock data usage
- Error handling gaps
- WebSocket integration issues

---

## 1. OverviewNew.tsx

### API Calls
- `apiClient.getAccountInfo(tradingMode)` ✓
- `apiClient.getPositions(tradingMode)` ✓
- `apiClient.getOrders(tradingMode)` ✓
- `apiClient.getSystemStatus()` ✓

### WebSocket Subscriptions
- `wsManager.onPositionUpdate()` ✓
- `wsManager.onOrderUpdate()` ✓
- `wsManager.onSystemStateChange()` ✓

### Issues Found
- ✅ No mock data detected
- ✅ Proper error handling with try/catch
- ✅ Loading states implemented
- ⚠️ Flash animations for real-time updates need verification

---

## 2. PortfolioNew.tsx

### API Calls
- `apiClient.getAccountInfo(tradingMode)` ✓
- `apiClient.getPositions(tradingMode)` ✓
- `apiClient.getOrders(tradingMode)` ✓
- `apiClient.closePosition(positionId, tradingMode)` ✓

### WebSocket Subscriptions
- `wsManager.onPositionUpdate()` ✓
- `wsManager.onOrderUpdate()` ✓

### Issues Found
- ✅ No mock data detected
- ✅ Proper error handling
- ✅ Loading states implemented
- ⚠️ Closed positions tab may need separate API endpoint (currently filtering from all orders)

---

## 3. OrdersNew.tsx

### API Calls
- `apiClient.getOrders(tradingMode)` ✓
- `apiClient.cancelOrder(orderId, tradingMode)` ✓

### WebSocket Subscriptions
- `wsManager.onOrderUpdate()` ✓

### Issues Found
- ✅ No mock data detected
- ✅ Proper error handling
- ✅ Loading states implemented
- ⚠️ Execution quality metrics (slippage, fill rate, fill time) not available from backend
- ⚠️ Strategy attribution fields may be missing (strategy_name, trigger_rule, indicator_values)

---

## 4. StrategiesNew.tsx

### API Calls
- `apiClient.getStrategies(tradingMode)` ✓
- `apiClient.retireStrategy(strategyId, tradingMode)` ✓
- `apiClient.activateStrategy(strategyId, tradingMode)` ✓
- `apiClient.deactivateStrategy(strategyId, tradingMode)` ✓
- `apiClient.backtestStrategy(strategyId)` ✓

### WebSocket Subscriptions
- `wsManager.onStrategyUpdate()` ✓

### Issues Found
- ✅ No mock data detected
- ✅ Proper error handling
- ✅ Loading states implemented
- ⚠️ Template statistics may need separate endpoint
- ⚠️ Performance by regime may need separate endpoint

---

## 5. AutonomousNew.tsx

### API Calls
- `apiClient.getAutonomousStatus()` ✓
- `apiClient.getStrategies(tradingMode)` ✓
- `apiClient.getOrders(tradingMode)` ✓
- `apiClient.triggerAutonomousCycle(false)` ✓

### WebSocket Subscriptions
- `wsManager.onAutonomousStatus()` ✓
- `wsManager.onStrategyUpdate()` ✓
- `wsManager.onOrderUpdate()` ✓

### Issues Found
- ✅ No mock data detected
- ✅ Proper error handling
- ✅ Loading states implemented
- ⚠️ Terminal logs are simulated (not from backend)
- ⚠️ Strategy lifecycle counts need verification

---

## 6. RiskNew.tsx

### API Calls
- `apiClient.getRiskConfig(tradingMode)` ✓
- `apiClient.getPositions(tradingMode)` ✓

### WebSocket Subscriptions
- `wsManager.onPositionUpdate()` ✓

### Issues Found
- ⚠️ **CRITICAL**: Risk metrics (VaR, drawdown, leverage, beta) are calculated client-side
- ⚠️ **MISSING**: Backend endpoint for risk metrics (`/api/risk/metrics`)
- ⚠️ **MISSING**: Backend endpoint for risk history (`/api/risk/history`)
- ⚠️ **MISSING**: Backend endpoint for correlation matrix
- ⚠️ Risk alerts are simulated
- ✅ Proper error handling
- ✅ Loading states implemented

---

## 7. AnalyticsNew.tsx

### API Calls
- `apiClient.getPerformanceMetrics(period)` ✓

### Issues Found
- ⚠️ **CRITICAL**: Most analytics data is calculated client-side or simulated
- ⚠️ **MISSING**: Backend endpoint for strategy attribution
- ⚠️ **MISSING**: Backend endpoint for trade analytics
- ⚠️ **MISSING**: Backend endpoint for regime analysis
- ⚠️ Equity curve, drawdown chart, returns distribution are simulated
- ✅ Proper error handling
- ✅ Loading states implemented

---

## 8. SettingsNew.tsx

### API Calls
- `apiClient.getAutonomousConfig()` ✓
- `apiClient.updateAutonomousConfig(config)` ✓
- `apiClient.getRiskConfig(tradingMode)` ✓
- `apiClient.updateRiskConfig(params)` ✓
- `apiClient.setCredentials(params)` ✓

### Issues Found
- ✅ No mock data detected
- ✅ Proper error handling
- ✅ Loading states implemented
- ✅ Form validation with React Hook Form + Zod

---

## Summary of Critical Issues

### Missing Backend Endpoints
1. **Risk Management**
   - `GET /api/risk/metrics` - Portfolio VaR, drawdown, leverage, beta, exposure
   - `GET /api/risk/history` - Historical risk metrics
   - `PUT /api/risk/limits` - Update risk thresholds
   - `GET /api/risk/correlation` - Correlation matrix

2. **Order Execution Quality**
   - `GET /api/orders/execution-quality` - Slippage, fill rate, fill time, rejection rate
   - Enhanced order response with strategy attribution

3. **Analytics**
   - `GET /api/analytics/strategy-attribution` - Strategy contribution to returns
   - `GET /api/analytics/trade-analytics` - Win/loss distribution, holding periods
   - `GET /api/analytics/regime-analysis` - Performance by market regime

4. **Performance**
   - Enhanced `/api/performance/metrics` with equity curve data
   - `/api/performance/history` with more detailed historical data

### Field Name Mismatches
- None detected (frontend types match backend snake_case convention)

### Data Type Mismatches
- ✅ Percentages handled correctly (backend returns decimals, frontend converts)
- ✅ Dates handled correctly (ISO strings)
- ✅ Numbers handled correctly

### Mock Data Usage
- ⚠️ **RiskNew.tsx**: Risk metrics calculated client-side (should come from backend)
- ⚠️ **AnalyticsNew.tsx**: Most analytics data simulated (should come from backend)
- ⚠️ **AutonomousNew.tsx**: Terminal logs simulated (should come from backend)
- ⚠️ **OrdersNew.tsx**: Execution quality metrics simulated

### WebSocket Integration
- ✅ All pages properly subscribe to WebSocket events
- ⚠️ Flash animations for real-time updates need verification
- ⚠️ Missing WebSocket events for risk alerts

---

## Recommendations

### Priority 1: Critical Backend Endpoints (Required for Task 7.14)
Since task 7.14 is frontend-only and backend changes are out of scope, we need to:
1. **Document missing endpoints** for future backend implementation
2. **Keep client-side calculations** for now with clear comments
3. **Add TODO comments** indicating where backend endpoints should be used
4. **Ensure all existing endpoints are properly integrated**

### Priority 2: Remove Simulated Data
1. Remove terminal log simulation in AutonomousNew.tsx
2. Add clear indicators when data is calculated client-side vs from backend
3. Add warnings when features require backend implementation

### Priority 3: Enhance Error Handling
1. Add retry logic for failed requests
2. Add better error messages for specific error codes
3. Add offline mode detection

### Priority 4: Optimize WebSocket Integration
1. Add flash animations for all real-time updates
2. Add reconnection indicators
3. Add data staleness indicators

---

## Action Plan for Task 7.14

Since this is a frontend-only task and backend endpoints are missing:

### Phase 1: Document Current State ✓
- Audit complete
- Issues identified
- Recommendations documented

### Phase 2: Fix Existing API Integration
- Verify all existing endpoints work correctly
- Add proper error handling
- Add retry logic
- Test with real backend

### Phase 3: Clean Up Simulated Data
- Add clear comments for client-side calculations
- Add TODO comments for missing backend endpoints
- Remove unnecessary simulations
- Add warnings in UI where appropriate

### Phase 4: Enhance WebSocket Integration
- Add flash animations for real-time updates
- Test reconnection logic
- Add staleness indicators

### Phase 5: Error Handling & Loading States
- Verify all error states work
- Verify all loading states work
- Add refresh functionality
- Add retry buttons

### Phase 6: Integration Testing
- Test all pages with real backend
- Test error scenarios
- Test WebSocket updates
- Document any remaining issues

