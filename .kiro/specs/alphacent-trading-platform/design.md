# Design Document: AlphaCent Trading Platform

## Overview

AlphaCent is a local web-based autonomous trading platform consisting of a Python backend service and React frontend UI, both running on localhost. The platform connects exclusively to eToro via their Public API for trading stocks, ETFs, and cryptocurrencies. The architecture follows a clean separation between the backend (trading logic, API integration, data persistence) and frontend (visualization, user interaction), communicating via REST API and WebSocket connections.

The system implements a strategy-driven trading approach where the Strategy Engine generates and manages trading strategies (using local Ollama LLM), the Risk Manager enforces safety constraints, and the Order Executor handles trade execution via eToro API. Market data flows from eToro API (primary) with Yahoo Finance as fallback, cached locally for performance.

Key design principles:
- **Local-first**: All processing and data storage on user's machine, zero cloud dependencies
- **Safety-first**: Multiple layers of risk management (position limits, circuit breakers, kill switch)
- **Strategy-driven**: AI-powered strategy generation with rigorous backtesting before deployment
- **Real-time**: WebSocket-based live updates for market data and portfolio changes
- **eToro-native**: Leverages eToro-specific features (social insights, Smart Portfolios, vibe-coding)

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser (localhost:3000)                 │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              React Frontend UI                        │  │
│  │  - Dashboard  - Portfolio View  - Strategy Manager    │  │
│  │  - Social Insights  - Vibe Coding  - Settings         │  │
│  └───────────────────────────────────────────────────────┘  │
│                    │                    │                    │
│              REST API              WebSocket                 │
└────────────────────┼────────────────────┼───────────────────┘
                     │                    │
┌────────────────────┼────────────────────┼───────────────────┐
│                    │                    │                    │
│              Backend Service (localhost:8000)               │
│  ┌─────────────────┴────────────────────┴────────────────┐  │
│  │              FastAPI Server                           │  │
│  │  - REST Endpoints  - WebSocket Handler  - Auth       │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                  │
│  ┌────────────────────────┴──────────────────────────────┐  │
│  │              Core Trading Engine                      │  │
│  │                                                        │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │  │
│  │  │   Strategy   │  │     Risk     │  │   Order    │  │  │
│  │  │    Engine    │──│   Manager    │──│  Executor  │  │  │
│  │  └──────────────┘  └──────────────┘  └────────────┘  │  │
│  │         │                                     │        │  │
│  │  ┌──────┴──────┐                       ┌─────┴─────┐  │  │
│  │  │ LLM Service │                       │  eToro    │  │  │
│  │  │  (Ollama)   │                       │ API Client│  │  │
│  │  └─────────────┘                       └─────┬─────┘  │  │
│  │                                              │        │  │
│  │  ┌──────────────────────────────────────────┴─────┐  │  │
│  │  │         Market Data Manager                    │  │  │
│  │  │  - eToro API (primary)  - Yahoo Finance (fallback) │
│  │  └────────────────────────────────────────────────┘  │  │
│  │                                                        │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │         Data Persistence Layer                 │  │  │
│  │  │  - SQLite DB  - Config Files  - Backups       │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
                           │
                           │ HTTPS
                           ▼
                  ┌─────────────────┐
                  │   eToro API     │
                  │  (Public API)   │
                  └─────────────────┘
```

### Component Responsibilities

**Frontend UI (React + TypeScript)**
- Renders dashboard with real-time portfolio, strategies, and market data
- Handles user interactions (strategy management, kill switch, settings)
- Establishes WebSocket connection for live updates
- Implements vibe-coding interface for natural language strategy creation
- Displays social insights and Smart Portfolio data

**Backend Service (Python + FastAPI)**
- Exposes REST API for frontend operations
- Manages WebSocket connections for real-time data push
- Orchestrates trading engine components
- Handles authentication and session management
- Persists data to SQLite database

**Strategy Engine**
- Generates trading strategies using Ollama LLM
- Backtests strategies using vectorbt with historical data
- Manages strategy lifecycle (PROPOSED → BACKTESTED → DEMO → LIVE → RETIRED)
- Generates trading signals based on active strategies
- Monitors strategy performance and triggers retirement

**Risk Manager**
- Validates all trading signals against risk parameters
- Enforces position size limits, exposure limits, daily loss limits
- Calculates position sizing based on account balance and risk percentage
- Activates circuit breakers when loss thresholds exceeded
- Executes kill switch (close all positions, halt trading)

**Order Executor**
- Constructs orders from validated trading signals
- Submits orders to eToro API
- Tracks order status until filled/cancelled
- Updates position records on fills
- Handles order failures and retries
- Attaches stop loss and take profit orders

**Market Data Manager**
- Fetches real-time and historical market data from eToro API
- Falls back to Yahoo Finance if eToro data unavailable
- Validates data integrity
- Caches data locally with expiration
- Provides unified interface for data access

**eToro API Client**
- Handles authentication (API key-based)
- Manages API rate limiting and retries
- Provides methods for market data, account data, order operations
- Supports demo and live account modes
- Retrieves social insights and Smart Portfolio data

**LLM Service**
- Connects to local Ollama instance
- Formats prompts for strategy generation
- Parses LLM responses into structured strategy definitions
- Validates generated strategies
- Supports vibe-coding (natural language to strategy translation)

**Data Persistence Layer**
- SQLite database for strategies, orders, positions, market data
- Configuration files for API credentials and settings
- Automatic backups at regular intervals
- Transaction logging for audit trail

## Components and Interfaces

### eToro API Client

```python
class EToroAPIClient:
    """Client for eToro Public API with authentication and rate limiting."""
    
    def __init__(self, public_key: str, user_key: str, mode: TradingMode):
        """Initialize with API credentials and trading mode (demo/live)."""
        
    def authenticate(self) -> AuthToken:
        """Authenticate with eToro API and return auth token."""
        
    def get_account_info(self) -> AccountInfo:
        """Retrieve account balance, buying power, margin, positions."""
        
    def get_market_data(self, symbol: str, timeframe: str) -> MarketData:
        """Fetch real-time or historical market data for symbol."""
        
    def place_order(self, order: OrderRequest) -> OrderResponse:
        """Submit order to eToro (market, limit, stop loss, take profit)."""
        
    def get_order_status(self, order_id: str) -> OrderStatus:
        """Check status of submitted order."""
        
    def cancel_order(self, order_id: str) -> bool:
        """Cancel pending order."""
        
    def get_positions(self) -> List[Position]:
        """Retrieve all open positions."""
        
    def close_position(self, position_id: str) -> bool:
        """Close an open position."""
        
    def get_social_insights(self, symbol: str) -> SocialInsights:
        """Retrieve social sentiment, trending status, Pro Investor activity."""
        
    def get_smart_portfolios(self) -> List[SmartPortfolio]:
        """Retrieve available Smart Portfolios with composition and performance."""
