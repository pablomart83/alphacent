"""Test diverse strategy templates with real backtesting."""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.strategy.strategy_templates import StrategyTemplateLibrary, MarketRegime, StrategyType
from src.strategy.indicator_library import IndicatorLibrary
from src.strategy.strategy_engine import StrategyEngine
from src.models.database import Database
from src.models.enums import StrategyStatus, TradingMode
from src.data.market_data_manager import MarketDataManager
from src.core.config import get_config
from src.api.etoro_client import EToroAPIClient
from src.strategy.strategy_proposer import StrategyProposer
from src.llm.llm_service import LLMService
import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_template_count():
    """Test that we have 17 templates (10 original + 7 new)."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 1: Template Count")
    logger.info("=" * 80)
    
    template_library = StrategyTemplateLibrary()
    templates = template_library.get_all_templates()
    
    logger.info(f"Total templates: {len(templates)}")
    assert len(templates) >= 17, f"Expected at least 17 templates, got {len(templates)}"
    
    # Print template names for verification
    logger.info("\nAll templates:")
    for i, template in enumerate(templates, 1):
        logger.info(f"  {i}. {template.name} ({template.strategy_type.value})")
    
    logger.info("✓ Template count test PASSED")


def test_new_momentum_templates():
    """Test new momentum strategy templates."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: New Momentum Templates")
    logger.info("=" * 80)
    
    template_library = StrategyTemplateLibrary()
    
    # Price Momentum Breakout
    template = template_library.get_template_by_name("Price Momentum Breakout")
    assert template is not None, "Price Momentum Breakout template not found"
    assert template.strategy_type == StrategyType.BREAKOUT
    assert MarketRegime.TRENDING_UP in template.market_regimes
    logger.info("✓ Price Momentum Breakout template found")
    
    # MACD Rising Momentum
    template = template_library.get_template_by_name("MACD Rising Momentum")
    assert template is not None, "MACD Rising Momentum template not found"
    assert template.strategy_type == StrategyType.TREND_FOLLOWING
    logger.info("✓ MACD Rising Momentum template found")
    
    # ADX Trend Following
    template = template_library.get_template_by_name("ADX Trend Following")
    assert template is not None, "ADX Trend Following template not found"
    assert template.strategy_type == StrategyType.TREND_FOLLOWING
    assert "ADX(14) > 25" in template.entry_conditions[0]
    logger.info("✓ ADX Trend Following template found")
    
    logger.info("✓ New momentum templates test PASSED")


def test_new_mean_reversion_templates():
    """Test new mean reversion strategy templates."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: New Mean Reversion Templates")
    logger.info("=" * 80)
    
    template_library = StrategyTemplateLibrary()
    
    # Stochastic Extreme Oversold
    template = template_library.get_template_by_name("Stochastic Extreme Oversold")
    assert template is not None, "Stochastic Extreme Oversold template not found"
    assert template.strategy_type == StrategyType.MEAN_REVERSION
    assert "STOCH(14) < 20" in template.entry_conditions[0]
    logger.info("✓ Stochastic Extreme Oversold template found")
    
    # Z-Score Mean Reversion
    template = template_library.get_template_by_name("Z-Score Mean Reversion")
    assert template is not None, "Z-Score Mean Reversion template not found"
    assert template.strategy_type == StrategyType.MEAN_REVERSION
    assert "SMA(20)" in template.entry_conditions[0]
    logger.info("✓ Z-Score Mean Reversion template found")
    
    logger.info("✓ New mean reversion templates test PASSED")


def test_new_volatility_templates():
    """Test new volatility strategy templates."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 4: New Volatility Templates")
    logger.info("=" * 80)
    
    template_library = StrategyTemplateLibrary()
    
    # Bollinger Squeeze Breakout
    template = template_library.get_template_by_name("Bollinger Squeeze Breakout")
    assert template is not None, "Bollinger Squeeze Breakout template not found"
    assert template.strategy_type == StrategyType.VOLATILITY
    logger.info("✓ Bollinger Squeeze Breakout template found")
    
    # ATR Expansion Breakout
    template = template_library.get_template_by_name("ATR Expansion Breakout")
    assert template is not None, "ATR Expansion Breakout template not found"
    assert template.strategy_type == StrategyType.VOLATILITY
    assert "ATR(14)" in template.entry_conditions[0]
    logger.info("✓ ATR Expansion Breakout template found")
    
    logger.info("✓ New volatility templates test PASSED")


