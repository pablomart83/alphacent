"""
Task 9.9.4: Test Data-Driven Generation and Measure Improvement

This test:
1. Runs autonomous cycle with data-driven generation
2. Compares to baseline (iteration 3: 0/3 strategies with positive Sharpe)
3. Verifies LLM uses market data in prompts
4. Documents improvements in TASK_9.9_RESULTS.md

Target: At least 1/3 strategies with positive Sharpe
"""

import logging
import sys
import yaml
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.models.database import Database
from src.models.enums import TradingMode
from src.strategy.autonomous_strategy_manager import AutonomousStrategyManager
from src.strategy.indicator_library import IndicatorLibrary
from src.strategy.portfolio_manager import PortfolioManager
from src.strategy.strategy_engine import StrategyEngine
from src.strategy.strategy_proposer import StrategyProposer

# Configure logging to capture market data
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('task_9_9_4_test.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def test_complete_autonomous_cycle():
    """Test data-driven generation and measure improvement."""
    logger.info("=" * 80)
    logger.info("Task 9.9.4: Testing Data-Driven Strategy Generation")
    logger.info("=" * 80)
    
    try:
        # 1. Initialize all components with real services
        logger.info("\n[1/6] Initializing components...")
        
        # Load configuration from YAML
        config_path = Path("config/autonomous_trading.yaml")
        if config_path.exists():
            with open(config_path, 'r') as f:
                autonomous_config = yaml.safe_load(f)
            logger.info("   ✓ Configuration loaded from YAML")
        else:
            logger.warning("   ⚠ Config file not found, using defaults")
            autonomous_config = {}
        
        # Initialize database
        db = Database()
        logger.info("   ✓ Database initialized")
        
        # Initialize configuration manager
        config_manager = get_config()
        logger.info("   ✓ Configuration manager initialized")
        
        # Initialize eToro client
        try:
            credentials = config_manager.load_credentials(TradingMode.DEMO)
            etoro_client = EToroAPIClient(
                public_key=credentials['public_key'],
                user_key=credentials['user_key'],
                mode=TradingMode.DEMO
            )
            logger.info("   ✓ eToro client initialized")
        except Exception as e:
            logger.warning(f"   ⚠ Could not initialize eToro client: {e}")
            logger.info("   Using mock eToro client for testing")
            from unittest.mock import Mock
            etoro_client = Mock()
        
        # Initialize LLM service
        llm_service = LLMService()
        logger.info("   ✓ LLM service initialized")
        
        # Initialize market data manager
        market_data = MarketDataManager(etoro_client=etoro_client)
        logger.info("   ✓ Market data manager initialized")
        
        # Initialize indicator library
        indicator_library = IndicatorLibrary()
        logger.info("   ✓ Indicator library initialized")
        
        # Initialize strategy engine
        strategy_engine = StrategyEngine(
            llm_service=llm_service,
            market_data=market_data
        )
        logger.info("   ✓ Strategy engine initialized")
        
        # Initialize strategy proposer
        strategy_proposer = StrategyProposer(
            llm_service=llm_service,
            market_data=market_data
        )
        logger.info("   ✓ Strategy proposer initialized")
        
        # Initialize portfolio manager
        portfolio_manager = PortfolioManager(
            strategy_engine=strategy_engine
        )
        logger.info("   ✓ Portfolio manager initialized")
        
        # Initialize autonomous strategy manager
        test_config = {
            "autonomous": autonomous_config.get("autonomous", {
                "enabled": True,
                "proposal_frequency": "weekly",
                "max_active_strategies": 10,
                "proposal_count": 3,
            }),
            "activation_thresholds": autonomous_config.get("activation_thresholds", {
                "min_sharpe": 1.5,
                "max_drawdown": 0.15,
                "min_win_rate": 0.5,
                "min_trades": 20,
            }),
            "retirement_thresholds": autonomous_config.get("retirement_thresholds", {
                "max_sharpe": 0.5,
                "max_drawdown": 0.15,
                "min_win_rate": 0.4,
                "min_trades_for_evaluation": 30,
            }),
            "backtest": {
                "days": 90,
            },
        }
        
        # Add proposal_count if not present
        if "proposal_count" not in test_config["autonomous"]:
            test_config["autonomous"]["proposal_count"] = 3
        
        autonomous_manager = AutonomousStrategyManager(
            llm_service=llm_service,
            market_data=market_data,
            strategy_engine=strategy_engine,
            config=test_config
        )
        logger.info("   ✓ Autonomous strategy manager initialized")
        
        # 2. Test market regime detection
        logger.info("\n[2/6] Testing market regime detection...")
        regime = strategy_proposer.analyze_market_conditions()
        logger.info(f"   ✓ Current market regime: {regime}")
        assert regime is not None, "Market regime should not be None"
        
        # 3. Test strategy proposal
        logger.info("\n[3/6] Testing strategy proposal...")
        initial_status = autonomous_manager.get_status()
        logger.info(f"   Initial active strategies: {initial_status['active_strategies_count']}")
        
        # Run the autonomous cycle
        logger.info("   Running autonomous cycle...")
        stats = autonomous_manager.run_strategy_cycle()
        
        logger.info(f"   ✓ Proposals generated: {stats['proposals_generated']}")
        logger.info(f"   ✓ Proposals backtested: {stats['proposals_backtested']}")
        logger.info(f"   ✓ Strategies activated: {stats['strategies_activated']}")
        logger.info(f"   ✓ Strategies retired: {stats['strategies_retired']}")
        
        if stats['errors']:
            logger.warning(f"   ⚠ Errors encountered: {len(stats['errors'])}")
            for error in stats['errors']:
                logger.warning(f"      - {error}")
        
        # Verify cycle ran successfully
        assert stats['proposals_generated'] > 0, "Should generate at least 1 proposal"
        assert stats['proposals_backtested'] > 0, "Should backtest at least 1 proposal"
        
        # 4. Test backtest results
        logger.info("\n[4/6] Verifying backtest results...")
        all_strategies = strategy_engine.get_all_strategies()
        logger.info(f"   Total strategies in database: {len(all_strategies)}")
        
        # Find recently proposed strategies (within last 15 minutes to account for long cycles)
        recent_proposals = [
            s for s in all_strategies
            if hasattr(s, 'created_at') and 
            s.created_at and
            (datetime.now() - s.created_at).total_seconds() < 900  # Last 15 minutes
        ]
        logger.info(f"   Recent proposals: {len(recent_proposals)}")
        
        if recent_proposals:
            for strategy in recent_proposals[:3]:  # Show first 3
                logger.info(f"      - {strategy.name}")
                logger.info(f"        Status: {strategy.status}")
                if hasattr(strategy, 'backtest_results') and strategy.backtest_results:
                    logger.info(f"        Sharpe: {strategy.backtest_results.sharpe_ratio:.2f}")
                    logger.info(f"        Return: {strategy.backtest_results.total_return:.2%}")
                    logger.info(f"        Drawdown: {strategy.backtest_results.max_drawdown:.2%}")
        
        # 5. Test activation logic
        logger.info("\n[5/6] Testing activation logic...")
        active_strategies = strategy_engine.get_active_strategies()
        logger.info(f"   Active strategies: {len(active_strategies)}")
        
        if active_strategies:
            for strategy in active_strategies[:3]:  # Show first 3
                logger.info(f"      - {strategy.name}")
                logger.info(f"        Status: {strategy.status}")
        
        # 6. Test portfolio metrics
        logger.info("\n[6/6] Testing portfolio metrics...")
        final_status = autonomous_manager.get_status()
        logger.info(f"   Enabled: {final_status['enabled']}")
        logger.info(f"   Market regime: {final_status['market_regime']}")
        logger.info(f"   Active strategies: {final_status['active_strategies_count']}")
        logger.info(f"   Last run: {final_status['last_run_time']}")
        logger.info(f"   Next run: {final_status['next_run_time']}")
        
        # Verify final state
        assert final_status['enabled'] is True, "System should be enabled"
        assert final_status['market_regime'] is not None, "Market regime should be detected"
        
        logger.info("\n" + "=" * 80)
        logger.info("=" * 80)
        logger.info("Task 9.9.4 Test Completed")
        logger.info("=" * 80)
        
        # Analyze results
        logger.info("\nAnalyzing strategy quality...")
        metrics = analyze_strategy_quality(recent_proposals)
        
        logger.info(f"\n  • Total strategies: {metrics['total_strategies']}")
        logger.info(f"  • Positive Sharpe: {metrics['positive_sharpe_count']}")
        logger.info(f"  • Negative Sharpe: {metrics['negative_sharpe_count']}")
        logger.info(f"  • Success rate: {(metrics['positive_sharpe_count'] / metrics['total_strategies'] * 100) if metrics['total_strategies'] > 0 else 0:.1f}%")
        
        # Check market data integration
        logger.info("\nVerifying market data integration...")
        market_data_found = extract_market_data_from_logs()
        logger.info(f"  • Market data elements found: {len(market_data_found)}")
        
        # Write results document
        logger.info("\nWriting results document...")
        write_results_document(metrics, market_data_found)
        
        # Check if target met
        if metrics['positive_sharpe_count'] >= 1:
            logger.info("\n✅ TARGET ACHIEVED: At least 1/3 strategies with positive Sharpe")
            return True
        else:
            logger.info("\n❌ TARGET NOT MET: Need at least 1/3 strategies with positive Sharpe")
            return False
        
    except Exception as e:
        logger.error(f"\n❌ TEST FAILED: {str(e)}", exc_info=True)
        return False


def analyze_strategy_quality(strategies):
    """Analyze strategy quality metrics."""
    metrics = {
        'total_strategies': len(strategies),
        'positive_sharpe_count': 0,
        'negative_sharpe_count': 0,
        'strategy_details': []
    }
    
    for strategy in strategies:
        if hasattr(strategy, 'backtest_results') and strategy.backtest_results:
            sharpe = strategy.backtest_results.sharpe_ratio
            if sharpe > 0:
                metrics['positive_sharpe_count'] += 1
            else:
                metrics['negative_sharpe_count'] += 1
            
            metrics['strategy_details'].append({
                'name': strategy.name,
                'sharpe': sharpe,
                'return': strategy.backtest_results.total_return,
                'trades': strategy.backtest_results.total_trades,
                'indicators': strategy.rules.get('indicators', [])
            })
        else:
            metrics['negative_sharpe_count'] += 1
            metrics['strategy_details'].append({
                'name': strategy.name,
                'sharpe': float('-inf'),
                'return': 0.0,
                'trades': 0,
                'indicators': strategy.rules.get('indicators', [])
            })
    
    return metrics


def extract_market_data_from_logs(log_file='task_9_9_4_test.log'):
    """Extract market statistics from log file."""
    market_data_found = []
    
    try:
        with open(log_file, 'r') as f:
            content = f.read()
            keywords = [
                'volatility', 'trend_strength', 'mean_reversion_score',
                'RSI below 30 occurs', 'RSI above 70 occurs',
                'CRITICAL MARKET DATA'
            ]
            for keyword in keywords:
                if keyword.lower() in content.lower():
                    market_data_found.append(keyword)
    except FileNotFoundError:
        logger.warning(f"Log file {log_file} not found")
    
    return market_data_found


def write_results_document(metrics, market_data_found):
    """Write comprehensive results document."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with open('TASK_9.9_RESULTS.md', 'w') as f:
        f.write(f"""# Task 9.9.4 Results: Data-Driven Generation Test

**Test Date**: {timestamp}

## Executive Summary

- **Total Strategies**: {metrics['total_strategies']}
- **Positive Sharpe**: {metrics['positive_sharpe_count']}/{metrics['total_strategies']}
- **Success Rate**: {(metrics['positive_sharpe_count'] / metrics['total_strategies'] * 100) if metrics['total_strategies'] > 0 else 0:.1f}%

### Baseline Comparison

- **Baseline (Iteration 3)**: 0/3 strategies with positive Sharpe
- **Current (Data-Driven)**: {metrics['positive_sharpe_count']}/{metrics['total_strategies']} strategies
- **Target Met**: {'✅ YES' if metrics['positive_sharpe_count'] >= 1 else '❌ NO'}

## Market Data Integration

Market data elements found in logs: {len(market_data_found)}

""")
        
        for keyword in market_data_found:
            f.write(f"- ✅ {keyword}\n")
        
        f.write(f"\n**Status**: {'✅ VERIFIED' if len(market_data_found) >= 5 else '⚠️ PARTIAL' if market_data_found else '❌ NOT VERIFIED'}\n\n")
        
        f.write("## Strategy Details\n\n")
        
        for i, detail in enumerate(metrics['strategy_details'], 1):
            status = "✅ PROFITABLE" if detail['sharpe'] > 0 else "❌ UNPROFITABLE"
            f.write(f"### {i}. {detail['name']} {status}\n\n")
            sharpe_str = f"{detail['sharpe']:.3f}" if detail['sharpe'] != float('-inf') else 'N/A'
            f.write(f"- Sharpe: {sharpe_str}\n")
            f.write(f"- Return: {detail['return']:.2%}\n")
            f.write(f"- Trades: {detail['trades']}\n")
            f.write(f"- Indicators: {', '.join(detail['indicators'])}\n\n")
        
        f.write(f"\n## Conclusion\n\n")
        f.write(f"{'✅ SUCCESS' if metrics['positive_sharpe_count'] >= 1 else '⚠️ NEEDS IMPROVEMENT'}: ")
        f.write(f"Data-driven generation {'achieved' if metrics['positive_sharpe_count'] >= 1 else 'did not achieve'} ")
        f.write(f"the target of at least 1/3 strategies with positive Sharpe.\n")
    
    logger.info("Results written to TASK_9.9_RESULTS.md")


if __name__ == "__main__":
    success = test_complete_autonomous_cycle()
    sys.exit(0 if success else 1)