```

### Market Data Manager

```python
class MarketDataManager:
    """Manages market data from eToro API with Yahoo Finance fallback."""
    
    def __init__(self, etoro_client: EToroAPIClient, cache_ttl: int = 60):
        """Initialize with eToro client and cache TTL in seconds."""
        
    def get_quote(self, symbol: str) -> Quote:
        """Get real-time quote (price, bid, ask, volume)."""
        
    def get_historical_data(self, symbol: str, start: datetime, end: datetime, 
                           interval: str = "1d") -> DataFrame:
        """Get historical OHLCV data for backtesting."""
        
    def validate_data(self, data: MarketData) -> bool:
        """Validate data integrity (no nulls, reasonable values, chronological)."""
        
    def cache_data(self, symbol: str, data: MarketData):
        """Store data in local cache with expiration."""
        
    def get_cached_data(self, symbol: str) -> Optional[MarketData]:
        """Retrieve cached data if not expired."""
```

### Strategy Engine

```python
class StrategyEngine:
    """Generates, backtests, and manages trading strategies to maximize returns."""
    
    def __init__(self, llm_service: LLMService, market_data: MarketDataManager):
        """Initialize with LLM service and market data manager."""
        
    def generate_strategy(self, prompt: str, constraints: Dict) -> Strategy:
        """Use LLM to generate strategy from natural language prompt."""
        
    def backtest_strategy(self, strategy: Strategy, start: datetime, 
                         end: datetime) -> BacktestResults:
        """Backtest strategy using vectorbt with historical data."""
        
    def activate_strategy(self, strategy_id: str, mode: TradingMode):
        """Activate strategy for demo or live trading."""
        
    def deactivate_strategy(self, strategy_id: str):
        """Deactivate strategy (stop generating signals)."""
        
    def generate_signals(self, strategy: Strategy) -> List[TradingSignal]:
        """Generate trading signals based on strategy rules and current market data."""
        
    def monitor_performance(self, strategy_id: str) -> PerformanceMetrics:
        """Calculate strategy performance metrics (returns, Sharpe, drawdown)."""
        
    def retire_strategy(self, strategy_id: str, reason: str):
        """Retire underperforming strategy and close positions."""
        
    def rebalance_portfolio(self, target_allocations: Dict[str, float]) -> List[Order]:
        """Rebalance portfolio to match target allocations across strategies/positions."""
        
    def optimize_allocations(self, strategies: List[Strategy]) -> Dict[str, float]:
        """Calculate optimal capital allocation across strategies based on performance."""
```

### Risk Manager

```python
class RiskManager:
    """Enforces risk limits and circuit breakers."""
    
    def __init__(self, config: RiskConfig):
        """Initialize with risk configuration (limits, thresholds)."""
        
    def validate_signal(self, signal: TradingSignal, account: AccountInfo) -> ValidationResult:
        """Validate signal against risk parameters."""
        
    def calculate_position_size(self, signal: TradingSignal, account: AccountInfo) -> float:
        """Calculate position size based on account balance and risk percentage."""
        
    def check_circuit_breaker(self, account: AccountInfo, daily_pnl: float) -> bool:
        """Check if circuit breaker should activate (daily loss limit exceeded)."""
        
    def activate_circuit_breaker(self):
        """Halt all trading, prevent new positions."""
        
    def execute_kill_switch(self, executor: OrderExecutor):
        """Emergency: close all positions, halt trading."""
        
    def check_position_limits(self, symbol: str, quantity: float, 
                             positions: List[Position]) -> bool:
        """Check if new position would exceed limits."""
        
    def check_exposure_limits(self, positions: List[Position], 
                             account: AccountInfo) -> bool:
        """Check if total exposure within limits."""
```

### Order Executor

```python
class OrderExecutor:
    """Manages order lifecycle via eToro API."""
    
    def __init__(self, etoro_client: EToroAPIClient, market_hours: MarketHoursManager):
        """Initialize with eToro client and market hours manager."""
        
    def execute_signal(self, signal: TradingSignal, position_size: float) -> Order:
        """Create and submit order from validated signal."""
        
    def track_order(self, order_id: str) -> OrderStatus:
        """Monitor order status until filled/cancelled."""
        
    def handle_fill(self, order: Order, fill: Fill):
        """Update position records when order filled."""
        
    def attach_stop_loss(self, position: Position, stop_price: float):
        """Attach stop loss order to position."""
        
    def attach_take_profit(self, position: Position, target_price: float):
        """Attach take profit order to position."""
        
    def close_position(self, position_id: str) -> Order:
        """Create market order to close position."""
        
    def close_all_positions(self) -> List[Order]:
        """Close all open positions (for kill switch)."""
        
    def handle_order_failure(self, order: Order, error: Exception):
        """Log failure, retry if appropriate, notify user."""
```

### LLM Service

```python
class LLMService:
    """Interface to local Ollama LLM for strategy generation."""
    
    def __init__(self, model: str = "qwen2.5-coder:7b", base_url: str = "http://localhost:11434"):
        """Initialize with Ollama model and endpoint."""
        
    def generate_strategy(self, prompt: str, market_context: Dict) -> StrategyDefinition:
        """Generate trading strategy from natural language prompt."""
        
    def parse_response(self, response: str) -> StrategyDefinition:
        """Parse LLM response into structured strategy definition."""
        
    def validate_strategy(self, strategy: StrategyDefinition) -> ValidationResult:
        """Validate strategy completeness and correctness."""
        
    def translate_vibe_code(self, natural_language: str) -> TradingCommand:
        """Translate natural language trading command to executable action."""
