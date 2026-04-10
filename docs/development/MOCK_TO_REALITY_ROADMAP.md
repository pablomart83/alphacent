# Mock to Reality Roadmap

## Overview

This document outlines the steps needed to move AlphaCent from mock/in-memory to a fully functional trading platform with:
1. Persistent database storage
2. Real eToro API integration (Demo mode)
3. Service manager implementation

---

## 🎯 Priority Order

1. **Database Persistence** (CRITICAL) - Without this, all data is lost on restart
2. **eToro Integration** (HIGH) - Enables real trading simulation
3. **Service Manager** (MEDIUM) - Enables service monitoring and control

---

## 1. Database Persistence Implementation

### Current State
- ✅ Database models exist (`src/models/database.py`, `src/models/orm.py`)
- ✅ SQLAlchemy ORM configured
- ❌ Not integrated into API layer
- ❌ Using in-memory storage in routers

### What Needs to Be Done

#### A. Database Initialization (30 minutes)
**File:** `src/api/app.py`

**Changes:**
1. Import database module
2. Initialize database in lifespan startup
3. Create tables if they don't exist
4. Add database session management

**Code to add:**
```python
from src.models.database import init_database, get_database

# In lifespan startup:
db = init_database("alphacent.db")
logger.info("Database initialized")
```

#### B. Add Database Dependencies (15 minutes)
**File:** `src/api/dependencies.py`

**Changes:**
1. Add `get_db_session()` dependency
2. Ensure proper session cleanup

**Code to add:**
```python
from src.models.database import get_database

def get_db_session():
    """Get database session for request."""
    db = get_database()
    session = db.get_session()
    try:
        yield session
    finally:
        session.close()
```


#### C. Update Routers to Use Database (2-3 hours)

**Files to update:**
- `src/api/routers/strategies.py`
- `src/api/routers/orders.py`
- `src/api/routers/account.py`
- `src/api/routers/control.py`

**Pattern for each router:**
1. Add `session: Session = Depends(get_db_session)` to endpoints
2. Replace in-memory dict/list with database queries
3. Use ORM models for CRUD operations

**Example transformation:**
```python
# BEFORE (in-memory):
_strategies = {}

@router.get("/strategies")
async def get_strategies():
    return list(_strategies.values())

# AFTER (database):
@router.get("/strategies")
async def get_strategies(
    session: Session = Depends(get_db_session)
):
    strategies = session.query(StrategyORM).all()
    return [strategy.to_dict() for strategy in strategies]
```

#### D. Data Migration (30 minutes)
**Optional:** Create migration script to preserve any existing data

**File:** `scripts/migrate_to_db.py`

---

## 2. eToro API Integration

### Current State
- ✅ Complete eToro client implementation (`src/api/etoro_client.py`)
- ✅ All methods implemented (auth, orders, positions, market data)
- ❌ Not connected to routers
- ❌ Using mock data in routers

### What Needs to Be Done

#### A. eToro Client Manager (1 hour)
**File:** `src/api/etoro_manager.py` (NEW)

**Purpose:** Manage eToro client instances per trading mode

**Implementation:**
```python
class EToroManager:
    def __init__(self):
        self._clients = {}  # mode -> client
        
    def get_client(self, mode: TradingMode, 
                   public_key: str, user_key: str) -> EToroAPIClient:
        # Return cached or create new client
        
    def disconnect_all(self):
        # Cleanup on shutdown
```


#### B. Update Config Router (30 minutes)
**File:** `src/api/routers/config.py`

**Changes:**
1. Store credentials in encrypted config
2. Test connection when credentials saved
3. Return real connection status

**Key changes:**
```python
@router.post("/credentials")
async def set_credentials(request: CredentialsRequest):
    # Save credentials (already implemented)
    config.save_credentials(...)
    
    # NEW: Test connection
    try:
        client = EToroAPIClient(
            public_key=request.public_key,
            user_key=request.user_key,
            mode=request.mode
        )
        client.authenticate()
        client.disconnect()
        return {"success": True, "message": "Connected successfully"}
    except Exception as e:
        return {"success": False, "message": str(e)}
```

#### C. Update Market Data Router (1 hour)
**File:** `src/api/routers/market_data.py`

**Changes:**
1. Get eToro client from manager
2. Call real API methods
3. Handle errors gracefully
4. Cache responses (optional)

**Pattern:**
```python
@router.get("/market-data/{symbol}")
async def get_quote(
    symbol: str,
    etoro_manager: EToroManager = Depends(get_etoro_manager),
    config: Configuration = Depends(get_configuration)
):
    # Get credentials
    creds = config.load_credentials(TradingMode.DEMO)
    
    # Get client
    client = etoro_manager.get_client(
        TradingMode.DEMO,
        creds['public_key'],
        creds['user_key']
    )
    
    # Fetch real data
    market_data = client.get_market_data(symbol)
    return market_data
```

