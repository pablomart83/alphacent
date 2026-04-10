"""
Test DSL Code Generator with comprehensive test cases.

This test verifies that the DSLCodeGenerator correctly converts
DSL Abstract Syntax Trees to pandas code.
"""

import logging
from src.strategy.trading_dsl import (
    TradingDSLParser,
    DSLCodeGenerator,
    CodeGenerationResult
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_basic_indicator_comparison():
    """Test basic indicator comparison (RSI(14) < 30)."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: Basic Indicator Comparison")
    logger.info("=" * 80)
    
    parser = TradingDSLParser()
    generator = DSLCodeGenerator()
    
    rule = "RSI(14) < 30"
    logger.info(f"Rule: {rule}")
    
    # Parse
    parse_result = parser.parse(rule)
    assert parse_result.success, f"Parse failed: {parse_result.error}"
    logger.info("✓ Parsed successfully")
    
    # Generate code
    code_result = generator.generate_code(parse_result.ast)
    assert code_result.success, f"Code generation failed: {code_result.error}"
    logger.info(f"✓ Generated code: {code_result.code}")
    
    # Verify code
    expected_code = "indicators['RSI_14'] < 30"
    assert code_result.code == expected_code, f"Expected '{expected_code}', got '{code_result.code}'"
    logger.info("✓ Code matches expected output")
    
    # Verify required indicators
    assert 'RSI_14' in code_result.required_indicators, "Should require RSI_14"
    logger.info(f"✓ Required indicators: {code_result.required_indicators}")
    
    logger.info("✅ TEST PASSED\n")
    return True


def test_price_field_comparison():
    """Test price field comparison (CLOSE > SMA(20))."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: Price Field Comparison")
    logger.info("=" * 80)
    
    parser = TradingDSLParser()
    generator = DSLCodeGenerator()
    
    rule = "CLOSE > SMA(20)"
    logger.info(f"Rule: {rule}")
    
    # Parse
    parse_result = parser.parse(rule)
    assert parse_result.success, f"Parse failed: {parse_result.error}"
    logger.info("✓ Parsed successfully")
    
    # Generate code
    code_result = generator.generate_code(parse_result.ast)
    assert code_result.success, f"Code generation failed: {code_result.error}"
    logger.info(f"✓ Generated code: {code_result.code}")
    
    # Verify code contains both data['close'] and indicators['SMA_20']
    assert "data['close']" in code_result.code, "Should reference data['close']"
    assert "indicators['SMA_20']" in code_result.code, "Should reference indicators['SMA_20']"
    logger.info("✓ Code contains correct references")
    
    # Verify required indicators
    assert 'SMA_20' in code_result.required_indicators, "Should require SMA_20"
    logger.info(f"✓ Required indicators: {code_result.required_indicators}")
    
    logger.info("✅ TEST PASSED\n")
    return True


def test_crossover_operation():
    """Test crossover operation (SMA(20) CROSSES_ABOVE SMA(50))."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: Crossover Operation")
    logger.info("=" * 80)
    
    parser = TradingDSLParser()
    generator = DSLCodeGenerator()
    
    rule = "SMA(20) CROSSES_ABOVE SMA(50)"
    logger.info(f"Rule: {rule}")
    
    # Parse
    parse_result = parser.parse(rule)
    assert parse_result.success, f"Parse failed: {parse_result.error}"
    logger.info("✓ Parsed successfully")
    
    # Generate code
    code_result = generator.generate_code(parse_result.ast)
    assert code_result.success, f"Code generation failed: {code_result.error}"
    logger.info(f"✓ Generated code: {code_result.code}")
    
    # Verify crossover logic
    assert "indicators['SMA_20'] > indicators['SMA_50']" in code_result.code, "Should have current comparison"
    assert ".shift(1)" in code_result.code, "Should have shift for previous values"
    assert "&" in code_result.code, "Should have AND logic"
    logger.info("✓ Crossover logic is correct")
    
    # Verify required indicators
    assert 'SMA_20' in code_result.required_indicators, "Should require SMA_20"
    assert 'SMA_50' in code_result.required_indicators, "Should require SMA_50"
    logger.info(f"✓ Required indicators: {code_result.required_indicators}")
    
    logger.info("✅ TEST PASSED\n")
    return True


def test_and_logic():
    """Test AND logic (RSI(14) < 30 AND CLOSE < BB_LOWER(20, 2))."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: AND Logic")
    logger.info("=" * 80)
    
    parser = TradingDSLParser()
    generator = DSLCodeGenerator()
    
    rule = "RSI(14) < 30 AND CLOSE < BB_LOWER(20, 2)"
    logger.info(f"Rule: {rule}")
    
    # Parse
    parse_result = parser.parse(rule)
    assert parse_result.success, f"Parse failed: {parse_result.error}"
    logger.info("✓ Parsed successfully")
    
    # Generate code
    code_result = generator.generate_code(parse_result.ast)
    assert code_result.success, f"Code generation failed: {code_result.error}"
    logger.info(f"✓ Generated code: {code_result.code}")
    
    # Verify AND logic
    assert "&" in code_result.code, "Should have AND operator (&)"
    assert "indicators['RSI_14']" in code_result.code, "Should reference RSI_14"
    assert "data['close']" in code_result.code, "Should reference close price"
    assert "indicators['Lower_Band_20']" in code_result.code, "Should reference Lower_Band_20"
    logger.info("✓ AND logic is correct")
    
    # Verify required indicators
    assert 'RSI_14' in code_result.required_indicators, "Should require RSI_14"
    assert 'Lower_Band_20' in code_result.required_indicators, "Should require Lower_Band_20"
    logger.info(f"✓ Required indicators: {code_result.required_indicators}")
    
    logger.info("✅ TEST PASSED\n")
    return True