```

## Return Maximization and Portfolio Optimization

### Strategy-Based Return Maximization

AlphaCent maximizes returns through a multi-strategy approach where the Strategy Engine continuously:

1. **Generates new strategies** using LLM based on market conditions and historical performance
2. **Backtests rigorously** using vectorbt with historical data to validate effectiveness
3. **Deploys incrementally** through Demo → Live progression to minimize risk
4. **Monitors performance** in real-time and retires underperforming strategies
5. **Optimizes capital allocation** across active strategies based on risk-adjusted returns

### Capital Allocation Optimization

The Strategy Engine uses a performance-weighted allocation approach:

```python
def optimize_allocations(strategies: List[Strategy]) -> Dict[str, float]:
    """
    Calculate optimal capital allocation using Sharpe ratio weighting.
    
    For each strategy:
    - Calculate Sharpe ratio from recent performance
    - Weight allocation proportional to Sharpe ratio
    - Apply minimum/maximum allocation constraints
    - Ensure total allocation = 100%
    """
    sharpe_ratios = {s.id: calculate_sharpe(s) for s in strategies}
    total_sharpe = sum(max(0, sr) for sr in sharpe_ratios.values())
    
    allocations = {}
    for strategy in strategies:
        sharpe = max(0, sharpe_ratios[strategy.id])
        allocation = sharpe / total_sharpe if total_sharpe > 0 else 1.0 / len(strategies)
        # Apply constraints
        allocation = max(MIN_ALLOCATION, min(MAX_ALLOCATION, allocation))
        allocations[strategy.id] = allocation
    
    # Normalize to 100%
    total = sum(allocations.values())
    return {sid: alloc / total for sid, alloc in allocations.items()}
```

### Automatic Portfolio Rebalancing

The platform performs automatic rebalancing to maintain optimal allocations:

**Rebalancing Triggers**:
- Scheduled: Daily at market open
- Threshold-based: When any strategy allocation drifts >5% from target
- Event-based: When strategy is activated, deactivated, or retired

**Rebalancing Process**:
1. Calculate current allocations across all strategies
2. Calculate target allocations using optimization algorithm
3. Determine required trades to reach targets
4. Validate trades through Risk Manager
5. Execute rebalancing orders via Order Executor
6. Log rebalancing activity and results

**Rebalancing Constraints**:
- Minimum trade size: $100 or 1% of position (whichever is larger)
- Maximum rebalancing frequency: Once per day per strategy
- Respect risk limits during rebalancing
- Avoid rebalancing during circuit breaker activation

```python
def rebalance_portfolio(target_allocations: Dict[str, float]) -> List[Order]:
    """
    Rebalance portfolio to match target allocations.
    
    1. Get current positions and account balance
    2. Calculate current allocations
    3. Determine trades needed: target_value - current_value
    4. Create orders for each required trade
    5. Validate through Risk Manager
    6. Return list of rebalancing orders
    """
    account = get_account_info()
    positions = get_all_positions()
    current_allocations = calculate_current_allocations(positions, account)
    
    orders = []
    for strategy_id, target_pct in target_allocations.items():
        current_pct = current_allocations.get(strategy_id, 0.0)
        drift = abs(target_pct - current_pct)
        
        if drift > REBALANCE_THRESHOLD:
            target_value = account.balance * target_pct
            current_value = account.balance * current_pct
            trade_value = target_value - current_value
            
            if abs(trade_value) >= MIN_TRADE_SIZE:
                order = create_rebalancing_order(strategy_id, trade_value)
                if risk_manager.validate_order(order):
                    orders.append(order)
    
    return orders
```

### Kill Switch Implementation

The Kill Switch provides emergency shutdown capability:

**Activation Methods**:
1. **Manual**: User clicks "Kill Switch" button in Dashboard (requires confirmation)
2. **Automatic**: Maximum drawdown threshold exceeded (default 10%)

**Kill Switch Actions** (executed in order):
1. Set global flag: `kill_switch_active = True`
2. Stop all strategy signal generation
3. Cancel all pending orders
4. Close all open positions at market price
5. Disconnect from eToro API
6. Log all actions with timestamps
7. Notify user via Dashboard with summary

**Kill Switch Reset**:
- Manual reset only (no automatic reset)
- User must review logs and confirm understanding
- Requires re-authentication with eToro API
- Strategies remain deactivated until manually re-enabled

```python
def execute_kill_switch(reason: str):
    """
    Emergency shutdown: close all positions and halt trading.
    
    This is a destructive operation that cannot be undone.
    All positions will be closed at market price.
    """
    logger.critical(f"KILL SWITCH ACTIVATED: {reason}")
    
    # Set global flag
    global_state.kill_switch_active = True
    
    # Stop strategy signal generation
    strategy_engine.deactivate_all_strategies()
    
    # Cancel pending orders
    pending_orders = order_executor.get_pending_orders()
    for order in pending_orders:
        order_executor.cancel_order(order.id)
        logger.info(f"Cancelled order {order.id}")
    
    # Close all positions
    positions = order_executor.get_all_positions()
    for position in positions:
        close_order = order_executor.close_position(position.id)
        logger.info(f"Closed position {position.id}: {position.symbol} {position.quantity} @ market")
    
    # Disconnect API
    etoro_client.disconnect()
    
    # Notify user
    dashboard.send_notification(
        severity="CRITICAL",
        title="Kill Switch Activated",
        message=f"All positions closed. Reason: {reason}. {len(positions)} positions closed, {len(pending_orders)} orders cancelled."
    )
    
    logger.critical(f"KILL SWITCH COMPLETE: {len(positions)} positions closed, {len(pending_orders)} orders cancelled")
