"""
Script to activate more diverse strategies by running an autonomous cycle.
This will help generate more trading signals across different market conditions.
"""

import sys
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.database import Database
from src.api.etoro_client import EToroAPIClient
from src.data.market_data_manager import MarketDataManager
from src.strategy.strategy_engine import StrategyEngine
from src.strategy.market_analyzer import MarketStatisticsAnalyzer
from src.strategy.performance_tracker import StrategyPerformanceTracker
from src.strategy.portfolio_manager import PortfolioManager
from src.strategy.autonomous_strategy_manager import AutonomousStrategyManager
from src.core.config import Configuration
from src.models import TradingMode

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    print("=" * 80)
    print("  ACTIVATING MORE DIVERSE STRATEGIES")
    print("  Started at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 80)
    
    # Initialize database
    db = Database()
    
    # Count current strategies
    import sqlite3
    conn = sqlite3.connect('alphacent.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM strategies WHERE status = 'DEMO'")
    demo_count_before = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM strategies WHERE status = 'BACKTESTED'")
    backtested_count = cursor.fetchone()[0]
    
    print(f"\nCurrent Strategy Counts:")
    print(f"  DEMO strategies: {demo_count_before}")
    print(f"  BACKTESTED strategies: {backtested_count}")
    
    # Initialize components
    config = Configuration()
    creds = config.load_credentials(TradingMode.DEMO)
    etoro = EToroAPIClient(
        mode=TradingMode.DEMO,
        public_key=creds['public_key'],
        user_key=creds['user_key']
    )
    
    market_data = MarketDataManager(etoro)
    strategy_engine = StrategyEngine(llm_service=None, market_data=market_data)
    
    # Initialize autonomous manager (it creates its own portfolio_manager)
    autonomous_manager = AutonomousStrategyManager(
        llm_service=None,
        market_data=market_data,
        strategy_engine=strategy_engine,
        websocket_manager=None,
    )
    
    # Override proposal count for more diversity
    autonomous_manager.config["autonomous"]["proposal_count"] = 50
    
    print("\n" + "=" * 80)
    print("  RUNNING AUTONOMOUS CYCLE (50 proposals)")
    print("=" * 80)
    
    # Run autonomous cycle
    cycle_stats = autonomous_manager.run_strategy_cycle()
    
    print("\n" + "=" * 80)
    print("  CYCLE COMPLETE")
    print("=" * 80)
    
    print(f"\nCycle Statistics:")
    print(f"  Duration: {cycle_stats.get('cycle_duration_seconds', 0):.1f} seconds")
    print(f"  Strategies cleaned: {cycle_stats.get('strategies_cleaned', 0)}")
    print(f"  Proposals generated: {cycle_stats.get('proposals_generated', 0)}")
    print(f"  Proposals backtested: {cycle_stats.get('proposals_backtested', 0)}")
    print(f"  Strategies activated: {cycle_stats.get('strategies_activated', 0)}")
    print(f"  Strategies retired: {cycle_stats.get('strategies_retired', 0)}")
    
    if cycle_stats.get('errors'):
        print(f"  Errors: {len(cycle_stats['errors'])}")
    
    # Count strategies after
    cursor.execute("SELECT COUNT(*) FROM strategies WHERE status = 'DEMO'")
    demo_count_after = cursor.fetchone()[0]
    
    print(f"\n" + "=" * 80)
    print("  FINAL RESULTS")
    print("=" * 80)
    
    print(f"\nDEMO Strategies:")
    print(f"  Before: {demo_count_before}")
    print(f"  After: {demo_count_after}")
    print(f"  Net Change: +{demo_count_after - demo_count_before}")
    
    # Show activated strategies
    cursor.execute("""
        SELECT name, symbols, 
               json_extract(performance, '$.sharpe_ratio') as sharpe,
               json_extract(performance, '$.win_rate') as win_rate,
               json_extract(performance, '$.total_trades') as trades
        FROM strategies 
        WHERE status = 'DEMO'
        ORDER BY json_extract(performance, '$.sharpe_ratio') DESC
    """)
    
    strategies = cursor.fetchall()
    
    print(f"\nAll Active DEMO Strategies ({len(strategies)}):")
    for i, (name, symbols, sharpe, win_rate, trades) in enumerate(strategies, 1):
        print(f"  {i}. {name}")
        print(f"     Symbols: {symbols}")
        print(f"     Sharpe: {sharpe:.2f}, Win Rate: {float(win_rate)*100:.1f}%, Trades: {trades}")
    
    print("\n" + "=" * 80)
    print("  COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()