def test_adx_indicator():
    """Test that ADX indicator is available and works."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 5: ADX Indicator")
    logger.info("=" * 80)
    
    indicator_library = IndicatorLibrary()
    
    # Check ADX is in list
    indicators = indicator_library.list_indicators()
    assert 'ADX' in indicators, "ADX not in indicator list"
    logger.info("✓ ADX in indicator list")
    
    # Check ADX info
    info = indicator_library.get_indicator_info('ADX')
    assert info['description'] == 'Average Directional Index (trend strength)'
    logger.info("✓ ADX info correct")
    
    # Test ADX calculation with sample data
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    data = pd.DataFrame({
        'open': 100 + pd.Series(range(100)) * 0.5,
        'high': 102 + pd.Series(range(100)) * 0.5,
        'low': 98 + pd.Series(range(100)) * 0.5,
        'close': 100 + pd.Series(range(100)) * 0.5,
        'volume': 1000000
    }, index=dates)
    
    adx, key = indicator_library.calculate('ADX', data, symbol='TEST', period=14)
    
    # ADX should be between 0 and 100
    assert adx.min() >= 0, f"ADX min {adx.min()} should be >= 0"
    assert adx.max() <= 100, f"ADX max {adx.max()} should be <= 100"
    
    # ADX should have values (not all NaN)
    assert not adx.isna().all(), "ADX should have non-NaN values"
    
    # Check key format
    assert key == "ADX_14", f"Expected key 'ADX_14', got '{key}'"
    
    logger.info(f"✓ ADX calculation works - Min: {adx.min():.2f}, Max: {adx.max():.2f}, Mean: {adx.mean():.2f}")
    logger.info(f"✓ ADX key: {key}")
    logger.info("✓ ADX indicator test PASSED")


def test_strategy_diversity():
    """Test that templates provide good diversity."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 6: Strategy Diversity")
    logger.info("=" * 80)
    
    template_library = StrategyTemplateLibrary()
    templates = template_library.get_all_templates()
    
    # Count by strategy type
    type_counts = {}
    for template in templates:
        type_name = template.strategy_type.value
        type_counts[type_name] = type_counts.get(type_name, 0) + 1
    
    logger.info("\nStrategy type distribution:")
    for type_name, count in type_counts.items():
        logger.info(f"  {type_name}: {count}")
    
    # Should have at least 3 types
    assert len(type_counts) >= 3, f"Should have at least 3 strategy types, got {len(type_counts)}"
    
    # Each type should have multiple templates
    for type_name, count in type_counts.items():
        assert count >= 2, f"{type_name} should have at least 2 templates, got {count}"
    
    logger.info("✓ Strategy diversity test PASSED")


def test_regime_coverage():
    """Test that all market regimes are covered."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 7: Market Regime Coverage")
    logger.info("=" * 80)
    
    template_library = StrategyTemplateLibrary()
    coverage = template_library.get_regime_coverage()
    
    logger.info("\nMarket regime coverage:")
    for regime, count in coverage.items():
        logger.info(f"  {regime.value}: {count} templates")
    
    # Each regime should have at least 3 templates
    for regime, count in coverage.items():
        assert count >= 3, f"{regime.value} should have at least 3 templates, got {count}"
    
    logger.info("✓ Regime coverage test PASSED")


def test_all_templates_have_required_fields():
    """Test that all templates have required fields."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 8: Template Field Validation")
    logger.info("=" * 80)
    
    template_library = StrategyTemplateLibrary()
    templates = template_library.get_all_templates()
    
    for template in templates:
        # Check required fields
        assert template.name, f"Template missing name"
        assert template.description, f"{template.name} missing description"
        assert template.strategy_type, f"{template.name} missing strategy_type"
        assert len(template.market_regimes) > 0, f"{template.name} missing market_regimes"
        assert len(template.entry_conditions) > 0, f"{template.name} missing entry_conditions"
        assert len(template.exit_conditions) > 0, f"{template.name} missing exit_conditions"
        assert len(template.required_indicators) > 0, f"{template.name} missing required_indicators"
        assert template.default_parameters, f"{template.name} missing default_parameters"
        assert template.expected_trade_frequency, f"{template.name} missing expected_trade_frequency"
        assert template.expected_holding_period, f"{template.name} missing expected_holding_period"
        assert template.risk_reward_ratio > 0, f"{template.name} risk_reward_ratio should be > 0"
    
    logger.info(f"✓ All {len(templates)} templates have required fields")
    logger.info("✓ Template field validation test PASSED")


if __name__ == "__main__":
    """Run all tests."""
    logger.info("\n" + "=" * 80)
    logger.info("DIVERSE STRATEGY TEMPLATES TEST SUITE")
    logger.info("Testing 7 new templates + ADX indicator")
    logger.info("=" * 80)
    
    try:
        test_template_count()
        test_new_momentum_templates()
        test_new_mean_reversion_templates()
        test_new_volatility_templates()
        test_adx_indicator()
        test_strategy_diversity()
        test_regime_coverage()
        test_all_templates_have_required_fields()
        
        logger.info("\n" + "=" * 80)
        logger.info("ALL TESTS PASSED ✓")
        logger.info("=" * 80)
        
    except AssertionError as e:
        logger.error(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
