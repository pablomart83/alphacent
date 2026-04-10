# WebSocket Autonomous Integration

## Overview

This document describes the WebSocket integration for autonomous trading system real-time updates. The implementation includes channel subscriptions, message throttling, automatic reconnection, and React hooks for easy component integration.

**Validates Requirements:** 7.1, 7.2, 7.3

## Architecture

### WebSocket Manager Enhancements

The `WebSocketManager` class has been enhanced with:

1. **Autonomous Channel Support**: Dedicated subscription methods for autonomous events
2. **Message Throttling**: Configurable throttling for high-frequency updates
3. **Channel-Based Message Routing**: Converts backend channel format to frontend message types
4. **Improved Reconnection Logic**: Exponential backoff with cleanup

### Message Flow

```
Backend → WebSocket → Message Parser → Throttle Handler → Subscribers
                           ↓
                    Channel Converter
                    (autonomous:status → autonomous_status)
```

## Features

### 1. Autonomous Channel Subscriptions

Four dedicated channels for autonomous trading events:

```typescript
// Subscribe to autonomous status updates
wsManager.onAutonomousStatus((status: AutonomousStatus) => {
  console.log('Status update:', status);
});

// Subscribe to cycle events
wsManager.onAutonomousCycle((event) => {
  console.log('Cycle event:', event.event, event.data);
});

// Subscribe to strategy lifecycle events
wsManager.onAutonomousStrategies((event) => {
  console.log('Strategy event:', event.event, event.data);
});

// Subscribe to autonomous notifications
wsManager.onAutonomousNotifications((notification) => {
  console.log('Notification:', notification);
});
```

### 2. Message Throttling

High-frequency updates are automatically throttled to prevent UI overload:

```typescript
const THROTTLE_CONFIG = {
  market_data: 1000,        // 1 second
  autonomous_status: 2000,  // 2 seconds
  position_update: 500,     // 500ms
  default: 0,               // No throttle
};
```

**How it works:**
- Messages are queued if received within throttle window
- Only the latest message is dispatched after throttle period
- Prevents excessive re-renders and improves performance

### 3. Channel Message Conversion

Backend sends messages in channel format:
```json
{
  "channel": "autonomous:status",
  "event": "status_update",
  "data": { ... },
  "timestamp": "2026-02-18T19:00:00Z"
}
```

Frontend converts to standard message type:
```typescript
{
  "type": "autonomous_status",
  "data": { ... }
}
```

### 4. Automatic Reconnection

- Exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s (max)
- Maximum 10 reconnection attempts
- Cleans up throttle timers on disconnect
- Preserves subscriptions across reconnections

## React Hooks

### useAutonomousStatus

Subscribe to autonomous system status updates:

```typescript
import { useAutonomousStatus } from '../hooks/useWebSocket';

function MyComponent() {
  const status = useAutonomousStatus();
  
  return (
    <div>
      System: {status?.enabled ? 'Enabled' : 'Disabled'}
      Regime: {status?.market_regime}
    </div>
  );
}
```

### useAutonomousCycle

Subscribe to cycle events (started, completed, progress):

```typescript
import { useAutonomousCycle } from '../hooks/useWebSocket';

function CycleMonitor() {
  const cycleEvent = useAutonomousCycle();
  
  useEffect(() => {
    if (cycleEvent?.event === 'cycle_started') {
      console.log('Cycle started:', cycleEvent.data);
    }
  }, [cycleEvent]);
  
  return <div>Last event: {cycleEvent?.event}</div>;
}
```

### useAutonomousStrategies

Subscribe to strategy lifecycle events:

```typescript
import { useAutonomousStrategies } from '../hooks/useWebSocket';

function StrategyMonitor() {
  const strategyEvent = useAutonomousStrategies();
  
  useEffect(() => {
    if (strategyEvent?.event === 'strategy_activated') {
      console.log('Strategy activated:', strategyEvent.data);
    }
  }, [strategyEvent]);
  
  return <div>Last event: {strategyEvent?.event}</div>;
}
```

### useAutonomousNotifications

Subscribe to autonomous notifications with management functions:

```typescript
import { useAutonomousNotifications } from '../hooks/useWebSocket';

function NotificationPanel() {
  const {
    notifications,
    unreadCount,
    markAsRead,
    markAllAsRead,
    clearNotification,
    clearAll,
  } = useAutonomousNotifications();
  
  return (
    <div>
      <h3>Notifications ({unreadCount} unread)</h3>
      {notifications.map((n) => (
        <div key={n.id}>
          {n.title}
          <button onClick={() => markAsRead(n.id)}>Mark Read</button>
          <button onClick={() => clearNotification(n.id)}>Clear</button>
        </div>
      ))}
      <button onClick={markAllAsRead}>Mark All Read</button>
      <button onClick={clearAll}>Clear All</button>
    </div>
  );
}
```

### useAutonomousWebSocket

Combined hook for all autonomous updates:

```typescript
import { useAutonomousWebSocket } from '../hooks/useWebSocket';

function AutonomousDashboard() {
  const {
    status,
    cycleEvent,
    strategyEvent,
    notifications,
    unreadCount,
    markAsRead,
    markAllAsRead,
    clearNotification,
    clearAll,
  } = useAutonomousWebSocket();
  
  return (
    <div>
      <StatusPanel status={status} />
      <CyclePanel event={cycleEvent} />
      <StrategyPanel event={strategyEvent} />
      <NotificationPanel
        notifications={notifications}
        unreadCount={unreadCount}
        onMarkAsRead={markAsRead}
        onMarkAllAsRead={markAllAsRead}
        onClear={clearNotification}
        onClearAll={clearAll}
      />
    </div>
  );
}
```

## Component Integration Examples

### AutonomousStatus Component

Already integrated with WebSocket updates:

```typescript
export const AutonomousStatus: FC = () => {
  const [status, setStatus] = useState<AutonomousStatusType | null>(null);
  
  // Subscribe to real-time WebSocket updates
  const wsStatus = useAutonomousStatus();

  // Update status from WebSocket
  useEffect(() => {
    if (wsStatus) {
      setStatus(wsStatus);
    }
  }, [wsStatus]);
  
  // ... rest of component
};
```

### NotificationContext

Already integrated with WebSocket notifications:

```typescript
export const NotificationProvider: FC<NotificationProviderProps> = ({ children }) => {
  // ... state management
  
  // Subscribe to WebSocket autonomous notifications
  useEffect(() => {
    const unsubscribe = wsManager.on('autonomous_notifications', (data: any) => {
      const notification: AutonomousNotification = {
        id: data.id || `notif-${Date.now()}-${Math.random()}`,
        type: data.type,
        severity: data.severity,
        title: data.title,
        message: data.message,
        timestamp: data.timestamp || new Date().toISOString(),
        read: false,
        data: data.data,
        actionButton: data.actionButton,
      };

      addNotification(notification);
    });

    return unsubscribe;
  }, [addNotification]);
  
  // ... rest of provider
};
```

## Backend Event Types

### Autonomous Status Updates

Channel: `autonomous:status`
Event: `status_update`

```json
{
  "channel": "autonomous:status",
  "event": "status_update",
  "data": {
    "enabled": true,
    "market_regime": "TRENDING_UP",
    "market_confidence": 0.85,
    "data_quality": "GOOD",
    "last_cycle_time": "2026-02-18T18:30:00Z",
    "next_scheduled_run": "2026-02-25T18:30:00Z",
    "cycle_duration": 2700,
    "cycle_stats": {
      "proposals_count": 6,
      "backtested_count": 6,
      "activated_count": 2,
      "retired_count": 1
    },
    "portfolio_health": {
      "active_strategies": 8,
      "max_strategies": 10,
      "total_allocation": 95.0,
      "avg_correlation": 0.42,
      "portfolio_sharpe": 1.85
    },
    "template_stats": [
      {
        "name": "RSI Mean Reversion",
        "success_rate": 45.0,
        "usage_count": 12
      }
    ]
  },
  "timestamp": "2026-02-18T19:00:00Z"
}
```

### Autonomous Cycle Events

Channel: `autonomous:cycle`
Events: `cycle_started`, `cycle_completed`, `cycle_progress`

```json
{
  "channel": "autonomous:cycle",
  "event": "cycle_started",
  "data": {
    "cycle_id": "cycle-abc123",
    "estimated_duration": 2700,
    "market_regime": "TRENDING_UP"
  },
  "timestamp": "2026-02-18T19:00:00Z"
}
```

### Autonomous Strategy Events

Channel: `autonomous:strategies`
Events: `strategy_proposed`, `strategy_backtested`, `strategy_activated`, `strategy_retired`

