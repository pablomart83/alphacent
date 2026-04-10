"""
Diagnostic script to check walk-forward validation issues.
"""

import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.database import Database
from src.api.etoro_client import EToroAPIClient
from src.data.market_data_manager import MarketDataManager
from src.strategy.strategy_engine import StrategyEngine
from src.core.config import Configuration
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    print("=" * 80)
    print("WALK-FORWARD VALIDATION DIAGNOSTIC")
    print("=" * 80)
    
    # Initialize
    db = Database()
    config = Configuration()
    etoro = EToroAPIClient(
        mode='DEMO',
        public_key=config.get('etoro', 'public_key'),
        user_key=config.get('etoro', 'user_key')
    )
    market_data = MarketDataManager(etoro)
    strategy_engine = StrategyEngine(llm_service=None, market_data=market_data)
    
    # Get a few BACKTESTED strategies to test
    conn = db.conn
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, name, symbols, rules, performance
        FROM strategies 
        WHERE status = 'BACKTESTED'
        AND json_extract(performance, '$.total_trades') >= 3
        ORDER BY json_extract(performance, '$.sharpe_ratio') DESC
        LIMIT 5
    """)
    
    strategies = cursor.fetchall()
    
    print(f"\nTesting {len(strategies)} strategies with walk-forward validation:")
    print()
    
    # Test walk-forward on each
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)  # 2 years
    
    for strategy_id, name, symbols_json, rules_json, perf_json in strategies:
        print("-" * 80)
        print(f"Strategy: {name}")
        print(f"Symbols: {symbols_json}")
        
        # Parse performance
        perf = json.loads(perf_json) if perf_json else {}
        print(f"Full backtest: Sharpe={perf.get('sharpe_ratio', 0):.2f}, "
              f"Return={perf.get('total_return', 0):.2%}, "
              f"Trades={perf.get('total_trades', 0)}")
        
        # Create strategy object
        from src.models.strategy import Strategy, StrategyStatus
        symbols = json.loads(symbols_json)
        rules = json.loads(rules_json)
        
        strategy = Strategy(
            id=strategy_id,
            name=name,
            symbols=symbols,
            rules=rules,
            status=StrategyStatus.BACKTESTED
        )
        
        # Run walk-forward validation
        try:
            wf_results = strategy_engine.walk_forward_validate(
                strategy=strategy,
                start=start_date,
                end=end_date,
                train_days=480,
                test_days=240
            )
            
            print(f"Walk-forward results:")
            print(f"  Train: Sharpe={wf_results['train_sharpe']:.2f}, "
                  f"Return={wf_results['train_return']:.2%}, "
                  f"Trades={wf_results['train_trades']}")
            print(f"  Test:  Sharpe={wf_results['test_sharpe']:.2f}, "
                  f"Return={wf_results['test_return']:.2%}, "
                  f"Trades={wf_results['test_trades']}")
            print(f"  Degradation: {wf_results['performance_degradation']:.1f}%")
            print(f"  Overfitted: {wf_results['is_overfitted']}")
            
            # Check if it would pass the 0.3 threshold
            passes_old = wf_results['train_sharpe'] > 0.5 and wf_results['test_sharpe'] > 0.5
            passes_new = wf_results['train_sharpe'] > 0.3 and wf_results['test_sharpe'] > 0.3
            
            print(f"  Would pass (Sharpe > 0.5): {passes_old}")
            print(f"  Would pass (Sharpe > 0.3): {passes_new}")
            
        except Exception as e:
            print(f"  ERROR: {e}")
        
        print()
    
    print("=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()
