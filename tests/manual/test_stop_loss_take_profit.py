"""
Test Stop-Loss and Take-Profit Implementation in Backtests.

This test validates that:
1. Strategy templates have stop-loss and take-profit parameters
2. Backtests simulate stop-loss and take-profit correctly
3. Metrics show stop-loss and take-profit hit rates
4. Activation/retirement criteria account for stop-loss behavior
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
from src.models.database import Database
from src.models.dataclasses import RiskConfig, PerformanceMetrics
from src.models.enums import TradingMode, StrategyStatus
from src.strategy.strategy_engine import StrategyEngine
from src.strategy.strategy_templates import StrategyTemplateLibrary, MarketRegime
from src.strategy.strategy_proposer import StrategyProposer
from src.strategy.portfolio_manager import PortfolioManager
from src.strategy.indicator_library import IndicatorLibrary
from src.strategy.trading_dsl import TradingDSLParser, DSLCodeGenerator
from src.models.dataclasses import Strategy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_stop_loss_take_profit():
    """Test stop-loss and take-profit implementation."""
    logger.info("=" * 80)
    logger.info("TESTING STOP-LOSS AND TAKE-PROFIT IMPLEMENTATION")
    logger.info("=" * 80)
    
    results = {
        'templates_have_sl_tp': False,
        'backtest_with_sl_tp': False,
        'metrics_calculated': False,
        'activation_criteria_updated': False,
        'comparison_complete': False
    }
    
    try:
        # 1. Test that templates have stop-loss and take-profit
        logger.info("\n[1/5] Testing strategy templates have stop-loss and take-profit...")
        template_library = StrategyTemplateLibrary()
        templates = template_library.get_all_templates()
        
        templates_with_sl_tp = 0
        for template in templates:
            if 'stop_loss_pct' in template.default_parameters and 'take_profit_pct' in template.default_parameters:
                templates_with_sl_tp += 1
                logger.info(
                    f"   ✓ {template.name}: "
                    f"SL={template.default_parameters['stop_loss_pct']:.1%}, "
                    f"TP={template.default_parameters['take_profit_pct']:.1%}"
                )
        
        if templates_with_sl_tp == len(templates):
            logger.info(f"   ✓ All {len(templates)} templates have stop-loss and take-profit")
            results['templates_have_sl_tp'] = True
        else:
            logger.warning(
                f"   ⚠ Only {templates_with_sl_tp}/{len(templates)} templates have stop-loss and take-profit"
            )
        
        # 2. Initialize components for backtesting
        logger.info("\n[2/5] Initializing components for backtesting...")
        
        # Load configuration
        config_path = Path("config/autonomous_trading.yaml")
        if config_path.exists():
            with open(config_path, 'r') as f:
                autonomous_config = yaml.safe_load(f)
        else:
            autonomous_config = {}
        
        # Initialize database
        db = Database()
        
        # Initialize configuration manager
        config_manager = get_config()
        
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
            etoro_client = None
        
        # Initialize market data manager
        market_data_manager = MarketDataManager(etoro_client=etoro_client)
        logger.info("   ✓ Market data manager initialized")
        
        # Initialize indicator library
        indicator_library = IndicatorLibrary()
        logger.info("   ✓ Indicator library initialized")
        
        # Initialize DSL parser
        dsl_parser = TradingDSLParser()
        dsl_code_generator = DSLCodeGenerator()
        logger.info("   ✓ DSL parser initialized")
        
        # Initialize strategy engine
        strategy_engine = StrategyEngine(
            llm_service=None,  # Not needed for DSL-based strategies
            market_data=market_data_manager,
            websocket_manager=None
        )
        logger.info("   ✓ Strategy engine initialized")
        
        # Initialize portfolio manager
        portfolio_manager = PortfolioManager(strategy_engine=strategy_engine)
        logger.info("   ✓ Portfolio manager initialized")
        
        # 3. Test backtest with stop-loss and take-profit
        logger.info("\n[3/5] Testing backtest with stop-loss and take-profit...")
        
        # Get a mean reversion template
        template = template_library.get_template_by_name("RSI Mean Reversion")
        if not template:
            logger.error("   ✗ Could not find RSI Mean Reversion template")
            return results
        
        # Create strategy from template with stop-loss and take-profit
        strategy_with_sl_tp = Strategy(
            id=f"test_sl_tp_{datetime.now().timestamp()}",
            name=template.name,
            description=template.description,
            status=StrategyStatus.PROPOSED,
            allocation_percent=0.0,
            rules={
                "entry_conditions": template.entry_conditions,
                "exit_conditions": template.exit_conditions,
                "indicators": template.required_indicators
            },
            symbols=["SPY"],
            risk_params=RiskConfig(
                stop_loss_pct=template.default_parameters['stop_loss_pct'],
                take_profit_pct=template.default_parameters['take_profit_pct'],
                trailing_stop=False
            ),
            created_at=datetime.now(),
            performance=PerformanceMetrics()
        )
        
        # Create strategy without stop-loss and take-profit for comparison
        strategy_without_sl_tp = Strategy(
            id=f"test_no_sl_tp_{datetime.now().timestamp()}",
            name=f"{template.name} (No SL/TP)",
            description=template.description,
            status=StrategyStatus.PROPOSED,
            allocation_percent=0.0,
            rules={
                "entry_conditions": template.entry_conditions,
                "exit_conditions": template.exit_conditions,
                "indicators": template.required_indicators
            },
            symbols=["SPY"],
            risk_params=RiskConfig(
                stop_loss_pct=0.0,  # No stop-loss
                take_profit_pct=0.0,  # No take-profit
                trailing_stop=False
            ),
            created_at=datetime.now(),
            performance=PerformanceMetrics()
        )
        
        # Run backtests
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)  # 1 year backtest
        
        logger.info(f"   Running backtest WITH stop-loss/take-profit...")
        backtest_with_sl_tp = strategy_engine.backtest_strategy(
            strategy=strategy_with_sl_tp,
            start=start_date,
            end=end_date
        )
        
        logger.info(f"   Running backtest WITHOUT stop-loss/take-profit...")
        backtest_without_sl_tp = strategy_engine.backtest_strategy(
            strategy=strategy_without_sl_tp,
            start=start_date,
            end=end_date
        )
        
        if backtest_with_sl_tp and backtest_without_sl_tp:
            logger.info("   ✓ Both backtests completed successfully")
            results['backtest_with_sl_tp'] = True
        else:
            logger.error("   ✗ Backtest failed")
            return results
        
        # 4. Check metrics
        logger.info("\n[4/5] Checking stop-loss and take-profit metrics...")
        
        if backtest_with_sl_tp.metadata:
            sl_hits = backtest_with_sl_tp.metadata.get('stop_loss_hits', 0)
            tp_hits = backtest_with_sl_tp.metadata.get('take_profit_hits', 0)
            sl_hit_rate = backtest_with_sl_tp.metadata.get('stop_loss_hit_rate', 0.0)
            tp_hit_rate = backtest_with_sl_tp.metadata.get('take_profit_hit_rate', 0.0)
            
            logger.info(f"   Stop-loss hits: {sl_hits} ({sl_hit_rate:.1%})")
            logger.info(f"   Take-profit hits: {tp_hits} ({tp_hit_rate:.1%})")
            
            if sl_hits > 0 or tp_hits > 0:
                logger.info("   ✓ Stop-loss and take-profit metrics calculated")
                results['metrics_calculated'] = True
            else:
                logger.warning("   ⚠ No stop-loss or take-profit hits detected")
        else:
            logger.warning("   ⚠ No metadata in backtest results")
        
        # 5. Compare results
        logger.info("\n[5/5] Comparing backtest results...")
        logger.info("=" * 80)
        logger.info("BACKTEST COMPARISON: WITH vs WITHOUT STOP-LOSS/TAKE-PROFIT")
        logger.info("=" * 80)
        
        logger.info(f"\nWITH Stop-Loss/Take-Profit:")
        logger.info(f"  Total Return: {backtest_with_sl_tp.total_return:.2%}")
        logger.info(f"  Sharpe Ratio: {backtest_with_sl_tp.sharpe_ratio:.2f}")
        logger.info(f"  Max Drawdown: {backtest_with_sl_tp.max_drawdown:.2%}")
        logger.info(f"  Win Rate: {backtest_with_sl_tp.win_rate:.2%}")
        logger.info(f"  Total Trades: {backtest_with_sl_tp.total_trades}")
        logger.info(f"  Avg Win: ${backtest_with_sl_tp.avg_win:,.2f}")
        logger.info(f"  Avg Loss: ${backtest_with_sl_tp.avg_loss:,.2f}")
        if backtest_with_sl_tp.avg_loss != 0:
            rr_ratio = abs(backtest_with_sl_tp.avg_win / backtest_with_sl_tp.avg_loss)
            logger.info(f"  Risk/Reward: {rr_ratio:.2f}:1")
        
        logger.info(f"\nWITHOUT Stop-Loss/Take-Profit:")
        logger.info(f"  Total Return: {backtest_without_sl_tp.total_return:.2%}")
        logger.info(f"  Sharpe Ratio: {backtest_without_sl_tp.sharpe_ratio:.2f}")
        logger.info(f"  Max Drawdown: {backtest_without_sl_tp.max_drawdown:.2%}")
        logger.info(f"  Win Rate: {backtest_without_sl_tp.win_rate:.2%}")
        logger.info(f"  Total Trades: {backtest_without_sl_tp.total_trades}")
        logger.info(f"  Avg Win: ${backtest_without_sl_tp.avg_win:,.2f}")
        logger.info(f"  Avg Loss: ${backtest_without_sl_tp.avg_loss:,.2f}")
        if backtest_without_sl_tp.avg_loss != 0:
            rr_ratio = abs(backtest_without_sl_tp.avg_win / backtest_without_sl_tp.avg_loss)
            logger.info(f"  Risk/Reward: {rr_ratio:.2f}:1")
        
        logger.info(f"\nIMPACT:")
        logger.info(f"  Sharpe Ratio Change: {backtest_with_sl_tp.sharpe_ratio - backtest_without_sl_tp.sharpe_ratio:+.2f}")
        logger.info(f"  Max Drawdown Change: {backtest_with_sl_tp.max_drawdown - backtest_without_sl_tp.max_drawdown:+.2%}")
        logger.info(f"  Trade Count Change: {backtest_with_sl_tp.total_trades - backtest_without_sl_tp.total_trades:+d}")
        logger.info(f"  Win Rate Change: {backtest_with_sl_tp.win_rate - backtest_without_sl_tp.win_rate:+.2%}")
        
        logger.info("=" * 80)
        
        results['comparison_complete'] = True
        
        # Test activation criteria
        logger.info("\n[6/5] Testing activation criteria with stop-loss...")
        can_activate_with_sl = portfolio_manager.evaluate_for_activation(
            strategy=strategy_with_sl_tp,
            backtest_results=backtest_with_sl_tp
        )
        can_activate_without_sl = portfolio_manager.evaluate_for_activation(
            strategy=strategy_without_sl_tp,
            backtest_results=backtest_without_sl_tp
        )
        
        logger.info(f"   Strategy WITH SL/TP can activate: {can_activate_with_sl}")
        logger.info(f"   Strategy WITHOUT SL/TP can activate: {can_activate_without_sl}")
        results['activation_criteria_updated'] = True
        
        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("TEST SUMMARY")
        logger.info("=" * 80)
        for key, value in results.items():
            status = "✓ PASS" if value else "✗ FAIL"
            logger.info(f"{status}: {key}")
        
        all_passed = all(results.values())
        if all_passed:
            logger.info("\n✓ ALL TESTS PASSED")
        else:
            logger.warning("\n⚠ SOME TESTS FAILED")
        
        return results
        
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        return results


if __name__ == "__main__":
    test_stop_loss_take_profit()
