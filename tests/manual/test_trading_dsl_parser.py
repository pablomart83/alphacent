"""
Test suite for Trading DSL Parser

Tests the DSL grammar definition and parser functionality.
"""

import pytest
from src.strategy.trading_dsl import TradingDSLParser, ParseResult, ValidationResult


class TestTradingDSLParser:
    """Test cases for Trading DSL Parser."""
    
    @pytest.fixture
    def parser(self):
        """Create a parser instance for testing."""
        return TradingDSLParser()
    
    def test_parser_initialization(self, parser):
        """Test that parser initializes successfully."""
        assert parser is not None
        assert parser.parser is not None
    
    def test_simple_comparison_less_than(self, parser):
        """Test simple comparison: RSI(14) < 30"""
        result = parser.parse("RSI(14) < 30")
        assert result.success is True
        assert result.ast is not None
        assert result.error is None
    
    def test_simple_comparison_greater_than(self, parser):
        """Test simple comparison: SMA(20) > CLOSE"""
        result = parser.parse("SMA(20) > CLOSE")
        assert result.success is True
        assert result.ast is not None
    
    def test_simple_comparison_greater_equal(self, parser):
        """Test comparison with >="""
        result = parser.parse("RSI(14) >= 30")
        assert result.success is True
        assert result.ast is not None
    
    def test_simple_comparison_less_equal(self, parser):
        """Test comparison with <="""
        result = parser.parse("RSI(14) <= 70")
        assert result.success is True
        assert result.ast is not None
    
    def test_simple_comparison_equal(self, parser):
        """Test comparison with =="""
        result = parser.parse("CLOSE == 100")
        assert result.success is True
        assert result.ast is not None
    
    def test_simple_comparison_not_equal(self, parser):
        """Test comparison with !="""
        result = parser.parse("CLOSE != 100")
        assert result.success is True
        assert result.ast is not None
    
    def test_crossover_above(self, parser):
        """Test crossover: SMA(20) CROSSES_ABOVE SMA(50)"""
        result = parser.parse("SMA(20) CROSSES_ABOVE SMA(50)")
        assert result.success is True
        assert result.ast is not None
    
    def test_crossover_below(self, parser):
        """Test crossover: SMA(20) CROSSES_BELOW SMA(50)"""
        result = parser.parse("SMA(20) CROSSES_BELOW SMA(50)")
        assert result.success is True
        assert result.ast is not None
    
    def test_compound_and(self, parser):
        """Test compound rule with AND"""
        result = parser.parse("RSI(14) < 30 AND CLOSE < BB_LOWER(20, 2)")
        assert result.success is True
        assert result.ast is not None
    
    def test_compound_or(self, parser):
        """Test compound rule with OR"""
        result = parser.parse("RSI(14) < 30 OR STOCH(14) < 20")
        assert result.success is True
        assert result.ast is not None
    
    def test_compound_and_or(self, parser):
        """Test compound rule with both AND and OR"""
        result = parser.parse("(RSI(14) < 30 OR STOCH(14) < 20) AND CLOSE < BB_LOWER(20, 2)")
        assert result.success is True
        assert result.ast is not None
    
    def test_indicator_to_indicator_comparison(self, parser):
        """Test indicator-to-indicator comparison"""
        result = parser.parse("SMA(20) > SMA(50)")
        assert result.success is True
        assert result.ast is not None
    
    def test_price_field_close(self, parser):
        """Test CLOSE price field"""
        result = parser.parse("CLOSE > 100")
        assert result.success is True
        assert result.ast is not None
    
    def test_price_field_open(self, parser):
        """Test OPEN price field"""
        result = parser.parse("OPEN < 100")
        assert result.success is True
        assert result.ast is not None
    
    def test_price_field_high(self, parser):
        """Test HIGH price field"""
        result = parser.parse("HIGH > 100")
        assert result.success is True
        assert result.ast is not None
    
    def test_price_field_low(self, parser):
        """Test LOW price field"""
        result = parser.parse("LOW < 100")
        assert result.success is True
        assert result.ast is not None
    
    def test_price_field_volume(self, parser):
        """Test VOLUME field"""
        result = parser.parse("VOLUME > 1000000")
        assert result.success is True
        assert result.ast is not None
    
    def test_indicator_no_params(self, parser):
        """Test indicator without parameters (uses defaults)"""
        result = parser.parse("MACD CROSSES_ABOVE MACD_SIGNAL")
        assert result.success is True
        assert result.ast is not None
    
    def test_bollinger_bands_upper(self, parser):
        """Test Bollinger Bands upper band"""
        result = parser.parse("CLOSE > BB_UPPER(20, 2)")
        assert result.success is True
        assert result.ast is not None
    
    def test_bollinger_bands_lower(self, parser):
        """Test Bollinger Bands lower band"""
        result = parser.parse("CLOSE < BB_LOWER(20, 2)")
        assert result.success is True
        assert result.ast is not None
    
    def test_bollinger_bands_middle(self, parser):
        """Test Bollinger Bands middle band"""
        result = parser.parse("CLOSE > BB_MIDDLE(20, 2)")
        assert result.success is True
        assert result.ast is not None
    
    def test_decimal_number(self, parser):
        """Test decimal number in comparison"""
        result = parser.parse("ATR(14) > 2.5")
        assert result.success is True
        assert result.ast is not None
    
    def test_parentheses_grouping(self, parser):
        """Test parentheses for grouping"""
        result = parser.parse("(RSI(14) < 30)")
        assert result.success is True
        assert result.ast is not None
    
    def test_complex_nested_logic(self, parser):
        """Test complex nested logic"""
        result = parser.parse("((RSI(14) < 30 AND STOCH(14) < 20) OR (RSI(14) > 70 AND STOCH(14) > 80)) AND VOLUME > VOLUME_MA(20)")
        assert result.success is True
        assert result.ast is not None
    
    def test_empty_rule(self, parser):
        """Test empty rule returns error"""
        result = parser.parse("")
        assert result.success is False
        assert result.error is not None
    
    def test_whitespace_only_rule(self, parser):
        """Test whitespace-only rule returns error"""
        result = parser.parse("   ")
        assert result.success is False
        assert result.error is not None
    
    def test_invalid_syntax(self, parser):
        """Test invalid syntax returns error"""
        result = parser.parse("INVALID SYNTAX HERE")
        assert result.success is False
        assert result.error is not None
    
    def test_missing_operator(self, parser):
        """Test missing operator returns error"""
        result = parser.parse("RSI(14) 30")
        assert result.success is False
        assert result.error is not None
    
    def test_unclosed_parenthesis(self, parser):
        """Test unclosed parenthesis returns error"""
        result = parser.parse("(RSI(14) < 30")
        assert result.success is False
        assert result.error is not None
    
    def test_invalid_indicator_name(self, parser):
        """Test lowercase indicator name (should fail - must be uppercase)"""
        result = parser.parse("rsi(14) < 30")
        assert result.success is False
        assert result.error is not None
    
    def test_validate_syntax_valid(self, parser):
        """Test validate_syntax with valid rule"""
        result = parser.validate_syntax("RSI(14) < 30")
        assert result.valid is True
        assert len(result.errors) == 0
    
    def test_validate_syntax_invalid(self, parser):
        """Test validate_syntax with invalid rule"""
        result = parser.validate_syntax("INVALID SYNTAX")
        assert result.valid is False
        assert len(result.errors) > 0


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
