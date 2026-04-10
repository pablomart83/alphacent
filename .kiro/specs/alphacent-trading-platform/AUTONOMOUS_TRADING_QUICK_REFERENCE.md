# Autonomous Trading System - Quick Reference

## For Developers

### System States

| State | Description | Signal Generation | Positions | User Action Required |
|-------|-------------|-------------------|-----------|---------------------|
| **ACTIVE** | Trading system running | ✅ Yes | Open | None |
| **PAUSED** | Temporarily halted | ❌ No | Maintained | Resume or Stop |
| **STOPPED** | Explicitly stopped | ❌ No | Maintained | Start |
| **EMERGENCY_HALT** | Kill Switch activated | ❌ No | Closed | Manual Reset |

### State Transitions

```
STOPPED --[start]--> ACTIVE
ACTIVE --[pause]--> PAUSED
PAUSED --[resume]--> ACTIVE
PAUSED --[stop]--> STOPPED
ACTIVE --[stop]--> STOPPED
ACTIVE --[kill_switch]--> EMERGENCY_HALT
EMERGENCY_HALT --[reset]--> STOPPED
```

### API Endpoints

#### System State Endpoints

#### Get System Status
```http
GET /system/status

Response:
{
  "state": "ACTIVE",
  "timestamp": "2026-02-14T10:30:00Z",
  "active_strategies": 3,
  "open_positions": 5,
  "reason": "User started trading",
  "uptime_seconds": 3600
}
```

#### Start Trading
```http
POST /system/start
Content-Type: application/json

{
  "confirmation": true
}

Response:
{
  "state": "ACTIVE",
  "message": "Autonomous trading started"
}
```

#### Pause Trading
```http
POST /system/pause
Content-Type: application/json

{
  "confirmation": true
}

Response:
{
  "state": "PAUSED",
  "message": "Autonomous trading paused"
}
```

#### Stop Trading
```http
POST /system/stop
Content-Type: application/json

{
  "confirmation": true
}

Response:
{
  "state": "STOPPED",
  "message": "Autonomous trading stopped"
}
```

#### Resume Trading
```http
POST /system/resume
Content-Type: application/json

{
  "confirmation": true
}

Response:
{
  "state": "ACTIVE",
  "message": "Autonomous trading resumed"
}
```

#### Reset from Emergency Halt
```http
POST /system/reset
Content-Type: application/json

{
  "confirmation": true,
  "acknowledge_risks": true
}

Response:
{
  "state": "STOPPED",
  "message": "System reset, ready to start"
}
```

}
```

#### Service Management Endpoints

#### Get All Services Status
```http
GET /system/services

Response:
{
  "ollama": {
    "name": "Ollama LLM",
    "is_healthy": true,
    "endpoint": "http://localhost:11434",
    "last_check": "2026-02-14T10:30:00Z",
    "error_message": null
  }
}
```

#### Start Service
```http
POST /system/services/ollama/start

Response:
{
  "success": true,
  "message": "Service ollama started successfully"
}
```

#### Stop Service
```http
POST /system/services/ollama/stop

Response:
{
  "success": true,
  "message": "Service ollama stopped"
}
```

#### Health Check Service
```http
GET /system/services/ollama/health

