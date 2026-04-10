"""Test improved strategy templates individually."""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime, timedelta
from src.strategy.strategy_templates import StrategyTemplateLibrary, MarketRegime
from src.strategy.strategy_proposer import StrategyProposer
from src.strategy.strategy_engine import StrategyEngine
from src.data.market_data_manager import MarketDataManager
from src.api.etoro_client import EToroAPIClient
from src.models.database import Database
from src.models.dataclasses import Strategy
from src.models.enums import StrategyStatus
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_template_individually(template_name: str):
    """Test a single template with 90-day backtest."""
    logger.info(f"\n{'='*80}")
    logger.info(f"Testing Template: {template_name}")
    logger.info(f"{'='*80}")
    
    # Initialize components
    db = Database()
    api_client = EToroAPIClient()
    market_data = MarketDataManager(api_client)
    strategy_engine = StrategyEngine(db, market_data)
    
    # Get template
    template_lib = StrategyTemplateLibrary()
    template = template_lib.get_template_by_name(template_name)
    
    if not template:
        logger.error(f"Template '{template_name}' not found!")
        return None
    
    logger.info(f"Template Type: {template.strategy_type}")
    logger.info(f"Market Regimes: {template.market_regimes}")
    logger.info(f"Entry Conditions: {template.entry_conditions}")
    logger.info(f"Exit Conditions: {template.exit_conditions}")
    logger.info(f"Required Indicators: {template.required_indicators}")
    logger.info(f"Default Parameters: {template.default_parameters}")
    
    # Create strategy from template
    strategy = Strategy(
        name=template.name,
        description=template.description,
        symbols=["SPY"],  # Test with SPY
        rules={
            "entry_conditions": template.entry_conditions,
            "exit_conditions": template.exit_conditions,
            "indicators": template.required_indicators
        },
        status=StrategyStatus.PROPOSED,
        parameters=template.default_parameters
    )
    
    # Backtest for 90 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    logger.info(f"\nBacktesting from {start_date.date()} to {end_date.date()}")
    
    try:
        results = strategy_engine.backtest_strategy(
            strategy=strategy,
            start_date=start_date,
            end_date=end_date
        )
        
        logger.info(f"\n{'='*80}")
        logger.info(f"BACKTEST RESULTS for {template_name}")
        logger.info(f"{'='*80}")
        logger.info(f"Total Return: {results.total_return:.2%}")
        logger.info(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
        logger.info(f"Max Drawdown: {results.max_drawdown:.2%}")
        logger.info(f"Win Rate: {results.win_rate:.2%}")
        logger.info(f"Total Trades: {results.total_trades}")
        logger.info(f"Avg Trade Duration: {results.avg_trade_duration:.1f} days")
        
        # Check if meets target (Sharpe > 0.5)
        meets_target = results.sharpe_ratio > 0.5
        logger.info(f"\nMeets Target (Sharpe > 0.5): {'✓ YES' if meets_target else '✗ NO'}")
        
        return {
            'template_name': template_name,
            'sharpe': results.sharpe_ratio,
            'return': results.total_return,
            'drawdown': results.max_drawdown,
            'trades': results.total_trades,
            'win_rate': results.win_rate,
            'meets_target': meets_target
        }
        
    except Exception as e:
        logger.error(f"Error backtesting {template_name}: {e}", exc_info=True)
        return None

def main():
    """Test all improved templates."""
    logger.info("Testing Improved Strategy Templates")
    logger.info("="*80)
    
    # Templates to test (the ones we improved)
    templates_to_test = [
        "RSI Mean Reversion",
        "Bollinger Band Bounce",
        "RSI Bollinger Combo",
        "Moving Average Crossover"
    ]
    
    results = []
    for template_name in templates_to_test:
        result = test_template_individually(template_name)
        if result:
            results.append(result)
    
    # Summary
    logger.info(f"\n{'='*80}")
    logger.info("SUMMARY OF ALL TEMPLATES")
    logger.info(f"{'='*80}")
    logger.info(f"{'Template':<30} {'Sharpe':<10} {'Return':<10} {'Drawdown':<12} {'Trades':<8} {'Target'}")
    logger.info("-"*80)
    
    for r in results:
        target_str = "✓" if r['meets_target'] else "✗"
        logger.info(
            f"{r['template_name']:<30} "
            f"{r['sharpe']:<10.2f} "
            f"{r['return']:<10.2%} "
            f"{r['drawdown']:<12.2%} "
            f"{r['trades']:<8} "
            f"{target_str}"
        )
    
    # Overall stats
    templates_meeting_target = sum(1 for r in results if r['meets_target'])
    logger.info("-"*80)
    logger.info(f"Templates Meeting Target (Sharpe > 0.5): {templates_meeting_target}/{len(results)}")
    
    avg_sharpe = sum(r['sharpe'] for r in results) / len(results) if results else 0
    logger.info(f"Average Sharpe Ratio: {avg_sharpe:.2f}")
    
    if templates_meeting_target >= len(results) * 0.75:  # 75% should meet target
        logger.info("\n✓ SUCCESS: Most templates meet performance targets!")
    else:
        logger.info("\n✗ NEEDS IMPROVEMENT: More templates need to meet targets")

if __name__ == "__main__":
    main()