def test_or_logic():
    """Test OR logic (RSI(14) < 30 OR STOCH(14) < 20)."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: OR Logic")
    logger.info("=" * 80)
    
    parser = TradingDSLParser()
    generator = DSLCodeGenerator()
    
    rule = "RSI(14) < 30 OR STOCH(14) < 20"
    logger.info(f"Rule: {rule}")
    
    # Parse
    parse_result = parser.parse(rule)
    assert parse_result.success, f"Parse failed: {parse_result.error}"
    logger.info("✓ Parsed successfully")
    
    # Generate code
    code_result = generator.generate_code(parse_result.ast)
    assert code_result.success, f"Code generation failed: {code_result.error}"
    logger.info(f"✓ Generated code: {code_result.code}")
    
    # Verify OR logic
    assert "|" in code_result.code, "Should have OR operator (|)"
    assert "indicators['RSI_14']" in code_result.code, "Should reference RSI_14"
    assert "indicators['STOCH_14']" in code_result.code, "Should reference STOCH_14"
    logger.info("✓ OR logic is correct")
    
    # Verify required indicators
    assert 'RSI_14' in code_result.required_indicators, "Should require RSI_14"
    assert 'STOCH_14' in code_result.required_indicators, "Should require STOCH_14"
    logger.info(f"✓ Required indicators: {code_result.required_indicators}")
    
    logger.info("✅ TEST PASSED\n")
    return True


def test_complex_nested_logic():
    """Test complex nested logic ((RSI(14) < 30 OR STOCH(14) < 20) AND CLOSE < BB_LOWER(20, 2))."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: Complex Nested Logic")
    logger.info("=" * 80)
    
    parser = TradingDSLParser()
    generator = DSLCodeGenerator()
    
    rule = "(RSI(14) < 30 OR STOCH(14) < 20) AND CLOSE < BB_LOWER(20, 2)"
    logger.info(f"Rule: {rule}")
    
    # Parse
    parse_result = parser.parse(rule)
    assert parse_result.success, f"Parse failed: {parse_result.error}"
    logger.info("✓ Parsed successfully")
    
    # Generate code
    code_result = generator.generate_code(parse_result.ast)
    assert code_result.success, f"Code generation failed: {code_result.error}"
    logger.info(f"✓ Generated code: {code_result.code}")
    
    # Verify nested logic
    assert "|" in code_result.code, "Should have OR operator (|)"
    assert "&" in code_result.code, "Should have AND operator (&)"
    assert "(" in code_result.code, "Should have parentheses for grouping"
    logger.info("✓ Nested logic is correct")
    
    # Verify all indicators
    assert 'RSI_14' in code_result.required_indicators, "Should require RSI_14"
    assert 'STOCH_14' in code_result.required_indicators, "Should require STOCH_14"
    assert 'Lower_Band_20' in code_result.required_indicators, "Should require Lower_Band_20"
    logger.info(f"✓ Required indicators: {code_result.required_indicators}")
    
    logger.info("✅ TEST PASSED\n")
    return True


