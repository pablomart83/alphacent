# AlphaCent Autonomous Trading System Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INTERACTION                         │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    Browser (localhost:3000)                 │ │
│  │                                                             │ │
│  │  ┌──────────────────────────────────────────────────────┐  │ │
│  │  │              Dashboard Home Page                      │  │ │
│  │  │                                                       │  │ │
│  │  │  [●] ACTIVE  ↑ 3 Strategies  💰 $10,245 P&L        │  │ │
│  │  │                                                       │  │ │
│  │  │  ┌─────────────────────────────────────────────┐    │  │ │
│  │  │  │  [Start Trading] [Pause] [Stop] [Kill Switch]│   │  │ │
│  │  │  └─────────────────────────────────────────────┘    │  │ │
│  │  │                                                       │  │ │
│  │  │  Last Active Strategies:                             │  │ │
│  │  │  • Momentum Tech (LIVE) - +2.3% today               │  │ │
│  │  │  • Crypto Swing (LIVE) - +5.1% today                │  │ │
│  │  │  • Value ETF (DEMO) - +1.2% today                   │  │ │
│  │  │                                                       │  │ │
│  │  │  Recent Activity:                                     │  │ │
│  │  │  • 10:30 - Bought 100 AAPL @ $150.25                │  │ │
│  │  │  • 10:15 - Sold 50 TSLA @ $245.80                   │  │ │
│  │  └───────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────┘  │ │
│                              │                                  │
│                              │ REST API + WebSocket             │
│                              ▼                                  │
└──────────────────────────────┼──────────────────────────────────┘
                               │
                               │ User logs out / closes browser
                               │ ▼ Backend continues running ▼
                               │
┌──────────────────────────────┼──────────────────────────────────┐
│                              │                                  │
│         Backend Service (localhost:8000) - ALWAYS RUNNING       │
│                              │                                  │
│  ┌───────────────────────────┴────────────────────────────────┐ │
│  │              System State Manager                          │ │
│  │                                                             │ │
│  │  Current State: ACTIVE                                     │ │
│  │  Started: 2026-02-14 08:00:00                             │ │
│  │  Uptime: 2h 30m                                            │ │
│  │  Active Strategies: 3                                      │ │
│  │  Open Positions: 5                                         │ │
│  │                                                             │ │
│  │  State Persistence: ✓ Saved to SQLite                     │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              Strategy Engine (Autonomous Loop)              │ │
│  │                                                             │ │
│  │  while system_state == ACTIVE:                             │ │
│  │      for strategy in enabled_strategies:                   │ │
│  │          signals = generate_signals(strategy)              │ │
│  │          for signal in signals:                            │ │
│  │              if risk_manager.validate(signal):             │ │
│  │                  order_executor.execute(signal)            │ │
│  │      sleep(interval)                                       │ │
│  │                                                             │ │
│  │  if system_state in [PAUSED, STOPPED, EMERGENCY_HALT]:    │ │
│  │      skip signal generation, maintain positions            │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    Data Persistence                         │ │
│  │                                                             │ │
│  │  SQLite Database:                                          │ │
│  │  • system_state (current state, timestamp, reason)         │ │
│  │  • state_history (audit trail of all changes)             │ │
│  │  • strategies (all strategies and their status)            │ │
│  │  • orders (all orders and fills)                           │ │
│  │  • positions (current and historical positions)            │ │
│  │  • performance_metrics (strategy performance)              │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## State Transition Diagram

