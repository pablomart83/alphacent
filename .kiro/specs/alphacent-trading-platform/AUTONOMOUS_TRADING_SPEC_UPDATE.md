# Autonomous Trading System Specification Update

**Date**: February 14, 2026  
**Purpose**: Formalize autonomous trading system requirements with explicit start/stop controls and state management

## Overview

This document captures the updates made to the AlphaCent Trading Platform specification to explicitly define the autonomous trading system's behavior, including:

1. Master start/stop controls for all trading operations
2. System state management (ACTIVE, PAUSED, STOPPED, EMERGENCY_HALT)
3. Backend service independence from frontend UI sessions
4. State persistence across browser sessions and service restarts
5. Dashboard home page display of system status and historical data

## Requirements Updates

### Requirement 7: LLM Integration

**Added Acceptance Criteria**:

8. WHEN autonomous trading is started, THE Backend_Service SHALL verify Ollama is running and accessible
9. IF Ollama is not accessible when starting autonomous trading, THE Backend_Service SHALL attempt to start Ollama service or alert the user
10. WHEN autonomous trading is stopped, THE Backend_Service MAY optionally stop Ollama service based on configuration

### Requirement 16: Web Application Architecture

**Added Acceptance Criteria**:

13. THE Backend_Service SHALL manage dependent services (Ollama LLM) lifecycle based on autonomous trading state
14. WHEN starting autonomous trading, THE Backend_Service SHALL verify all required services are running and accessible
15. IF required services are not running, THE Backend_Service SHALL attempt to start them or provide clear instructions to the user

### NEW Requirement 16.1: Service Dependency Management

**User Story:** As a trader, I want the platform to automatically manage required services, so that I don't have to manually start/stop dependencies.

**Acceptance Criteria**:

1. THE Backend_Service SHALL maintain a list of required dependent services (Ollama LLM)
2. WHEN autonomous trading is started, THE Backend_Service SHALL check if Ollama is running at localhost:11434
3. IF Ollama is not running, THE Backend_Service SHALL attempt to start Ollama using system commands
4. IF Ollama cannot be started automatically, THE Backend_Service SHALL transition to PAUSED state and alert the user with instructions
5. WHEN Ollama becomes unavailable during active trading, THE Backend_Service SHALL disable strategy generation but maintain existing positions
6. THE Backend_Service SHALL periodically health-check Ollama service (every 60 seconds)
7. WHEN autonomous trading is stopped, THE Backend_Service MAY optionally stop Ollama based on user configuration
8. THE Dashboard SHALL display status of all dependent services (Running, Stopped, Error)
9. THE Dashboard SHALL provide manual controls to start/stop dependent services
10. THE AlphaCent SHALL log all service lifecycle events (start, stop, health check failures)

**Rationale**: Ensures that Start/Stop Autonomous Trading manages all required backend services, not just the trading logic.

### Requirement 11: Dashboard and User Interface

**Added Acceptance Criteria**:

11. THE Dashboard SHALL provide a master control to start/stop all autonomous trading operations
12. THE Dashboard SHALL display the current autonomous trading system status (ACTIVE, PAUSED, STOPPED)
13. WHEN a user logs in, THE Dashboard home page SHALL display last active strategies and their current status
14. WHEN a user logs in, THE Dashboard home page SHALL display performance metrics from the current and previous sessions
15. WHEN a user logs in, THE Dashboard home page SHALL display system operational status and any alerts
16. WHEN autonomous trading is stopped, THE Backend_Service SHALL halt signal generation for all strategies while maintaining existing positions

**Rationale**: These criteria explicitly define the master control mechanism and home page display requirements that were previously implicit or missing.

## Design Document Updates

### New Section: Autonomous Trading State Management

Added comprehensive section covering:

#### Service Dependency Management

New section defining how the platform manages dependent services (Ollama LLM):

**Service Lifecycle**:
- Health checking (every 60 seconds)
- Automatic startup on trading start
- Graceful degradation on service failure
- Optional shutdown on trading stop

**Service Manager Class**:
- `check_all_services()` - Check status of all services
- `start_service()` - Start a dependent service
- `stop_service()` - Stop a dependent service
- `ensure_services_running()` - Ensure all required services available

**Integration with State Manager**:
- Check services before transitioning to ACTIVE
- Transition to PAUSED if services unavailable
- Alert user with service status and instructions
- Disable affected features when services down

**API Endpoints**:
- `GET /system/services` - Get status of all services
- `POST /system/services/:name/start` - Start a service
- `POST /system/services/:name/stop` - Stop a service
- `GET /system/services/:name/health` - Health check a service

