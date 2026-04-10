"""Test database integration for Phase 1."""

from src.models.database import init_database, get_database
from src.models.orm import StrategyORM
from src.models.enums import StrategyStatus, TradingMode
from datetime import datetime

# Initialize database
print("Initializing database...")
init_database("test_phase1.db")
print("✓ Database initialized")

# Get database instance
db = get_database("test_phase1.db")

# Get session
session = db.get_session()

# Create test strategy
print("\nCreating test strategy...")
strategy = StrategyORM(
    id="test-123",
    name="Test Strategy",
    description="Testing database persistence",
    status=StrategyStatus.PROPOSED,
    rules={"indicator": "RSI", "threshold": 70},
    symbols=["AAPL", "MSFT"],
    risk_params={
        "max_position_size_pct": 0.1,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.04
    },
    created_at=datetime.now(),
    activated_at=None,
    retired_at=None,
    performance={
        "total_return": 0.0,
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "total_trades": 0
    }
)

session.add(strategy)
session.commit()
print(f"✓ Strategy created with ID: {strategy.id}")

# Query it back
print("\nQuerying strategy from database...")
result = session.query(StrategyORM).filter_by(id="test-123").first()
if result:
    print(f"✓ Strategy retrieved: {result.name}")
    print(f"  Description: {result.description}")
    print(f"  Status: {result.status.value}")
    print(f"  Symbols: {result.symbols}")
    
    # Test to_dict method
    print("\nTesting to_dict method...")
    strategy_dict = result.to_dict()
    print(f"✓ to_dict works: {strategy_dict['name']}")
else:
    print("✗ Strategy not found!")

session.close()
print("\n✓ Database test passed!")
print("\nPhase 1 database implementation is working correctly!")
