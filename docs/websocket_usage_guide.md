# WebSocket Autonomous Integration - Usage Guide

## Quick Start

### 1. Basic Setup

The WebSocket connection is automatically established when the user logs in. No manual setup required!

```typescript
import { useWebSocketManager } from '../hooks/useWebSocket';

function App() {
  // Automatically connects on mount, disconnects on unmount
  useWebSocketManager();
  
  return <YourApp />;
}
```

### 2. Subscribe to Status Updates

```typescript
import { useAutonomousStatus } from '../hooks/useWebSocket';

function StatusDisplay() {
  const status = useAutonomousStatus();
  
  if (!status) return <div>Loading...</div>;
  
  return (
    <div>
      <h2>System Status</h2>
      <p>Enabled: {status.enabled ? 'Yes' : 'No'}</p>
      <p>Market Regime: {status.market_regime}</p>
      <p>Active Strategies: {status.portfolio_health.active_strategies}</p>
    </div>
  );
}
```

### 3. Monitor Cycle Events

```typescript
import { useAutonomousCycle } from '../hooks/useWebSocket';
import { useEffect } from 'react';

function CycleMonitor() {
  const cycleEvent = useAutonomousCycle();
  
  useEffect(() => {
    if (cycleEvent?.event === 'cycle_started') {
      console.log('Cycle started!', cycleEvent.data);
      // Show progress indicator
    } else if (cycleEvent?.event === 'cycle_completed') {
      console.log('Cycle completed!', cycleEvent.data);
      // Hide progress indicator, refresh data
    }
  }, [cycleEvent]);
  
  return (
    <div>
      {cycleEvent && (
        <div>Last event: {cycleEvent.event}</div>
      )}
    </div>
  );
}
```

### 4. Handle Notifications

```typescript
import { useAutonomousNotifications } from '../hooks/useWebSocket';

function NotificationBell() {
  const { notifications, unreadCount, markAsRead } = useAutonomousNotifications();
  
  return (
    <div>
      <button>
        🔔 {unreadCount > 0 && <span>{unreadCount}</span>}
      </button>
      <div className="dropdown">
        {notifications.map(n => (
          <div key={n.id} onClick={() => markAsRead(n.id)}>
            <strong>{n.title}</strong>
            <p>{n.message}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
```

## Common Patterns

### Pattern 1: Combining API Fetch with WebSocket Updates

Use API for initial data, WebSocket for real-time updates:

```typescript
import { useState, useEffect } from 'react';
import { apiClient } from '../services/api';
import { useAutonomousStatus } from '../hooks/useWebSocket';

function AutonomousStatusPanel() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  
  // Get real-time updates
  const wsStatus = useAutonomousStatus();
  
  // Initial fetch
  useEffect(() => {
    apiClient.getAutonomousStatus()
      .then(data => {
        setStatus(data);
        setLoading(false);
      })
      .catch(err => console.error(err));
  }, []);
  
  // Update from WebSocket
  useEffect(() => {
    if (wsStatus) {
      setStatus(wsStatus);
    }
  }, [wsStatus]);
  
  if (loading) return <div>Loading...</div>;
  
  return <div>{/* Render status */}</div>;
}
```

### Pattern 2: Flash Effect on Updates

Highlight changes when data updates:

```typescript
import { useUpdateFlash } from '../hooks/useUpdateFlash';
import { useAutonomousStatus } from '../hooks/useWebSocket';

function StatusCard() {
  const status = useAutonomousStatus();
  
  // Flash when regime changes
  const regimeFlash = useUpdateFlash(status?.market_regime);
  
  return (
    <div className={regimeFlash ? 'flash-animation' : ''}>
      Market Regime: {status?.market_regime}
    </div>
  );
}
```

### Pattern 3: Event-Driven Actions

Trigger actions based on WebSocket events:

```typescript
import { useEffect } from 'react';
import { useAutonomousStrategies } from '../hooks/useWebSocket';
import { toast } from '../components/Toast';

function StrategyEventHandler() {
  const strategyEvent = useAutonomousStrategies();
  
  useEffect(() => {
    if (!strategyEvent) return;
    
    switch (strategyEvent.event) {
      case 'strategy_activated':
        toast.success(`Strategy activated: ${strategyEvent.data.name}`);
        // Refresh strategy list
        break;
        
      case 'strategy_retired':
        toast.warning(`Strategy retired: ${strategyEvent.data.name}`);
        // Update UI
        break;
        
      case 'strategy_proposed':
        // Show notification
        break;
    }
  }, [strategyEvent]);
  
  return null; // This is an event handler component
}
```

### Pattern 4: Connection Status Indicator

Show connection state to user:

