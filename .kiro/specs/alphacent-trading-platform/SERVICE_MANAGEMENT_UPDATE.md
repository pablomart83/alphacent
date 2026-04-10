# Service Management Update - Autonomous Trading System

**Date**: February 14, 2026  
**Purpose**: Ensure Start/Stop Autonomous Trading manages all required backend services (Ollama LLM)

## Summary

Updated the AlphaCent specification to ensure that the "Start Autonomous Trading" and "Stop Autonomous Trading" controls manage not just the trading logic, but also all required dependent services like the Ollama LLM service.

## Key Changes

### 1. Requirements Updates

#### Requirement 7: LLM Integration
Added 3 new acceptance criteria:
- 7.8: Verify Ollama is running when starting autonomous trading
- 7.9: Attempt to start Ollama if not accessible
- 7.10: Optionally stop Ollama when stopping trading (configurable)

#### Requirement 16: Web Application Architecture
Added 2 new acceptance criteria:
- 16.13: Backend manages dependent services lifecycle
- 16.14: Verify all services running before starting trading
- 16.15: Attempt to start services or provide instructions

#### NEW Requirement 16.1: Service Dependency Management
Complete new requirement with 10 acceptance criteria covering:
- Service health checking
- Automatic service startup
- Graceful degradation on failure
- Periodic health monitoring
- Dashboard service status display
- Manual service controls
- Service lifecycle logging

### 2. Design Document Updates

Added comprehensive "Service Dependency Management" section:

**Service Manager Class**:
```python
class ServiceManager:
    def check_all_services() -> Dict[str, ServiceStatus]
    def start_service(service_name: str) -> bool
    def stop_service(service_name: str) -> bool
    def ensure_services_running() -> Tuple[bool, List[str]]
```

**Service Lifecycle**:
- **On Start Trading**: Check Ollama → Start if needed → Wait 30s → Proceed or alert
- **During Trading**: Health check every 60s → Disable features if down → Auto-recover
- **On Stop Trading**: Optionally stop Ollama (configurable, default: leave running)

**Integration with State Manager**:
- Check services before ACTIVE transition
- Transition to PAUSED if services unavailable
- Alert user with clear instructions
- Disable strategy generation when Ollama down

**New API Endpoints**:
- `GET /system/services` - Get all service statuses
- `POST /system/services/:name/start` - Start a service
- `POST /system/services/:name/stop` - Stop a service
- `GET /system/services/:name/health` - Health check

**Dashboard Display**:
- Service status cards with health indicators
- Manual start/stop/restart buttons
- Error messages and impact warnings
- Real-time updates via WebSocket

### 3. Tasks Updates

#### New Backend Tasks

**Task 17.8.3: Implement service dependency management**
- Create ServiceManager class
- Implement Ollama health checking (localhost:11434)
- Add automatic service startup
- Implement periodic health checks (60s)
- Handle failures gracefully
- Add recovery logic
- Create service status endpoints

**Task 17.8.4: Integrate service checks with state transitions**
- Check Ollama before ACTIVE transition
- Transition to PAUSED if unavailable
- Alert user with instructions
- Disable strategy generation when down
- Re-enable when recovered

#### New Frontend Tasks

**Task 19.12.3: Implement Dependent Services Status Display**
- Display service status (Running/Stopped/Error)
- Show health indicators
- Add manual start/stop controls
- Show error messages
- Display feature impact
- Real-time WebSocket updates

## Service Management Flow

### Starting Autonomous Trading

```
User clicks "Start Autonomous Trading"
    │
    ▼
Check Ollama health (GET localhost:11434/api/tags)
    │
    ├─ Healthy ──────────────────────────────────┐
    │                                             │
    └─ Not Healthy                                │
        │                                         │
        ▼                                         │
    Attempt to start Ollama                       │
    (subprocess: "ollama serve")                  │
        │                                         │
        ├─ Success (within 30s) ─────────────────┤
        │                                         │
        └─ Failed                                 │
            │                                     │
            ▼                                     │
        Transition to PAUSED                      │
        Alert user:                               │
        "Ollama service unavailable.              │
         Please start manually:                   │
         $ ollama serve"                          │
            │                                     │
            └─────────────────────────────────────┤
                                                  │
                                                  ▼
                                    Transition to ACTIVE
                                    Start signal generation
```

### During Active Trading

```
Every 60 seconds:
    │
    ▼
Check Ollama health
    │
    ├─ Healthy ──────────────────────────────────┐
    │                                             │
    │                                             ▼
    │                                    Continue normally
    │
    └─ Not Healthy
        │
        ▼
    Log warning
    Disable strategy generation
    Maintain existing positions
    Continue other operations
        │
        ▼
    Attempt reconnection every 60s
        │
        ├─ Recovered ────────────────────────────┐
        │                                         │
        │                                         ▼
        │                                Log recovery
        │                                Re-enable strategy generation
        │
        └─ Still down
            │
            ▼
        Continue monitoring
```

### Stopping Autonomous Trading

