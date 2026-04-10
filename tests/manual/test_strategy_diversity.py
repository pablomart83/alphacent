"""Test to verify strategy diversity after bug fix."""

import logging
from datetime import datetime, timedelta

from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.strategy.strategy_engine import StrategyEngine
from src.strategy.strategy_proposer import StrategyProposer

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_strategy_diversity():
    """Test that generated strategies are diverse (not identical)."""
    
    # Initialize services
    from src.api.etoro_client import EToroAPIClient
    from src.core.config import get_config
    from src.models.enums import TradingMode
    from unittest.mock import Mock
    
    # Try to get real credentials, fall back to mock
    try:
        config_manager = get_config()
        credentials = config_manager.load_credentials(TradingMode.DEMO)
        etoro_client = EToroAPIClient(
            public_key=credentials['public_key'],
            user_key=credentials['user_key'],
            mode=TradingMode.DEMO
        )
        logger.info("Using real eToro client")
    except Exception as e:
        logger.warning(f"Could not initialize eToro client: {e}")
        logger.info("Using mock eToro client")
        etoro_client = Mock()
    
    market_data = MarketDataManager(etoro_client)
    llm_service = LLMService()
    
    # Initialize StrategyEngine with correct parameter order
    # Signature: __init__(self, llm_service, market_data, websocket_manager=None)
    strategy_engine = StrategyEngine(
        llm_service=llm_service,
        market_data=market_data,
        websocket_manager=None
    )
    strategy_proposer = StrategyProposer(llm_service, market_data)
    
    # Generate 16 strategies (same as the failing test)
    logger.info("Generating 16 strategies to test diversity...")
    strategies = strategy_proposer.propose_strategies(
        count=16,
        symbols=["SPY", "QQQ", "DIA"],
        use_walk_forward=False,
        optimize_parameters=False
    )
    
    logger.info(f"\nGenerated {len(strategies)} strategies\n")
    
    # Collect strategy details
    strategy_details = []
    for i, strategy in enumerate(strategies, 1):
        details = {
            'name': strategy.name,
            'symbol': strategy.symbols[0] if strategy.symbols else 'N/A',
            'template': strategy.metadata.get('template_name', 'Unknown'),
            'indicators': strategy.rules.get('indicators', []),
            'entry_conditions': strategy.rules.get('entry_conditions', []),
            'exit_conditions': strategy.rules.get('exit_conditions', []),
            'params': strategy.metadata.get('customized_parameters', {})
        }
        strategy_details.append(details)
        
        logger.info(f"Strategy {i}: {details['name']}")
        logger.info(f"  Symbol: {details['symbol']}")
        logger.info(f"  Template: {details['template']}")
        logger.info(f"  Indicators: {details['indicators']}")
        logger.info(f"  Entry: {details['entry_conditions'][:2]}")  # First 2 conditions
        logger.info(f"  Exit: {details['exit_conditions'][:2]}")   # First 2 conditions
        logger.info(f"  Params: {details['params']}")
        logger.info("")
    
    # Check diversity
    logger.info("\n" + "="*80)
    logger.info("DIVERSITY ANALYSIS")
    logger.info("="*80)
    
    # 1. Check unique names
    unique_names = set(s['name'] for s in strategy_details)
    logger.info(f"\nUnique strategy names: {len(unique_names)}/{len(strategies)}")
    if len(unique_names) < len(strategies):
        logger.warning(f"  Duplicate names found!")
        name_counts = {}
        for s in strategy_details:
            name_counts[s['name']] = name_counts.get(s['name'], 0) + 1
        for name, count in name_counts.items():
            if count > 1:
                logger.warning(f"    '{name}' appears {count} times")
    
    # 2. Check unique symbols
    unique_symbols = set(s['symbol'] for s in strategy_details)
    logger.info(f"\nUnique symbols: {len(unique_symbols)}")
    logger.info(f"  Symbols: {sorted(unique_symbols)}")
    
    # 3. Check unique templates
    unique_templates = set(s['template'] for s in strategy_details)
    logger.info(f"\nUnique templates: {len(unique_templates)}")
    logger.info(f"  Templates: {sorted(unique_templates)}")
    
    # 4. Check parameter diversity
    unique_param_sets = set()
    for s in strategy_details:
        # Convert params dict to frozenset for hashing
        param_items = tuple(sorted(s['params'].items()))
        unique_param_sets.add(param_items)
    
    logger.info(f"\nUnique parameter sets: {len(unique_param_sets)}/{len(strategies)}")
    if len(unique_param_sets) < len(strategies):
        logger.warning(f"  Some strategies have identical parameters!")
    
    # 5. Check entry condition diversity
    unique_entry_conditions = set()
    for s in strategy_details:
        # Convert list to tuple for hashing
        entry_tuple = tuple(s['entry_conditions'])
        unique_entry_conditions.add(entry_tuple)
    
    logger.info(f"\nUnique entry condition sets: {len(unique_entry_conditions)}/{len(strategies)}")
    if len(unique_entry_conditions) < len(strategies):
        logger.warning(f"  Some strategies have identical entry conditions!")
    
    # 6. Overall diversity score
    diversity_score = (
        len(unique_names) / len(strategies) * 0.3 +
        len(unique_param_sets) / len(strategies) * 0.4 +
        len(unique_entry_conditions) / len(strategies) * 0.3
    )
    
    logger.info(f"\n" + "="*80)
    logger.info(f"OVERALL DIVERSITY SCORE: {diversity_score:.1%}")
    logger.info("="*80)
    
    if diversity_score >= 0.9:
        logger.info("✅ EXCELLENT diversity - strategies are highly varied")
    elif diversity_score >= 0.7:
        logger.info("✅ GOOD diversity - strategies have reasonable variation")
    elif diversity_score >= 0.5:
        logger.warning("⚠️  MODERATE diversity - some strategies are too similar")
    else:
        logger.error("❌ POOR diversity - strategies are mostly identical (BUG NOT FIXED)")
    
    # Now backtest a few strategies to verify they produce different results
    logger.info("\n" + "="*80)
    logger.info("BACKTESTING SAMPLE STRATEGIES")
    logger.info("="*80)
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    backtest_results = []
    for i, strategy in enumerate(strategies[:5], 1):  # Test first 5
        logger.info(f"\nBacktesting strategy {i}: {strategy.name}")
        try:
            results = strategy_engine.backtest_strategy(strategy, start_date, end_date)
            backtest_results.append({
                'name': strategy.name,
                'sharpe': results.sharpe_ratio,
                'return': results.total_return,
                'drawdown': results.max_drawdown,
                'trades': results.total_trades,
                'win_rate': results.win_rate
            })
            logger.info(f"  Sharpe: {results.sharpe_ratio:.2f}, Return: {results.total_return:.2%}, "
                       f"Drawdown: {results.max_drawdown:.2%}, Trades: {results.total_trades}")
        except Exception as e:
            logger.error(f"  Backtest failed: {e}")
            backtest_results.append({
                'name': strategy.name,
                'sharpe': 0,
                'return': 0,
                'drawdown': 0,
                'trades': 0,
                'win_rate': 0
            })
    
    # Check if backtest results are diverse
    unique_sharpes = len(set(r['sharpe'] for r in backtest_results))
    unique_returns = len(set(r['return'] for r in backtest_results))
    unique_trades = len(set(r['trades'] for r in backtest_results))
    
    logger.info(f"\n" + "="*80)
    logger.info(f"BACKTEST DIVERSITY:")
    logger.info(f"  Unique Sharpe ratios: {unique_sharpes}/{len(backtest_results)}")
    logger.info(f"  Unique returns: {unique_returns}/{len(backtest_results)}")
    logger.info(f"  Unique trade counts: {unique_trades}/{len(backtest_results)}")
    logger.info("="*80)
    
    if unique_sharpes == 1 and unique_returns == 1 and unique_trades == 1:
        logger.error("\n❌ BUG NOT FIXED: All strategies produce IDENTICAL backtest results!")
        return False
    else:
        logger.info("\n✅ BUG FIXED: Strategies produce DIFFERENT backtest results!")
        return True

if __name__ == "__main__":
    success = test_strategy_diversity()
    exit(0 if success else 1)
