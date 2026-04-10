# WebSocket Autonomous Trading Events

This document describes the WebSocket event channels and messages for the autonomous trading system.

**Validates: Requirements 7.1, 7.2, 7.3**

## Overview

The autonomous trading system broadcasts real-time events through WebSocket channels to keep clients informed of system status, cycle progress, strategy lifecycle changes, and important notifications.

## Channels

### 1. `autonomous:status`

Real-time updates about the autonomous trading system status.

**Event Types:**
- `status_update` - System status changed

**Message Format:**
```json
{
  "channel": "autonomous:status",
  "event": "status_update",
  "data": {
    "enabled": true,
    "market_regime": "TRENDING_UP",
    "last_run_time": "2024-01-15T10:30:00Z",
    "next_run_time": "2024-01-22T10:30:00Z",
    "active_strategies_count": 5,
    "total_strategies_count": 12,
    "status_counts": {
      "PROPOSED": 2,
      "BACKTESTED": 1,
      "DEMO": 5,
      "RETIRED": 4
    }
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### 2. `autonomous:cycle`

Real-time updates about autonomous cycle execution.

**Event Types:**
- `cycle_started` - Cycle has begun
- `cycle_completed` - Cycle has finished
- `cycle_progress` - Progress update during cycle

**Message Format (cycle_started):**
```json
{
  "channel": "autonomous:cycle",
  "event": "cycle_started",
  "data": {
    "cycle_id": "cycle_abc123",
    "estimated_duration": 2700,
    "timestamp": "2024-01-15T10:30:00Z"
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Message Format (cycle_completed):**
```json
{
  "channel": "autonomous:cycle",
  "event": "cycle_completed",
  "data": {
    "cycle_id": "cycle_abc123",
    "duration_seconds": 2450,
    "proposals_generated": 5,
    "proposals_backtested": 5,
    "strategies_activated": 2,
    "strategies_retired": 1,
    "errors_count": 0,
    "timestamp": "2024-01-15T11:15:00Z"
  },
  "timestamp": "2024-01-15T11:15:00Z"
}
```

### 3. `autonomous:strategies`

Real-time updates about strategy lifecycle events.

**Event Types:**
- `strategy_proposed` - New strategy proposed
- `strategy_backtested` - Strategy backtest completed
- `strategy_activated` - Strategy activated
- `strategy_retired` - Strategy retired

**Message Format (strategy_proposed):**
```json
{
  "channel": "autonomous:strategies",
  "event": "strategy_proposed",
  "data": {
    "id": "strat_123",
    "name": "RSI Mean Reversion",
    "symbols": ["SPY", "QQQ"],
    "status": "PROPOSED",
    "timestamp": "2024-01-15T10:32:00Z"
  },
  "timestamp": "2024-01-15T10:32:00Z"
}
```

**Message Format (strategy_backtested):**
```json
{
  "channel": "autonomous:strategies",
  "event": "strategy_backtested",
  "data": {
    "id": "strat_123",
    "name": "RSI Mean Reversion",
    "symbols": ["SPY", "QQQ"],
    "status": "BACKTESTED",
    "backtest_results": {
      "sharpe_ratio": 1.85,
      "total_return": 0.243,
      "max_drawdown": 0.082,
      "win_rate": 0.625,
      "total_trades": 45
    },
    "timestamp": "2024-01-15T10:45:00Z"
  },
  "timestamp": "2024-01-15T10:45:00Z"
}
```

**Message Format (strategy_activated):**
```json
{
  "channel": "autonomous:strategies",
  "event": "strategy_activated",
  "data": {
    "id": "strat_123",
    "name": "RSI Mean Reversion",
    "symbols": ["SPY", "QQQ"],
    "status": "DEMO",
    "backtest_results": {
      "sharpe_ratio": 1.85,
      "total_return": 0.243,
      "max_drawdown": 0.082,
      "win_rate": 0.625
    },
    "timestamp": "2024-01-15T10:50:00Z"
  },
  "timestamp": "2024-01-15T10:50:00Z"
}
```

**Message Format (strategy_retired):**
```json
{
  "channel": "autonomous:strategies",
  "event": "strategy_retired",
  "data": {
    "id": "strat_456",
    "name": "MACD Momentum",
    "symbols": ["AAPL", "MSFT"],
    "status": "RETIRED",
    "retirement_reason": "Sharpe ratio below threshold (0.42 < 0.5)",
    "final_metrics": {
      "sharpe_ratio": 0.42,
      "total_return": -0.082,
      "max_drawdown": 0.18
    },
    "timestamp": "2024-01-15T11:00:00Z"
  },
  "timestamp": "2024-01-15T11:00:00Z"
}
```

### 4. `autonomous:notifications`

User-facing notifications about autonomous system events.

**Event Types:**
- `notification` - All notification types

**Notification Types:**
- `cycle_started` - Cycle has begun
- `cycle_completed` - Cycle has finished
- `cycle_error` - Error occurred during cycle
- `strategies_proposed` - Strategies have been proposed
- `strategy_activated` - Strategy was activated
- `strategy_retired` - Strategy was retired
- `regime_changed` - Market regime changed

**Message Format:**
```json
{
  "channel": "autonomous:notifications",
  "event": "notification",
  "data": {
    "type": "strategy_activated",
    "severity": "success",
    "title": "Strategy Activated",
    "message": "RSI Mean Reversion activated with Sharpe 1.85",
    "timestamp": "2024-01-15T10:50:00Z",
    "data": {
      "strategy_id": "strat_123",
      "strategy_name": "RSI Mean Reversion"
    }
  },
  "timestamp": "2024-01-15T10:50:00Z"
}
```

**Severity Levels:**
- `info` - Informational message
- `success` - Successful operation
- `warning` - Warning condition
- `error` - Error condition

## Client Implementation

### Connecting to WebSocket

```javascript
const ws = new WebSocket(`ws://localhost:8000/ws?session_id=${sessionId}`);

ws.onopen = () => {
  console.log('WebSocket connected');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  handleWebSocketMessage(message);
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('WebSocket disconnected');
  // Implement reconnection logic
};
```

### Handling Messages

```javascript
function handleWebSocketMessage(message) {
  const { channel, event, data, timestamp } = message;
  
  switch (channel) {
    case 'autonomous:status':
      handleStatusUpdate(data);
      break;
    
    case 'autonomous:cycle':
      handleCycleEvent(event, data);
      break;
    
    case 'autonomous:strategies':
      handleStrategyEvent(event, data);
      break;
    
    case 'autonomous:notifications':
      handleNotification(data);
      break;
    
    default:
      console.warn('Unknown channel:', channel);
  }
}

function handleStatusUpdate(data) {
  // Update UI with system status
  updateSystemStatus(data);
}

function handleCycleEvent(event, data) {
  if (event === 'cycle_started') {
    showCycleProgress(data.cycle_id, data.estimated_duration);
  } else if (event === 'cycle_completed') {
    hideCycleProgress();
    updateCycleStats(data);
  }
}

function handleStrategyEvent(event, data) {
  if (event === 'strategy_proposed') {
    addStrategyToList(data);
  } else if (event === 'strategy_backtested') {
    updateStrategyBacktestResults(data);
  } else if (event === 'strategy_activated') {
    updateStrategyStatus(data.id, 'DEMO');
    showSuccessToast(`${data.name} activated`);
  } else if (event === 'strategy_retired') {
    updateStrategyStatus(data.id, 'RETIRED');
    showWarningToast(`${data.name} retired: ${data.retirement_reason}`);
  }
}

function handleNotification(data) {
  const { type, severity, title, message } = data;
  showToast(title, message, severity);
}
```

### Keepalive

Send periodic ping messages to keep the connection alive:

```javascript
setInterval(() => {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send('ping');
  }
}, 30000); // Every 30 seconds
```

## Backend Implementation

### Broadcasting Events

The `WebSocketManager` provides methods for broadcasting events:

```python
from src.api.websocket_manager import get_websocket_manager

ws_manager = get_websocket_manager()

# Broadcast status update
await ws_manager.broadcast_autonomous_status_update({
    "enabled": True,
    "market_regime": "TRENDING_UP",
    "active_strategies_count": 5
})

# Broadcast cycle event
await ws_manager.broadcast_autonomous_cycle_event(
    "cycle_started",
    {
        "cycle_id": "cycle_abc123",
        "estimated_duration": 2700
    }
)

# Broadcast strategy event
await ws_manager.broadcast_autonomous_strategy_event(
    "strategy_activated",
    {
        "id": strategy.id,
        "name": strategy.name,
        "status": "DEMO"
    }
)

# Broadcast notification
await ws_manager.broadcast_autonomous_notification({
    "type": "strategy_activated",
    "severity": "success",
    "title": "Strategy Activated",
    "message": f"{strategy.name} activated"
})
```

### Integration with AutonomousStrategyManager

The `AutonomousStrategyManager` automatically broadcasts events during cycle execution:

```python
from src.strategy.autonomous_strategy_manager import AutonomousStrategyManager

# Initialize with WebSocket manager
autonomous_manager = AutonomousStrategyManager(
    llm_service=llm_service,
    market_data=market_data,
    strategy_engine=strategy_engine,
    websocket_manager=ws_manager  # Pass WebSocket manager
)

# Run cycle - events will be broadcast automatically
stats = autonomous_manager.run_strategy_cycle()
```

Events are broadcast at key points:
- Cycle start/completion
- Strategy proposal
- Backtest completion
- Strategy activation
- Strategy retirement
- Errors

## Testing

Run the WebSocket event tests:

```bash
pytest tests/test_websocket_autonomous_events.py -v
```

The test suite validates:
- All four channels (status, cycle, strategies, notifications)
- All event types
- Message structure and required fields
- Broadcasting to multiple clients
- Error handling

## Requirements Validation

- **Requirement 7.1**: Real-time autonomous status updates via `autonomous:status` channel
- **Requirement 7.2**: Real-time cycle progress and strategy lifecycle updates via `autonomous:cycle` and `autonomous:strategies` channels
- **Requirement 7.3**: Real-time notifications for autonomous events via `autonomous:notifications` channel