```

### Performance Monitoring and Strategy Retirement

To maximize returns, the platform continuously monitors strategy performance and retires underperformers:

**Retirement Triggers**:
- Sharpe ratio < 0.5 for 30 consecutive days
- Maximum drawdown > 15%
- Win rate < 40% over 50+ trades
- Negative returns for 60 consecutive days
- Manual retirement by user

**Retirement Process**:
1. Mark strategy status as RETIRED
2. Stop generating new signals
3. Close all positions opened by this strategy
4. Calculate final performance metrics
5. Log retirement reason and metrics
6. Archive strategy for historical analysis
7. Reallocate capital to remaining strategies

This continuous optimization ensures capital is always allocated to the best-performing strategies, maximizing overall returns while managing risk.

## Autonomous Trading State Management

The platform maintains a global autonomous trading state that persists across browser sessions and user logins, ensuring the backend service operates independently of the frontend UI.

### Trading System States

**ACTIVE**
- All enabled strategies generate signals and execute trades
- Risk Manager validates all signals
- Order Executor submits orders to eToro API
- Market data updates continuously
- Performance monitoring active
- Portfolio rebalancing scheduled

**PAUSED**
- Signal generation halted for all strategies
- Existing positions maintained (not closed)
- Market data updates continue
- Performance monitoring continues
- No new orders submitted
- User can resume or stop trading

**STOPPED**
- All signal generation halted
- Existing positions maintained (not closed)
- Market data updates continue
- Performance monitoring continues
- Similar to PAUSED but requires explicit restart
- Used for maintenance or extended breaks

**EMERGENCY_HALT** (Kill Switch or Circuit Breaker)
- All signal generation halted immediately
- All pending orders cancelled
- All open positions closed at market price
- Requires manual reset and review
- Strategies remain deactivated until manually re-enabled

### State Transitions

```
STOPPED ──[Start Trading]──> ACTIVE
ACTIVE ──[Pause Trading]──> PAUSED
PAUSED ──[Resume Trading]──> ACTIVE
PAUSED ──[Stop Trading]──> STOPPED
ACTIVE ──[Stop Trading]──> STOPPED
ACTIVE ──[Kill Switch]──> EMERGENCY_HALT
ACTIVE ──[Circuit Breaker]──> EMERGENCY_HALT
EMERGENCY_HALT ──[Manual Reset]──> STOPPED
```

### State Persistence

**Storage**:
- State saved to SQLite database on every change
- Includes: current state, timestamp, reason for change, user who initiated
- Transaction log records all state transitions

**Restoration**:
- Backend service reads state on startup
- Resumes in last known state (ACTIVE, PAUSED, or STOPPED)
- If EMERGENCY_HALT, remains halted until manual reset
- Independent of user login/logout
- Survives backend service restarts

**Validation**:
- On startup, verify eToro API connection before resuming ACTIVE state
- If API unavailable, transition to PAUSED with alert
- Validate all active strategies are still valid
- Check for any pending orders or position discrepancies

### Dashboard Controls

**Master Control Button**:
- Prominent "Start Autonomous Trading" / "Stop Autonomous Trading" button
- Shows current state with color coding:
  - Green: ACTIVE
  - Yellow: PAUSED
  - Red: STOPPED
  - Dark Red: EMERGENCY_HALT
- Requires confirmation for state changes
- Disabled during EMERGENCY_HALT (requires reset first)

**State Indicator**:
- Always visible status badge showing current state
- Last state change timestamp
- Reason for current state (if applicable)
- Number of active strategies

**Home Page Display** (on login):
- Current autonomous trading status
- Last active strategies and their status
- Performance metrics from current session
- Performance summary from previous sessions
- Active positions count and total P&L
- Recent trades and orders
- Any system alerts or warnings

### Backend Service Independence

**Validates Requirement 16.12**: "THE Backend_Service SHALL continue running trading strategies even when the browser is closed"

**Implementation**:
- Backend service runs as independent process
- Does not depend on active user sessions
- Continues operation when:
  - Browser is closed
  - User logs out
  - Frontend UI is not accessed
  - Network connection to frontend is lost
- Only stops when:
  - User explicitly stops trading via Dashboard
  - Kill Switch activated
  - Circuit Breaker triggered
  - Backend service process terminated
  - Critical error occurs

**State Synchronization**:
- WebSocket connection pushes state changes to connected clients
- When user logs in, Dashboard fetches current state
- Multiple users can view same state (single-user system, but supports reconnection)
- State changes from Dashboard immediately reflected in backend

### API Endpoints

```python
# Get current autonomous trading state
GET /system/status
Response: {
    "state": "ACTIVE",
    "timestamp": "2024-02-14T10:30:00Z",
    "active_strategies": 3,
    "reason": "User started trading",
    "uptime_seconds": 3600
}

# Start autonomous trading
POST /system/start
Request: {"confirmation": true}
Response: {"state": "ACTIVE", "message": "Autonomous trading started"}

# Pause autonomous trading
POST /system/pause
Request: {"confirmation": true}
Response: {"state": "PAUSED", "message": "Autonomous trading paused"}

# Stop autonomous trading
POST /system/stop
Request: {"confirmation": true}
Response: {"state": "STOPPED", "message": "Autonomous trading stopped"}

# Resume from paused state
POST /system/resume
Request: {"confirmation": true}
Response: {"state": "ACTIVE", "message": "Autonomous trading resumed"}