**Dashboard Display**:
- Service status indicators
- Manual start/stop controls
- Error messages and impact warnings
- Real-time updates via WebSocket

#### Trading System States

1. **ACTIVE**: All enabled strategies generate signals and execute trades
2. **PAUSED**: Signal generation halted, existing positions maintained
3. **STOPPED**: All trading halted, positions maintained, requires explicit restart
4. **EMERGENCY_HALT**: Kill Switch or Circuit Breaker activated, all positions closed

#### State Transitions

Defined valid state transitions:
- STOPPED → ACTIVE (Start Trading)
- ACTIVE → PAUSED (Pause Trading)
- PAUSED → ACTIVE (Resume Trading)
- PAUSED → STOPPED (Stop Trading)
- ACTIVE → STOPPED (Stop Trading)
- ACTIVE → EMERGENCY_HALT (Kill Switch/Circuit Breaker)
- EMERGENCY_HALT → STOPPED (Manual Reset)

#### State Persistence

- State saved to SQLite database on every change
- Backend service restores state on startup
- Independent of user login/logout
- Survives backend service restarts
- Transaction log records all state transitions

#### Dashboard Controls

- Master "Start/Stop Autonomous Trading" button
- Color-coded status indicator (Green/Yellow/Red/Dark Red)
- Confirmation dialogs for state changes
- Home page displays system status on login

#### Backend Service Independence

Explicitly validates **Requirement 16.12**: "THE Backend_Service SHALL continue running trading strategies even when the browser is closed"

Implementation details:
- Backend runs as independent process
- Does not depend on active user sessions
- Continues when browser closed, user logged out, or frontend disconnected
- Only stops on explicit user action or critical errors

#### API Endpoints

New endpoints defined:
- `GET /system/status` - Get current state
- `POST /system/start` - Start autonomous trading
- `POST /system/pause` - Pause trading
- `POST /system/stop` - Stop trading
- `POST /system/resume` - Resume from paused
- `POST /system/reset` - Reset from emergency halt

### New Data Model: SystemState

```python
@dataclass
class SystemState:
    state: SystemStateEnum  # ACTIVE, PAUSED, STOPPED, EMERGENCY_HALT
    timestamp: datetime
    reason: str
    initiated_by: Optional[str]  # Username who initiated change
    active_strategies_count: int
    open_positions_count: int
    uptime_seconds: int
    last_signal_generated: Optional[datetime]
    last_order_executed: Optional[datetime]
```

```python
class SystemStateEnum(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    EMERGENCY_HALT = "emergency_halt"
```

## Tasks Updates

### New Backend Tasks

**Task 17.8.3: Implement service dependency management**
- Create ServiceManager class for managing dependent services
- Implement Ollama service health checking (localhost:11434)
- Add automatic service startup on autonomous trading start
- Implement periodic health checks (every 60 seconds)
- Handle service failures gracefully (disable features, maintain positions)
- Add service recovery logic (automatic reconnection attempts)
- Implement optional service shutdown on trading stop
- Create service status API endpoints
- _Requirements: 7.8, 7.9, 16.1.1-16.1.10_

**Task 17.8.4: Integrate service checks with state transitions**
- Check Ollama availability before transitioning to ACTIVE
- Transition to PAUSED if services unavailable
- Alert user with service status and instructions
- Disable strategy generation when Ollama unavailable
- Re-enable when service recovers
- _Requirements: 16.1.2, 16.1.3, 16.1.4, 16.1.5_

**Task 17.8.1: Implement system state management endpoints**
- GET /system/status for current autonomous trading state
- POST /system/start for starting autonomous trading
- POST /system/pause for pausing autonomous trading
- POST /system/stop for stopping autonomous trading
- POST /system/resume for resuming from paused state
- POST /system/reset for resetting from emergency halt
- Implement state validation and transition logic
- Add confirmation requirement for state changes
- Log all state transitions with audit trail
- _Requirements: 11.11, 11.12, 16.12_

**Task 17.8.2: Implement system state persistence**
- Create SystemState data model and ORM mapping
- Save state to database on every change
- Restore state on backend service startup
- Implement state validation on restoration
- Handle invalid states gracefully
- Create state transition history table
- _Requirements: 11.12, 14.1, 16.12_

**Task 17.9: Updated WebSocket handler**
- Added: Push system state changes to connected clients
- _Requirements: 11.9, 11.12, 16.11_

**Task 10.5.1: Integrate system state checks in signal generation**
- Check system state before generating signals
- Skip signal generation when state is PAUSED, STOPPED, or EMERGENCY_HALT
- Log skipped signal generation with reason
- Resume signal generation when state returns to ACTIVE
- _Requirements: 11.12, 11.16, 16.12_