```typescript
import { useWebSocketConnection } from '../hooks/useWebSocket';

function ConnectionIndicator() {
  const isConnected = useWebSocketConnection();
  
  return (
    <div className={`indicator ${isConnected ? 'connected' : 'disconnected'}`}>
      <div className="dot" />
      <span>{isConnected ? 'Live' : 'Disconnected'}</span>
    </div>
  );
}
```

### Pattern 5: Conditional Rendering Based on Events

```typescript
import { useState, useEffect } from 'react';
import { useAutonomousCycle } from '../hooks/useWebSocket';

function CycleProgressIndicator() {
  const [isRunning, setIsRunning] = useState(false);
  const cycleEvent = useAutonomousCycle();
  
  useEffect(() => {
    if (cycleEvent?.event === 'cycle_started') {
      setIsRunning(true);
    } else if (cycleEvent?.event === 'cycle_completed') {
      setIsRunning(false);
    }
  }, [cycleEvent]);
  
  if (!isRunning) return null;
  
  return (
    <div className="progress-bar">
      <div className="spinner" />
      <span>Autonomous cycle in progress...</span>
    </div>
  );
}
```

## Advanced Usage

### Custom Hook for Specific Strategy

```typescript
import { useEffect, useState } from 'react';
import { useAutonomousStrategies } from '../hooks/useWebSocket';

function useStrategyById(strategyId: string) {
  const [strategy, setStrategy] = useState(null);
  const strategyEvent = useAutonomousStrategies();
  
  useEffect(() => {
    if (strategyEvent?.data?.id === strategyId) {
      setStrategy(strategyEvent.data);
    }
  }, [strategyEvent, strategyId]);
  
  return strategy;
}

// Usage
function StrategyDetail({ strategyId }) {
  const strategy = useStrategyById(strategyId);
  
  return <div>{/* Render strategy */}</div>;
}
```

### Aggregating Multiple Events

```typescript
import { useState, useEffect } from 'react';
import { useAutonomousCycle, useAutonomousStrategies } from '../hooks/useWebSocket';

function EventTimeline() {
  const [events, setEvents] = useState([]);
  const cycleEvent = useAutonomousCycle();
  const strategyEvent = useAutonomousStrategies();
  
  useEffect(() => {
    if (cycleEvent) {
      setEvents(prev => [{
        type: 'cycle',
        event: cycleEvent.event,
        data: cycleEvent.data,
        timestamp: new Date(),
      }, ...prev].slice(0, 50)); // Keep last 50 events
    }
  }, [cycleEvent]);
  
  useEffect(() => {
    if (strategyEvent) {
      setEvents(prev => [{
        type: 'strategy',
        event: strategyEvent.event,
        data: strategyEvent.data,
        timestamp: new Date(),
      }, ...prev].slice(0, 50));
    }
  }, [strategyEvent]);
  
  return (
    <div>
      {events.map((event, idx) => (
        <div key={idx}>
          {event.timestamp.toLocaleTimeString()} - {event.type}: {event.event}
        </div>
      ))}
    </div>
  );
}
```

### Notification Filtering

```typescript
import { useMemo } from 'react';
import { useAutonomousNotifications } from '../hooks/useWebSocket';

function FilteredNotifications({ severityFilter = ['error', 'warning'] }) {
  const { notifications } = useAutonomousNotifications();
  
  const filteredNotifications = useMemo(() => {
    return notifications.filter(n => severityFilter.includes(n.severity));
  }, [notifications, severityFilter]);
  
  return (
    <div>
      {filteredNotifications.map(n => (
        <div key={n.id}>{n.title}</div>
      ))}
    </div>
  );
}
```

### Debounced Updates

```typescript
import { useState, useEffect } from 'react';
import { useAutonomousStatus } from '../hooks/useWebSocket';

function DebouncedStatusDisplay() {
  const wsStatus = useAutonomousStatus();
  const [status, setStatus] = useState(null);
  
  useEffect(() => {
    // Debounce updates by 500ms
    const timer = setTimeout(() => {
      if (wsStatus) {
        setStatus(wsStatus);
      }
    }, 500);
    
    return () => clearTimeout(timer);
  }, [wsStatus]);
  
  return <div>{/* Render status */}</div>;
}
```

## Performance Tips

### 1. Memoize Expensive Computations

```typescript
import { useMemo } from 'react';
import { useAutonomousStatus } from '../hooks/useWebSocket';

function PerformanceMetrics() {
  const status = useAutonomousStatus();
  
  // Expensive calculation - only recompute when status changes
  const metrics = useMemo(() => {
    if (!status) return null;
    
    return {
      efficiency: calculateEfficiency(status),
      riskScore: calculateRiskScore(status),
      // ... other expensive calculations
    };
  }, [status]);
  
  return <div>{/* Render metrics */}</div>;
}
```

