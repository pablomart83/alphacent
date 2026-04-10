# Autonomous Trading Notification System

## Overview

The notification system provides real-time alerts and updates for autonomous trading events. It includes toast notifications, notification history, and customizable preferences.

## Architecture

### Components

1. **NotificationContext** (`frontend/src/contexts/NotificationContext.tsx`)
   - React Context for managing notification state
   - Handles WebSocket subscriptions
   - Persists notifications to localStorage
   - Manages notification preferences

2. **AutonomousNotificationToast** (`frontend/src/components/AutonomousNotificationToast.tsx`)
   - Displays floating toast notifications
   - Auto-dismisses info/success notifications after 10 seconds
   - Supports action buttons
   - Shows up to 3 notifications at once

3. **NotificationHistory** (`frontend/src/components/NotificationHistory.tsx`)
   - Full notification history view
   - Filtering by severity and event type
   - Search functionality
   - Mark as read/delete actions

4. **NotificationSettings** (`frontend/src/components/NotificationSettings.tsx`)
   - Configure notification preferences
   - Enable/disable notifications
   - Toggle sound alerts
   - Filter by severity and event type

## Notification Types

### Event Types

```typescript
type AutonomousEventType =
  | 'cycle_started'        // Autonomous cycle begins
  | 'cycle_completed'      // Autonomous cycle finishes
  | 'strategies_proposed'  // New strategies generated
  | 'backtest_completed'   // Strategy backtest finishes
  | 'strategy_activated'   // Strategy goes live
  | 'strategy_retired'     // Strategy is retired
  | 'regime_changed'       // Market regime changes
  | 'portfolio_rebalanced' // Portfolio allocation adjusted
  | 'error_occurred';      // System errors
```

### Severity Levels

```typescript
type NotificationSeverity = 'info' | 'success' | 'warning' | 'error';
```

## Data Structure

### AutonomousNotification

```typescript
interface AutonomousNotification {
  id: string;                    // Unique identifier
  type: AutonomousEventType;     // Event type
  severity: NotificationSeverity; // Severity level
  title: string;                 // Notification title
  message: string;               // Notification message
  timestamp: string;             // ISO timestamp
  read: boolean;                 // Read status
  data?: any;                    // Optional event data
  actionButton?: {               // Optional action button
    label: string;
    action: string;
    url?: string;
  };
}
```

### NotificationPreferences

```typescript
interface NotificationPreferences {
  enabled: boolean;                        // Master enable/disable
  soundEnabled: boolean;                   // Sound alerts
  showToasts: boolean;                     // Show toast notifications
  severityFilter: NotificationSeverity[];  // Filter by severity
  eventTypeFilter: AutonomousEventType[];  // Filter by event type
}
```

## Usage

### Using the Notification Context

```typescript
import { useAutonomousNotifications } from '../contexts/NotificationContext';

function MyComponent() {
  const {
    notifications,      // All notifications
    unreadCount,        // Count of unread notifications
    preferences,        // Current preferences
    addNotification,    // Add a notification
    markAsRead,         // Mark notification as read
    markAllAsRead,      // Mark all as read
    clearNotification,  // Remove a notification
    clearAll,           // Remove all notifications
    updatePreferences,  // Update preferences
  } = useAutonomousNotifications();

  // Add a notification
  const handleAddNotification = () => {
    addNotification({
      id: 'unique-id',
      type: 'strategy_activated',
      severity: 'success',
      title: 'Strategy Activated',
      message: 'RSI Mean Reversion strategy is now live',
      timestamp: new Date().toISOString(),
      read: false,
      actionButton: {
        label: 'View Strategy',
        action: 'navigate',
        url: '/trading',
      },
    });
  };

  return (
    <div>
      <p>Unread: {unreadCount}</p>
      <button onClick={handleAddNotification}>Add Notification</button>
    </div>
  );
}
```

### WebSocket Integration

The notification system automatically subscribes to the `autonomous_notifications` WebSocket channel:

```typescript
// Backend sends notifications via WebSocket
{
  type: 'autonomous_notifications',
  data: {
    id: 'notif-123',
    type: 'strategy_activated',
    severity: 'success',
    title: 'Strategy Activated',
    message: 'RSI Mean Reversion activated',
    timestamp: '2024-01-15T10:30:00Z',
    actionButton: {
      label: 'View Strategy',
      action: 'navigate',
      url: '/trading'
    }
  }
}
```

## Features

### Toast Notifications

- Display in top-right corner
- Show up to 3 notifications at once
- Auto-dismiss info/success after 10 seconds
- Warning/error require manual acknowledgment
- Support action buttons
- Animated slide-in effect

### Notification History

- View all notifications
- Filter by severity (info, success, warning, error)
- Filter by event type
- Search by title/message
- Mark as read/unread
- Delete individual or all notifications
- Persistent across sessions (localStorage)

### Notification Preferences

- Master enable/disable toggle
- Sound alerts toggle
- Toast notifications toggle
- Severity filter (select which severities to show)
- Event type filter (select which events to show)
- Preferences persist to localStorage

### Sound Alerts

When enabled, plays a simple beep sound using Web Audio API:
- 800Hz sine wave
- 0.5 second duration
- Plays for all new notifications (if enabled)

## Storage

### localStorage Keys

- `autonomous_notifications` - Stores notification history (max 100)
- `notification_preferences` - Stores user preferences

### Data Persistence

- Notifications persist across page reloads
- Limited to 100 most recent notifications
- Preferences persist indefinitely
- Cleared on logout (optional)

## Testing

### Manual Testing

Use the `NotificationDemo` component to test all notification types:

```typescript
import { NotificationDemo } from '../components/NotificationDemo';

// Add to any page for testing
<NotificationDemo />
```

### Integration Testing

See `frontend/src/__tests__/NotificationSystem.test.tsx` for test examples.

## Backend Integration

### WebSocket Event Format

Backend should send notifications in this format:

```python
# Python backend example
await websocket_manager.broadcast({
    "type": "autonomous_notifications",
    "data": {
        "id": f"notif-{uuid.uuid4()}",
        "type": "strategy_activated",
        "severity": "success",
        "title": "Strategy Activated",
        "message": f"{strategy_name} activated with {allocation}% allocation",
        "timestamp": datetime.utcnow().isoformat(),
        "data": {
            "strategy_id": strategy_id,
            "allocation": allocation
        },
        "actionButton": {
            "label": "View Strategy",
            "action": "navigate",
            "url": f"/trading?strategy={strategy_id}"
        }
    }
})
```

## Best Practices

### When to Send Notifications

- **Info**: General updates, cycle started, regime changes
- **Success**: Completed actions, strategy activated, cycle completed
- **Warning**: Strategy retired, performance degradation
- **Error**: Failed operations, system errors

### Notification Content

- **Title**: Short, descriptive (max 50 chars)
- **Message**: Detailed information (max 200 chars)
- **Action Button**: Only for actionable notifications
- **Data**: Include relevant IDs for debugging

### Performance

- Limit to 100 stored notifications
- Auto-dismiss info/success to reduce clutter
- Batch notifications during high-frequency events
- Use debouncing for rapid updates

## Accessibility

- ARIA labels on interactive elements
- Keyboard navigation support
- Screen reader friendly
- Color contrast meets WCAG AA standards
- Focus indicators on all buttons

## Future Enhancements

- [ ] Email notifications
- [ ] Push notifications (browser API)
- [ ] Notification grouping
- [ ] Custom sound selection
- [ ] Notification templates
- [ ] Export notification history
- [ ] Notification analytics