# Reset from emergency halt
POST /system/reset
Request: {"confirmation": true, "acknowledge_risks": true}
Response: {"state": "STOPPED", "message": "System reset, ready to start"}
```

### Logging and Audit Trail

All state transitions are logged with:
- Timestamp
- Previous state
- New state
- User who initiated (if manual)
- Reason for change
- Active strategies at time of change
- Open positions at time of change

This ensures complete audit trail for regulatory compliance and debugging.

### Service Dependency Management

The platform manages dependent services (Ollama LLM) to ensure all required components are available when autonomous trading is active.

#### Dependent Services

**Ollama LLM Service**:
- Required for: Strategy generation, vibe-coding translation
- Endpoint: http://localhost:11434
- Start command: `ollama serve` (or system-specific)
- Health check: GET http://localhost:11434/api/tags

#### Service Lifecycle Management

**On Start Autonomous Trading**:
1. Check if Ollama is running (health check)
2. If not running:
   - Attempt to start Ollama using subprocess
   - Wait up to 30 seconds for service to become available
   - If successful: Continue with ACTIVE state
   - If failed: Transition to PAUSED, alert user with instructions
3. If running: Continue with ACTIVE state

**During Active Trading**:
- Health check Ollama every 60 seconds
- If Ollama becomes unavailable:
  - Log warning
  - Disable strategy generation
  - Maintain existing positions
  - Continue monitoring other operations
  - Attempt to reconnect every 60 seconds
- If Ollama recovers:
  - Log recovery
  - Re-enable strategy generation

**On Stop Autonomous Trading**:
- Check configuration: `stop_dependent_services`
- If true: Stop Ollama service
- If false: Leave Ollama running
- Default: false (leave running for manual use)

#### Service Manager Class

```python
class ServiceManager:
    """Manages dependent service lifecycle."""
    
    def __init__(self, config: ServiceConfig):
        self.config = config
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
    
    def stop_service(self, service_name: str) -> bool:
        """Stop a dependent service."""
        service = self.services.get(service_name)
        if not service:
            raise ValueError(f"Unknown service: {service_name}")
        
        try:
            service.stop()
            logger.info(f"Service {service_name} stopped")
            return True
        except Exception as e:
            logger.error(f"Error stopping service {service_name}: {e}")
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

```python
@dataclass
class ServiceStatus:
    name: str
    is_healthy: bool
    endpoint: str
    last_check: datetime
    error_message: Optional[str] = None
```

#### Integration with State Manager

```python
def transition_to_active(self, reason: str, user: Optional[str] = None):
    """Transition to ACTIVE state with service checks."""
    
    # Check dependent services
    all_healthy, failed_services = self.service_manager.ensure_services_running()
    
    if not all_healthy:
        # Cannot start trading without required services
        logger.error(
            f"Cannot start autonomous trading: "
            f"services not available: {', '.join(failed_services)}"
        )
        
        # Transition to PAUSED instead
        self.transition_to(
            SystemStateEnum.PAUSED,
            reason=f"Required services unavailable: {', '.join(failed_services)}",
            user=user
        )
        
        # Alert user
        self.alert_user(
            severity="ERROR",
            title="Cannot Start Trading",
            message=f"Required services are not running: {', '.join(failed_services)}. "
                   f"Please start these services manually or check logs for details."
        )
        
        return False
    
    # All services healthy, proceed with transition
    self.transition_to(SystemStateEnum.ACTIVE, reason=reason, user=user)
    return True
```

#### API Endpoints for Service Management

```python
# Get status of all dependent services
GET /system/services
Response: {
    "ollama": {
        "name": "Ollama LLM",
        "is_healthy": true,
        "endpoint": "http://localhost:11434",
        "last_check": "2026-02-14T10:30:00Z"
    }
}

# Start a specific service
POST /system/services/:name/start
Response: {
    "success": true,
    "message": "Service ollama started successfully"
}

# Stop a specific service
POST /system/services/:name/stop
Response: {
    "success": true,
    "message": "Service ollama stopped"
}

# Health check a specific service
GET /system/services/:name/health
Response: {
    "is_healthy": true,
    "last_check": "2026-02-14T10:30:00Z"
}
```

#### Dashboard Service Status Display

The Dashboard displays status of all dependent services:

```
┌─────────────────────────────────────────────┐
│          Dependent Services                 │
├─────────────────────────────────────────────┤
│                                             │
│  Ollama LLM                                 │
│  Status: ● Running                          │
│  Endpoint: localhost:11434                  │
│  Last Check: 2 seconds ago                  │
│  [Restart] [Stop]                           │
│                                             │
└─────────────────────────────────────────────┘
```

If service is not running:
```
┌─────────────────────────────────────────────┐
│  Ollama LLM                                 │
│  Status: ● Stopped                          │
│  Error: Connection refused                  │
│  [Start Service] [View Logs]                │
│                                             │
│  ⚠️ Strategy generation disabled            │
└─────────────────────────────────────────────┘
```

## Data Models

### SystemState

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
    ACTIVE = "active"  # Trading system running, generating signals
    PAUSED = "paused"  # Temporarily paused, positions maintained
    STOPPED = "stopped"  # Stopped, positions maintained
    EMERGENCY_HALT = "emergency_halt"  # Kill switch or circuit breaker activated
```

### Strategy

```python
@dataclass
class Strategy:
    id: str
    name: str
    description: str
    status: StrategyStatus  # PROPOSED, BACKTESTED, DEMO, LIVE, RETIRED
    rules: Dict[str, Any]  # Strategy-specific rules and parameters
    symbols: List[str]  # Instruments traded by this strategy
    risk_params: RiskParams  # Position size, stop loss, take profit
    created_at: datetime
    activated_at: Optional[datetime]
    retired_at: Optional[datetime]
    performance: PerformanceMetrics
```

### Order

```python
@dataclass
class Order:
    id: str
    strategy_id: str
    symbol: str
    side: OrderSide  # BUY, SELL
    order_type: OrderType  # MARKET, LIMIT, STOP_LOSS, TAKE_PROFIT
    quantity: float
    price: Optional[float]  # For limit orders
    stop_price: Optional[float]  # For stop orders
    status: OrderStatus  # PENDING, SUBMITTED, FILLED, CANCELLED, FAILED
    submitted_at: Optional[datetime]
    filled_at: Optional[datetime]
    filled_price: Optional[float]
    filled_quantity: Optional[float]
    etoro_order_id: Optional[str]
```

### Position

```python
@dataclass
class Position:
    id: str
    strategy_id: str
    symbol: str
    side: PositionSide  # LONG, SHORT
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    opened_at: datetime
    closed_at: Optional[datetime]
    etoro_position_id: str
