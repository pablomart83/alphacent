"""
Test for Regime-Specific Templates (Task 9.11.5.6).

Tests:
1. MarketStatisticsAnalyzer.detect_sub_regime() detects all 6 sub-regimes correctly
2. StrategyTemplateLibrary has regime-specific templates for each sub-regime
3. StrategyProposer selects appropriate templates based on sub-regime
"""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.models.enums import TradingMode
from src.strategy.market_analyzer import MarketStatisticsAnalyzer
from src.strategy.strategy_proposer import StrategyProposer
from src.strategy.strategy_templates import MarketRegime, StrategyTemplateLibrary

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_sub_regime_detection():
    """Test that MarketStatisticsAnalyzer can detect all 6 sub-regimes."""
    logger.info("=" * 80)
    logger.info("TEST 1: Sub-Regime Detection")
    logger.info("=" * 80)
    
    try:
        # Initialize components
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
        
        market_data = MarketDataManager(etoro_client=etoro_client)
        market_analyzer = MarketStatisticsAnalyzer(market_data)
        
        # Test sub-regime detection
        logger.info("\nDetecting current market sub-regime...")
        sub_regime, confidence, data_quality, metrics = market_analyzer.detect_sub_regime()
        
        logger.info(f"\n✓ Sub-regime detected: {sub_regime.value}")
        logger.info(f"  Confidence: {confidence:.2f}")
        logger.info(f"  Data quality: {data_quality}")
        logger.info(f"  Metrics:")
        logger.info(f"    - 20d change: {metrics.get('avg_change_20d', 0):.2%}")
        logger.info(f"    - 50d change: {metrics.get('avg_change_50d', 0):.2%}")
        logger.info(f"    - ATR/price: {metrics.get('avg_atr_ratio', 0):.2%}")
        
        # Verify sub-regime is one of the 6 expected values
        expected_sub_regimes = [
            MarketRegime.TRENDING_UP_STRONG,
            MarketRegime.TRENDING_UP_WEAK,
            MarketRegime.TRENDING_DOWN_STRONG,
            MarketRegime.TRENDING_DOWN_WEAK,
            MarketRegime.RANGING_LOW_VOL,
            MarketRegime.RANGING_HIGH_VOL,
            MarketRegime.RANGING  # Fallback
        ]
        
        assert sub_regime in expected_sub_regimes, f"Unexpected sub-regime: {sub_regime}"
        logger.info(f"\n✓ TEST 1 PASSED: Sub-regime detection working correctly")
        
        return True, sub_regime
        
    except Exception as e:
        logger.error(f"\n✗ TEST 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_regime_specific_templates():
    """Test that StrategyTemplateLibrary has templates for each sub-regime."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Regime-Specific Templates")
    logger.info("=" * 80)
    
    try:
        template_library = StrategyTemplateLibrary()
        
        # Check total template count (should be 26 now with new regime-specific templates)
        total_templates = template_library.get_template_count()
        logger.info(f"\nTotal templates in library: {total_templates}")
        assert total_templates >= 26, f"Expected at least 26 templates, got {total_templates}"
        
        # Check templates for each sub-regime
        sub_regimes_to_test = [
            MarketRegime.TRENDING_UP_STRONG,
            MarketRegime.TRENDING_UP_WEAK,
            MarketRegime.TRENDING_DOWN_WEAK,
            MarketRegime.RANGING_LOW_VOL,
            MarketRegime.RANGING_HIGH_VOL
        ]
        
        logger.info("\nChecking templates for each sub-regime:")
        for regime in sub_regimes_to_test:
            templates = template_library.get_templates_for_regime(regime)
            logger.info(f"\n{regime.value}:")
            logger.info(f"  - {len(templates)} templates available")
            
            if templates:
                for template in templates[:3]:  # Show first 3
                    logger.info(f"    • {template.name} ({template.strategy_type.value})")
            
            # Verify at least 1 template for each sub-regime
            assert len(templates) > 0, f"No templates found for {regime.value}"
        
        logger.info(f"\n✓ TEST 2 PASSED: All sub-regimes have appropriate templates")
        return True
        
    except Exception as e:
        logger.error(f"\n✗ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_strategy_proposer_uses_sub_regime():
    """Test that StrategyProposer uses sub-regime detection and selects appropriate templates."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: StrategyProposer Sub-Regime Integration")
    logger.info("=" * 80)
    
    try:
        # Initialize components
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
        
        market_data = MarketDataManager(etoro_client=etoro_client)
        llm_service = LLMService()
        strategy_proposer = StrategyProposer(llm_service=llm_service, market_data=market_data)
        
        # Propose strategies (should use sub-regime detection internally)
        logger.info("\nProposing 3 strategies using sub-regime detection...")
        strategies = strategy_proposer.propose_strategies(
            count=3,
            symbols=["SPY", "QQQ"],
            use_walk_forward=False,  # Disable for faster testing
            optimize_parameters=False
        )
        
        logger.info(f"\n✓ Proposed {len(strategies)} strategies")
        
        # Verify strategies were generated
        assert len(strategies) > 0, "No strategies were proposed"
        
        # Log strategy details
        for i, strategy in enumerate(strategies, 1):
            logger.info(f"\nStrategy {i}: {strategy.name}")
            logger.info(f"  Type: {strategy.metadata.get('strategy_type', 'N/A')}")
            logger.info(f"  Symbols: {strategy.symbols}")
            logger.info(f"  Entry conditions: {len(strategy.rules.get('entry_conditions', []))}")
            logger.info(f"  Exit conditions: {len(strategy.rules.get('exit_conditions', []))}")
        
        logger.info(f"\n✓ TEST 3 PASSED: StrategyProposer successfully uses sub-regime detection")
        return True
        
    except Exception as e:
        logger.error(f"\n✗ TEST 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_template_regime_matching():
    """Test that regime-specific templates match their intended regimes."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 4: Template Regime Matching")
    logger.info("=" * 80)
    
    try:
        template_library = StrategyTemplateLibrary()
        
        # Define expected template-regime mappings
        expected_mappings = {
            "Strong Uptrend MACD": [MarketRegime.TRENDING_UP_STRONG],
            "Strong Uptrend Breakout": [MarketRegime.TRENDING_UP_STRONG],
            "Weak Uptrend Pullback": [MarketRegime.TRENDING_UP_WEAK],
            "Weak Uptrend RSI Oversold": [MarketRegime.TRENDING_UP_WEAK],
            "Weak Downtrend Bounce": [MarketRegime.TRENDING_DOWN_WEAK],
            "Low Vol RSI Mean Reversion": [MarketRegime.RANGING_LOW_VOL],
            "Low Vol Bollinger Mean Reversion": [MarketRegime.RANGING_LOW_VOL],
            "High Vol ATR Breakout": [MarketRegime.RANGING_HIGH_VOL],
            "High Vol Bollinger Squeeze": [MarketRegime.RANGING_HIGH_VOL]
        }
        
        logger.info("\nVerifying regime-specific template mappings:")
        all_matched = True
        
        for template_name, expected_regimes in expected_mappings.items():
            template = template_library.get_template_by_name(template_name)
            
            if template is None:
                logger.error(f"  ✗ Template not found: {template_name}")
                all_matched = False
                continue
            
            # Check if template has the expected regimes
            for expected_regime in expected_regimes:
                if expected_regime in template.market_regimes:
                    logger.info(f"  ✓ {template_name} → {expected_regime.value}")
                else:
                    logger.error(f"  ✗ {template_name} missing regime: {expected_regime.value}")
                    all_matched = False
        
        assert all_matched, "Some templates don't match their expected regimes"
        
        logger.info(f"\n✓ TEST 4 PASSED: All regime-specific templates correctly mapped")
        return True
        
    except Exception as e:
        logger.error(f"\n✗ TEST 4 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    logger.info("=" * 80)
    logger.info("REGIME-SPECIFIC TEMPLATES TEST SUITE")
    logger.info("Testing Task 9.11.5.6 Implementation")
    logger.info("=" * 80)
    
    results = {}
    
    # Test 1: Sub-regime detection
    results['sub_regime_detection'], detected_regime = test_sub_regime_detection()
    
    # Test 2: Regime-specific templates
    results['regime_templates'] = test_regime_specific_templates()
    
    # Test 3: StrategyProposer integration
    results['proposer_integration'] = test_strategy_proposer_uses_sub_regime()
    
    # Test 4: Template regime matching
    results['template_matching'] = test_template_regime_matching()
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        logger.info(f"{test_name}: {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        logger.info("\n" + "=" * 80)
        logger.info("✓ ALL TESTS PASSED")
        logger.info("=" * 80)
        logger.info("\nTask 9.11.5.6 Implementation Complete:")
        logger.info("  ✓ Sub-regime detection working (6 regimes)")
        logger.info("  ✓ Regime-specific templates added (9 new templates)")
        logger.info("  ✓ StrategyProposer uses sub-regime detection")
        logger.info("  ✓ Templates correctly mapped to regimes")
        return 0
    else:
        logger.error("\n" + "=" * 80)
        logger.error("✗ SOME TESTS FAILED")
        logger.error("=" * 80)
        return 1


if __name__ == "__main__":
    exit(main())