#### D. Update Orders Router (1.5 hours)
**File:** `src/api/routers/orders.py`

**Changes:**
1. Place real orders via eToro API
2. Store orders in database
3. Poll for order status updates
4. Handle fills and rejections

**Key implementation:**
```python
@router.post("/orders")
async def place_order(
    request: OrderRequest,
    session: Session = Depends(get_db_session),
    etoro_manager: EToroManager = Depends(get_etoro_manager)
):
    # Get eToro client
    client = etoro_manager.get_client(request.mode, ...)
    
    # Place order via eToro
    etoro_response = client.place_order(
        symbol=request.symbol,
        side=request.side,
        order_type=request.type,
        quantity=request.quantity,
        price=request.price
    )
    
    # Save to database
    order = OrderORM(
        id=generate_id(),
        etoro_order_id=etoro_response['order_id'],
        symbol=request.symbol,
        ...
    )
    session.add(order)
    session.commit()
    
    return order.to_dict()
```


#### E. Update Account Router (45 minutes)
**File:** `src/api/routers/account.py`

**Changes:**
1. Fetch real account info from eToro
2. Fetch real positions from eToro
3. Sync with database

#### F. Background Tasks (1 hour)
**File:** `src/api/background_tasks.py` (NEW)

**Purpose:** Poll eToro for updates

**Tasks:**
1. Order status updates (every 5 seconds)
2. Position updates (every 10 seconds)
3. Account balance updates (every 30 seconds)

**Implementation:**
```python
import asyncio
from fastapi import BackgroundTasks

async def poll_order_updates():
    while True:
        # Check pending orders
        # Update status in database
        # Notify via WebSocket
        await asyncio.sleep(5)

async def poll_position_updates():
    while True:
        # Fetch positions from eToro
        # Update database
        # Notify via WebSocket
        await asyncio.sleep(10)
```

---

## 3. Service Manager Implementation

### Current State
- ❌ No service manager exists
- ❌ Services endpoint returns mock data
- ❌ Service control endpoints not functional

### What Needs to Be Done

#### A. Service Manager Class (2 hours)
**File:** `src/core/service_manager.py` (NEW)

**Purpose:** Monitor and control dependent services

**Services to manage:**
1. Ollama (LLM service)
2. Database
3. eToro API connection
4. WebSocket server

**Implementation:**
```python
class ServiceManager:
    def __init__(self):
        self.services = {}
        
    def register_service(self, name: str, 
                        health_check: Callable,
                        start: Callable = None,
                        stop: Callable = None):
        # Register service with health check
        
    async def check_health(self, service_name: str) -> ServiceStatus:
        # Run health check
        
    async def start_service(self, service_name: str):
        # Start service if start function provided
        
    async def stop_service(self, service_name: str):
        # Stop service if stop function provided
        
    async def get_all_status(self) -> Dict[str, DependentService]:
        # Get status of all services
```


#### B. Service Health Checks (1 hour)
**File:** `src/core/health_checks.py` (NEW)

**Implement health checks for:**

1. **Ollama Service:**
```python
async def check_ollama_health() -> bool:
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        return response.status_code == 200
    except:
        return False
```

2. **Database:**
```python
def check_database_health() -> bool:
    try:
        db = get_database()
        session = db.get_session()
        session.execute("SELECT 1")
        session.close()
        return True
    except:
        return False
```

3. **eToro API:**
```python
async def check_etoro_health(mode: TradingMode) -> bool:
    try:
        client = get_etoro_client(mode)
        return client.is_authenticated()
    except:
        return False
```

#### C. Update Control Router (30 minutes)
**File:** `src/api/routers/control.py`

**Changes:**
1. Use real ServiceManager
2. Return actual service status
3. Implement start/stop if applicable

**Implementation:**
```python
@router.get("/services")
async def get_services_status(
    service_manager: ServiceManager = Depends(get_service_manager)
):
    return await service_manager.get_all_status()

@router.post("/services/{service_name}/start")
async def start_service(
    service_name: str,
    service_manager: ServiceManager = Depends(get_service_manager)
):
    await service_manager.start_service(service_name)
    return {"success": True, "message": f"{service_name} started"}
```

#### D. Initialize in App Startup (15 minutes)
**File:** `src/api/app.py`

**Changes:**
```python
# In lifespan startup:
service_manager = ServiceManager()

# Register services
service_manager.register_service(
    "ollama",
    health_check=check_ollama_health
)
service_manager.register_service(
    "database",
    health_check=check_database_health
)
service_manager.register_service(
    "etoro_demo",
    health_check=lambda: check_etoro_health(TradingMode.DEMO)
)

# Start health check loop
asyncio.create_task(service_manager.health_check_loop())
```

---

