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
#
# Sprint 1 F1 (2026-05-02): extended to support string and symbol-list arguments
# in indicator calls so cross-asset primitives like LAG_RETURN("BTC", 2, "1h") and
# RANK_IN_UNIVERSE("SELF", ["BTC","ETH","SOL","AVAX","LINK","DOT"], 14, 3) can be
# expressed natively in entry/exit rules. These primitives must run identically
# in backtest and live signal-gen; encoding them as DSL (not runtime metadata
# gates) is the only way to keep WF honest.
TRADING_DSL_GRAMMAR = r"""
    ?start: expression

    ?expression: or_expr

    ?or_expr: and_expr
        | or_expr "OR" and_expr -> or_op

    ?and_expr: comparison
        | and_expr "AND" comparison -> and_op

    ?comparison: arith_expr COMPARATOR arith_expr -> compare
        | arith_expr CROSSOVER arith_expr -> crossover
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
        | INDICATOR_NAME "(" [arg ("," arg)*] ")" -> indicator_with_params
        | INDICATOR_NAME -> indicator_no_params

    // arg: individual argument to an indicator call. Can be:
    //   - NUMBER: 14, 2.0, etc.
    //   - STRING: "BTC", "1h", etc. (double-quoted, ASCII uppercase/digits/_)
    //   - SYMBOL_LIST: ["BTC","ETH","SOL"] (array of strings, used by RANK_IN_UNIVERSE)
    arg: NUMBER      -> arg_number
        | STRING     -> arg_string
        | SYMBOL_LIST -> arg_symbol_list

    COMPARATOR: ">" | "<" | ">=" | "<=" | "==" | "!="
    CROSSOVER: "CROSSES_ABOVE" | "CROSSES_BELOW"
    PRICE_FIELD.2: /(?:CLOSE|OPEN|HIGH|LOW|VOLUME)(?!_)/
    INDICATOR_NAME.1: /[A-Z][A-Z0-9_]*/
    NUMBER: /[0-9]+\.?[0-9]*/
    STRING: /"[A-Za-z0-9_]+"/
    SYMBOL_LIST: /\[\s*"[A-Za-z0-9_]+"(?:\s*,\s*"[A-Za-z0-9_]+")*\s*\]/

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

    # ───── On-Balance Volume (Sprint 2 crypto alpha, 2026-05-02) ─────
    # OBV is cumulative — no period argument. OBV_MA wraps it with a
    # rolling mean for use as a signal line.
    'OBV': lambda params: 'OBV',
    'OBV_MA': lambda params: f'OBV_MA_{params[0] if params else 20}',

    # ───── Donchian Channels (Sprint 2, 2026-05-02) ─────
    # Turtle-style breakout thresholds. Unlike HIGH_N / LOW_N, Donchian
    # applies shift=1 so the threshold excludes the current bar —
    # `close > DONCHIAN_UPPER(20)` is "today closed above the prior
    # 20-bar high" rather than the tautological "today's high is the
    # 20-bar high". Use DONCHIAN for entry breakouts, HIGH_N for range
    # checks (support/resistance) that should include the current bar.
    'DONCHIAN_UPPER': lambda params: f'DONCHIAN_UPPER_{params[0] if params else 20}',
    'DONCHIAN_LOWER': lambda params: f'DONCHIAN_LOWER_{params[0] if params else 20}',

    # ───── Keltner Channels (Sprint 2, 2026-05-02) ─────
    # EMA-centered, ATR-scaled channel. Reacts to true trading range
    # rather than close-price dispersion (unlike Bollinger). Canonical
    # params: EMA(20), ATR(14), mult=2.0.
    # Args: (ema_period, atr_period, mult). Defaults: (20, 14, 2.0).
    'KELTNER_UPPER': lambda params: (
        f"KELTNER_UPPER_{params[0] if params else 20}_"
        f"{params[1] if len(params) > 1 else 14}_"
        f"{float(params[2]) if len(params) > 2 else 2.0}"
    ),
    'KELTNER_MIDDLE': lambda params: (
        f"KELTNER_MIDDLE_{params[0] if params else 20}_"
        f"{params[1] if len(params) > 1 else 14}_"
        f"{float(params[2]) if len(params) > 2 else 2.0}"
    ),
    'KELTNER_LOWER': lambda params: (
        f"KELTNER_LOWER_{params[0] if params else 20}_"
        f"{params[1] if len(params) > 1 else 14}_"
        f"{float(params[2]) if len(params) > 2 else 2.0}"
    ),

    # ───── Cross-asset primitives (Sprint 1 F1, 2026-05-02) ─────
    # These indicators reference external symbols, not just the primary's bars.
    # The actual Series is pre-computed by strategy_engine._compute_cross_asset_indicators
    # and injected into the `indicators` dict BEFORE DSL evaluation. The mapping
    # below produces a deterministic, parseable key so both the compute step
    # and the DSL-generated eval code agree on the lookup string.
    #
    # LAG_RETURN(SYMBOL, BARS, INTERVAL):
    #   Returns the pct return of SYMBOL over the last BARS bars at INTERVAL.
    #   Key format: LAG_RETURN__<SYMBOL>__<BARS>__<INTERVAL>
    #   Example: LAG_RETURN("BTC", 2, "1h") → LAG_RETURN__BTC__2__1h
    'LAG_RETURN': lambda params: f'LAG_RETURN__{params[0]}__{params[1]}__{params[2] if len(params) > 2 else "1d"}',

    # RANK_IN_UNIVERSE(SELF_OR_SYMBOL, UNIVERSE_LIST, WINDOW_DAYS, TOP_N):
    #   Returns True when SELF_OR_SYMBOL is in the top TOP_N of UNIVERSE_LIST
    #   by WINDOW_DAYS-day return, evaluated at each bar.
    #   "SELF" substitutes the strategy's primary symbol at compute time.
    #   Key format: RANK_IN_UNIVERSE__<SELF_OR_SYMBOL>__<UNIVERSE_HASH>__<WINDOW>__<TOPN>
    #   We hash the universe list so keys are stable across orderings but
    #   distinguish genuinely different universes.
    'RANK_IN_UNIVERSE': lambda params: _rank_in_universe_key(params),

    # ───── On-chain primitives (Sprint 4 S4.1, 2026-05-02) ─────
    # ONCHAIN(METRIC_NAME, LOOKBACK_DAYS):
    #   Returns the value of a market-structure metric at each bar.
    #   METRIC_NAME is a quoted string identifying the metric; see
    #   src/api/onchain_client.SUPPORTED_METRICS for the registry.
    #   LOOKBACK_DAYS is informational for the compute step (lets the
    #   same metric be referenced at multiple lookbacks without refetch);
    #   the DSL eval sees the aligned value at each bar.
    #   Key format: ONCHAIN__<metric_lowercase>__<lookback>
    #   Example: ONCHAIN("btc_dominance", 7) → ONCHAIN__btc_dominance__7
    #
    # Pre-computed by strategy_engine._compute_onchain_for_strategy and
    # merged into `indicators` before DSL eval, same pattern as the
    # cross-asset primitives above.
    'ONCHAIN': lambda params: f'ONCHAIN__{str(params[0]).lower()}__{int(params[1])}',
}


def _rank_in_universe_key(params) -> str:
    """
    Build a deterministic key for RANK_IN_UNIVERSE calls.

    params = [self_or_symbol, universe_list, window_days, top_n]
    universe_list is a list of strings (from DSL SYMBOL_LIST token).
    We sort it for order-independence and use the first 8 chars of the
    sorted-joined-hashed string as the universe tag.
    """
    import hashlib
    if len(params) < 4:
        raise ValueError(
            f"RANK_IN_UNIVERSE requires 4 args (self_or_symbol, universe, window, top_n), "
            f"got {len(params)}: {params}"
        )
    self_sym = params[0]
    universe = params[1] if isinstance(params[1], list) else [str(params[1])]
    window = int(params[2])
    top_n = int(params[3])
    uni_sorted = sorted(str(s) for s in universe)
    uni_tag = hashlib.md5(','.join(uni_sorted).encode()).hexdigest()[:8]
    return f'RANK_IN_UNIVERSE__{self_sym}__{uni_tag}__{window}__{top_n}'


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
        
        CROSSES_ABOVE: expr1 > expr2 AND expr1.shift(1) <= expr2.shift(1)
        CROSSES_BELOW: expr1 < expr2 AND expr1.shift(1) >= expr2.shift(1)

        Each side may be an arbitrary arith_expr (e.g. `VOLUME_MA(20) * 2.0`
        or `SMA(50) * 0.75` or a bare `30` constant), not just a bare
        indicator. The LHS is always wrapped as a pd.Series so `.shift(1)`
        is valid. The RHS is only wrapped if it contains an indicators[...]
        reference; pure scalars (bare numbers like `30`) stay as scalars
        because `scalar.shift(1)` is invalid — instead we use the literal
        scalar directly on both sides of the inequality.
        """
        lhs = self._visit_node(node.children[0])
        crossover_type = str(node.children[1])
        rhs = self._visit_node(node.children[2])

        # LHS is always a pd.Series — even if it's a bare PRICE_FIELD like
        # CLOSE, _handle_price_field returns `data["close"]` which is a
        # Series. Wrap unconditionally so `.shift(1)` is always safe.
        ind1 = f"pd.Series({lhs}, index=data.index)"

        # RHS: if it references an indicator or price_field, it's a Series
        # and needs wrapping for .shift(). If it's a pure scalar (e.g. 30),
        # don't wrap — use it as a scalar on both sides of the inequality.
        rhs_is_series = ("indicators[" in rhs) or ("data[" in rhs)
        if rhs_is_series:
            ind2 = f"pd.Series({rhs}, index=data.index)"
            shift_rhs = f"{ind2}.shift(1)"
        else:
            ind2 = rhs
            shift_rhs = rhs  # scalar — no shift

        if crossover_type == 'CROSSES_ABOVE':
            return (f"({ind1} > {ind2}) & "
                   f"({ind1}.shift(1) <= {shift_rhs})")
        elif crossover_type == 'CROSSES_BELOW':
            return (f"({ind1} < {ind2}) & "
                   f"({ind1}.shift(1) >= {shift_rhs})")
        else:
            raise ValueError(f"Unknown crossover type: {crossover_type}")

    def _handle_indicator_with_params(self, node: Tree) -> str:
        """
        Handle indicator with parameters (e.g., RSI(14), BB_LOWER(20, 2)).

        Maps DSL indicator name to actual indicator key using INDICATOR_MAPPING.

        Sprint 1 F1: parameters can now be numbers, strings (for cross-asset
        symbol/interval args), or lists (for RANK_IN_UNIVERSE).
        """
        indicator_name = str(node.children[0])

        # Extract parameters. Children after the indicator name are arg nodes
        # wrapping either NUMBER, STRING, or SYMBOL_LIST tokens.
        params = []
        for child in node.children[1:]:
            params.append(self._extract_arg_value(child))

        # Map indicator name to actual key
        if indicator_name not in INDICATOR_MAPPING:
            raise ValueError(f"Unknown indicator: {indicator_name}")

        indicator_key = INDICATOR_MAPPING[indicator_name](params)

        # Track required indicator
        self.required_indicators.append(indicator_key)

        return f"indicators['{indicator_key}']"

    def _extract_arg_value(self, node):
        """
        Extract the Python value from an `arg` AST node.

        arg nodes wrap one of: NUMBER, STRING, or SYMBOL_LIST.
        Returns int/float for NUMBER, str (without quotes) for STRING,
        list[str] for SYMBOL_LIST.
        """
        # Direct Token (grammar edge-case — numeric-only indicator call
        # where the old NUMBER path still applies during migration).
        if isinstance(node, Token):
            val = float(node)
            return int(val) if val.is_integer() else val

        if not isinstance(node, Tree):
            return node

        node_type = node.data
        if node_type == 'arg_number':
            tok = node.children[0]
            val = float(str(tok))
            return int(val) if val.is_integer() else val
        if node_type == 'arg_string':
            # STRING token value is '"BTC"' — strip quotes.
            raw = str(node.children[0])
            return raw.strip('"')
        if node_type == 'arg_symbol_list':
            # SYMBOL_LIST token value is '["BTC","ETH",...]'. Parse with json.
            import json
            raw = str(node.children[0])
            return json.loads(raw)
        raise ValueError(f"Unknown arg node type: {node_type}")
    
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
