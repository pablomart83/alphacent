# New API Endpoints Quick Reference

## Risk Management Endpoints

### Get Risk Metrics
```typescript
const riskMetrics = await apiClient.getRiskMetrics(tradingMode);
// Returns: portfolio_var, current_drawdown, max_drawdown, leverage, 
//          margin_utilization, portfolio_beta, max_position_size, 
//          total_exposure, risk_score, active_positions_count, risk_breakdown
```

### Get Risk History
```typescript
const riskHistory = await apiClient.getRiskHistory(tradingMode, '1W');
// Periods: '1D', '1W', '1M', '3M'
// Returns: Array of { timestamp, var, drawdown, leverage, beta }
```

### Get/Update Risk Limits
```typescript
const limits = await apiClient.getRiskLimits(tradingMode);
// Returns: max_position_size, max_portfolio_exposure, max_daily_loss, 
//          max_drawdown, max_leverage, risk_per_trade

await apiClient.updateRiskLimits(tradingMode, {
  max_position_size: 15.0,
  max_drawdown: 20.0
});
```

### Get Risk Alerts
```typescript
const alerts = await apiClient.getRiskAlerts(tradingMode);
// Returns: Array of { id, severity, metric, current_value, threshold, message, timestamp }
```

### Get Position Risks
```typescript
const positionRisks = await apiClient.getPositionRisks(tradingMode);
// Returns: Array of { position_id, symbol, strategy_id, risk_amount, 
//                     risk_percent, stop_loss, take_profit, risk_level }
```

---

## Analytics Endpoints

### Get Strategy Attribution
```typescript
const attribution = await apiClient.getStrategyAttribution(tradingMode, '1M');
// Periods: '1M', '3M', '6M', '1Y', 'ALL'
// Returns: Array of { strategy_id, strategy_name, total_return, 
//                     contribution_percent, sharpe_ratio, total_trades, win_rate }
```

### Get Trade Analytics
```typescript
const tradeAnalytics = await apiClient.getTradeAnalytics(tradingMode, '1M');
// Returns: { total_trades, winning_trades, losing_trades, win_rate, 
//            avg_win, avg_loss, profit_factor, avg_holding_time_hours, 
//            largest_win, largest_loss, win_loss_distribution }
```

### Get Regime Analysis
```typescript
const regimeAnalysis = await apiClient.getRegimeAnalysis(tradingMode);
// Returns: Array of { regime, total_return, sharpe_ratio, win_rate, 
//                     total_trades, avg_return_per_trade }
```

### Get Performance Analytics
```typescript
const performance = await apiClient.getPerformanceAnalytics(tradingMode, '1M');
// Returns: { total_return, sharpe_ratio, sortino_ratio, max_drawdown, 
//            win_rate, profit_factor, total_trades, equity_curve, 
//            monthly_returns, returns_distribution }
```

---

## Execution Quality Endpoint

### Get Execution Quality
```typescript
const execQuality = await apiClient.getExecutionQuality(tradingMode, '1W');
// Periods: '1D', '1W', '1M', '3M'
// Returns: { avg_slippage, fill_rate, avg_fill_time_seconds, rejection_rate, 
//            total_orders, filled_orders, rejected_orders, pending_orders, 
//            slippage_by_strategy, rejection_reasons }
```

---

## Error Handling

### Using Error Utilities
```typescript
import { getErrorMessage, isNetworkError, isAuthError, getErrorSeverity } from '@/lib/error-messages';

try {
  const data = await apiClient.getRiskMetrics(tradingMode);
} catch (error) {
  const message = getErrorMessage(error);
  const severity = getErrorSeverity(error);
  
  if (isNetworkError(error)) {
    // Handle network error
  } else if (isAuthError(error)) {
    // Handle auth error (will auto-redirect to login)
  }
  
  toast.error(message);
}
```

### Automatic Retry
All critical endpoints automatically retry on transient failures:
- Max retries: 3
- Exponential backoff: 1s, 2s, 4s
- Skips retry on 4xx errors (except 429 rate limit)
- 30 second timeout per request

---

## Usage Examples

### RiskNew.tsx
```typescript
const fetchRiskData = async () => {
  try {
    setLoading(true);
    const [metrics, history, alerts] = await Promise.all([
      apiClient.getRiskMetrics(tradingMode),
      apiClient.getRiskHistory(tradingMode, '1W'),
      apiClient.getRiskAlerts(tradingMode)
    ]);
    setRiskMetrics(metrics);
    setRiskHistory(history);
    setRiskAlerts(alerts);
  } catch (error) {
    setError(getErrorMessage(error));
  } finally {
    setLoading(false);
  }
};
```

### AnalyticsNew.tsx
```typescript
const fetchAnalytics = async () => {
  try {
    setLoading(true);
    const [attribution, tradeAnalytics, performance] = await Promise.all([
      apiClient.getStrategyAttribution(tradingMode, period),
      apiClient.getTradeAnalytics(tradingMode, period),
      apiClient.getPerformanceAnalytics(tradingMode, period)
    ]);
    setStrategyAttribution(attribution);
    setTradeAnalytics(tradeAnalytics);
    setPerformance(performance);
  } catch (error) {
    setError(getErrorMessage(error));
  } finally {
    setLoading(false);
  }
};
```

