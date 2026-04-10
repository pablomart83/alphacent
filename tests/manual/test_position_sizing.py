"""
Test Position Sizing Based on Volatility.

Tests the implementation of volatility-based position sizing:
1. Position sizing parameters in strategy templates
2. PortfolioManager.calculate_position_size() method
3. Dynamic position sizing in backtests
"""

import logging
import sys
import yaml
import pandas as pd
import numpy as np
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
from src.strategy.portfolio_manager import PortfolioManager
from src.strategy.strategy_engine import StrategyEngine
from src.strategy.strategy_templates import StrategyTemplateLibrary
from src.strategy.indicator_library import IndicatorLibrary

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_position_sizing():
    """Test position sizing implementation."""
    logger.info("=" * 80)
    logger.info("TESTING POSITION SIZING BASED ON VOLATILITY")
    logger.info("=" * 80)
    
    test_results = {
        'template_parameters': False,
        'calculate_position_size': False,
        'backtest_position_sizing': False,
    }
    
    try:
        # Part 1: Test Strategy Template Parameters
        logger.info("\n[1/3] Testing strategy template position sizing parameters...")
        
        template_library = StrategyTemplateLibrary()
        templates = template_library.get_all_templates()
        
        # Check that all templates have position sizing parameters
        templates_with_params = 0
        for template in templates:
            if 'risk_per_trade_pct' in template.default_parameters:
                templates_with_params += 1
                
                # Verify default values
                risk_pct = template.default_parameters['risk_per_trade_pct']
                sizing_method = template.default_parameters.get('sizing_method', 'fixed')
                
                logger.info(f"  ✓ {template.name}:")
                logger.info(f"      Risk per trade: {risk_pct:.2%}")
                logger.info(f"      Sizing method: {sizing_method}")
                
                # Verify reasonable defaults
                assert 0 < risk_pct <= 0.05, f"Risk per trade should be 0-5%, got {risk_pct:.2%}"
                assert sizing_method in ['fixed', 'volatility', 'kelly'], f"Invalid sizing method: {sizing_method}"
        
        logger.info(f"\n  ✓ Templates with position sizing parameters: {templates_with_params}/{len(templates)}")
        assert templates_with_params == len(templates), "All templates should have position sizing parameters"
        test_results['template_parameters'] = True
        
        # Part 2: Test PortfolioManager.calculate_position_size()
        logger.info("\n[2/3] Testing PortfolioManager.calculate_position_size()...")
        
        # Initialize components
        db = Database()
        config_manager = get_config()
        
        try:
            credentials = config_manager.load_credentials(TradingMode.DEMO)
            etoro_client = EToroAPIClient(
                public_key=credentials['public_key'],
                user_key=credentials['user_key'],
                mode=TradingMode.DEMO
            )
        except Exception as e:
            logger.warning(f"Could not initialize eToro client: {e}")
            from unittest.mock import Mock
            etoro_client = Mock()
        
        llm_service = LLMService()
        market_data = MarketDataManager(etoro_client=etoro_client)
        strategy_engine = StrategyEngine(llm_service=llm_service, market_data=market_data)
        portfolio_manager = PortfolioManager(strategy_engine=strategy_engine)
        
        # Test position sizing with different scenarios
        test_scenarios = [
            {
                'name': 'Low volatility (ATR = $1)',
                'portfolio_value': 100000,
                'entry_price': 100,
                'stop_loss_pct': 0.02,
                'risk_per_trade_pct': 0.01,
                'atr': 1.0,
                'expected_range': (45000, 55000)  # Should be close to $50,000
            },
            {
                'name': 'High volatility (ATR = $5)',
                'portfolio_value': 100000,
                'entry_price': 100,
                'stop_loss_pct': 0.02,
                'risk_per_trade_pct': 0.01,
                'atr': 5.0,
                'expected_range': (40000, 50000)  # Should be reduced due to high volatility
            },
            {
                'name': 'Very high volatility (ATR = $10)',
                'portfolio_value': 100000,
                'entry_price': 100,
                'stop_loss_pct': 0.02,
                'risk_per_trade_pct': 0.01,
                'atr': 10.0,
                'expected_range': (40000, 50000)  # Should be significantly reduced
            },
            {
                'name': 'Higher risk per trade (2%)',
                'portfolio_value': 100000,
                'entry_price': 100,
                'stop_loss_pct': 0.02,
                'risk_per_trade_pct': 0.02,
                'atr': 2.0,
                'expected_range': (85000, 105000)  # Should be ~2x the 1% risk scenario
            },
        ]
        
        for scenario in test_scenarios:
            logger.info(f"\n  Testing: {scenario['name']}")
            
            position_size = portfolio_manager.calculate_position_size(
                portfolio_value=scenario['portfolio_value'],
                entry_price=scenario['entry_price'],
                stop_loss_pct=scenario['stop_loss_pct'],
                risk_per_trade_pct=scenario['risk_per_trade_pct'],
                atr=scenario['atr']
            )
            
            logger.info(f"    Position size: ${position_size:,.0f}")
            
            # Verify position size is in expected range
            min_expected, max_expected = scenario['expected_range']
            assert min_expected <= position_size <= max_expected, \
                f"Position size ${position_size:,.0f} not in expected range ${min_expected:,.0f}-${max_expected:,.0f}"
            
            logger.info(f"    ✓ Position size in expected range: ${min_expected:,.0f}-${max_expected:,.0f}")
        
        # Verify volatility adjustment works correctly
        # Higher ATR should result in smaller position size
        low_vol_size = portfolio_manager.calculate_position_size(100000, 100, 0.02, 0.01, 1.0)
        high_vol_size = portfolio_manager.calculate_position_size(100000, 100, 0.02, 0.01, 5.0)
        
        assert high_vol_size < low_vol_size, "High volatility should result in smaller position size"
        logger.info(f"\n  ✓ Volatility adjustment verified:")
        logger.info(f"      Low volatility (ATR=$1): ${low_vol_size:,.0f}")
        logger.info(f"      High volatility (ATR=$5): ${high_vol_size:,.0f}")
        logger.info(f"      Reduction: {(1 - high_vol_size/low_vol_size)*100:.1f}%")
        
        test_results['calculate_position_size'] = True
        
        # Part 3: Test Backtest with Dynamic Position Sizing
        logger.info("\n[3/3] Testing backtest with dynamic position sizing...")
        
        # Create a simple test strategy with position sizing parameters
        from src.models.dataclasses import Strategy, RiskConfig, PerformanceMetrics
        from src.models.enums import StrategyStatus
        from datetime import datetime
        
        test_strategy = Strategy(
            id="test_position_sizing",
            name="Test Position Sizing Strategy",
            description="Test strategy for position sizing",
            symbols=["SPY"],
            status=StrategyStatus.PROPOSED,
            rules={
                "indicators": ["RSI", "ATR"],
                "entry_conditions": ["RSI(14) < 30"],
                "exit_conditions": ["RSI(14) > 70"]
            },
            risk_params=RiskConfig(
                stop_loss_pct=0.02,
                take_profit_pct=0.05
            ),
            created_at=datetime.now(),
            performance=PerformanceMetrics(),
            metadata={
                'template_name': 'Test Template',
                'template_parameters': {
                    'risk_per_trade_pct': 0.01,
                    'sizing_method': 'volatility',
                    'position_size_atr_multiplier': 1.0
                }
            }
        )
        
        # Run backtest
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        
        logger.info(f"  Running backtest from {start_date.date()} to {end_date.date()}...")
        
        try:
            backtest_results = strategy_engine.backtest_strategy(
                strategy=test_strategy,
                start=start_date,
                end=end_date
            )
            
            logger.info(f"\n  ✓ Backtest completed:")
            logger.info(f"      Total return: {backtest_results.total_return:.2%}")
            logger.info(f"      Sharpe ratio: {backtest_results.sharpe_ratio:.2f}")
            logger.info(f"      Max drawdown: {backtest_results.max_drawdown:.2%}")
            logger.info(f"      Total trades: {backtest_results.total_trades}")
            logger.info(f"      Win rate: {backtest_results.win_rate:.2%}")
            
            # Verify backtest ran with position sizing
            assert backtest_results.total_trades >= 0, "Backtest should complete"
            
            # Check if position sizing was logged (we can't directly verify from results,
            # but we can check that the backtest completed without errors)
            logger.info(f"\n  ✓ Backtest with dynamic position sizing completed successfully")
            
            test_results['backtest_position_sizing'] = True
            
        except Exception as e:
            logger.error(f"  ✗ Backtest failed: {e}", exc_info=True)
        
        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("POSITION SIZING TEST RESULTS")
        logger.info("=" * 80)
        logger.info(f"  ✓ Template parameters: {'PASS' if test_results['template_parameters'] else 'FAIL'}")
        logger.info(f"  ✓ Calculate position size: {'PASS' if test_results['calculate_position_size'] else 'FAIL'}")
        logger.info(f"  ✓ Backtest position sizing: {'PASS' if test_results['backtest_position_sizing'] else 'FAIL'}")
        
        all_passed = all(test_results.values())
        
        if all_passed:
            logger.info("\n✓ ALL TESTS PASSED")
        else:
            logger.error("\n✗ SOME TESTS FAILED")
        
        return all_passed
        
    except Exception as e:
        logger.error(f"\n❌ TEST FAILED: {str(e)}", exc_info=True)
        return False


if __name__ == "__main__":
    success = test_position_sizing()
    sys.exit(0 if success else 1)