Response:
{
  "is_healthy": true,
  "last_check": "2026-02-14T10:30:00Z",
  "error_message": null
}
```

### Database Schema

#### system_state Table
```sql
CREATE TABLE system_state (
    id INTEGER PRIMARY KEY,
    state TEXT NOT NULL,  -- ACTIVE, PAUSED, STOPPED, EMERGENCY_HALT
    timestamp DATETIME NOT NULL,
    reason TEXT,
    initiated_by TEXT,
    active_strategies_count INTEGER,
    open_positions_count INTEGER,
    uptime_seconds INTEGER,
    last_signal_generated DATETIME,
    last_order_executed DATETIME
);
```

#### state_history Table (Audit Trail)
```sql
CREATE TABLE state_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    previous_state TEXT NOT NULL,
    new_state TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    reason TEXT,
    initiated_by TEXT,
    active_strategies_count INTEGER,
    open_positions_count INTEGER
);
```

#### service_status Table
```sql
CREATE TABLE service_status (
    id INTEGER PRIMARY KEY,
    service_name TEXT NOT NULL,
    is_healthy BOOLEAN NOT NULL,
    endpoint TEXT NOT NULL,
    last_check DATETIME NOT NULL,
    error_message TEXT
);
```

#### service_events Table (Audit Trail)
```sql
CREATE TABLE service_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_name TEXT NOT NULL,
    event_type TEXT NOT NULL,  -- START, STOP, HEALTH_CHECK_FAILED, RECOVERED
    timestamp DATETIME NOT NULL,
    details TEXT
);
```

### Python Implementation

#### State Manager Class
```python
class SystemStateManager:
    """Manages autonomous trading system state."""
    
    def __init__(self, db: Database):
        self.db = db
        self.current_state = self._load_state()
    
    def _load_state(self) -> SystemState:
        """Load state from database."""
        state = self.db.get_system_state()
        if state is None:
            # Default to STOPPED on first run
            state = SystemState(
                state=SystemStateEnum.STOPPED,
                timestamp=datetime.now(),
                reason="Initial state",
                initiated_by=None,
                active_strategies_count=0,
                open_positions_count=0,
                uptime_seconds=0
            )
            self.db.save_system_state(state)
        return state
    
    def transition_to(self, new_state: SystemStateEnum, 
                     reason: str, user: Optional[str] = None):
        """Transition to new state."""
        old_state = self.current_state.state
        
        # Validate transition
        if not self._is_valid_transition(old_state, new_state):
            raise ValueError(
                f"Invalid transition: {old_state.value} -> {new_state.value}"
            )
        
        # Create new state
        self.current_state = SystemState(
            state=new_state,
            timestamp=datetime.now(),
            reason=reason,
            initiated_by=user,
            active_strategies_count=self._count_active_strategies(),
            open_positions_count=self._count_open_positions(),
            uptime_seconds=self._calculate_uptime()
        )
        
        # Save to database
        self.db.save_system_state(self.current_state)
        
        # Log to audit trail
        self.db.log_state_transition(old_state, new_state, reason, user)
        
        logger.info(
            f"State transition: {old_state.value} -> {new_state.value} "
            f"(reason: {reason}, user: {user})"
        )
    
    def _is_valid_transition(self, old: SystemStateEnum, 
                            new: SystemStateEnum) -> bool:
        """Check if state transition is valid."""
        valid_transitions = {
            SystemStateEnum.STOPPED: [SystemStateEnum.ACTIVE],
            SystemStateEnum.ACTIVE: [
                SystemStateEnum.PAUSED,
                SystemStateEnum.STOPPED,
                SystemStateEnum.EMERGENCY_HALT
            ],
            SystemStateEnum.PAUSED: [
                SystemStateEnum.ACTIVE,
                SystemStateEnum.STOPPED
            ],
            SystemStateEnum.EMERGENCY_HALT: [SystemStateEnum.STOPPED]
        }
        return new in valid_transitions.get(old, [])
    
    def get_current_state(self) -> SystemState:
        """Get current system state."""
        return self.current_state
    
    def is_active(self) -> bool:
        """Check if system is in ACTIVE state."""
        return self.current_state.state == SystemStateEnum.ACTIVE
```

#### Service Manager Class
```python
class ServiceManager:
    """Manages dependent service lifecycle."""
    
    def __init__(self):
        self.services = {
            'ollama': OllamaService(
                endpoint='http://localhost:11434',
                start_command='ollama serve',
                health_check_interval=60
            )
        }
    
    def check_all_services(self) -> Dict[str, ServiceStatus]:
        """Check status of all dependent services."""
        status = {}
        for name, service in self.services.items():
            status[name] = service.check_health()
        return status
    
    def start_service(self, service_name: str) -> bool:
        """Start a dependent service."""
        service = self.services.get(service_name)
        if not service:
            raise ValueError(f"Unknown service: {service_name}")
        
        try:
            service.start()
            # Wait for service to become available
            for _ in range(30):
                if service.check_health().is_healthy:
                    logger.info(f"Service {service_name} started successfully")
                    return True
                time.sleep(1)
            
            logger.error(f"Service {service_name} failed to start within timeout")
            return False
        
        except Exception as e:
            logger.error(f"Error starting service {service_name}: {e}")
            return False
    
    def ensure_services_running(self) -> Tuple[bool, List[str]]:
        """Ensure all required services are running."""
        failed_services = []
        
        for name, service in self.services.items():
            if not service.check_health().is_healthy:
                logger.warning(f"Service {name} not running, attempting to start")
                if not self.start_service(name):
                    failed_services.append(name)
        
        return len(failed_services) == 0, failed_services
```

#### Check System State Before Signal Generation
```python
def generate_signals(self, strategy: Strategy) -> List[TradingSignal]:
    """Generate trading signals for a strategy."""
    
    # Check system state
    system_state = self.state_manager.get_current_state()
    
    if system_state.state != SystemStateEnum.ACTIVE:
        logger.info(
            f"Skipping signal generation for {strategy.name}: "
            f"system state is {system_state.state.value}"
        )
        return []
    
    # Check if Ollama is available
    ollama_status = self.service_manager.check_service('ollama')
    if not ollama_status.is_healthy:
        logger.warning(
            f"Skipping signal generation for {strategy.name}: "
            f"Ollama service unavailable"
        )
        return []
    
    # Generate signals
    signals = self._generate_signals_internal(strategy)
    return signals
