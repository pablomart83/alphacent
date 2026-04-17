"""
Trading Rule Domain-Specific Language (DSL) Parser

This module provides a DSL for defining trading rules in a deterministic,
industry-standard way (similar to Pine Script, MQL, QuantConnect).

Replaces LLM-based rule interpretation with a proper parser that:
- Generates correct pandas code 100% of the time
- Provides clear error messages
- Is maintainable and extensible
- Traders understand the syntax naturally

Example DSL Rules:
- Simple: RSI(14) < 30
- Crossover: SMA(20) CROSSES_ABOVE SMA(50)
- Compound: RSI(14) < 30 AND CLOSE < BB_LOWER(20, 2)
- Indicator comparison: SMA(20) > SMA(50)
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from lark import Lark, Transformer, v_args, Tree, Token
import logging

logger = logging.getLogger(__name__)


# DSL Grammar Definition using Lark's EBNF syntax
TRADING_DSL_GRAMMAR = r"""
    ?start: expression

    ?expression: or_expr

    ?or_expr: and_expr
        | or_expr "OR" and_expr -> or_op

    ?and_expr: comparison
        | and_expr "AND" comparison -> and_op

    ?comparison: arith_expr COMPARATOR arith_expr -> compare
        | indicator CROSSOVER indicator -> crossover
        | indicator CROSSOVER NUMBER -> crossover_number
        | "(" expression ")"

    ?arith_expr: term
        | arith_expr "+" term -> add
        | arith_expr "-" term -> subtract

    ?term: factor
        | term "*" factor -> multiply
        | term "/" factor -> divide

    ?factor: indicator
        | NUMBER -> number_value
        | "-" factor -> negate
        | "(" arith_expr ")"

    indicator: PRICE_FIELD -> price_field
        | INDICATOR_NAME "(" [NUMBER ("," NUMBER)*] ")" -> indicator_with_params
        | INDICATOR_NAME -> indicator_no_params

    COMPARATOR: ">" | "<" | ">=" | "<=" | "==" | "!="
    CROSSOVER: "CROSSES_ABOVE" | "CROSSES_BELOW"
    PRICE_FIELD.2: /(?:CLOSE|OPEN|HIGH|LOW|VOLUME)(?!_)/
    INDICATOR_NAME.1: /[A-Z][A-Z0-9_]*/
    NUMBER: /[0-9]+\.?[0-9]*/

    %import common.WS
    %ignore WS
