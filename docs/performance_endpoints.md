# Performance & Analytics API Endpoints

This document describes the Performance & Analytics API endpoints for the AlphaCent trading platform.

**Validates:** Requirements 5.1, 5.2, 5.3, 6.1, 6.2

## Overview

The Performance & Analytics endpoints provide comprehensive portfolio performance metrics, risk analysis, and historical event tracking for the autonomous trading system.

## Endpoints

### 1. GET /api/performance/metrics

Get portfolio performance metrics for a specified time period.

**Authentication:** Required

**Query Parameters:**
- `period` (optional): Time period for metrics
  - Values: `1M`, `3M`, `6M`, `1Y`, `ALL`
  - Default: `3M`
- `strategy_id` (optional): Filter by specific strategy ID

**Response Model:**
```json
{
  "sharpe": {
    "value": 1.85,
    "change": 0.15,
    "change_percentage": 8.8
  },
  "total_return": {
    "value": 24.3,
    "change": 2.1,
    "change_percentage": 9.4
  },
  "max_drawdown": {
    "value": -8.2,
    "change": -1.3,
    "change_percentage": -13.7
  },
  "win_rate": {
    "value": 62.5,
    "change": 3.2,
    "change_percentage": 5.4
  },
  "portfolio_history": [
    {
      "date": "2024-01-01T00:00:00",
      "value": 100000.0,
      "benchmark": 100000.0
    }
  ],
  "strategy_contributions": [
    {
      "strategy_id": "strategy_001",
      "strategy_name": "RSI Mean Reversion",
      "contribution": 35.0,
      "return_value": 8.2,
      "allocation": 15.0
    }
  ],
  "period": "3M",
  "last_updated": "2024-01-15T10:30:00"
}
```

**Example Usage:**
```bash
# Get 3-month metrics (default)
curl -X GET "http://localhost:8000/api/performance/metrics" \
  -H "Authorization: Bearer <token>"

# Get 1-year metrics
curl -X GET "http://localhost:8000/api/performance/metrics?period=1Y" \
  -H "Authorization: Bearer <token>"

# Get metrics for specific strategy
curl -X GET "http://localhost:8000/api/performance/metrics?strategy_id=strategy_001" \
  -H "Authorization: Bearer <token>"
```

**Validates:** Requirements 5.1, 5.2, 5.3

---

### 2. GET /api/performance/portfolio

Get current portfolio composition with risk metrics and correlation matrix.

**Authentication:** Required

**Query Parameters:** None

**Response Model:**
```json
{
  "strategies": [
    {
      "id": "strategy_001",
      "name": "RSI Mean Reversion",
      "allocation": 15.0,
      "performance": {
        "sharpe_ratio": 1.92,
        "total_return": 12.3,
        "max_drawdown": -5.2,
        "win_rate": 65.0,
        "total_trades": 24,
        "profit_factor": 2.1
      }
    }
  ],
  "correlation_matrix": [
    [1.0, 0.42, 0.35],
    [0.42, 1.0, 0.28],
    [0.35, 0.28, 1.0]
  ],
  "risk_metrics": {
    "portfolio_var": 2450.0,
    "max_position_size": 15.0,
    "diversification_score": 0.78,
    "portfolio_beta": 1.05,
    "correlation_avg": 0.35
  },
  "total_value": 100000.0,
  "last_updated": "2024-01-15T10:30:00"
}
```

**Example Usage:**
```bash
curl -X GET "http://localhost:8000/api/performance/portfolio" \
  -H "Authorization: Bearer <token>"
```

**Risk Metrics Explained:**
- **portfolio_var**: Value at Risk at 95% confidence level (potential loss)
- **max_position_size**: Largest position as percentage of portfolio
- **diversification_score**: Portfolio diversification (0-1, higher is better)
- **portfolio_beta**: Portfolio sensitivity to market movements
- **correlation_avg**: Average correlation between strategies

**Validates:** Requirements 6.1, 6.2

---

### 3. GET /api/performance/history

Get historical events timeline for autonomous trading system.

**Authentication:** Required

**Query Parameters:**
- `start_date` (optional): Start date for history (ISO 8601 format)
- `end_date` (optional): End date for history (ISO 8601 format)
- `event_types` (optional): Filter by event types (can specify multiple)
  - Values: `cycle_started`, `cycle_completed`, `strategies_proposed`, `backtest_completed`, `strategy_activated`, `strategy_retired`, `regime_changed`, `portfolio_rebalanced`, `error_occurred`
- `limit` (optional): Maximum number of events (1-1000)
  - Default: 100

**Response Model:**
```json
{
  "events": [
    {
      "id": "proposal_123",
      "type": "strategies_proposed",
      "timestamp": "2024-01-15T10:00:00",
      "data": {
        "strategy_id": "strategy_001",
        "market_regime": "TRENDING_UP",
        "evaluation_score": 0.85,
        "activated": true
      },
      "description": "Strategy proposed: strategy_001 for TRENDING_UP regime"
    },
    {
      "id": "retirement_456",
      "type": "strategy_retired",
      "timestamp": "2024-01-14T15:30:00",
      "data": {
        "strategy_id": "strategy_002",
        "reason": "Performance degradation",
        "final_sharpe": 0.42,
        "final_return": -8.2,
        "final_drawdown": -15.5
      },
      "description": "Strategy retired: strategy_002 - Performance degradation"
    }
  ],
  "total": 2,
  "start_date": "2024-01-01T00:00:00",
  "end_date": "2024-01-15T23:59:59"
}
```