```

### React/TypeScript Implementation

#### Service Status Hook
```typescript
interface ServiceStatus {
  name: string;
  isHealthy: boolean;
  endpoint: string;
  lastCheck: string;
  errorMessage?: string;
}

function useServiceStatus() {
  const [services, setServices] = useState<Record<string, ServiceStatus>>({});
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    // Fetch initial status
    fetchServiceStatus();
    
    // Subscribe to WebSocket updates
    const ws = new WebSocket('ws://localhost:8000/ws');
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'service_status_change') {
        setServices(prev => ({
          ...prev,
          [data.service]: data.status
        }));
      }
    };
    
    return () => ws.close();
  }, []);
  
  const fetchServiceStatus = async () => {
    const response = await fetch('/system/services');
    const data = await response.json();
    setServices(data);
    setLoading(false);
  };
  
  const startService = async (serviceName: string) => {
    await fetch(`/system/services/${serviceName}/start`, {
      method: 'POST'
    });
  };
  
  const stopService = async (serviceName: string) => {
    await fetch(`/system/services/${serviceName}/stop`, {
      method: 'POST'
    });
  };
  
  return { services, loading, startService, stopService };
}
```

#### System State Hook
```typescript
interface SystemState {
  state: 'ACTIVE' | 'PAUSED' | 'STOPPED' | 'EMERGENCY_HALT';
  timestamp: string;
  reason: string;
  activeStrategies: number;
  openPositions: number;
  uptimeSeconds: number;
}

function useSystemState() {
  const [state, setState] = useState<SystemState | null>(null);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    // Fetch initial state
    fetchSystemState();
    
    // Subscribe to WebSocket updates
    const ws = new WebSocket('ws://localhost:8000/ws');
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'system_state_change') {
        setState(data.state);
      }
    };
    
    return () => ws.close();
  }, []);
  
  const fetchSystemState = async () => {
    const response = await fetch('/system/status');
    const data = await response.json();
    setState(data);
    setLoading(false);
  };
  
  const startTrading = async () => {
    await fetch('/system/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmation: true })
    });
  };
  
  const pauseTrading = async () => {
    await fetch('/system/pause', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmation: true })
    });
  };
  
  const stopTrading = async () => {
    await fetch('/system/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmation: true })
    });
  };
  
  return { state, loading, startTrading, pauseTrading, stopTrading };
}
```

#### Control Panel Component
```typescript
function ControlPanel() {
  const { state, startTrading, pauseTrading, stopTrading } = useSystemState();
  
  const getStatusColor = () => {
    switch (state?.state) {
      case 'ACTIVE': return 'green';
      case 'PAUSED': return 'yellow';
      case 'STOPPED': return 'red';
      case 'EMERGENCY_HALT': return 'darkred';
      default: return 'gray';
    }
  };
  
  return (
    <div className="control-panel">
      <div className="status-indicator" style={{ color: getStatusColor() }}>
        ● {state?.state}
      </div>
      
      <div className="controls">
        {state?.state === 'STOPPED' && (
          <button onClick={startTrading}>Start Trading</button>
        )}
        
        {state?.state === 'ACTIVE' && (
          <>
            <button onClick={pauseTrading}>Pause Trading</button>
            <button onClick={stopTrading}>Stop Trading</button>
          </>
        )}
        
        {state?.state === 'PAUSED' && (
          <>
            <button onClick={startTrading}>Resume Trading</button>
            <button onClick={stopTrading}>Stop Trading</button>
          </>
        )}
      </div>
      
      <div className="status-info">
        <p>Active Strategies: {state?.activeStrategies}</p>
        <p>Open Positions: {state?.openPositions}</p>
        <p>Uptime: {formatUptime(state?.uptimeSeconds)}</p>
      </div>
    </div>
  );
}
```

}
```