"""


@dataclass
class ParseResult:
    """Result of parsing a DSL rule."""
    success: bool
    ast: Optional[Tree] = None
    error: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of validating a parsed rule."""
    valid: bool
    errors: List[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []


class TradingDSLParser:
    """
    Parser for trading rule DSL.
    
    Converts trading rules from DSL syntax to Abstract Syntax Tree (AST).
    """
    
    def __init__(self):
        """Initialize the Lark parser with trading DSL grammar."""
        try:
            self.parser = Lark(
                TRADING_DSL_GRAMMAR,
                start='start',
                parser='lalr',  # Fast LALR parser
                debug=False
            )
            logger.info("Trading DSL parser initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize DSL parser: {e}")
            raise
    
    def parse(self, rule_text: str) -> ParseResult:
        """
        Parse a trading rule from DSL syntax to AST.
        
        Args:
            rule_text: Trading rule in DSL syntax (e.g., "RSI(14) < 30")
            
        Returns:
            ParseResult with AST if successful, error message if failed
            
        Examples:
            >>> parser = TradingDSLParser()
            >>> result = parser.parse("RSI(14) < 30")
            >>> result.success
            True
            >>> result = parser.parse("INVALID SYNTAX")
            >>> result.success
            False
        """
        if not rule_text or not rule_text.strip():
            return ParseResult(
                success=False,
                error="Empty rule text"
            )
        
        try:
            # Parse the rule text into AST
            ast = self.parser.parse(rule_text.strip())
            
            logger.debug(f"Successfully parsed rule: {rule_text}")
            logger.debug(f"AST: {ast.pretty()}")
            
            return ParseResult(
                success=True,
                ast=ast
            )
            
        except Exception as e:
            error_msg = f"Failed to parse rule '{rule_text}': {str(e)}"
            logger.error(error_msg)
            
            return ParseResult(
                success=False,
                error=error_msg
            )
    
    def validate_syntax(self, rule_text: str) -> ValidationResult:
        """
        Validate DSL syntax without generating code.
        
        Args:
            rule_text: Trading rule in DSL syntax
            
        Returns:
            ValidationResult with any syntax errors
        """
        result = self.parse(rule_text)
        
        if not result.success:
            return ValidationResult(
                valid=False,
                errors=[result.error]
            )
        
        return ValidationResult(valid=True)


# Indicator name mapping from DSL to actual indicator keys
INDICATOR_MAPPING = {
    # Simple indicators
    'RSI': lambda params: f'RSI_{params[0] if params else 14}',
    'SMA': lambda params: f'SMA_{params[0] if params else 20}',
    'STDDEV': lambda params: f'STDDEV_{params[0] if params else 20}',
    'EMA': lambda params: f'EMA_{params[0] if params else 20}',
    'ATR': lambda params: f'ATR_{params[0] if params else 14}',
    'STOCH': lambda params: f'STOCH_{params[0] if params else 14}',
    'STOCH_SIGNAL': lambda params: f'STOCH_SIGNAL_{params[0] if params else 14}',
    'VOLUME_MA': lambda params: f'VOLUME_MA_{params[0] if params else 20}',
    'PRICE_CHANGE_PCT': lambda params: f'PRICE_CHANGE_PCT_{params[0] if params else 1}',
    
    # Rolling high/low lookback
    'HIGH_N': lambda params: f'HIGH_{params[0] if params else 20}',
    'LOW_N': lambda params: f'LOW_{params[0] if params else 20}',
    'HIGH_20': lambda params: f'HIGH_20',
    'LOW_20': lambda params: f'LOW_20',
    
    # Multi-output indicators (Bollinger Bands)
    # Keys include std_dev so BB(20,1.5) and BB(20,2.0) resolve to different indicators.
    # Always format std_dev as float (e.g., "1.5", "2.0") for consistent key matching.
    'BB_UPPER': lambda params: f'Upper_Band_{params[0] if params else 20}_{float(params[1]) if len(params) > 1 else 2.0}',
    'BB_MIDDLE': lambda params: f'Middle_Band_{params[0] if params else 20}_{float(params[1]) if len(params) > 1 else 2.0}',
    'BB_LOWER': lambda params: f'Lower_Band_{params[0] if params else 20}_{float(params[1]) if len(params) > 1 else 2.0}',
    'BBANDS_UB': lambda params: f'BBANDS_{params[0] if params else 20}_{float(params[1]) if len(params) > 1 else 2.0}_UB',
    'BBANDS_MB': lambda params: f'BBANDS_{params[0] if params else 20}_{float(params[1]) if len(params) > 1 else 2.0}_MB',
    'BBANDS_LB': lambda params: f'BBANDS_{params[0] if params else 20}_{float(params[1]) if len(params) > 1 else 2.0}_LB',
    
    # MACD components
    'MACD': lambda params: 'MACD_12_26_9',
    'MACD_SIGNAL': lambda params: 'MACD_12_26_9_SIGNAL',
    'MACD_HIST': lambda params: 'MACD_12_26_9_HIST',
    
    # Support/Resistance
    'SUPPORT': lambda params: 'Support',
    'RESISTANCE': lambda params: 'Resistance',
    
    # VWAP
    'VWAP': lambda params: f'VWAP_{params[0] if params else 0}',

    # ADX — Average Directional Index (trend strength)
    'ADX': lambda params: f'ADX_{params[0] if params else 14}',
}


# Price field mapping
PRICE_FIELD_MAPPING = {
    'CLOSE': 'close',
    'OPEN': 'open',
    'HIGH': 'high',
    'LOW': 'low',
    'VOLUME': 'volume',
}


@dataclass
class CodeGenerationResult:
    """Result of generating pandas code from AST."""
    success: bool
    code: Optional[str] = None
    required_indicators: List[str] = None
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.required_indicators is None:
            self.required_indicators = []


class DSLCodeGenerator:
    """
    Converts DSL Abstract Syntax Tree (AST) to pandas code.
    
    Traverses the AST and generates executable pandas expressions that can be
    evaluated against market data and indicators.
    """
    
    def __init__(self, available_indicators: Optional[List[str]] = None):
        """
        Initialize code generator.
        
        Args:
            available_indicators: List of indicator keys available for use.
                                 If None, validation is skipped.
        """
        self.available_indicators = set(available_indicators) if available_indicators else None
        self.required_indicators = []
        
    def generate_code(self, ast: Tree) -> CodeGenerationResult:
        """
        Generate pandas code from AST.
        
        Args:
            ast: Abstract Syntax Tree from TradingDSLParser
            
        Returns:
            CodeGenerationResult with pandas code string and required indicators
            
        Examples:
            >>> parser = TradingDSLParser()
            >>> generator = DSLCodeGenerator()
            >>> result = parser.parse("RSI(14) < 30")
            >>> code_result = generator.generate_code(result.ast)
            >>> code_result.code
            "indicators['RSI_14'] < 30"
        """
        if ast is None:
            return CodeGenerationResult(
                success=False,
                error="AST is None"
            )
        
        # Reset required indicators for this generation
        self.required_indicators = []
        
        try:
            # Generate code by traversing AST
            code = self._visit_node(ast)
            
            # Validate all required indicators are available
            if self.available_indicators is not None:
                missing = [ind for ind in self.required_indicators 
                          if ind not in self.available_indicators]
                if missing:
                    return CodeGenerationResult(
                        success=False,
                        error=f"Missing indicators: {', '.join(missing)}",
                        required_indicators=self.required_indicators
                    )
            
            logger.debug(f"Generated code: {code}")
            logger.debug(f"Required indicators: {self.required_indicators}")
            
            return CodeGenerationResult(
                success=True,
                code=code,
                required_indicators=self.required_indicators
            )
            
        except Exception as e:
            error_msg = f"Failed to generate code: {str(e)}"
            logger.error(error_msg)
            return CodeGenerationResult(
                success=False,
                error=error_msg,
                required_indicators=self.required_indicators
            )
    
    def _visit_node(self, node) -> str:
        """
        Visit a node in the AST and generate code.
        
        Args:
            node: Tree or Token node from AST
            
        Returns:
            Generated pandas code string
        """
        if isinstance(node, Token):
            return str(node)
        
        if not isinstance(node, Tree):
            return str(node)
        
        # Dispatch to appropriate handler based on node type
        node_type = node.data
        
        if node_type == 'or_op':
            return self._handle_or(node)
        elif node_type == 'and_op':
            return self._handle_and(node)
        elif node_type == 'compare':
            return self._handle_compare(node)
        elif node_type == 'crossover':
            return self._handle_crossover(node)
        elif node_type == 'crossover_number':
            return self._handle_crossover_number(node)
        elif node_type == 'add':
            return self._handle_add(node)
        elif node_type == 'subtract':
            return self._handle_subtract(node)
        elif node_type == 'multiply':
            return self._handle_multiply(node)
        elif node_type == 'divide':
            return self._handle_divide(node)
        elif node_type == 'negate':
            return self._handle_negate(node)
        elif node_type == 'indicator_with_params':
            return self._handle_indicator_with_params(node)
        elif node_type == 'indicator_no_params':
            return self._handle_indicator_no_params(node)
        elif node_type == 'price_field':
            return self._handle_price_field(node)
        elif node_type == 'number_value':
            return self._handle_number(node)
        else:
            # For other nodes, recursively visit children
            if len(node.children) == 1:
                return self._visit_node(node.children[0])
            else:
                raise ValueError(f"Unknown node type: {node_type}")
    
    def _handle_or(self, node: Tree) -> str:
        """Handle OR logical operation."""
        left = self._visit_node(node.children[0])
        right = self._visit_node(node.children[1])
        return f"({left}) | ({right})"
    
    def _handle_and(self, node: Tree) -> str:
        """Handle AND logical operation."""
        left = self._visit_node(node.children[0])
        right = self._visit_node(node.children[1])
        return f"({left}) & ({right})"

    def _handle_add(self, node: Tree) -> str:
        """Handle addition operation."""
        left = self._visit_node(node.children[0])
        right = self._visit_node(node.children[1])
        return f"({left} + {right})"

    def _handle_subtract(self, node: Tree) -> str:
        """Handle subtraction operation."""
        left = self._visit_node(node.children[0])
        right = self._visit_node(node.children[1])
        return f"({left} - {right})"

    def _handle_multiply(self, node: Tree) -> str:
        """Handle multiplication operation."""
        left = self._visit_node(node.children[0])
        right = self._visit_node(node.children[1])
        return f"({left} * {right})"

    def _handle_divide(self, node: Tree) -> str:
        """Handle division operation."""
        left = self._visit_node(node.children[0])
        right = self._visit_node(node.children[1])
        return f"({left} / {right})"

    def _handle_negate(self, node: Tree) -> str:
        """Handle negation operation (unary minus)."""
        operand = self._visit_node(node.children[0])
        return f"(-{operand})"


    
    def _handle_compare(self, node: Tree) -> str:
        """Handle comparison operation (>, <, >=, <=, ==, !=)."""
        left = self._visit_node(node.children[0])
        comparator = str(node.children[1])
        right = self._visit_node(node.children[2])
        
        # CRITICAL FIX: Always ensure both sides are aligned to the same index.
        # This prevents "Boolean index has wrong length" errors.
        #
        # Previous approach used .index/.values which crashes with:
        #   'numpy.ndarray' object has no attribute 'index'
        # when the indicator cache returns a stale numpy array from a prior backtest.
        #
        # New approach: always align to data.index (the DataFrame index) which is
        # guaranteed to be a proper pandas DatetimeIndex. Use pd.Series() wrapping
        # to safely handle both pd.Series and numpy array inputs.
        if "indicators[" in left and "indicators[" in right:
            # Both are indicators — align both to data.index, compare as Series
            return (
                f"(pd.Series({left}, index=data.index).reindex(data.index).ffill() "
                f"{comparator} "
                f"pd.Series({right}, index=data.index).reindex(data.index).ffill())"
            )
        elif "indicators[" in left and "data[" in right:
            # Indicator vs data column — align indicator to data's index
            return f"(pd.Series({left}, index=data.index) {comparator} {right})"
        elif "data[" in left and "indicators[" in right:
            # Data column vs indicator — align indicator to data's index
            return f"({left} {comparator} pd.Series({right}, index=data.index))"
        elif "indicators[" in left or "indicators[" in right:
            # One side is indicator, other is number — wrap indicator in Series for safety
            if "indicators[" in left:
                return f"(pd.Series({left}, index=data.index) {comparator} {right})"
            else:
                return f"({left} {comparator} pd.Series({right}, index=data.index))"
        else:
            # Neither side is indicator (e.g., data vs number)
            return f"({left} {comparator} {right})"
    
    def _handle_crossover(self, node: Tree) -> str:
        """
        Handle crossover operation (CROSSES_ABOVE, CROSSES_BELOW).
        
        CROSSES_ABOVE: indicator1 > indicator2 AND indicator1.shift(1) <= indicator2.shift(1)
        CROSSES_BELOW: indicator1 < indicator2 AND indicator1.shift(1) >= indicator2.shift(1)
        """
        indicator1 = self._visit_node(node.children[0])
        crossover_type = str(node.children[1])
        indicator2 = self._visit_node(node.children[2])
        
        # Wrap indicators in pd.Series for safety — prevents crashes when
        # indicator cache returns numpy arrays instead of pandas Series.
        # .shift() only works on pd.Series, not numpy arrays.
        ind1 = f"pd.Series({indicator1}, index=data.index)" if "indicators[" in indicator1 else indicator1
        ind2 = f"pd.Series({indicator2}, index=data.index)" if "indicators[" in indicator2 else indicator2
        
        if crossover_type == 'CROSSES_ABOVE':
            return (f"({ind1} > {ind2}) & "
                   f"({ind1}.shift(1) <= {ind2}.shift(1))")
        elif crossover_type == 'CROSSES_BELOW':
            return (f"({ind1} < {ind2}) & "
                   f"({ind1}.shift(1) >= {ind2}.shift(1))")
        else:
            raise ValueError(f"Unknown crossover type: {crossover_type}")

    def _handle_crossover_number(self, node: Tree) -> str:
        """
        Handle crossover against a scalar number (e.g., STOCH(14) CROSSES_ABOVE 30).

        CROSSES_ABOVE number: indicator > number AND indicator.shift(1) <= number
        CROSSES_BELOW number: indicator < number AND indicator.shift(1) >= number
        """
        indicator1 = self._visit_node(node.children[0])
        crossover_type = str(node.children[1])
        number = str(node.children[2])

        ind1 = f"pd.Series({indicator1}, index=data.index)" if "indicators[" in indicator1 else indicator1

        if crossover_type == 'CROSSES_ABOVE':
            return (f"({ind1} > {number}) & "
                    f"({ind1}.shift(1) <= {number})")
        elif crossover_type == 'CROSSES_BELOW':
            return (f"({ind1} < {number}) & "
                    f"({ind1}.shift(1) >= {number})")
        else:
            raise ValueError(f"Unknown crossover type: {crossover_type}")(self, node: Tree) -> str:
        """
        Handle indicator with parameters (e.g., RSI(14), BB_LOWER(20, 2)).
        
        Maps DSL indicator name to actual indicator key using INDICATOR_MAPPING.
        """
        indicator_name = str(node.children[0])
        
        # Extract parameters (keep as integers if they are whole numbers)
        params = []
        for child in node.children[1:]:
            if isinstance(child, Token):
                val = float(child)
                # Convert to int if it's a whole number
                params.append(int(val) if val.is_integer() else val)
        
        # Map indicator name to actual key
        if indicator_name not in INDICATOR_MAPPING:
            raise ValueError(f"Unknown indicator: {indicator_name}")
        
        indicator_key = INDICATOR_MAPPING[indicator_name](params)
        
        # Track required indicator
        self.required_indicators.append(indicator_key)
        
        return f"indicators['{indicator_key}']"
    
    def _handle_indicator_no_params(self, node: Tree) -> str:
        """
        Handle indicator without parameters (e.g., SUPPORT, RESISTANCE).
        """
        indicator_name = str(node.children[0])
        
        # Map indicator name to actual key
        if indicator_name not in INDICATOR_MAPPING:
            raise ValueError(f"Unknown indicator: {indicator_name}")
        
        indicator_key = INDICATOR_MAPPING[indicator_name]([])
        
        # Track required indicator
        self.required_indicators.append(indicator_key)
        
        return f"indicators['{indicator_key}']"
    
    def _handle_price_field(self, node: Tree) -> str:
        """
        Handle price field (CLOSE, OPEN, HIGH, LOW, VOLUME).
        
        Maps to data DataFrame columns.
        """
        field_name = str(node.children[0])
        
        if field_name not in PRICE_FIELD_MAPPING:
            raise ValueError(f"Unknown price field: {field_name}")
        
        column_name = PRICE_FIELD_MAPPING[field_name]
        return f"data['{column_name}']"
    
    def _handle_number(self, node: Tree) -> str:
        """Handle numeric literal."""
        return str(node.children[0])


if __name__ == "__main__":
    # Test the parser and code generator
    logging.basicConfig(level=logging.DEBUG)
    
    parser = TradingDSLParser()
    generator = DSLCodeGenerator()
    
    test_rules = [
        "RSI(14) < 30",
        "SMA(20) > CLOSE",
        "SMA(20) CROSSES_ABOVE SMA(50)",
        "RSI(14) < 30 AND CLOSE < BB_LOWER(20, 2)",
        "SMA(20) > SMA(50)",
        "(RSI(14) < 30 OR STOCH(14) < 20) AND CLOSE < BB_LOWER(20, 2)",
    ]
    
    print("\n=== Testing Trading DSL Parser & Code Generator ===\n")
    
    for rule in test_rules:
        print(f"Rule: {rule}")
        
        # Parse
        parse_result = parser.parse(rule)
        if not parse_result.success:
            print(f"❌ Parse failed: {parse_result.error}\n")
            continue
        
        print("✅ Parsed successfully")
        
        # Generate code
        code_result = generator.generate_code(parse_result.ast)
        if not code_result.success:
            print(f"❌ Code generation failed: {code_result.error}\n")
            continue
        
        print(f"✅ Generated code: {code_result.code}")
        print(f"   Required indicators: {code_result.required_indicators}\n")