### 2. Avoid Inline Functions

```typescript
// ❌ Bad - creates new function on every render
function NotificationList() {
  const { notifications, markAsRead } = useAutonomousNotifications();
  
  return (
    <div>
      {notifications.map(n => (
        <div onClick={() => markAsRead(n.id)}>{n.title}</div>
      ))}
    </div>
  );
}

// ✅ Good - use useCallback
import { useCallback } from 'react';

function NotificationList() {
  const { notifications, markAsRead } = useAutonomousNotifications();
  
  const handleClick = useCallback((id: string) => {
    markAsRead(id);
  }, [markAsRead]);
  
  return (
    <div>
      {notifications.map(n => (
        <NotificationItem key={n.id} notification={n} onClick={handleClick} />
      ))}
    </div>
  );
}
```

### 3. Selective Subscriptions

```typescript
// Only subscribe to what you need
function MinimalComponent() {
  // ❌ Don't do this if you only need status
  const { status, cycleEvent, strategyEvent, notifications } = useAutonomousWebSocket();
  
  // ✅ Do this instead
  const status = useAutonomousStatus();
  
  return <div>{/* Use only status */}</div>;
}
```

## Debugging

### Enable Verbose Logging

```typescript
// In browser console
localStorage.setItem('debug', 'websocket:*');

// Or in code
wsManager.on('*', (data) => {
  console.log('WebSocket message:', data);
});
```

### Check Connection State

```typescript
import { wsManager } from '../services/websocket';

// In browser console
console.log('Connected:', wsManager.isConnected());
console.log('State:', wsManager.getConnectionState());
console.log('Connection count:', wsManager.getConnectionCount());
```

### Monitor Throttling

```typescript
// Check throttle state
console.log('Throttle timers:', wsManager['throttleTimers']);
console.log('Pending messages:', wsManager['pendingMessages']);
console.log('Last message times:', wsManager['lastMessageTime']);
```

## Testing

### Mock WebSocket in Tests

```typescript
import { vi } from 'vitest';
import { wsManager } from '../services/websocket';

describe('MyComponent', () => {
  beforeEach(() => {
    // Mock WebSocket
    global.WebSocket = vi.fn().mockImplementation(() => ({
      readyState: WebSocket.OPEN,
      send: vi.fn(),
      close: vi.fn(),
    }));
  });
  
  it('should handle status updates', () => {
    const { result } = renderHook(() => useAutonomousStatus());
    
    // Simulate WebSocket message
    act(() => {
      wsManager['handleMessage']({
        type: 'autonomous_status',
        data: { enabled: true, market_regime: 'TRENDING_UP' },
      });
    });
    
    expect(result.current?.enabled).toBe(true);
  });
});
```

## Troubleshooting

### Problem: Not Receiving Updates

**Solution:**
1. Check WebSocket connection: `wsManager.isConnected()`
2. Verify auth token is valid
3. Check browser console for errors
4. Ensure backend is broadcasting events

### Problem: Too Many Re-renders

**Solution:**
1. Use `useMemo` for expensive computations
2. Use `useCallback` for event handlers
3. Check if throttling is configured correctly
4. Avoid creating new objects/arrays in render

### Problem: Stale Data

**Solution:**
1. Ensure WebSocket is connected
2. Check if component is subscribed to correct channel
3. Verify backend is sending updates
4. Check throttle configuration (might be too aggressive)

### Problem: Memory Leaks

**Solution:**
1. Ensure cleanup functions are called (useEffect return)
2. Check if unsubscribe functions are being called
3. Verify components are unmounting properly
4. Use React DevTools Profiler to identify leaks

## Best Practices

1. **Always Clean Up**: Use cleanup functions in useEffect
2. **Handle Loading States**: Show loading indicators while waiting for data
3. **Handle Errors**: Implement error boundaries and error handling
4. **Optimize Re-renders**: Use memoization and callbacks
5. **Monitor Connection**: Show connection status to users
6. **Provide Fallbacks**: Have fallback polling if WebSocket fails
7. **Test Thoroughly**: Test with network disconnections and reconnections
8. **Log Appropriately**: Log important events but avoid spam
9. **Document Usage**: Document how components use WebSocket
10. **Version Carefully**: Ensure frontend/backend message formats match

## Resources

- [WebSocket API Documentation](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [React Hooks Documentation](https://react.dev/reference/react)
- [WebSocket Integration Documentation](./websocket_autonomous_integration.md)
- [Flow Diagrams](./websocket_flow_diagram.md)