### OrdersNew.tsx
```typescript
const fetchExecutionQuality = async () => {
  try {
    const quality = await apiClient.getExecutionQuality(tradingMode, '1W');
    setExecutionQuality(quality);
  } catch (error) {
    console.error('Failed to fetch execution quality:', error);
    // Non-critical - don't show error to user
  }
};
```

---

## WebSocket Integration

All endpoints return data that can be updated via WebSocket:

```typescript
useEffect(() => {
  const unsubscribe = wsManager.onPositionUpdate(() => {
    // Refresh risk metrics when positions change
    fetchRiskData();
  });
  
  return () => unsubscribe();
}, [tradingMode]);
```

---

## Testing

### Backend Testing
```bash
# Start backend
cd src
python -m uvicorn api.app:app --reload

# Test endpoints
curl http://localhost:8000/api/risk/metrics?mode=DEMO
curl http://localhost:8000/api/analytics/strategy-attribution?mode=DEMO&period=1M
curl http://localhost:8000/api/orders/execution-quality?mode=DEMO&period=1W
```

### Frontend Testing
```bash
# Start frontend
cd frontend
npm run dev

# Navigate to pages
http://localhost:5173/risk
http://localhost:5173/analytics
http://localhost:5173/orders
```

---

## Performance Considerations

### Caching
Consider caching responses for:
- Risk metrics: 30 seconds
- Analytics: 1 minute
- Execution quality: 1 minute

### Batch Requests
Use `Promise.all()` to fetch multiple endpoints in parallel:
```typescript
const [metrics, history, alerts] = await Promise.all([
  apiClient.getRiskMetrics(tradingMode),
  apiClient.getRiskHistory(tradingMode, '1W'),
  apiClient.getRiskAlerts(tradingMode)
]);
```

### Debouncing
Debounce period changes to avoid excessive API calls:
```typescript
const debouncedFetch = useMemo(
  () => debounce(fetchAnalytics, 500),
  [tradingMode]
);

useEffect(() => {
  debouncedFetch();
}, [period]);
```

---

## Migration Guide

### Before (Client-Side Calculation)
```typescript
// RiskNew.tsx - OLD
const calculateVaR = (positions) => {
  // Complex client-side calculation
  return positions.reduce(...);
};
```

### After (Backend Endpoint)
```typescript
// RiskNew.tsx - NEW
const riskMetrics = await apiClient.getRiskMetrics(tradingMode);
const var = riskMetrics.portfolio_var; // Already calculated by backend
```

### Before (Simulated Data)
```typescript
// AnalyticsNew.tsx - OLD
const equityCurve = generateMockEquityCurve();
```

### After (Real Data)
```typescript
// AnalyticsNew.tsx - NEW
const performance = await apiClient.getPerformanceAnalytics(tradingMode, period);
const equityCurve = performance.equity_curve; // Real data from backend
```



---

## Account Endpoints

### Get Closed Positions
```typescript
const closedPositions = await apiClient.getClosedPositions(tradingMode, 100);
// Parameters: mode (required), limit (optional, default: 100)
// Returns: Array of closed positions with realized P&L and holding time
```

**Response Structure**:
```json
{
  "positions": [
    {
      "id": "string",
      "symbol": "string",
      "quantity": 0,
      "entry_price": 0,
      "exit_price": 0,
      "realized_pnl": 0,
      "closed_at": "2024-01-01T00:00:00Z",
      "holding_time_hours": 0
    }
  ]
}
```

---

## Analytics Endpoints (New)

### Get Correlation Matrix
```typescript
const correlationData = await apiClient.getCorrelationMatrix(tradingMode, '1M');
// Periods: '1D', '1W', '1M', '3M', 'ALL'
// Returns: Strategy correlation matrix with diversification metrics
```

**Response Structure**:
```json
{
  "matrix": [
    { "x": "S1", "y": "S1", "value": 1.0 },
    { "x": "S1", "y": "S2", "value": 0.42 }
  ],
  "strategies": ["S1", "S2", "S3"],
  "avg_correlation": 0.42,
  "diversification_score": 0.58
}
```

**Notes**:
- Calculates Pearson correlation between strategy returns
- Limits to top 8 strategies for visualization
- Returns empty matrix if < 2 strategies
- Diversification score = 1 - avg_correlation (higher is better)
- Used in RiskNew.tsx correlation analysis tab

---

## Summary of New Endpoints

### Task 7.14 - Real-Time Data Integration:
1. ✅ `GET /api/account/positions/closed` - Closed positions history
2. ✅ `GET /api/analytics/correlation-matrix` - Strategy correlation analysis

### Previously Implemented:
1. ✅ `GET /api/orders/execution-quality` - Order execution metrics
2. ✅ `GET /api/risk/history` - Historical risk metrics
3. ✅ `GET /api/risk/positions` - Position risk analysis
4. ✅ `GET /api/risk/metrics` - Current risk metrics
5. ✅ `GET /api/risk/limits` - Risk limit configuration
6. ✅ `GET /api/risk/alerts` - Risk alerts and warnings

All endpoints support both DEMO and LIVE trading modes via the `mode` query parameter.