```

### MarketData

```python
@dataclass
class MarketData:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: DataSource  # ETORO, YAHOO_FINANCE
```

### TradingSignal

```python
@dataclass
class TradingSignal:
    strategy_id: str
    symbol: str
    action: SignalAction  # ENTER_LONG, ENTER_SHORT, EXIT_LONG, EXIT_SHORT
    confidence: float  # 0.0 to 1.0
    reason: str
    generated_at: datetime
    metadata: Dict[str, Any]
```

### AccountInfo

```python
@dataclass
class AccountInfo:
    account_id: str
    mode: TradingMode  # DEMO, LIVE
    balance: float
    buying_power: float
    margin_used: float
    margin_available: float
    daily_pnl: float
    total_pnl: float
    positions_count: int
    updated_at: datetime
```

### RiskConfig

```python
@dataclass
class RiskConfig:
    max_position_size_pct: float  # Max % of portfolio per position
    max_exposure_pct: float  # Max % of portfolio in all positions
    max_daily_loss_pct: float  # Circuit breaker threshold (e.g., 3%)
    max_drawdown_pct: float  # Kill switch threshold (e.g., 10%)
    position_risk_pct: float  # Risk per trade (e.g., 1%)
    stop_loss_pct: float  # Default stop loss distance
    take_profit_pct: float  # Default take profit distance