### New Frontend Tasks

**Task 19.12.1: Implement Autonomous Trading Master Control**
- Add "Start Autonomous Trading" / "Stop Autonomous Trading" toggle button
- Add "Pause Trading" / "Resume Trading" controls
- Display system status indicator (ACTIVE/PAUSED/STOPPED/EMERGENCY_HALT)
- Implement color-coded status badge (Green/Yellow/Red/Dark Red)
- Add confirmation dialogs for all state changes
- Show last state change timestamp and reason
- Display number of active strategies
- Persist autonomous trading state across sessions
- Disable controls appropriately during EMERGENCY_HALT
- _Requirements: 11.11, 11.12, 11.16, 16.12_

**Task 19.12.2: Implement Home Page System Status Display**
- Display current autonomous trading status on login
- Show last active strategies and their current status
- Display performance metrics from current session
- Show performance summary from previous sessions
- Display active positions count and total P&L
- Show recent trades and orders
- Display system alerts and warnings
- Show system uptime and last activity timestamps
- _Requirements: 11.13, 11.14, 11.15_

**Task 19.12.3: Implement Dependent Services Status Display**
- Display status of all dependent services (Ollama LLM)
- Show service health indicator (Running/Stopped/Error)
- Display service endpoint and last health check time
- Add manual start/stop/restart controls for each service
- Show error messages when services are unavailable
- Display impact on features when services are down
- Update service status in real-time via WebSocket
- _Requirements: 16.1.8, 16.1.9_

## Key Principles

### 1. Backend Independence

The backend service operates independently of the frontend UI:
- Continues running when browser is closed
- Maintains state across user sessions
- Only stops on explicit command or critical error
- Validates Requirement 16.12

### 2. State Persistence

All system state is persisted:
- Saved to database on every change
- Restored on service startup
- Complete audit trail maintained
- Survives service restarts

### 3. User Control

Users have explicit control over trading:
- Master start/stop button
- Pause/resume capability
- Emergency halt (Kill Switch)
- Automatic halt (Circuit Breaker)
- All actions require confirmation

### 4. Transparency

System status is always visible:
- Color-coded status indicator
- Home page shows current state
- Historical performance displayed
- Active strategies listed
- Recent activity shown

### 5. Safety First

Multiple layers of protection:
- Explicit confirmation for state changes
- EMERGENCY_HALT cannot be bypassed
- Circuit Breaker automatic protection
- Kill Switch manual override
- All state changes logged

## Implementation Priority

### Phase 1: Backend State Management (Critical)
1. Task 17.8.2: System state persistence
2. Task 17.8.1: System state endpoints
3. Task 10.5.1: Signal generation integration

### Phase 2: Frontend Controls (High Priority)
1. Task 19.12.1: Master control implementation
2. Task 19.12.2: Home page status display
3. Task 17.9: WebSocket state updates

### Phase 3: Testing and Validation
1. End-to-end testing of state transitions
2. Verify backend independence
3. Test state restoration on startup
4. Validate WebSocket synchronization

## Validation Checklist

- [ ] Backend service continues running when browser closed
- [ ] System state persists across service restarts
- [ ] User can start/stop autonomous trading from Dashboard
- [ ] User can pause/resume trading
- [ ] Home page displays last session data on login
- [ ] All state transitions logged with audit trail
- [ ] Signal generation respects system state
- [ ] WebSocket pushes state changes to clients
- [ ] Confirmation required for all state changes
- [ ] EMERGENCY_HALT requires manual reset
- [ ] State restoration validates on startup
- [ ] Multiple browser sessions show same state

## Benefits

1. **Explicit Control**: Users have clear, explicit control over autonomous trading
2. **Transparency**: System status always visible and understandable
3. **Persistence**: State survives browser closure and service restarts
4. **Safety**: Multiple layers of protection with confirmation dialogs
5. **Auditability**: Complete audit trail of all state changes
6. **Independence**: Backend operates independently of frontend
7. **Flexibility**: Pause/resume capability for temporary halts
8. **Recovery**: Graceful handling of service restarts

## Conclusion

These updates formalize the autonomous trading system's behavior, making explicit what was previously implicit or missing. The specification now clearly defines:

- How the system operates independently of the browser
- How users control the autonomous trading system
- What users see when they log in
- How state persists across sessions
- How the system handles different operational states

This provides a complete specification for implementing a truly autonomous trading system that operates reliably in the background while giving users full visibility and control.