```
                    ┌─────────────────────┐
                    │      STOPPED        │
                    │   (Initial State)   │
                    └──────────┬──────────┘
                               │
                               │ [Start Trading]
                               │ User clicks button
                               ▼
                    ┌─────────────────────┐
                    │       ACTIVE        │◄────────┐
                    │  Generating Signals │         │
                    │  Executing Trades   │         │
                    └──────────┬──────────┘         │
                               │                    │
                ┌──────────────┼──────────────┐     │
                │              │              │     │
    [Pause]     │   [Stop]     │   [Kill      │     │ [Resume]
    Temporary   │   Explicit   │   Switch]    │     │ Continue
    halt        │   halt       │   Emergency  │     │ trading
                │              │              │     │
                ▼              ▼              ▼     │
    ┌─────────────────┐  ┌──────────┐  ┌──────────────────┐
    │     PAUSED      │  │ STOPPED  │  │ EMERGENCY_HALT   │
    │ Positions Open  │  │ Positions│  │ All Closed       │
    │ No New Signals  │  │ Open     │  │ Manual Reset Req │
    └────────┬────────┘  └──────────┘  └────────┬─────────┘
             │                                   │
             │ [Resume]                          │ [Reset]
             └───────────────────────────────────┴──────────┐
                                                             │
                                                             ▼
                                                  ┌─────────────────┐
                                                  │    STOPPED      │
                                                  │ Ready to Start  │
                                                  └─────────────────┘
```

## Session Independence Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         Timeline                                 │
└─────────────────────────────────────────────────────────────────┘

08:00 │ User logs in
      │ Dashboard shows: STOPPED, 0 strategies, $0 P&L
      │
08:05 │ User clicks "Start Autonomous Trading"
      │ System State: STOPPED → ACTIVE
      │ Backend: Starts signal generation loop
      │
08:10 │ Strategy 1 activated (Momentum Tech)
      │ Strategy 2 activated (Crypto Swing)
      │ Backend: Generating signals, executing trades
      │
08:30 │ User closes browser ◄─── CRITICAL MOMENT
      │ Frontend: Disconnected
      │ Backend: CONTINUES RUNNING ✓
      │ System State: Still ACTIVE
      │ Strategies: Still generating signals
      │ Positions: Still being managed
      │
09:00 │ Backend: Bought 100 AAPL @ $150.25
      │ Backend: Sold 50 TSLA @ $245.80
      │ (No user interaction, fully autonomous)
      │
10:30 │ User logs in again ◄─── USER RETURNS
      │ Dashboard fetches current state from backend
      │ Shows: ACTIVE, 2 strategies, $245 P&L
      │ Shows: Recent trades (AAPL, TSLA)
      │ Shows: Current positions
      │ Shows: Performance metrics
      │
10:35 │ User clicks "Pause Trading"
      │ System State: ACTIVE → PAUSED
      │ Backend: Stops generating new signals
      │ Positions: Maintained (not closed)
      │
11:00 │ User logs out
      │ Frontend: Disconnected
      │ Backend: CONTINUES RUNNING ✓
      │ System State: Still PAUSED
      │ Positions: Still maintained
      │
14:00 │ User logs in
      │ Dashboard shows: PAUSED, 2 strategies, $245 P&L
      │ User clicks "Resume Trading"
      │ System State: PAUSED → ACTIVE
      │ Backend: Resumes signal generation
      │
17:00 │ User clicks "Stop Trading"
      │ System State: ACTIVE → STOPPED
      │ Backend: Stops signal generation
      │ Positions: Maintained (not closed)
      │
17:05 │ User logs out
      │ Backend: CONTINUES RUNNING ✓
      │ System State: STOPPED
      │ Ready for next session
```

## Control Panel UI Mockup

```
┌─────────────────────────────────────────────────────────────────┐
│                      Control Panel                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Autonomous Trading System                                       │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Status: ● ACTIVE                                          │ │
│  │  Started: 2026-02-14 08:05:23                             │ │
│  │  Uptime: 2h 30m 15s                                        │ │
│  │  Active Strategies: 3                                      │ │
│  │  Open Positions: 5                                         │ │
│  │  Last Signal: 2 minutes ago                                │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                                                             │ │
│  │   [  Stop Trading  ]  [  Pause Trading  ]                 │ │
│  │                                                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Emergency Controls                                              │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                                                             │ │
│  │   [ 🔴 Kill Switch ]  [ Reset Circuit Breaker ]           │ │
│  │                                                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Portfolio Management                                            │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                                                             │ │
│  │   [ Rebalance Portfolio ]                                  │ │
│  │                                                             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## State Color Coding