```

## Correctness Properties


*A property is a characteristic or behavior that should hold true across all valid executions of a system - essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Core Trading Properties

Property 1: Authentication failure handling
*For any* invalid or expired API credentials, authentication attempts should fail gracefully with appropriate error logging and trading operations should be prevented.
**Validates: Requirements 1.3**

Property 2: API retry with exponential backoff
*For any* failed API operation when eToro API is unavailable, the operation should be queued and retried with exponentially increasing delays between attempts.
**Validates: Requirements 1.7**

Property 3: Credential encryption at rest
*For any* sensitive data (API credentials, passwords, tokens) stored locally, the stored value should be encrypted and not readable as plaintext.
**Validates: Requirements 2.3, 18.5**

Property 4: Authentication token lifecycle
*For any* authentication token received from eToro API, it should be stored securely and reused for subsequent API calls, and when expired, automatic re-authentication should occur using stored credentials.
**Validates: Requirements 2.9, 2.10**

Property 5: Market data validation
*For any* market data received from any source, it should be validated for integrity (no nulls, reasonable values, chronological order) before storage or use.
**Validates: Requirements 3.5**

Property 6: Strategy validation
*For any* proposed trading strategy (from LLM or user), it should be validated against risk parameters and rejected if invalid.
**Validates: Requirements 4.2**

Property 7: Backtest metrics completeness
*For any* completed backtest, the results should include all required performance metrics (returns, Sharpe ratio, maximum drawdown).
**Validates: Requirements 4.4**

Property 8: Data persistence round-trip
*For any* critical data (strategies, configuration, state), storing then retrieving should produce equivalent data.
**Validates: Requirements 4.5, 13.4, 14.1**

Property 9: Signal risk validation
*For any* trading signal generated by any strategy, it must pass through Risk Manager validation before execution, and signals violating risk parameters should be rejected with logged reasons.
**Validates: Requirements 4.8, 5.6, 5.7**

### Risk Management Properties

Property 10: Risk limits enforcement
*For any* portfolio state, the following invariants must hold: individual position sizes ≤ max_position_size_pct, total exposure ≤ max_exposure_pct, and daily losses ≤ max_daily_loss_pct (or circuit breaker activates).
**Validates: Requirements 5.1, 5.2, 5.3**

Property 11: Circuit breaker prevents new positions
*For any* new position request when circuit breaker is active, the request should be rejected.
**Validates: Requirements 5.5**

Property 12: Position sizing calculation
*For any* position size calculation, the size should be computed as: (account_balance × position_risk_pct) / (entry_price - stop_loss_price), respecting maximum position size limits.
**Validates: Requirements 5.8**

### Order Execution Properties

Property 13: Order lifecycle management
*For any* validated trading signal, an order should be created, submitted to eToro API with appropriate order type, tracked until completion, and position records updated on fill.
**Validates: Requirements 6.1, 6.2, 6.3, 6.4**

Property 14: Order failure logging
*For any* failed order, the error should be logged with details and user notification should occur.
**Validates: Requirements 6.5**

Property 15: Automatic stop loss and take profit attachment
*For any* new position opened, stop loss and take profit orders should be automatically attached based on strategy risk parameters.
**Validates: Requirements 6.7**

Property 16: Partial fill tracking
*For any* partially filled order, the remaining unfilled quantity should be accurately tracked and equal to (original_quantity - filled_quantity).
**Validates: Requirements 6.8**

Property 17: Market hours enforcement
*For any* order request when the target market is closed, the order should be queued for execution at market open rather than submitted immediately.
**Validates: Requirements 6.9, 12.2, 12.3**

Property 18: Asset class market hours
*For any* asset class (stocks, ETFs, cryptocurrencies), the correct market hours should be applied, with cryptocurrencies always considered open (24/7).
**Validates: Requirements 12.4, 15.2**

Property 19: Holiday and early closure handling
*For any* date that is a holiday or early closure for a given exchange, the market should be treated as closed for that exchange.
**Validates: Requirements 12.7**

### LLM and Strategy Properties

Property 20: LLM strategy generation context
*For any* strategy generation request to LLM Service, market context and risk constraints should be included in the prompt.
**Validates: Requirements 7.3**

Property 21: LLM response parsing
*For any* LLM response, it should be parsed into a structured StrategyDefinition with all required fields (name, rules, symbols, risk_params).
**Validates: Requirements 7.4**

Property 22: Generated strategy validation
*For any* strategy generated by LLM, it should be validated for completeness (all required fields present) and correctness (rules are executable, symbols are valid).
**Validates: Requirements 7.6**

### Data Management Properties

Property 23: Smart Portfolio position isolation
*For any* Smart Portfolio position, it should be tracked separately from individual instrument positions in the data model.
**Validates: Requirements 9.4**

Property 24: Trading mode data isolation
*For any* configuration or state data, it should be isolated by trading mode (Demo vs Live) with no cross-contamination.
**Validates: Requirements 10.7**

Property 25: Performance metrics calculation
*For any* strategy with completed trades, performance metrics (daily/weekly/monthly returns, Sharpe ratio, Sortino ratio, max drawdown, win rate, avg win, avg loss) should be calculated and available.
**Validates: Requirements 13.1, 13.2, 13.7**

Property 26: Benchmark comparison
*For any* strategy, returns should be comparable against relevant benchmarks (SPY for stocks, BTC for crypto).
**Validates: Requirements 13.3**

Property 27: P&L attribution
*For any* profit or loss, it should be correctly attributed to the specific strategy and position that generated it.
**Validates: Requirements 13.6**

Property 28: Transaction logging
*For any* order submission or fill event, it should be logged to the transaction log with timestamp and details.
**Validates: Requirements 14.5**

Property 29: Cryptocurrency risk parameters
*For any* cryptocurrency position, risk parameters (position size, stop loss distance) should be adjusted for higher volatility compared to traditional assets.
**Validates: Requirements 15.3**

Property 30: Cryptocurrency order types
*For any* cryptocurrency order, appropriate order types (market, limit, stop loss, take profit) should be used based on strategy requirements.
**Validates: Requirements 15.5**

### Security Properties

Property 31: Password hashing
*For any* user password stored in the system, it should be hashed using bcrypt or equivalent secure algorithm, never stored as plaintext.
**Validates: Requirements 18.2**

Property 32: Input validation and sanitization
*For any* user input received by the system, it should be validated against expected format and sanitized to prevent injection attacks.
**Validates: Requirements 18.6**

Property 33: Session timeout enforcement
*For any* user session, it should automatically expire after a configured period of inactivity.
**Validates: Requirements 18.4**

Property 34: Authentication rate limiting
*For any* authentication endpoint, rate limiting should be enforced to prevent brute force attacks, with excessive attempts logged.
**Validates: Requirements 18.7**

Property 35: Security event logging
*For any* authentication attempt or security-related event, it should be logged with timestamp, user identifier, and outcome.
**Validates: Requirements 18.8**

### Error Handling Properties

Property 36: Error logging format
*For any* error that occurs, it should be logged with timestamp, severity level, component name, and contextual information.
**Validates: Requirements 19.1, 19.2**

Property 37: Critical error notification
*For any* error with severity level CRITICAL, a notification should be sent to the user via the Dashboard.
**Validates: Requirements 19.3**

Property 38: API rate limit throttling
*For any* API usage approaching rate limits, request throttling should activate and warnings should be logged.
**Validates: Requirements 19.6**

Property 39: Graceful degradation
*For any* non-critical component failure, the system should continue operating with reduced functionality rather than complete failure.
**Validates: Requirements 19.7**

## Error Handling

### Error Categories

**API Errors**
- Authentication failures: Log error, prompt for credential update, prevent trading
- Rate limit exceeded: Activate throttling, queue requests, log warnings
- Connection failures: Retry with exponential backoff, fall back to Yahoo Finance for market data
- Invalid responses: Log error, validate data, reject if invalid

**Trading Errors**
- Order rejection: Log reason, notify user, do not retry automatically
- Partial fills: Track remaining quantity, decide whether to cancel or wait
- Position reconciliation failures: Log discrepancy, alert user, halt trading until resolved
- Risk limit violations: Reject signal, log reason, continue monitoring

**Strategy Errors**
- Backtest failures: Log error, mark strategy as failed, do not activate
- Signal generation errors: Log error, skip signal, continue with other strategies
- LLM unavailable: Log error, disable strategy generation, continue with active strategies
- Invalid strategy definition: Reject strategy, log validation errors, prompt user

**Data Errors**
- Market data validation failures: Reject data, log error, attempt fallback source
- Database errors: Log error, attempt recovery from backup, alert user if critical
- Cache corruption: Clear cache, log error, fetch fresh data
- Backup failures: Log error, retry, alert user if persistent

**Security Errors**
- Authentication failures: Log attempt, enforce rate limiting, lock account after threshold
- Session expiration: Clear session, redirect to login, preserve unsaved work if possible
- Invalid input: Reject input, log attempt, return sanitized error message
- Encryption failures: Log error, halt operation, alert user

### Error Recovery Strategies

**Automatic Recovery**
- API connection failures: Retry with exponential backoff (1s, 2s, 4s, 8s, max 60s)
- Transient errors: Retry up to 3 times before failing
- Cache misses: Fetch from primary source
- Token expiration: Automatic re-authentication

**Manual Recovery**
- Credential updates: User must provide new credentials via UI
- Position reconciliation: User must review and confirm corrections
- Strategy failures: User must review and fix strategy definition
- Database corruption: User must confirm backup restoration

**Graceful Degradation**
- LLM unavailable: Disable strategy generation, continue with active strategies
- Yahoo Finance unavailable: Use cached data, reduce update frequency
- WebSocket disconnection: Fall back to polling, attempt reconnection
- Non-critical component failure: Log error, disable feature, continue core operations

### Circuit Breakers and Kill Switch

**Circuit Breaker Activation**
- Trigger: Daily loss exceeds max_daily_loss_pct (default 3%)
- Action: Prevent new position entries, allow exits, log activation
- Reset: Automatic at start of next trading day
- Override: Manual override by user with confirmation

**Kill Switch Activation**
- Trigger: Manual activation by user OR max drawdown exceeded (default 10%)
- Action: Immediately close all positions, halt all trading, disconnect strategies
- Reset: Manual reset by user after review
- Logging: Log all positions closed, reasons, timestamps

## Testing Strategy

### Dual Testing Approach

The testing strategy employs both unit tests and property-based tests as complementary approaches:

**Unit Tests** focus on:
- Specific examples demonstrating correct behavior
- Integration points between components (eToro API client, Strategy Engine, Risk Manager)
- Edge cases (empty portfolios, zero balances, market closed)
- Error conditions (API failures, invalid data, authentication errors)

**Property-Based Tests** focus on:
- Universal properties that hold for all inputs
- Comprehensive input coverage through randomization
- Invariants that must always hold (risk limits, data integrity)
- Round-trip properties (serialization, persistence)

Together, unit tests catch concrete bugs in specific scenarios while property tests verify general correctness across all possible inputs.

### Property-Based Testing Configuration

**Framework**: Hypothesis (Python property-based testing library)

**Configuration**:
- Minimum 100 iterations per property test (due to randomization)
- Each test tagged with comment referencing design property
- Tag format: `# Feature: alphacent-trading-platform, Property {N}: {property_text}`