```json
{
  "channel": "autonomous:strategies",
  "event": "strategy_activated",
  "data": {
    "id": "strat-xyz789",
    "name": "RSI Mean Reversion - SPY, QQQ",
    "template_name": "RSI Mean Reversion",
    "allocation": 15.0,
    "sharpe_ratio": 1.92,
    "expected_return": 12.3
  },
  "timestamp": "2026-02-18T19:05:00Z"
}
```

### Autonomous Notifications

Channel: `autonomous:notifications`
Event: `notification`

```json
{
  "channel": "autonomous:notifications",
  "event": "notification",
  "data": {
    "id": "notif-123",
    "type": "strategy_activated",
    "severity": "success",
    "title": "Strategy Activated",
    "message": "RSI Mean Reversion activated with 15% allocation",
    "timestamp": "2026-02-18T19:05:00Z",
    "actionButton": {
      "label": "View Strategy",
      "action": "view_strategy",
      "url": "/strategies/strat-xyz789"
    }
  },
  "timestamp": "2026-02-18T19:05:00Z"
}
```

## Performance Considerations

### Throttling Benefits

- **Reduced Re-renders**: Prevents excessive component updates
- **Lower CPU Usage**: Fewer handler invocations
- **Smoother UI**: Eliminates jank from rapid updates
- **Network Efficiency**: Reduces message processing overhead

### Memory Management

- **Automatic Cleanup**: Throttle timers cleared on disconnect
- **Subscription Cleanup**: Unsubscribe functions prevent memory leaks
- **Pending Message Limit**: Only latest message kept per type

### Best Practices

1. **Always unsubscribe**: Use cleanup functions in useEffect
2. **Avoid inline handlers**: Define handlers outside render
3. **Use appropriate throttle values**: Balance freshness vs. performance
4. **Monitor connection state**: Handle disconnections gracefully

## Testing

### Manual Testing

1. **Start backend**: Ensure WebSocket server is running
2. **Open browser console**: Monitor WebSocket messages
3. **Trigger autonomous cycle**: Verify events are received
4. **Check throttling**: Send rapid updates, verify throttling works
5. **Test reconnection**: Disconnect network, verify reconnection

### Integration Testing

```typescript
// Example test
describe('WebSocket Autonomous Integration', () => {
  it('should receive autonomous status updates', async () => {
    const handler = vi.fn();
    wsManager.onAutonomousStatus(handler);
    
    // Simulate WebSocket message
    const message = {
      channel: 'autonomous:status',
      event: 'status_update',
      data: { enabled: true, market_regime: 'TRENDING_UP' },
    };
    
    // Trigger message handler
    (wsManager as any).handleMessage(message);
    
    expect(handler).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: true })
    );
  });
});
```

## Troubleshooting

### Messages Not Received

1. Check WebSocket connection state: `wsManager.isConnected()`
2. Verify backend is broadcasting to correct channel
3. Check browser console for errors
4. Ensure auth token is valid

### Throttling Issues

1. Adjust throttle values in `THROTTLE_CONFIG`
2. Check if message type is being throttled
3. Monitor pending messages: `(wsManager as any).pendingMessages`

### Reconnection Failures

1. Check max reconnection attempts (default: 10)
2. Verify backend WebSocket endpoint is accessible
3. Check auth token expiration
4. Monitor reconnection attempts in console

## Future Enhancements

1. **Message Queuing**: Queue messages during disconnection
2. **Selective Subscriptions**: Subscribe to specific strategy IDs
3. **Compression**: Support WebSocket compression
4. **Binary Messages**: Support binary message format
5. **Heartbeat**: Implement ping/pong for connection health

## Related Files

- `frontend/src/services/websocket.ts` - WebSocket manager implementation
- `frontend/src/hooks/useWebSocket.ts` - React hooks for WebSocket
- `frontend/src/types/index.ts` - TypeScript type definitions
- `frontend/src/types/notifications.ts` - Notification type definitions
- `frontend/src/contexts/NotificationContext.tsx` - Notification context provider
- `frontend/src/components/AutonomousStatus.tsx` - Example component integration
- `src/api/websocket_manager.py` - Backend WebSocket manager

## Conclusion

The WebSocket autonomous integration provides a robust, performant, and developer-friendly way to receive real-time updates from the autonomous trading system. The implementation includes throttling, automatic reconnection, and easy-to-use React hooks that make integration straightforward.