#### Services Status Component
```typescript
function ServicesStatus() {
  const { services, startService, stopService } = useServiceStatus();
  
  const getStatusColor = (isHealthy: boolean) => {
    return isHealthy ? 'green' : 'red';
  };
  
  return (
    <div className="services-status">
      <h3>Dependent Services</h3>
      
      {Object.entries(services).map(([name, status]) => (
        <div key={name} className="service-card">
          <div className="service-header">
            <span className="service-name">{status.name}</span>
            <span 
              className="status-indicator" 
              style={{ color: getStatusColor(status.isHealthy) }}
            >
              ● {status.isHealthy ? 'Running' : 'Stopped'}
            </span>
          </div>
          
          <div className="service-details">
            <p>Endpoint: {status.endpoint}</p>
            <p>Last Check: {formatTime(status.lastCheck)}</p>
            {status.errorMessage && (
              <p className="error">Error: {status.errorMessage}</p>
            )}
          </div>
          
          <div className="service-controls">
            {!status.isHealthy && (
              <button onClick={() => startService(name)}>
                Start Service
              </button>
            )}
            {status.isHealthy && (
              <button onClick={() => stopService(name)}>
                Stop Service
              </button>
            )}
          </div>
          
          {!status.isHealthy && (
            <div className="service-impact">
              ⚠️ Strategy generation disabled
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
```

### Testing Checklist

#### System State Tests
- [ ] Backend continues running when browser closed
- [ ] State persists after backend restart
- [ ] Signal generation stops when state != ACTIVE
- [ ] WebSocket pushes state changes to clients
- [ ] Dashboard shows correct state on login
- [ ] Confirmation dialogs work for all state changes
- [ ] Invalid state transitions are rejected
- [ ] Audit trail logs all state changes
- [ ] Emergency halt requires manual reset
- [ ] Multiple browser tabs show same state

#### Service Management Tests
- [ ] Ollama health check works correctly
- [ ] Automatic Ollama startup on trading start
- [ ] Transition to PAUSED if Ollama unavailable
- [ ] User alert when services unavailable
- [ ] Strategy generation disabled when Ollama down
- [ ] Automatic recovery when Ollama comes back
- [ ] Periodic health checks run every 60 seconds
- [ ] Manual service start/stop from Dashboard
- [ ] Service status displayed correctly
- [ ] WebSocket pushes service status changes

### Common Issues

#### Issue: Backend stops when browser closes
**Solution**: Ensure backend runs as independent service, not tied to frontend process.

#### Issue: State not persisting across restarts
**Solution**: Verify database connection and state save/load logic.

#### Issue: Signals generated when state is PAUSED
**Solution**: Add state check at beginning of signal generation function.

#### Issue: Dashboard shows stale state
**Solution**: Ensure WebSocket connection is established and state updates are pushed.

#### Issue: Can't transition from EMERGENCY_HALT
**Solution**: Implement reset endpoint that transitions to STOPPED first.

#### Issue: Ollama not starting automatically
**Solution**: 
1. Check if Ollama is installed (`ollama --version`)
2. Verify start command in configuration
3. Check system permissions for subprocess execution
4. Review logs for startup errors
5. Try manual start: `ollama serve`

#### Issue: Strategy generation disabled despite Ollama running
**Solution**:
1. Check Ollama endpoint (http://localhost:11434)
2. Verify health check: `curl http://localhost:11434/api/tags`
3. Check firewall settings
4. Review service status in Dashboard
5. Manually restart Ollama service from Dashboard

### Performance Considerations

- State checks are fast (in-memory)
- Database writes are async (don't block signal generation)
- WebSocket updates are batched (max 1 per second)
- State history table should be indexed on timestamp
- Consider archiving old state history (keep last 90 days)

### Security Considerations

- All state change endpoints require authentication
- Confirmation required for all state changes
- Audit trail cannot be modified (append-only)
- Emergency halt cannot be bypassed
- Rate limit state change endpoints (max 10 per minute)

## For Users

### Quick Start

1. **Login** to Dashboard at http://localhost:3000
2. **Check Status** - See current system state (should be STOPPED initially)
3. **Start Trading** - Click "Start Autonomous Trading" button
4. **Monitor** - Watch strategies generate signals and execute trades
5. **Pause/Stop** - Use controls to pause or stop trading as needed

### What Happens When You Close Browser?

✅ **Backend continues running**  
✅ **Strategies keep generating signals**  
✅ **Trades continue to execute**  
✅ **Positions are maintained**  
✅ **Performance is tracked**

When you log back in, you'll see:
- Current system status
- All trades executed while you were away
- Updated performance metrics
- Current positions

### Emergency Controls

- **Pause**: Temporarily stop signal generation, keep positions
- **Stop**: Stop trading, keep positions, requires restart
- **Kill Switch**: Emergency halt, close all positions immediately

### Best Practices

1. **Start in Demo Mode** - Test strategies with paper trading first
2. **Monitor Regularly** - Check performance and positions daily
3. **Use Pause for Breaks** - Pause instead of stop for short breaks
4. **Review Before Restart** - Check logs and performance before restarting
5. **Set Risk Limits** - Configure appropriate risk parameters
6. **Enable Circuit Breaker** - Let system auto-halt on excessive losses
