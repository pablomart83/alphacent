"""Test all problematic templates."""

import logging
from src.strategy.strategy_templates import StrategyTemplateLibrary
from src.strategy.trading_dsl import TradingDSLParser, DSLCodeGenerator

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get the templates
template_library = StrategyTemplateLibrary()
problematic_templates = [
    "Z-Score Mean Reversion",
    "Bollinger Squeeze Breakout",
    "ATR Expansion Breakout",
    "Price Breakout",
    "ATR Volatility Breakout"
]

parser = TradingDSLParser()
code_gen = DSLCodeGenerator()

for template_name in problematic_templates:
    template = template_library.get_template_by_name(template_name)
    logger.info(f"\n{'='*80}")
    logger.info(f"Template: {template.name}")
    logger.info(f"Entry conditions: {template.entry_conditions}")
    logger.info(f"Exit conditions: {template.exit_conditions}")
    
    all_pass = True
    
    for i, condition in enumerate(template.entry_conditions):
        try:
            result = parser.parse(condition)
            if result.success:
                code_result = code_gen.generate_code(result.ast)
                if code_result.success:
                    logger.info(f"✓ Entry {i+1} OK: {code_result.code[:80]}...")
                else:
                    logger.error(f"✗ Entry {i+1} code gen failed: {code_result.error}")
                    all_pass = False
            else:
                logger.error(f"✗ Entry {i+1} parse failed: {result.error}")
                all_pass = False
        except Exception as e:
            logger.error(f"✗ Entry {i+1} exception: {e}")
            all_pass = False
    
    for i, condition in enumerate(template.exit_conditions):
        try:
            result = parser.parse(condition)
            if result.success:
                code_result = code_gen.generate_code(result.ast)
                if code_result.success:
                    logger.info(f"✓ Exit {i+1} OK: {code_result.code[:80]}...")
                else:
                    logger.error(f"✗ Exit {i+1} code gen failed: {code_result.error}")
                    all_pass = False
            else:
                logger.error(f"✗ Exit {i+1} parse failed: {result.error}")
                all_pass = False
        except Exception as e:
            logger.error(f"✗ Exit {i+1} exception: {e}")
            all_pass = False
    
    if all_pass:
        logger.info(f"✅ {template.name}: ALL CONDITIONS PASS")
    else:
        logger.error(f"❌ {template.name}: SOME CONDITIONS FAIL")