**Test Organization**:
```
tests/
├── unit/
│   ├── test_etoro_client.py
│   ├── test_market_data.py
│   ├── test_strategy_engine.py
│   ├── test_risk_manager.py
│   ├── test_order_executor.py
│   └── test_llm_service.py
├── property/
│   ├── test_authentication_properties.py
│   ├── test_risk_properties.py
│   ├── test_order_properties.py
│   ├── test_data_properties.py
│   └── test_security_properties.py
└── integration/
    ├── test_trading_flow.py
    └── test_strategy_lifecycle.py
```

### Key Property Test Examples

**Property 3: Credential encryption**
```python
@given(credentials=st.text(min_size=1))
@settings(max_examples=100)
def test_credential_encryption_property(credentials):
    # Feature: alphacent-trading-platform, Property 3: Credential encryption at rest
    stored = encrypt_and_store(credentials)
    assert stored != credentials  # Not plaintext
    assert is_encrypted(stored)
    decrypted = load_and_decrypt()
    assert decrypted == credentials
```

**Property 10: Risk limits enforcement**
```python
@given(
    positions=st.lists(st.builds(Position), min_size=0, max_size=20),
    account=st.builds(AccountInfo),
    config=st.builds(RiskConfig)
)
@settings(max_examples=100)
def test_risk_limits_enforcement_property(positions, account, config):
    # Feature: alphacent-trading-platform, Property 10: Risk limits enforcement
    risk_manager = RiskManager(config)
    
    # Check position size limits
    for pos in positions:
        position_value = pos.quantity * pos.current_price
        assert position_value <= account.balance * config.max_position_size_pct
    
    # Check total exposure
    total_exposure = sum(p.quantity * p.current_price for p in positions)
    assert total_exposure <= account.balance * config.max_exposure_pct
    
    # Check daily loss limit (or circuit breaker active)
    if account.daily_pnl < -account.balance * config.max_daily_loss_pct:
        assert risk_manager.is_circuit_breaker_active()
```

**Property 8: Data persistence round-trip**
```python
@given(strategy=st.builds(Strategy))
@settings(max_examples=100)
def test_data_persistence_roundtrip_property(strategy):
    # Feature: alphacent-trading-platform, Property 8: Data persistence round-trip
    db = Database()
    db.save_strategy(strategy)
    loaded = db.load_strategy(strategy.id)
    assert loaded == strategy
```

### Unit Test Examples

**Authentication failure handling**
```python
def test_authentication_with_invalid_credentials():
    client = EToroAPIClient("invalid_key", "invalid_secret", TradingMode.DEMO)
    with pytest.raises(AuthenticationError):
        client.authenticate()
    # Verify error logged
    assert "Authentication failed" in get_logs()
    # Verify trading prevented
    assert not client.is_authenticated()
```

**Circuit breaker activation**
```python
def test_circuit_breaker_activates_on_daily_loss_limit():
    config = RiskConfig(max_daily_loss_pct=0.03)
    risk_manager = RiskManager(config)
    account = AccountInfo(balance=10000, daily_pnl=-350)  # 3.5% loss
    
    assert risk_manager.check_circuit_breaker(account, account.daily_pnl)
    assert risk_manager.is_circuit_breaker_active()
```

**Market hours enforcement**
```python
def test_order_queued_when_market_closed():
    executor = OrderExecutor(etoro_client, market_hours)
    signal = TradingSignal(symbol="AAPL", action=SignalAction.ENTER_LONG)
    
    # Mock market closed
    market_hours.is_market_open = Mock(return_value=False)
    
    order = executor.execute_signal(signal, position_size=100)
    assert order.status == OrderStatus.QUEUED
    assert order.submitted_at is None
```

### Integration Tests

**End-to-end trading flow**
```python
def test_complete_trading_flow():
    # Setup
    platform = AlphaCent(mode=TradingMode.DEMO)
    platform.authenticate()
    
    # Generate strategy
    strategy = platform.strategy_engine.generate_strategy(
        "Momentum strategy for tech stocks"
    )
    
    # Backtest
    results = platform.strategy_engine.backtest_strategy(
        strategy, start=datetime(2023, 1, 1), end=datetime(2023, 12, 31)
    )
    assert results.sharpe_ratio > 0
    
    # Activate in demo mode
    platform.strategy_engine.activate_strategy(strategy.id, TradingMode.DEMO)
    
    # Generate signal
    signals = platform.strategy_engine.generate_signals(strategy)
    assert len(signals) > 0
    
    # Validate through risk manager
    validated = platform.risk_manager.validate_signal(signals[0], platform.account)
    assert validated.is_valid
    
    # Execute order
    order = platform.order_executor.execute_signal(signals[0], validated.position_size)
    assert order.status in [OrderStatus.SUBMITTED, OrderStatus.FILLED]
```

### Test Coverage Goals

- Unit test coverage: >80% of code
- Property test coverage: All 39 correctness properties
- Integration test coverage: All major workflows (strategy lifecycle, trading flow, error recovery)
- Edge case coverage: All identified edge cases in requirements
- Error path coverage: All error handling paths tested

### Continuous Testing

- Run unit tests on every commit
- Run property tests (100 iterations) on every commit
- Run full property test suite (1000 iterations) nightly
- Run integration tests before deployment
- Monitor test execution time and optimize slow tests
