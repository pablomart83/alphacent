# WebSocket Autonomous Integration Flow Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Backend System                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         Autonomous Strategy Manager                       │  │
│  │  - Proposes strategies                                    │  │
│  │  - Runs backtests                                         │  │
│  │  - Activates/retires strategies                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            │                                     │
│                            ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         WebSocket Manager (Python)                        │  │
│  │  - broadcast_autonomous_status_update()                   │  │
│  │  - broadcast_autonomous_cycle_event()                     │  │
│  │  - broadcast_autonomous_strategy_event()                  │  │
│  │  - broadcast_autonomous_notification()                    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            │                                     │
└────────────────────────────┼─────────────────────────────────────┘
                             │
                             │ WebSocket Connection
                             │ (wss://localhost:8000/ws?token=...)
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Frontend Application                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         WebSocket Manager (TypeScript)                    │  │
│  │                                                            │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │  Message Parser                                     │  │  │
│  │  │  - Parses JSON messages                             │  │  │
│  │  │  - Converts channel format to message type          │  │  │
│  │  │  - Routes to appropriate handler                    │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  │                            │                               │  │
│  │                            ▼                               │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │  Throttle Handler                                   │  │  │
│  │  │  - Checks throttle configuration                    │  │  │
│  │  │  - Queues high-frequency messages                   │  │  │
│  │  │  - Dispatches latest message after throttle period  │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  │                            │                               │  │
│  │                            ▼                               │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │  Message Dispatcher                                 │  │  │
│  │  │  - Invokes registered handlers                      │  │  │
│  │  │  - Error handling per handler                       │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  │                                                            │  │
│  │  Subscriptions:                                            │  │
│  │  - autonomous_status                                       │  │
│  │  - autonomous_cycle                                        │  │
│  │  - autonomous_strategies                                   │  │
│  │  - autonomous_notifications                                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            │                                     │
│                            ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         React Hooks                                       │  │
│  │  - useAutonomousStatus()                                  │  │
│  │  - useAutonomousCycle()                                   │  │
│  │  - useAutonomousStrategies()                              │  │
│  │  - useAutonomousNotifications()                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                            │                                     │
│                            ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         React Components                                  │  │
│  │  - AutonomousStatus                                       │  │
│  │  - PerformanceDashboard                                   │  │
│  │  - Strategies                                             │  │
│  │  - NotificationToast                                      │  │
│  │  - Autonomous Page (future)                               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Message Flow Example: Strategy Activation

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Backend Event                                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Autonomous Strategy Manager activates a strategy                │
│  ↓                                                                │
│  Calls: ws_manager.broadcast_autonomous_strategy_event(          │
│    event_type='strategy_activated',                              │
│    strategy={...}                                                 │
│  )                                                                │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: WebSocket Broadcast                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Message sent to all connected clients:                          │
│  {                                                                │
│    "channel": "autonomous:strategies",                           │
│    "event": "strategy_activated",                                │
│    "data": {                                                      │
│      "id": "strat-xyz789",                                        │
│      "name": "RSI Mean Reversion - SPY, QQQ",                    │
│      "allocation": 15.0,                                          │
│      "sharpe_ratio": 1.92                                         │
│    },                                                             │
│    "timestamp": "2026-02-18T19:05:00Z"                           │
│  }                                                                │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Frontend Receives Message                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  WebSocket.onmessage triggered                                   │
│  ↓                                                                │
│  Message Parser:                                                 │
│  - Detects channel format (has "channel" and "event" fields)     │
│  - Converts: "autonomous:strategies" → "autonomous_strategies"   │
│  - Creates WebSocketMessage: {                                   │
│      type: "autonomous_strategies",                              │
│      data: { event: "strategy_activated", data: {...} }          │
│    }                                                              │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Throttle Check                                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Throttle Handler:                                               │
│  - Checks THROTTLE_CONFIG["autonomous_strategies"]               │
│  - No throttle configured (default: 0)                           │
│  - Dispatches immediately                                        │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 5: Handler Invocation                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Message Dispatcher:                                             │
│  - Looks up handlers for "autonomous_strategies"                 │
│  - Invokes each registered handler with data                     │
│                                                                   │
│  Registered handlers:                                            │
│  1. useAutonomousStrategies hook → updates state                 │
│  2. NotificationContext → creates notification                   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 6: Component Updates                                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  React Components re-render with new data:                       │
│                                                                   │
│  1. Strategies Component:                                        │
│     - Adds new strategy to list                                  │
│     - Shows "ACTIVE" badge                                       │
│     - Displays allocation: 15%                                   │
│                                                                   │
│  2. AutonomousStatus Component:                                  │
│     - Updates active strategies count                            │
│     - Updates total allocation                                   │
│     - Flash effect on change                                     │
│                                                                   │
│  3. NotificationToast:                                           │
│     - Shows success notification                                 │
│     - "Strategy Activated"                                       │
│     - "RSI Mean Reversion activated with 15% allocation"         │
│     - [View Strategy] button                                     │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Throttling Example: Market Data Updates

```
Time: 0ms
┌─────────────────────────────────────────────────────────────────┐
│ Message 1: AAPL price = $150.00                                  │
│ ↓                                                                 │
│ Throttle Check: Last message = never                             │
│ ↓                                                                 │
│ Action: Dispatch immediately                                     │
│ ↓                                                                 │
│ Result: Handler called with $150.00                              │
│ lastMessageTime["market_data"] = 0ms                             │
└─────────────────────────────────────────────────────────────────┘

Time: 100ms
┌─────────────────────────────────────────────────────────────────┐
│ Message 2: AAPL price = $150.10                                  │
│ ↓                                                                 │
│ Throttle Check: Last message = 0ms, elapsed = 100ms             │
│ Throttle delay = 1000ms                                          │
│ ↓                                                                 │
│ Action: Queue message, schedule dispatch in 900ms                │
│ ↓                                                                 │
│ Result: Handler NOT called yet                                   │
│ pendingMessages["market_data"] = $150.10                         │
└─────────────────────────────────────────────────────────────────┘

Time: 500ms
┌─────────────────────────────────────────────────────────────────┐
│ Message 3: AAPL price = $150.25                                  │
│ ↓                                                                 │
│ Throttle Check: Last message = 0ms, elapsed = 500ms             │
│ Throttle delay = 1000ms                                          │
│ ↓                                                                 │
│ Action: Replace queued message, reschedule dispatch in 500ms     │
│ ↓                                                                 │
│ Result: Handler NOT called yet                                   │
│ pendingMessages["market_data"] = $150.25 (replaced $150.10)     │
└─────────────────────────────────────────────────────────────────┘

Time: 1000ms
┌─────────────────────────────────────────────────────────────────┐
│ Scheduled dispatch triggered                                     │
│ ↓                                                                 │
│ Action: Dispatch pending message                                 │
│ ↓                                                                 │
│ Result: Handler called with $150.25                              │
│ lastMessageTime["market_data"] = 1000ms                          │
│ pendingMessages["market_data"] = deleted                         │
└─────────────────────────────────────────────────────────────────┘

Summary:
- 3 messages received
- 2 handler invocations (33% reduction)
- Latest data always dispatched
- UI updates smoothly without jank
```

## Reconnection Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ Connection Lost                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  WebSocket.onclose triggered                                     │
│  ↓                                                                │
│  Check: isIntentionallyClosed = false                            │
│  ↓                                                                │
│  Action: Schedule reconnection                                   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Reconnection Attempt 1                                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Delay: 1000ms (1s)                                              │
│  ↓                                                                │
│  Attempt: connect()                                              │
│  ↓                                                                │
│  Result: Failed                                                  │
│  ↓                                                                │
│  Action: Schedule next attempt                                   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Reconnection Attempt 2                                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Delay: 2000ms (2s) - exponential backoff                       │
│  ↓                                                                │
│  Attempt: connect()                                              │
│  ↓                                                                │
│  Result: Failed                                                  │
│  ↓                                                                │
│  Action: Schedule next attempt                                   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Reconnection Attempt 3                                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Delay: 4000ms (4s) - exponential backoff                       │
│  ↓                                                                │
│  Attempt: connect()                                              │
│  ↓                                                                │
│  Result: Success!                                                │
│  ↓                                                                │
│  Actions:                                                        │
│  - Reset reconnectAttempts = 0                                   │
│  - Reset reconnectDelay = 1000ms                                 │
│  - Notify connection state handlers (connected = true)           │
│  - Subscriptions automatically restored                          │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Component Integration Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│ Component: AutonomousStatus                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  const wsStatus = useAutonomousStatus();                         │
│                                                                   │
│  useEffect(() => {                                               │
│    if (wsStatus) {                                               │
│      setStatus(wsStatus);  // Update local state                │
│    }                                                              │
│  }, [wsStatus]);                                                 │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ Render Cycle                                               │ │
│  │                                                             │ │
│  │ 1. Initial render: wsStatus = null                         │ │
│  │    → Shows loading state                                   │ │
│  │                                                             │ │
│  │ 2. WebSocket message received                              │ │
│  │    → useAutonomousStatus updates                           │ │
│  │    → wsStatus = { enabled: true, ... }                     │ │
│  │    → useEffect triggers                                    │ │
│  │    → setStatus called                                      │ │
│  │    → Component re-renders with data                        │ │
│  │                                                             │ │
│  │ 3. Subsequent WebSocket messages                           │ │
│  │    → useAutonomousStatus updates                           │ │
│  │    → useEffect triggers                                    │ │
│  │    → setStatus called                                      │ │
│  │    → Component re-renders (with flash effect)             │ │
│  │                                                             │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Performance Optimization

```
Without Throttling:
┌─────────────────────────────────────────────────────────────────┐
│ 100 messages/second                                              │
│ ↓                                                                 │
│ 100 handler invocations/second                                   │
│ ↓                                                                 │
│ 100 React re-renders/second                                      │
│ ↓                                                                 │
│ Result: UI jank, high CPU usage, poor UX                        │
└─────────────────────────────────────────────────────────────────┘

With Throttling (1000ms):
┌─────────────────────────────────────────────────────────────────┐
│ 100 messages/second                                              │
│ ↓                                                                 │
│ 1 handler invocation/second (99% reduction)                      │
│ ↓                                                                 │
│ 1 React re-render/second                                         │
│ ↓                                                                 │
│ Result: Smooth UI, low CPU usage, great UX                      │
│ Bonus: Always shows latest data                                  │
└─────────────────────────────────────────────────────────────────┘
```
