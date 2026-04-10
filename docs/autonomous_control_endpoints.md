# Autonomous Control Endpoints

This document describes the three new autonomous trading control endpoints added to the AlphaCent API.

## Overview

These endpoints provide control and configuration capabilities for the autonomous trading system:

1. **POST /api/strategies/autonomous/trigger** - Manually trigger an autonomous cycle
2. **GET /api/strategies/autonomous/config** - Retrieve current configuration
3. **PUT /api/strategies/autonomous/config** - Update configuration settings

## Endpoints

### 1. Trigger Autonomous Cycle

**Endpoint:** `POST /api/strategies/autonomous/trigger`

**Description:** Manually initiates a complete autonomous trading cycle including strategy proposal, backtesting, evaluation, activation, and retirement checks.

**Request Body:**
```json
{
  "force": false
}
```

**Parameters:**
- `force` (boolean, optional): Force cycle execution even if not scheduled. Default: `false`

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Cycle completed: 6 strategies proposed, 6 backtested, 2 activated, 1 retired",
  "cycle_id": "cycle_a1b2c3d4",
  "estimated_duration": 2700
}
```

**Response Fields:**
- `success`: Whether the cycle completed successfully
- `message`: Human-readable summary of cycle results
- `cycle_id`: Unique identifier for this cycle execution
- `estimated_duration`: Duration in seconds (null if not available)

**Error Responses:**

400 Bad Request - System disabled:
```json
{
  "detail": "Autonomous system is disabled. Enable it in settings or use force=true to override."
}
```

400 Bad Request - Not scheduled:
```json
{
  "detail": "Cycle not scheduled to run yet. Use force=true to override schedule."
}
```

503 Service Unavailable - Credentials not configured:
```json
{
  "detail": "eToro credentials not configured. Please set up credentials first."
}
```

**WebSocket Events:**

The endpoint broadcasts the following events:
- `autonomous:cycle_started` - When cycle begins
- `autonomous:cycle_completed` - When cycle finishes successfully
- `autonomous:cycle_error` - If cycle fails

**Example Usage:**

```bash
# Trigger cycle (respects schedule)
curl -X POST http://localhost:8000/api/strategies/autonomous/trigger \
  -H "Content-Type: application/json" \
  -d '{"force": false}'

# Force trigger (ignores schedule)
curl -X POST http://localhost:8000/api/strategies/autonomous/trigger \
  -H "Content-Type: application/json" \
  -d '{"force": true}'
```

---

### 2. Get Autonomous Configuration

**Endpoint:** `GET /api/strategies/autonomous/config`

**Description:** Retrieves the current autonomous trading system configuration from `config/autonomous_trading.yaml`.

**Request:** No body required

**Response (200 OK):**
```json
{
  "config": {
    "llm": {
      "model": "qwen2.5-coder:7b",
      "temperature": 0.7
    },
    "autonomous": {
      "enabled": true,
      "proposal_frequency": "weekly",
      "max_active_strategies": 10,
      "min_active_strategies": 5
    },
    "activation_thresholds": {
      "min_sharpe": 1.5,
      "max_drawdown": 0.15,
      "min_win_rate": 0.5,
      "min_trades": 50
    },
    "retirement_thresholds": {
      "max_sharpe": 0.5,
      "max_drawdown": 0.15,
      "min_win_rate": 0.4,
      "min_trades_for_evaluation": 30
    },
    "backtest": {
      "days": 730,
      "warmup_days": 250,
      "min_trades": 50
    }
  },
  "last_updated": "2024-02-18T10:30:00",
  "updated_by": null
}
```

**Response Fields:**
- `config`: Complete configuration object
- `last_updated`: ISO timestamp of last file modification
- `updated_by`: Username who last updated (currently null, could be tracked separately)

**Error Responses:**

404 Not Found - Config file missing:
```json
{
  "detail": "Configuration file not found: config/autonomous_trading.yaml"
}
```

**Example Usage:**

```bash
curl -X GET http://localhost:8000/api/strategies/autonomous/config
```

---

### 3. Update Autonomous Configuration

**Endpoint:** `PUT /api/strategies/autonomous/config`

**Description:** Updates the autonomous trading system configuration. Supports partial updates (only specified fields are changed). Validates all changes before saving.

**Request Body:**
```json
{
  "config": {
    "autonomous": {
      "enabled": true,
      "max_active_strategies": 12
    },
    "activation_thresholds": {
      "min_sharpe": 1.8
    }
  }
}
```

**Parameters:**
- `config` (object, required): Configuration updates (partial or full)

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Configuration updated successfully",
  "config": {
    "llm": { ... },
    "autonomous": { ... },
    "activation_thresholds": { ... },
    "retirement_thresholds": { ... },
    "backtest": { ... }
  }
}
```

