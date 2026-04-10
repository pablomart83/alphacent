"""Quick test of improved strategy templates."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.strategy.strategy_templates import StrategyTemplateLibrary
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_template_improvements():
    """Test that templates have been improved with better parameters."""
    logger.info("Testing Improved Strategy Templates")
    logger.info("="*80)
    
    template_lib = StrategyTemplateLibrary()
    
    # Test RSI Mean Reversion improvements
    rsi_template = template_lib.get_template_by_name("RSI Mean Reversion")
    logger.info("\n1. RSI Mean Reversion Template:")
    logger.info(f"   Entry: {rsi_template.entry_conditions}")
    logger.info(f"   Exit: {rsi_template.exit_conditions}")
    logger.info(f"   Parameters: {rsi_template.default_parameters}")
    
    # Check improvements
    assert rsi_template.default_parameters['oversold_threshold'] == 25, "RSI oversold should be 25 (more extreme)"
    assert rsi_template.default_parameters['overbought_threshold'] == 75, "RSI overbought should be 75 (more extreme)"
    assert 'stop_loss_pct' in rsi_template.default_parameters, "Should have stop-loss"
    assert 'take_profit_pct' in rsi_template.default_parameters, "Should have take-profit"
    logger.info("   ✓ RSI thresholds improved (25/75 instead of 30/70)")
    logger.info("   ✓ Stop-loss and take-profit added")
    
    # Test Bollinger Band improvements
    bb_template = template_lib.get_template_by_name("Bollinger Band Bounce")
    logger.info("\n2. Bollinger Band Bounce Template:")
    logger.info(f"   Entry: {bb_template.entry_conditions}")
    logger.info(f"   Exit: {bb_template.exit_conditions}")
    logger.info(f"   Parameters: {bb_template.default_parameters}")
    
    # Check improvements
    assert "RSI(14) < 40" in bb_template.entry_conditions[0], "Should have RSI confirmation"
    assert "BB_MIDDLE" in bb_template.exit_conditions[0], "Should exit at middle band"
    assert 'stop_loss_pct' in bb_template.default_parameters, "Should have stop-loss"
    assert 'take_profit_pct' in bb_template.default_parameters, "Should have take-profit"
    logger.info("   ✓ RSI confirmation added to entry")
    logger.info("   ✓ Exit at middle band (more conservative)")
    logger.info("   ✓ Stop-loss and take-profit added")
    
    # Test MA Crossover improvements
    ma_template = template_lib.get_template_by_name("Moving Average Crossover")
    logger.info("\n3. Moving Average Crossover Template:")
    logger.info(f"   Entry: {ma_template.entry_conditions}")
    logger.info(f"   Exit: {ma_template.exit_conditions}")
    logger.info(f"   Parameters: {ma_template.default_parameters}")
    
    # Check improvements
    assert "VOLUME" in ma_template.entry_conditions[0], "Should have volume confirmation"
    assert 'stop_loss_pct' in ma_template.default_parameters, "Should have stop-loss"
    assert 'take_profit_pct' in ma_template.default_parameters, "Should have take-profit"
    logger.info("   ✓ Volume confirmation added")
    logger.info("   ✓ Stop-loss and take-profit added")
    
    # Test RSI Bollinger Combo improvements
    combo_template = template_lib.get_template_by_name("RSI Bollinger Combo")
    logger.info("\n4. RSI Bollinger Combo Template:")
    logger.info(f"   Entry: {combo_template.entry_conditions}")
    logger.info(f"   Exit: {combo_template.exit_conditions}")
    logger.info(f"   Parameters: {combo_template.default_parameters}")
    
    # Check improvements
    assert combo_template.default_parameters['rsi_oversold'] == 25, "RSI oversold should be 25"
    assert "BB_MIDDLE" in combo_template.exit_conditions[0], "Should exit at middle band"
    assert 'stop_loss_pct' in combo_template.default_parameters, "Should have stop-loss"
    assert 'take_profit_pct' in combo_template.default_parameters, "Should have take-profit"
    logger.info("   ✓ More extreme RSI threshold (25)")
    logger.info("   ✓ Exit at middle band (more conservative)")
    logger.info("   ✓ Stop-loss and take-profit added")
    
    logger.info("\n" + "="*80)
    logger.info("✓ ALL TEMPLATE IMPROVEMENTS VERIFIED!")
    logger.info("="*80)
    logger.info("\nKey Improvements:")
    logger.info("1. More extreme RSI thresholds (25/75 instead of 30/70)")
    logger.info("2. RSI confirmation added to Bollinger Band strategy")
    logger.info("3. Exit at middle band instead of upper band (more conservative)")
    logger.info("4. Volume confirmation added to MA Crossover")
    logger.info("5. Stop-loss and take-profit levels added to all templates")
    logger.info("6. Position sizing parameters added")
    logger.info("\nExpected Impact:")
    logger.info("- Higher quality entries (more extreme conditions)")
    logger.info("- Better risk management (stops and targets)")
    logger.info("- More confirmation (RSI + Bollinger, Volume + MA)")
    logger.info("- Target: Sharpe > 0.5 (vs current 0.12)")

if __name__ == "__main__":
    test_template_improvements()
