"""Test strategy generation to see how many are actually created."""
import sys
sys.path.insert(0, '.')

from src.strategy.autonomous_strategy_manager import AutonomousStrategyManager
from src.models.database import get_database

print("=" * 70)
print("TESTING STRATEGY GENERATION")
print("=" * 70)

# Initialize autonomous manager
manager = AutonomousStrategyManager()

# Override proposal count for testing
manager.config["autonomous"]["proposal_count"] = 150

print(f"\nConfiguration:")
print(f"  Proposal count: {manager.config['autonomous']['proposal_count']}")
print(f"  Max active strategies: {manager.config['autonomous']['max_active_strategies']}")

print(f"\nRunning strategy cycle...")
stats = manager.run_strategy_cycle()

print(f"\n" + "=" * 70)
print("RESULTS")
print("=" * 70)
print(f"  Proposals generated: {stats.get('proposals_generated', 0)}")
print(f"  Proposals backtested: {stats.get('proposals_backtested', 0)}")
print(f"  Strategies activated: {stats.get('strategies_activated', 0)}")
print(f"  Strategies retired: {stats.get('strategies_retired', 0)}")

# Check database
db = get_database()
with db.get_session() as session:
    from src.models.orm import StrategyORM
    from src.models.enums import StrategyStatus
    
    demo_strategies = session.query(StrategyORM).filter(
        StrategyORM.status == StrategyStatus.DEMO
    ).all()
    
    print(f"\nDEMO strategies in database: {len(demo_strategies)}")
    
    # Count symbols
    symbol_counts = {}
    for strat in demo_strategies:
        symbols = strat.symbols if isinstance(strat.symbols, list) else []
        for sym in symbols:
            symbol_counts[sym] = symbol_counts.get(sym, 0) + 1
    
    print(f"Unique symbols being traded: {len(symbol_counts)}")
    print(f"\nTop 10 symbols by strategy count:")
    for sym, count in sorted(symbol_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {sym}: {count} strategies")