**Example Usage:**
```bash
# Get last 100 events (default)
curl -X GET "http://localhost:8000/api/performance/history" \
  -H "Authorization: Bearer <token>"

# Get events for specific date range
curl -X GET "http://localhost:8000/api/performance/history?start_date=2024-01-01T00:00:00&end_date=2024-01-31T23:59:59" \
  -H "Authorization: Bearer <token>"

# Filter by event types
curl -X GET "http://localhost:8000/api/performance/history?event_types=strategy_activated&event_types=strategy_retired" \
  -H "Authorization: Bearer <token>"

# Limit results
curl -X GET "http://localhost:8000/api/performance/history?limit=50" \
  -H "Authorization: Bearer <token>"
```

**Event Types:**
- **cycle_started**: Autonomous cycle began
- **cycle_completed**: Autonomous cycle finished
- **strategies_proposed**: New strategies generated
- **backtest_completed**: Strategy backtest finished
- **strategy_activated**: Strategy activated for trading
- **strategy_retired**: Strategy retired from portfolio
- **regime_changed**: Market regime changed
- **portfolio_rebalanced**: Portfolio allocations adjusted
- **error_occurred**: System error occurred

**Validates:** Requirements 5.3, 6.2

---

## Error Responses

All endpoints return standard HTTP error codes:

**401 Unauthorized**
```json
{
  "detail": "Not authenticated"
}
```

**500 Internal Server Error**
```json
{
  "detail": "Failed to fetch performance metrics: <error message>"
}
```

**422 Unprocessable Entity** (for invalid parameters)
```json
{
  "detail": [
    {
      "loc": ["query", "period"],
      "msg": "value is not a valid enumeration member",
      "type": "type_error.enum"
    }
  ]
}
```

---

## Data Sources

The performance endpoints integrate with existing backend components:

1. **StrategyEngine**: Provides active strategy data
2. **PortfolioManager**: Calculates portfolio-level metrics
3. **CorrelationAnalyzer**: Generates correlation matrices
4. **Database (ORM)**: 
   - `StrategyProposalORM`: Strategy proposal history
   - `StrategyRetirementORM`: Strategy retirement history

---

## Implementation Notes

### Performance Calculations

**Sharpe Ratio:**
```python
sharpe = (mean_excess_return / std_excess_return) * sqrt(252)
```
- Annualized using 252 trading days
- Risk-free rate: 4.5% (configurable)

**Maximum Drawdown:**
```python
drawdown = (current_value - peak_value) / peak_value
max_drawdown = min(all_drawdowns)
```

**Win Rate:**
```python
win_rate = (winning_trades / total_trades) * 100
```

**Value at Risk (VaR):**
```python
var_95 = 1.65 * portfolio_value * allocation * volatility
```
- 95% confidence level
- Based on portfolio volatility

### Correlation Matrix

The correlation matrix shows pairwise correlations between strategy returns:
- Diagonal elements are always 1.0 (perfect correlation with self)
- Off-diagonal elements range from -1.0 to 1.0
- Values near 0 indicate low correlation (good diversification)
- Values near 1.0 indicate high correlation (poor diversification)

### Historical Data

Currently, portfolio history is simulated based on current metrics. In production:
- Historical portfolio values should be stored in database
- Daily snapshots should be captured
- Benchmark data should be fetched from market data provider

---

## Testing

Comprehensive tests are available in `tests/test_performance_endpoints.py`:

```bash
# Run all performance endpoint tests
pytest tests/test_performance_endpoints.py -v

# Run specific test class
pytest tests/test_performance_endpoints.py::TestPerformanceMetricsEndpoint -v
```

Test coverage includes:
- Response structure validation
- Query parameter handling
- Empty portfolio scenarios
- Correlation matrix calculations
- Historical event filtering
- Authentication requirements

---

## Future Enhancements

1. **Real-time Updates**: Add WebSocket support for live performance updates
2. **Benchmark Comparison**: Integrate with market data for benchmark tracking
3. **Custom Metrics**: Allow users to define custom performance metrics
4. **Export Functionality**: Add CSV/PDF export for reports
5. **Caching**: Implement Redis caching for frequently accessed metrics
6. **Historical Storage**: Store daily portfolio snapshots in database
7. **Advanced Analytics**: Add Monte Carlo simulations, stress testing

---

## Related Documentation

- [Autonomous Status Endpoints](./autonomous_status_endpoints.md)
- [Strategy Management Endpoints](./strategy_management_endpoints.md)
- [Requirements Document](../.kiro/specs/autonomous-trading-ui-overhaul/requirements.md)
- [Design Document](../.kiro/specs/autonomous-trading-ui-overhaul/design.md)
