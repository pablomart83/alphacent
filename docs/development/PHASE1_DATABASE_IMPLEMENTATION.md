# Phase 1: Database Implementation Guide

## Quick Start - Get Database Working in 30 Minutes

This guide will get you from in-memory to persistent database storage.

---

## Step 1: Update app.py (5 minutes)

**File:** `src/api/app.py`

Add these imports at the top:
```python
from src.models.database import init_database, get_database
```

In the `lifespan` function, add after authentication setup:
```python
# Initialize database
logger.info("Initializing database...")
db = init_database("alphacent.db")
logger.info(f"Database initialized at: alphacent.db")
```

---

## Step 2: Update dependencies.py (5 minutes)

**File:** `src/api/dependencies.py`

Add this import:
```python
from sqlalchemy.orm import Session
from src.models.database import get_database
```

Add this new dependency function:
```python
def get_db_session():
    """
    Get database session for request.
    
    Yields:
        SQLAlchemy session
    """
    db = get_database()
    session = db.get_session()
    try:
        yield session
    finally:
        session.close()
```

---

## Step 3: Test Database Works (5 minutes)

Create a test script:

**File:** `test_database.py`
```python
from src.models.database import init_database, get_database
from src.models.orm import StrategyORM
from src.models.enums import StrategyStatus, TradingMode

# Initialize
db = init_database("test.db")
session = db.get_session()

# Create test strategy
strategy = StrategyORM(
    id="test-123",
    name="Test Strategy",
    description="Testing database",
    status=StrategyStatus.DRAFT,
    mode=TradingMode.DEMO
)

session.add(strategy)
session.commit()

# Query it back
result = session.query(StrategyORM).filter_by(id="test-123").first()
print(f"✓ Strategy saved and retrieved: {result.name}")

session.close()
print("✓ Database test passed!")
```

Run it:
```bash
python test_database.py
```

---

## Step 4: Update Strategies Router (15 minutes)

**File:** `src/api/routers/strategies.py`

### Add imports:
```python
from sqlalchemy.orm import Session
from src.api.dependencies import get_db_session
from src.models.orm import StrategyORM
```

### Update GET /strategies endpoint:

**BEFORE:**
```python
# Mock in-memory storage
_strategies = {}

@router.get("")
async def get_strategies(mode: TradingMode):
    return [s for s in _strategies.values() if s.mode == mode]
```

**AFTER:**
```python
@router.get("")
async def get_strategies(
    mode: TradingMode,
    session: Session = Depends(get_db_session)
):
    strategies = session.query(StrategyORM).filter_by(mode=mode).all()
    return [strategy.to_dict() for strategy in strategies]
```

### Update POST /strategies endpoint:

**BEFORE:**
```python
@router.post("")
async def create_strategy(request: CreateStrategyRequest):
    strategy_id = generate_id()
    strategy = Strategy(
        id=strategy_id,
        name=request.name,
        ...
    )
    _strategies[strategy_id] = strategy
    return strategy
```

**AFTER:**
```python
@router.post("")
async def create_strategy(
    request: CreateStrategyRequest,
    session: Session = Depends(get_db_session)
):
    strategy_id = generate_id()
    strategy = StrategyORM(
        id=strategy_id,
        name=request.name,
        description=request.description,
        status=StrategyStatus.DRAFT,
        mode=request.mode,
        created_at=datetime.now()
    )
    session.add(strategy)
    session.commit()
    session.refresh(strategy)
    return strategy.to_dict()
```

### Update GET /strategies/{id} endpoint:

**BEFORE:**
```python
@router.get("/{strategy_id}")
async def get_strategy(strategy_id: str):
    if strategy_id not in _strategies:
        raise HTTPException(404, "Strategy not found")
    return _strategies[strategy_id]
```

**AFTER:**
```python
@router.get("/{strategy_id}")
async def get_strategy(
    strategy_id: str,
    session: Session = Depends(get_db_session)
):
    strategy = session.query(StrategyORM).filter_by(id=strategy_id).first()
    if not strategy:
        raise HTTPException(404, "Strategy not found")
    return strategy.to_dict()
```

---

## Step 5: Test It Works!

1. **Start the backend:**
```bash
python -m src.api.app
```

2. **Test creating a strategy:**
```bash
curl -X POST http://localhost:8000/strategies \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "name": "My First Strategy",
    "description": "Testing database",
    "prompt": "Buy low, sell high",
    "mode": "DEMO"
  }'
```

3. **Test retrieving strategies:**
```bash
curl http://localhost:8000/strategies?mode=DEMO -b cookies.txt
```

4. **Restart the server and test again:**
```bash
# Stop server (Ctrl+C)
# Start again
python -m src.api.app

# Query strategies - should still be there!
curl http://localhost:8000/strategies?mode=DEMO -b cookies.txt
```

If you see your strategy after restart, **SUCCESS!** 🎉

---

## Common Issues & Solutions

### Issue: "No module named 'sqlalchemy'"
**Solution:**
```bash
pip install sqlalchemy
```

### Issue: "Table doesn't exist"
**Solution:** Database tables are created automatically on first run. If you see this error, check that `init_database()` is being called in app startup.

### Issue: "Database is locked"
**Solution:** Make sure you're closing sessions properly. The `get_db_session()` dependency handles this automatically.

### Issue: "Can't find alphacent.db"
**Solution:** The database file is created in the current working directory. Check where you're running the server from.

---

## Next Steps

Once strategies router works:

1. **Update Orders Router** - Same pattern
2. **Update Account Router** - Same pattern  
3. **Update Control Router** - Same pattern

Each router follows the same pattern:
1. Add `session: Session = Depends(get_db_session)`
2. Replace in-memory dict/list with `session.query(ORM).filter(...).all()`
3. Use `session.add()` and `session.commit()` for writes

---

## Verification Checklist

- [ ] Database file created (alphacent.db)
- [ ] Can create strategies
- [ ] Can retrieve strategies
- [ ] Strategies persist after server restart
- [ ] No errors in logs
- [ ] Frontend can still access strategies

---

**Time to complete:** ~30 minutes  
**Difficulty:** Easy  
**Impact:** HIGH - Data now persists!

Ready to implement? Let's do it! 🚀
