"""
Demo: DSL Code Generator End-to-End

Shows how the DSL parser and code generator work together to convert
trading rules from natural DSL syntax to executable pandas code.
"""

import logging
from src.strategy.trading_dsl import TradingDSLParser, DSLCodeGenerator

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def demo_dsl_pipeline():
    """Demonstrate the complete DSL pipeline."""
    
    logger.info("\n" + "=" * 100)
    logger.info("DSL CODE GENERATOR DEMO")
    logger.info("=" * 100)
    logger.info("\nThis demo shows how trading rules are converted from DSL to pandas code.\n")
    
    # Initialize parser and generator
    parser = TradingDSLParser()
    generator = DSLCodeGenerator()
    
    # Example trading rules
    rules = [
        {
            "name": "Simple RSI Oversold",
            "dsl": "RSI(14) < 30",
            "description": "Entry when RSI is oversold"
        },
        {
            "name": "Price Below SMA",
            "dsl": "CLOSE < SMA(20)",
            "description": "Entry when price drops below moving average"
        },
        {
            "name": "Golden Cross",
            "dsl": "SMA(20) CROSSES_ABOVE SMA(50)",
            "description": "Entry on bullish crossover"
        },
        {
            "name": "Bollinger Band Bounce",
            "dsl": "RSI(14) < 30 AND CLOSE < BB_LOWER(20, 2)",
            "description": "Entry on oversold bounce from lower band"
        },
        {
            "name": "Multi-Indicator Confirmation",
            "dsl": "(RSI(14) < 30 OR STOCH(14) < 20) AND CLOSE < BB_LOWER(20, 2)",
            "description": "Entry with multiple oscillator confirmation"
        },
        {
            "name": "Momentum Breakout",
            "dsl": "CLOSE > SMA(20) AND VOLUME > VOLUME_MA(20)",
            "description": "Entry on volume-confirmed breakout"
        },
    ]
    
    # Process each rule
    for i, rule_info in enumerate(rules, 1):
        logger.info("=" * 100)
        logger.info(f"RULE {i}: {rule_info['name']}")
        logger.info("=" * 100)
        logger.info(f"Description: {rule_info['description']}")
        logger.info(f"DSL Input:   {rule_info['dsl']}")
        logger.info("")
        
        # Parse
        parse_result = parser.parse(rule_info['dsl'])
        if not parse_result.success:
            logger.error(f"❌ Parse failed: {parse_result.error}")
            continue
        
        logger.info("✓ Parsing successful")
        
        # Generate code
        code_result = generator.generate_code(parse_result.ast)
        if not code_result.success:
            logger.error(f"❌ Code generation failed: {code_result.error}")
            continue
        
        logger.info("✓ Code generation successful")
        logger.info("")
        logger.info("Generated Pandas Code:")
        logger.info(f"  {code_result.code}")
        logger.info("")
        logger.info("Required Indicators:")
        for indicator in code_result.required_indicators:
            logger.info(f"  - {indicator}")
        logger.info("")
    
    logger.info("=" * 100)
    logger.info("DEMO COMPLETE")
    logger.info("=" * 100)
    logger.info("\nKey Takeaways:")
    logger.info("1. DSL syntax is intuitive and readable")
    logger.info("2. Generated pandas code is correct and executable")
    logger.info("3. Required indicators are tracked automatically")
    logger.info("4. Complex logic (AND/OR/crossovers) handled correctly")
    logger.info("5. No LLM needed - 100% deterministic!")
    logger.info("=" * 100)


def demo_validation():
    """Demonstrate indicator validation."""
    
    logger.info("\n" + "=" * 100)
    logger.info("VALIDATION DEMO")
    logger.info("=" * 100)
    logger.info("\nThis demo shows how the generator validates indicator availability.\n")
    
    parser = TradingDSLParser()
    
    # Simulate available indicators
    available_indicators = ['RSI_14', 'SMA_20', 'SMA_50', 'Lower_Band_20']
    generator = DSLCodeGenerator(available_indicators=available_indicators)
    
    logger.info("Available Indicators:")
    for indicator in available_indicators:
        logger.info(f"  - {indicator}")
    logger.info("")
    
    # Test rules
    test_cases = [
        ("RSI(14) < 30", True, "Uses RSI_14 (available)"),
        ("SMA(20) CROSSES_ABOVE SMA(50)", True, "Uses SMA_20 and SMA_50 (both available)"),
        ("STOCH(14) < 20", False, "Uses STOCH_14 (NOT available)"),
        ("RSI(14) < 30 AND STOCH(14) < 20", False, "Uses STOCH_14 (NOT available)"),
    ]
    
    for rule, should_pass, reason in test_cases:
        logger.info("-" * 100)
        logger.info(f"Rule: {rule}")
        logger.info(f"Expected: {'✓ Pass' if should_pass else '✗ Fail'} - {reason}")
        
        # Parse
        parse_result = parser.parse(rule)
        if not parse_result.success:
            logger.error(f"Parse error: {parse_result.error}")
            continue
        
        # Generate with validation
        code_result = generator.generate_code(parse_result.ast)
        
        if code_result.success:
            logger.info(f"Result:   ✓ Pass")
            logger.info(f"Code:     {code_result.code}")
        else:
            logger.info(f"Result:   ✗ Fail")
            logger.info(f"Error:    {code_result.error}")
        
        logger.info("")
    
    logger.info("=" * 100)
    logger.info("VALIDATION DEMO COMPLETE")
    logger.info("=" * 100)


if __name__ == "__main__":
    demo_dsl_pipeline()
    demo_validation()
