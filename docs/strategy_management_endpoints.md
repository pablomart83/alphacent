# Strategy Management Endpoints

## Overview

This document describes the three new strategy management endpoints implemented for the Autonomous Trading UI Overhaul (Task 2.3).

## Endpoints

### 1. GET /api/strategies/proposals

Retrieves strategy proposals from the autonomous trading system with pagination and filtering.

**Query Parameters:**
- `page` (int, default: 1): Page number (1-indexed)
- `page_size` (int, default: 20, max: 100): Items per page
- `market_regime` (string, optional): Filter by market regime (e.g., "trending_up", "ranging")
- `activated` (boolean, optional): Filter by activation status

**Response:**
```json
{
  "proposals": [
    {
      "id": 1,
      "strategy_id": "strat_001",
      "proposed_at": "2024-01-01T12:00:00",
      "market_regime": "trending_up",
      "backtest_sharpe": 1.85,
      "activated": true,
      "strategy": {
        "id": "strat_001",
        "name": "RSI Mean Reversion",
        "status": "DEMO",
        "symbols": ["SPY", "QQQ"],
        "template_name": "RSI Mean Reversion",
        "rules": {
          "entry": ["RSI(14) < 30"],
          "exit": ["RSI(14) > 70"]
        }
      },
      "evaluation_score": 92.5
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

**Validates:** Requirements 2.6, 4.1

---

### 2. GET /api/strategies/retirements

Retrieves retired strategies from the autonomous trading system with pagination and filtering.

**Query Parameters:**
- `page` (int, default: 1): Page number (1-indexed)
- `page_size` (int, default: 20, max: 100): Items per page
- `reason` (string, optional): Filter by retirement reason (partial match)

**Response:**
```json
{
  "retirements": [
    {
      "id": 1,
      "strategy_id": "strat_003",
      "strategy_name": "MACD Momentum",
      "retired_at": "2024-01-15T12:00:00",
      "reason": "Performance degradation",
      "final_metrics": {
        "sharpe": 0.42,
        "totalReturn": -8.2,
        "maxDrawdown": null,
        "winRate": null
      }
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

**Validates:** Requirements 2.7, 4.2

---

### 3. GET /api/strategies/templates

Retrieves available strategy templates with usage statistics.

**Query Parameters:**
- `market_regime` (string, optional): Filter templates by market regime

**Response:**
```json
{
  "templates": [
    {
      "name": "RSI Mean Reversion",
      "description": "Buy when RSI indicates extreme oversold conditions, sell when overbought or profit target hit",
      "market_regimes": ["ranging"],
      "indicators": ["RSI"],
      "entry_rules": ["RSI(14) < 25"],
      "exit_rules": ["RSI(14) > 75"],
      "success_rate": 45.0,
      "usage_count": 12
    }
  ],
  "total": 26
}
```

**Validates:** Requirements 2.6, 4.1

---

## Implementation Details

### Database Tables

The endpoints query the following database tables:
- `strategy_proposals`: Stores proposed strategies with backtest results
- `strategy_retirements`: Stores retired strategies with retirement reasons
- Strategy templates are loaded from `StrategyTemplateLibrary` in memory

### Usage Statistics

Template usage statistics are calculated by:
1. Querying all proposals from `strategy_proposals` table
2. Fetching strategy details to extract `template_name`
3. Counting total uses and activations per template
4. Calculating success rate as: `(activated / used) * 100`

### Market Regimes

Valid market regime values (lowercase with underscores):
- `trending_up_strong`
- `trending_up_weak`
- `trending_up` (legacy)
- `trending_down_strong`
- `trending_down_weak`
- `trending_down` (legacy)
- `ranging_low_vol`
- `ranging_high_vol`
- `ranging` (legacy)

### Pagination

All list endpoints support pagination:
- Default page size: 20 items
- Maximum page size: 100 items
- Pages are 1-indexed
- Total count is returned for client-side pagination UI

### Error Handling

All endpoints include comprehensive error handling:
- Invalid parameters return 400 Bad Request
- Database errors return 500 Internal Server Error
- Missing strategies are handled gracefully (logged as warnings)

---

## Testing

Tests are located in `tests/test_strategy_management_endpoints.py` and cover:
- Proposals endpoint structure and data
- Retirements endpoint structure and data
- Templates endpoint structure and data
- Market regime filtering
- Template library integration

Run tests with:
```bash
python -m pytest tests/test_strategy_management_endpoints.py -v
```

---

## Future Enhancements

Potential improvements for future iterations:
1. Add more retirement metrics (max drawdown, win rate) to database schema
2. Add sorting options for proposals and retirements
3. Add date range filtering for proposals and retirements
4. Cache template statistics for better performance
5. Add WebSocket events for real-time proposal/retirement updates