```
User clicks "Stop Autonomous Trading"
    │
    ▼
Transition to STOPPED
Stop signal generation
Maintain positions
    │
    ▼
Check configuration: stop_dependent_services
    │
    ├─ true ─────────────────────────────────────┐
    │                                             │
    │                                             ▼
    │                                    Stop Ollama service
    │                                    Log: "Ollama stopped"
    │
    └─ false (default)
        │
        ▼
    Leave Ollama running
    Log: "Ollama left running for manual use"
```

## Configuration

### Service Configuration File

```python
# config/services.yaml

services:
  ollama:
    enabled: true
    endpoint: "http://localhost:11434"
    start_command: "ollama serve"
    health_check_endpoint: "/api/tags"
    health_check_interval: 60  # seconds
    startup_timeout: 30  # seconds
    stop_on_trading_stop: false  # Leave running by default
    auto_restart_on_failure: true
    max_restart_attempts: 3
```

### User Configuration Options

Users can configure service management behavior:

1. **Auto-start services**: Enable/disable automatic service startup
2. **Stop on trading stop**: Whether to stop services when stopping trading
3. **Health check interval**: How often to check service health
4. **Auto-restart**: Whether to automatically restart failed services

## Dashboard UI

### Service Status Card

```
┌─────────────────────────────────────────────┐
│          Dependent Services                 │
├─────────────────────────────────────────────┤
│                                             │
│  Ollama LLM Service                         │
│  Status: ● Running                          │
│  Endpoint: localhost:11434                  │
│  Last Check: 2 seconds ago                  │
│  [Restart] [Stop] [View Logs]               │
│                                             │
└─────────────────────────────────────────────┘
```

### Service Error State

```
┌─────────────────────────────────────────────┐
│  Ollama LLM Service                         │
│  Status: ● Stopped                          │
│  Error: Connection refused                  │
│  Last Check: 5 seconds ago                  │
│                                             │
│  [Start Service] [View Logs] [Help]         │
│                                             │
│  ⚠️ Impact:                                 │
│  • Strategy generation disabled             │
│  • Vibe-coding unavailable                  │
│  • Existing positions maintained            │
│                                             │
│  💡 To start manually:                      │
│  $ ollama serve                             │
└─────────────────────────────────────────────┘
```

## Benefits

1. **Seamless Experience**: Users don't need to manually manage Ollama
2. **Automatic Recovery**: System automatically recovers when services come back
3. **Graceful Degradation**: Trading continues with reduced features if Ollama down
4. **Clear Feedback**: Users see exactly what's wrong and how to fix it
5. **Flexible Configuration**: Users can customize service management behavior
6. **Complete Visibility**: Dashboard shows status of all services
7. **Manual Override**: Users can manually control services if needed

## Implementation Priority

### Phase 1: Core Service Management (Critical)
1. ServiceManager class implementation
2. Ollama health checking
3. Automatic startup on trading start
4. Integration with state transitions

### Phase 2: Monitoring and Recovery (High)
1. Periodic health checks
2. Automatic recovery logic
3. Service status API endpoints
4. Logging and audit trail

### Phase 3: Dashboard Integration (High)
1. Service status display
2. Manual controls
3. Error messages and help
4. Real-time WebSocket updates

### Phase 4: Configuration and Polish (Medium)
1. User configuration options
2. Service lifecycle preferences
3. Advanced troubleshooting tools
4. Documentation and help text

## Testing Scenarios

### Scenario 1: Ollama Already Running
1. User clicks "Start Trading"
2. System checks Ollama → Healthy
3. Transition to ACTIVE immediately
4. ✅ Expected: Trading starts normally

### Scenario 2: Ollama Not Running
1. User clicks "Start Trading"
2. System checks Ollama → Not healthy
3. System starts Ollama automatically
4. Wait for Ollama to become available
5. Transition to ACTIVE
6. ✅ Expected: Trading starts after brief delay

### Scenario 3: Ollama Cannot Start
1. User clicks "Start Trading"
2. System checks Ollama → Not healthy
3. System attempts to start Ollama → Fails
4. Transition to PAUSED
5. Alert user with instructions
6. ✅ Expected: Clear error message, manual instructions

### Scenario 4: Ollama Fails During Trading
1. Trading is ACTIVE
2. Ollama becomes unavailable
3. Health check detects failure
4. Disable strategy generation
5. Maintain existing positions
6. Continue monitoring
7. ✅ Expected: Graceful degradation, no crashes

### Scenario 5: Ollama Recovers
1. Trading is ACTIVE, Ollama down
2. Strategy generation disabled
3. Ollama comes back online
4. Health check detects recovery
5. Re-enable strategy generation
6. ✅ Expected: Automatic recovery, resume normal operation

### Scenario 6: Stop Trading with Ollama
1. Trading is ACTIVE
2. User clicks "Stop Trading"
3. Check configuration: stop_dependent_services = false
4. Stop trading, leave Ollama running
5. ✅ Expected: Ollama continues for manual use

## Conclusion

The specification now ensures that "Start/Stop Autonomous Trading" is a true master control that manages:
- ✅ Trading logic (signal generation, order execution)
- ✅ Dependent services (Ollama LLM)
- ✅ System state (ACTIVE, PAUSED, STOPPED)
- ✅ Service health monitoring
- ✅ Automatic recovery
- ✅ User notifications

Users get a seamless experience where starting trading "just works" - the system handles all the complexity of managing dependent services automatically.