**Response Fields:**
- `success`: Whether update was successful
- `message`: Human-readable result message
- `config`: Complete updated configuration

**Validation Rules:**

The endpoint validates the following:

**Autonomous Settings:**
- `enabled`: Must be boolean
- `proposal_frequency`: Must be "daily", "weekly", or "monthly"
- `max_active_strategies`: Must be integer between 1 and 50
- `min_active_strategies`: Must be integer >= 1
- `min_active_strategies` must be <= `max_active_strategies`

**Activation Thresholds:**
- `min_sharpe`: Must be number >= 0
- `max_drawdown`: Must be number between 0 and 1
- `min_win_rate`: Must be number between 0 and 1
- `min_trades`: Must be integer >= 1

**Retirement Thresholds:**
- `max_sharpe`: Must be number >= 0
- `max_drawdown`: Must be number between 0 and 1
- `min_win_rate`: Must be number between 0 and 1
- `min_trades_for_evaluation`: Must be integer >= 1

**Backtest Settings:**
- `days`: Must be integer between 30 and 3650
- `warmup_days`: Must be integer >= 0
- `min_trades`: Must be integer >= 1

**Error Responses:**

400 Bad Request - Validation failed:
```json
{
  "detail": "Configuration validation failed: autonomous.max_active_strategies must be between 1 and 50; activation_thresholds.min_sharpe must be >= 0"
}
```

**WebSocket Events:**

The endpoint broadcasts:
- `autonomous:config_updated` - When configuration is successfully updated

**Example Usage:**

```bash
# Update multiple settings
curl -X PUT http://localhost:8000/api/strategies/autonomous/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "autonomous": {
        "enabled": true,
        "max_active_strategies": 12
      },
      "activation_thresholds": {
        "min_sharpe": 1.8,
        "max_drawdown": 0.12
      }
    }
  }'

# Update single setting
curl -X PUT http://localhost:8000/api/strategies/autonomous/config \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "autonomous": {
        "enabled": false
      }
    }
  }'
```

---

## Configuration File Structure

The configuration is stored in `config/autonomous_trading.yaml`:

```yaml
llm:
  model: "qwen2.5-coder:7b"
  temperature: 0.7

autonomous:
  enabled: true
  proposal_frequency: "weekly"  # or "daily", "monthly"
  max_active_strategies: 10
  min_active_strategies: 5

activation_thresholds:
  min_sharpe: 1.5
  max_drawdown: 0.15
  min_win_rate: 0.5
  min_trades: 50

retirement_thresholds:
  max_sharpe: 0.5
  max_drawdown: 0.15
  min_win_rate: 0.4
  min_trades_for_evaluation: 30

backtest:
  days: 730
  warmup_days: 250
  min_trades: 50
  walk_forward:
    train_days: 480
    test_days: 240
```

## Integration with Frontend

These endpoints are designed to support the Autonomous Trading UI components:

1. **AutonomousStatus Component** - Uses GET /config and POST /trigger
2. **AutonomousSettings Component** - Uses GET /config and PUT /config
3. **Real-time Updates** - WebSocket events keep UI synchronized

## Security Considerations

1. **Authentication Required** - All endpoints require valid user authentication
2. **Validation** - All configuration updates are validated before saving
3. **File Permissions** - Configuration file should have appropriate permissions
4. **Audit Trail** - Consider adding audit logging for configuration changes

## Testing

Unit tests are provided in:
- `tests/test_autonomous_config_validation.py` - Validation logic tests
- `tests/test_autonomous_endpoints.py` - Manual integration tests

Run tests:
```bash
# Unit tests
pytest tests/test_autonomous_config_validation.py -v

# Manual integration tests (requires running server)
python tests/test_autonomous_endpoints.py
```

## Requirements Validation

These endpoints satisfy the following requirements from the spec:

- **Requirement 2.4**: Manual trigger functionality for autonomous cycles
- **Requirement 2.5**: Configuration retrieval and updates
- **Requirement 3.1**: System configuration interface (backend support)
- **Requirement 3.2**: Configuration validation and persistence

## Future Enhancements

Potential improvements:
1. Add audit trail tracking (who changed what and when)
2. Add configuration versioning and rollback
3. Add configuration validation preview (dry-run mode)
4. Add configuration templates for different trading styles
5. Add configuration export/import functionality
