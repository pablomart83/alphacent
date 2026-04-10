"""Debug test for Z-Score Mean Reversion strategy."""

import logging
from src.strategy.strategy_templates import StrategyTemplateLibrary
from src.strategy.trading_dsl import TradingDSLParser, DSLCodeGenerator

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get the Z-Score template
template_library = StrategyTemplateLibrary()
template = template_library.get_template_by_name("Z-Score Mean Reversion")

logger.info(f"Template: {template.name}")
logger.info(f"Entry conditions: {template.entry_conditions}")
logger.info(f"Exit conditions: {template.exit_conditions}")
logger.info(f"Required indicators: {template.required_indicators}")

# Test parsing the entry condition
parser = TradingDSLParser()
code_gen = DSLCodeGenerator()

for i, condition in enumerate(template.entry_conditions):
    logger.info(f"\n=== Testing Entry Condition {i+1}: {condition} ===")
    try:
        result = parser.parse(condition)
        if result.success:
            logger.info(f"✓ Parsed successfully")
            logger.info(f"AST: {result.ast}")
            
            # Try to generate code
            code_result = code_gen.generate_code(result.ast)
            if code_result.success:
                logger.info(f"✓ Code generated: {code_result.code}")
                logger.info(f"Required indicators: {code_result.required_indicators}")
            else:
                logger.error(f"✗ Code generation failed: {code_result.error}")
        else:
            logger.error(f"✗ Parse failed: {result.error}")
    except Exception as e:
        logger.error(f"✗ Exception: {e}")

for i, condition in enumerate(template.exit_conditions):
    logger.info(f"\n=== Testing Exit Condition {i+1}: {condition} ===")
    try:
        result = parser.parse(condition)
        if result.success:
            logger.info(f"✓ Parsed successfully")
            logger.info(f"AST: {result.ast}")
            
            # Try to generate code
            code_result = code_gen.generate_code(result.ast)
            if code_result.success:
                logger.info(f"✓ Code generated: {code_result.code}")
                logger.info(f"Required indicators: {code_result.required_indicators}")
            else:
                logger.error(f"✗ Code generation failed: {code_result.error}")
        else:
            logger.error(f"✗ Parse failed: {result.error}")
    except Exception as e:
        logger.error(f"✗ Exception: {e}")