def test_bollinger_bands_mapping():
    """Test Bollinger Bands indicator mapping."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: Bollinger Bands Mapping")
    logger.info("=" * 80)
    
    parser = TradingDSLParser()
    generator = DSLCodeGenerator()
    
    test_cases = [
        ("BB_UPPER(20, 2) > CLOSE", "Upper_Band_20"),
        ("BB_MIDDLE(20, 2) > CLOSE", "Middle_Band_20"),
        ("BB_LOWER(20, 2) < CLOSE", "Lower_Band_20"),
    ]
    
    for rule, expected_indicator in test_cases:
        logger.info(f"\nRule: {rule}")
        
        # Parse
        parse_result = parser.parse(rule)
        assert parse_result.success, f"Parse failed: {parse_result.error}"
        
        # Generate code
        code_result = generator.generate_code(parse_result.ast)
        assert code_result.success, f"Code generation failed: {code_result.error}"
        logger.info(f"✓ Generated code: {code_result.code}")
        
        # Verify indicator mapping
        assert f"indicators['{expected_indicator}']" in code_result.code, \
            f"Should map to {expected_indicator}"
        assert expected_indicator in code_result.required_indicators, \
            f"Should require {expected_indicator}"
        logger.info(f"✓ Correctly mapped to {expected_indicator}")
    
    logger.info("\n✅ TEST PASSED\n")
    return True


def test_indicator_validation():
    """Test that missing indicators are detected."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: Indicator Validation")
    logger.info("=" * 80)
    
    parser = TradingDSLParser()
    
    # Create generator with limited available indicators
    available_indicators = ['RSI_14', 'SMA_20']
    generator = DSLCodeGenerator(available_indicators=available_indicators)
    
    rule = "RSI(14) < 30 AND STOCH(14) < 20"
    logger.info(f"Rule: {rule}")
    logger.info(f"Available indicators: {available_indicators}")
    
    # Parse
    parse_result = parser.parse(rule)
    assert parse_result.success, f"Parse failed: {parse_result.error}"
    logger.info("✓ Parsed successfully")
    
    # Generate code (should fail due to missing STOCH_14)
    code_result = generator.generate_code(parse_result.ast)
    assert not code_result.success, "Should fail due to missing indicator"
    assert "Missing indicators" in code_result.error, "Should report missing indicators"
    assert "STOCH_14" in code_result.error, "Should identify STOCH_14 as missing"
    logger.info(f"✓ Correctly detected missing indicator: {code_result.error}")
    
    logger.info("✅ TEST PASSED\n")
    return True


def test_all_price_fields():
    """Test all price field mappings."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: All Price Fields")
    logger.info("=" * 80)
    
    parser = TradingDSLParser()
    generator = DSLCodeGenerator()
    
    price_fields = {
        'CLOSE': 'close',
        'OPEN': 'open',
        'HIGH': 'high',
        'LOW': 'low',
        'VOLUME': 'volume',
    }
    
    for dsl_field, expected_column in price_fields.items():
        rule = f"{dsl_field} > 100"
        logger.info(f"\nRule: {rule}")
        
        # Parse
        parse_result = parser.parse(rule)
        assert parse_result.success, f"Parse failed: {parse_result.error}"
        
        # Generate code
        code_result = generator.generate_code(parse_result.ast)
        assert code_result.success, f"Code generation failed: {code_result.error}"
        logger.info(f"✓ Generated code: {code_result.code}")
        
        # Verify mapping
        assert f"data['{expected_column}']" in code_result.code, \
            f"Should map {dsl_field} to data['{expected_column}']"
        logger.info(f"✓ Correctly mapped {dsl_field} to data['{expected_column}']")
    
    logger.info("\n✅ TEST PASSED\n")
    return True


def test_comparison_operators():
    """Test all comparison operators."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST: Comparison Operators")
    logger.info("=" * 80)
    
    parser = TradingDSLParser()
    generator = DSLCodeGenerator()
    
    operators = ['>', '<', '>=', '<=', '==', '!=']
    
    for op in operators:
        rule = f"RSI(14) {op} 50"
        logger.info(f"\nRule: {rule}")
        
        # Parse
        parse_result = parser.parse(rule)
        assert parse_result.success, f"Parse failed: {parse_result.error}"
        
        # Generate code
        code_result = generator.generate_code(parse_result.ast)
        assert code_result.success, f"Code generation failed: {code_result.error}"
        logger.info(f"✓ Generated code: {code_result.code}")
        
        # Verify operator is in code
        assert f" {op} " in code_result.code, f"Should contain operator {op}"
        logger.info(f"✓ Operator {op} correctly included")
    
    logger.info("\n✅ TEST PASSED\n")
    return True


def run_all_tests():
    """Run all DSL code generator tests."""
    logger.info("\n" + "=" * 100)
    logger.info("DSL CODE GENERATOR TEST SUITE")
    logger.info("=" * 100)
    
    tests = [
        ("Basic Indicator Comparison", test_basic_indicator_comparison),
        ("Price Field Comparison", test_price_field_comparison),
        ("Crossover Operation", test_crossover_operation),
        ("AND Logic", test_and_logic),
        ("OR Logic", test_or_logic),
        ("Complex Nested Logic", test_complex_nested_logic),
        ("Bollinger Bands Mapping", test_bollinger_bands_mapping),
        ("Indicator Validation", test_indicator_validation),
        ("All Price Fields", test_all_price_fields),
        ("Comparison Operators", test_comparison_operators),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            logger.error(f"\n❌ {test_name} FAILED: {e}\n")
            failed += 1
        except Exception as e:
            logger.error(f"\n❌ {test_name} ERROR: {e}\n")
            import traceback
            traceback.print_exc()
            failed += 1
    
    logger.info("\n" + "=" * 100)
    logger.info("TEST SUMMARY")
    logger.info("=" * 100)
    logger.info(f"Total tests: {len(tests)}")
    logger.info(f"Passed: {passed}")
    logger.info(f"Failed: {failed}")
    
    if failed == 0:
        logger.info("\n✅ ALL TESTS PASSED!")
    else:
        logger.error(f"\n❌ {failed} TEST(S) FAILED")
    
    logger.info("=" * 100)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