## 📋 Implementation Checklist

### Phase 1: Database Persistence (4-5 hours)
- [ ] Initialize database in app startup
- [ ] Add database session dependency
- [ ] Update strategies router to use database
- [ ] Update orders router to use database
- [ ] Update account router to use database
- [ ] Update control router to use database
- [ ] Test CRUD operations
- [ ] Verify data persists across restarts

### Phase 2: eToro Integration (5-6 hours)
- [ ] Create EToroManager class
- [ ] Add eToro manager dependency
- [ ] Update config router (credentials & connection test)
- [ ] Update market data router (real quotes)
- [ ] Update orders router (real order placement)
- [ ] Update account router (real account info)
- [ ] Implement background polling tasks
- [ ] Test with Demo API keys
- [ ] Handle API errors gracefully
- [ ] Add rate limiting protection

### Phase 3: Service Manager (3-4 hours)
- [ ] Create ServiceManager class
- [ ] Implement health check functions
- [ ] Register services in app startup
- [ ] Update control router endpoints
- [ ] Add health check background task
- [ ] Test service status reporting
- [ ] Test service control (if applicable)

---

## 🧪 Testing Strategy

### Database Testing
1. Create test data
2. Restart server
3. Verify data still exists
4. Test concurrent access
5. Test transaction rollback

### eToro Integration Testing
1. Test authentication with Demo keys
2. Test market data fetching
3. Test order placement (Demo mode)
4. Test order cancellation
5. Test position fetching
6. Test error handling (invalid symbol, etc.)

### Service Manager Testing
1. Test health checks for each service
2. Test service status reporting
3. Test service start/stop (if applicable)
4. Test health check loop
5. Test error recovery

---

## ⚠️ Important Notes

### eToro API Considerations
1. **Rate Limits:** eToro has rate limits - implement backoff
2. **Demo vs Live:** Keep modes strictly separated
3. **Error Handling:** API can fail - always have fallbacks
4. **Authentication:** Tokens expire - implement refresh
5. **WebSocket:** Consider eToro WebSocket for real-time data

### Database Considerations
1. **Migrations:** Use Alembic for schema changes
2. **Backups:** Implement regular backups
3. **Indexes:** Add indexes for frequently queried fields
4. **Transactions:** Use transactions for multi-step operations
5. **Connection Pool:** Configure appropriate pool size

### Security Considerations
1. **API Keys:** Never log API keys
2. **Encryption:** Credentials are encrypted in config
3. **Session Security:** Validate sessions on every request
4. **HTTPS:** Use HTTPS in production
5. **Rate Limiting:** Implement rate limiting per user

---

## 📊 Estimated Timeline

| Phase | Time | Priority |
|-------|------|----------|
| Database Persistence | 4-5 hours | CRITICAL |
| eToro Integration | 5-6 hours | HIGH |
| Service Manager | 3-4 hours | MEDIUM |
| **Total** | **12-15 hours** | |

### Recommended Order
1. **Day 1 (4-5 hours):** Database Persistence
   - Get data persisting across restarts
   - Test thoroughly before moving on

2. **Day 2 (5-6 hours):** eToro Integration
   - Start with market data (read-only)
   - Then orders (write operations)
   - Test extensively with Demo keys

3. **Day 3 (3-4 hours):** Service Manager
   - Implement monitoring
   - Polish and test

---

## 🚀 Quick Start Guide

### Step 1: Database (Start Here!)
```bash
# 1. Update app.py
# 2. Update dependencies.py
# 3. Update one router (strategies)
# 4. Test it works
# 5. Update remaining routers
```

### Step 2: eToro Integration
```bash
# 1. Get Demo API keys from eToro
# 2. Create EToroManager
# 3. Update config router
# 4. Test authentication
# 5. Update market data router
# 6. Test data fetching
# 7. Update orders router
# 8. Test order placement (Demo!)
```

### Step 3: Service Manager
```bash
# 1. Create ServiceManager class
# 2. Create health check functions
# 3. Register services
# 4. Update control router
# 5. Test monitoring
```

---

## 💡 Pro Tips

1. **Start Small:** Get one router working with database before doing all
2. **Test Often:** Test after each change, don't wait until the end
3. **Use Demo Mode:** Always test with Demo keys first
4. **Log Everything:** Add detailed logging for debugging
5. **Handle Errors:** Assume everything can fail, handle gracefully
6. **Keep Mock Fallback:** Keep mock data as fallback for testing
7. **Version Control:** Commit after each working phase
8. **Documentation:** Update docs as you implement

---

## 📞 Need Help?

If you get stuck on any phase:
1. Check the existing examples in `examples/` directory
2. Review the test files in `tests/` directory
3. Check eToro API documentation
4. Test each component in isolation
5. Use logging to debug issues

---

*Ready to move from mock to reality! 🚀*