```
┌──────────────┬─────────────┬──────────────────────────────────┐
│    State     │    Color    │         Description              │
├──────────────┼─────────────┼──────────────────────────────────┤
│   ACTIVE     │   🟢 Green  │ Trading system running normally  │
│   PAUSED     │   🟡 Yellow │ Temporarily paused by user       │
│   STOPPED    │   🔴 Red    │ Stopped, ready to restart        │
│ EMERGENCY_   │   🔴 Dark   │ Emergency halt, requires reset   │
│   HALT       │     Red     │                                  │
└──────────────┴─────────────┴──────────────────────────────────┘
```

## Backend Service Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                    Backend Service Startup                       │
└─────────────────────────────────────────────────────────────────┘

1. Initialize FastAPI application
   │
   ▼
2. Connect to SQLite database
   │
   ▼
3. Restore system state from database
   │
   ├─ If state = ACTIVE:
   │  └─ Verify eToro API connection
   │     ├─ If connected: Resume signal generation
   │     └─ If not connected: Transition to PAUSED, alert user
   │
   ├─ If state = PAUSED:
   │  └─ Maintain paused state, wait for user action
   │
   ├─ If state = STOPPED:
   │  └─ Maintain stopped state, wait for user action
   │
   └─ If state = EMERGENCY_HALT:
      └─ Maintain halt state, require manual reset
   │
   ▼
4. Load active strategies from database
   │
   ▼
5. Load open positions from database
   │
   ▼
6. Start WebSocket server for real-time updates
   │
   ▼
7. Start background tasks:
   │  • Market data updates
   │  • Performance monitoring
   │  • Session cleanup
   │  • Backup scheduler
   │
   ▼
8. Start signal generation loop (if ACTIVE)
   │
   ▼
9. Ready to accept API requests

┌─────────────────────────────────────────────────────────────────┐
│                    Signal Generation Loop                        │
└─────────────────────────────────────────────────────────────────┘

while True:
    # Check system state
    if system_state != ACTIVE:
        log("Signal generation skipped: state is {system_state}")
        sleep(60)
        continue
    
    # Generate signals for each enabled strategy
    for strategy in get_enabled_strategies():
        try:
            signals = strategy_engine.generate_signals(strategy)
            
            for signal in signals:
                # Validate through risk manager
                validation = risk_manager.validate_signal(signal)
                
                if validation.is_valid:
                    # Execute order
                    order = order_executor.execute_signal(signal)
                    log(f"Order executed: {order.id}")
                else:
                    log(f"Signal rejected: {validation.reason}")
        
        except Exception as e:
            log(f"Error generating signals for {strategy.name}: {e}")
    
    # Sleep until next iteration
    sleep(signal_generation_interval)
```

## Key Architectural Principles

### 1. Separation of Concerns
- **Frontend**: User interface, visualization, controls
- **Backend**: Trading logic, state management, execution
- **Database**: Persistent storage, audit trail

### 2. State-Driven Behavior
- All components check system state before acting
- State changes propagate immediately via WebSocket
- State persists across all sessions and restarts

### 3. Fail-Safe Design
- Default to safe state (STOPPED) on errors
- Require explicit confirmation for risky actions
- Maintain audit trail of all state changes
- Emergency halt cannot be bypassed

### 4. User Transparency
- Always show current state
- Display historical data on login
- Show recent activity and performance
- Alert on any issues or state changes

### 5. Backend Independence
- Backend operates independently of frontend
- State persists across browser sessions
- Trading continues when user is not logged in
- Only stops on explicit command or critical error

## Summary

This architecture ensures:
- ✅ Backend runs autonomously, independent of browser
- ✅ User has explicit control via master start/stop
- ✅ System state persists across all sessions
- ✅ Dashboard shows current and historical data on login
- ✅ Multiple safety mechanisms (pause, stop, kill switch)
- ✅ Complete audit trail of all operations
- ✅ Graceful handling of service restarts
- ✅ Real-time synchronization via WebSocket
