"""LLM Service for strategy generation using Ollama."""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

from src.models.dataclasses import RiskConfig
from src.models.enums import SignalAction

logger = logging.getLogger(__name__)


@dataclass
class AlphaSource:
    """Source of alpha in a trading strategy."""
    type: str  # "momentum", "mean_reversion", "volatility", etc.
    weight: float  # Relative importance (0.0 to 1.0)
    description: str


@dataclass
class StrategyReasoning:
    """LLM reasoning metadata for strategy generation."""
    hypothesis: str  # Core market hypothesis
    alpha_sources: List[AlphaSource]  # Sources of alpha
    market_assumptions: List[str]  # Assumptions about market behavior
    signal_logic: str  # Explanation of signal generation
    confidence_factors: Dict[str, float] = field(default_factory=dict)  # Factors affecting confidence
    llm_prompt: str = ""  # Original prompt
    llm_response: str = ""  # Raw LLM response


@dataclass
class StrategyDefinition:
    """Structured strategy definition from LLM."""
    name: str
    description: str
    rules: Dict[str, Any]
    symbols: List[str]
    risk_params: RiskConfig
    reasoning: Optional[StrategyReasoning] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradingCommand:
    """Structured trading command from natural language."""
    action: SignalAction
    symbol: str
    quantity: Optional[float] = None
    price: Optional[float] = None
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of strategy validation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class LLMService:
    """Interface to local Ollama LLM for strategy generation."""
    
    def __init__(self, model: str = None, base_url: str = "http://localhost:11434", 
                 code_model: str = None):
        """
        Initialize LLM service with Ollama connection.
        
        Args:
            model: Ollama model name for general tasks (default: from env or qwen2.5-coder:7b)
            base_url: Ollama API endpoint (default: http://localhost:11434)
            code_model: Ollama model for code generation (default: qwen2.5-coder:7b)
        """
        # Get model from environment variable or use default
        if model is None:
            import os
            model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
        
        # Set code generation model (use same model for code generation)
        if code_model is None:
            import os
            code_model = os.getenv("OLLAMA_CODE_MODEL", "qwen2.5-coder:7b")
        
        self.model = model
        self.code_model = code_model
        self.base_url = base_url
        self.api_url = f"{base_url}/api/generate"
        self._check_connection()
        
        logger.info(f"LLM Service initialized with model: {model}, code model: {code_model}")
    
    def _check_connection(self) -> None:
        """Check if Ollama is available and verify model exists."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            
            # Get list of available models
            available_models = [model['name'] for model in response.json().get('models', [])]
            
            # Check if requested model is available
            if self.model not in available_models:
                logger.warning(f"Requested model '{self.model}' not found")
                
                # Try to find a better fallback model
                preferred_models = [
                    "qwen2.5-coder:7b",
                    "llama3.1:8b", 
                    "mistral:7b",
                    "llama3.2:3b",
                    "llama3.2:1b"
                ]
                
                fallback_model = None
                for preferred in preferred_models:
                    if preferred in available_models:
                        fallback_model = preferred
                        break
                
                if fallback_model:
                    logger.info(f"Using fallback model: {fallback_model}")
                    self.model = fallback_model
                else:
                    logger.warning(f"No suitable fallback model found. Available: {available_models}")
                    if available_models:
                        self.model = available_models[0]
                        logger.info(f"Using first available model: {self.model}")
            
            logger.info(f"Connected to Ollama at {self.base_url}")
            logger.info(f"Using model: {self.model}")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to Ollama at {self.base_url}: {e}")
            logger.warning("Strategy generation will be unavailable")
    
    def generate_strategy(self, prompt: str, market_context: Dict[str, Any], temperature: float = 0.8) -> StrategyDefinition:
        """
        Generate trading strategy from natural language prompt.
        
        Args:
            prompt: Natural language description of desired strategy
            market_context: Current market conditions and constraints
            temperature: Temperature for generation (0.0-1.0). Higher = more random/creative. Default 0.8 for diversity
        
        Returns:
            StrategyDefinition with structured strategy
        
        Raises:
            ConnectionError: If Ollama is unavailable
            ValueError: If LLM response cannot be parsed after retries
        """
        # Format prompt with market context
        formatted_prompt = self._format_strategy_prompt(prompt, market_context)
        
        # Generate response from LLM
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self._call_ollama(formatted_prompt, temperature=temperature)
                strategy_def = self.parse_response(response)
                
                # Validate the generated strategy
                validation = self.validate_strategy(strategy_def)
                if validation.is_valid:
                    logger.info(f"Generated strategy: {strategy_def.name}")
                    return strategy_def
                else:
                    logger.warning(f"Invalid strategy on attempt {attempt + 1}: {validation.errors}")
                    if attempt < max_retries - 1:
                        # Retry with clarified prompt
                        formatted_prompt = self._format_retry_prompt(
                            prompt, market_context, validation.errors
                        )
            except Exception as e:
                logger.error(f"Error generating strategy on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise
        
        raise ValueError("Failed to generate valid strategy after maximum retries")
    
    def _format_strategy_prompt(self, prompt: str, market_context: Dict[str, Any]) -> str:
        """Format prompt with market context and constraints."""
        risk_config = market_context.get("risk_config", RiskConfig())
        available_symbols = market_context.get("available_symbols", [])
        
        # Get symbols from constraints if provided
        constraint_symbols = market_context.get("symbols", [])
        if constraint_symbols:
            symbols_text = ', '.join(constraint_symbols)
            symbols_instruction = f"CRITICAL: You MUST use ONLY these symbols: {symbols_text}. Do not add any other symbols."
            symbols_example = constraint_symbols[:2] if len(constraint_symbols) >= 2 else constraint_symbols
        else:
            symbols_text = ', '.join(available_symbols) if available_symbols else 'AAPL, GOOGL, MSFT'
            symbols_instruction = f"Available symbols: {symbols_text}"
            symbols_example = ["AAPL", "GOOGL"]
        
        formatted = f"""You are a JSON-generating trading strategy AI. Your ONLY job is to output valid JSON.

USER REQUEST: {prompt}

CONTEXT:
- {symbols_instruction}
- Max position: {risk_config.max_position_size_pct * 100}%
- Stop loss: {risk_config.stop_loss_pct * 100}%
- Take profit: {risk_config.take_profit_pct * 100}%

RULES:
1. Output ONLY valid JSON - no text before or after
2. Use double quotes for all strings
3. No trailing commas
4. All numbers must be valid (no NaN, Infinity)
5. Arrays must have at least one element
6. IMPORTANT: Use ONLY the symbols specified in the context above
7. CRITICAL: Entry/exit conditions MUST reference indicators with EXACT naming format:
   - Use "SMA_20" for 20-period Simple Moving Average
   - Use "RSI_14" for 14-period RSI
   - Use "EMA_20" for 20-period Exponential Moving Average
   - Format: {{INDICATOR}}_{{PERIOD}} (e.g., "SMA_50", "RSI_30")
8. CRITICAL: Entry/exit conditions MUST use these EXACT formats:
   - "Price is above SMA_20" (not "Price is above its 20-period SMA")
   - "Price drops below SMA_20" (not "Price drops below its 20-period SMA")
   - "RSI_14 is below 70" (not "RSI is below 70")
   - "RSI_14 is above 30" (not "RSI is above 30")
   - "RSI_14 rises above 70" (not "RSI rises above 70")

OUTPUT THIS EXACT JSON STRUCTURE:
{{
  "name": "Short descriptive name",
  "description": "One sentence description",
  "rules": {{
    "entry_conditions": ["Price is above SMA_20", "RSI_14 is below 70"],
    "exit_conditions": ["Price drops below SMA_20", "RSI_14 rises above 70"],
    "indicators": ["RSI", "SMA"],
    "timeframe": "1d"
  }},
  "symbols": {symbols_example},
  "risk_params": {{
    "max_position_size_pct": 0.1,
    "stop_loss_pct": 0.02,
    "take_profit_pct": 0.04
  }},
  "reasoning": {{
    "hypothesis": "One sentence market hypothesis",
    "alpha_sources": [
      {{
        "type": "momentum",
        "weight": 0.6,
        "description": "Price momentum indicator"
      }}
    ],
    "market_assumptions": ["assumption 1", "assumption 2"],
    "signal_logic": "How signals are generated",
    "confidence_factors": {{
      "trend_strength": 0.8
    }}
  }}
}}

IMPORTANT: Make sure entry conditions are COMPATIBLE and can occur together:
- AVOID contradictory conditions like "Price above Upper_Band_20 AND RSI_14 below 30" (overbought + oversold)
- PREFER conditions that reinforce each other: "Price above SMA_20 AND RSI_14 above 50" (both bullish)
- OR use a SINGLE strong condition: "RSI_14 crosses below 30" (simple and clear)
- Exit conditions should be OPPOSITE of entry conditions to avoid conflicts:
  * If entry uses "RSI_14 is below X", exit should use "RSI_14 rises above Y" where Y >= X
  * If entry uses "Price is above SMA_20", exit should use "Price drops below SMA_20"
  * Exit conditions should trigger when the entry thesis is invalidated

GOOD ENTRY EXAMPLES (compatible conditions):
- "Price is above SMA_20" OR "RSI_14 is below 30" (either condition triggers entry)
- "Price crosses above Lower_Band_20" (single clear condition)
- "RSI_14 is below 30 AND Price is below Lower_Band_20" (both oversold - compatible)

BAD ENTRY EXAMPLES (contradictory conditions):
- "Price crosses above Upper_Band_20 AND RSI_14 is below 30" (overbought + oversold - contradictory)
- "Price is above SMA_50 AND Price is below SMA_20" (impossible if SMA_20 > SMA_50)

Generate the JSON now based on the user request. Output ONLY the JSON, nothing else:"""
        
        return formatted
    
    def _format_retry_prompt(self, prompt: str, market_context: Dict[str, Any], 
                            errors: List[str]) -> str:
        """Format retry prompt with validation errors."""
        base_prompt = self._format_strategy_prompt(prompt, market_context)
        error_text = "\n".join(f"- {error}" for error in errors)
        
        return f"""{base_prompt}

PREVIOUS ATTEMPT HAD ERRORS:
{error_text}

Please fix these errors and generate a valid strategy."""
    
    def interpret_trading_rule(self, rule: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interpret a natural language trading rule into executable Python code.
        
        Args:
            rule: Natural language rule (e.g., "RSI below 30", "20-day price change > 5%")
            context: Available indicators, data columns, and other context
        
        Returns:
            Dict with:
                - code: Python code string that evaluates to boolean
                - required_indicators: List of indicators needed
                - description: Human-readable description
        
        Raises:
            ConnectionError: If Ollama is unavailable
            ValueError: If rule cannot be interpreted after retries
        """
        available_indicators = context.get("available_indicators", [
            "SMA", "EMA", "RSI", "MACD", "Bollinger Bands", "ATR", "Volume"
        ])
        data_columns = context.get("data_columns", ["open", "high", "low", "close", "volume"])
        
        prompt = f"""You are a trading rule interpreter. Convert natural language trading rules to Python code.

RULE TO INTERPRET: "{rule}"

AVAILABLE CONTEXT:
- Data columns: {', '.join(data_columns)}
- Available indicators: {', '.join(available_indicators)}
- Data is in pandas DataFrame 'data' with columns: {', '.join(data_columns)}
- Indicators are in dict 'indicators' with EXACT keys as shown below

CRITICAL - EXACT INDICATOR NAMING CONVENTION:
You MUST use EXACT indicator names from the available_indicators list. Do NOT invent variations.

STANDARD NAMING FORMAT: {{INDICATOR}}_{{PERIOD}} or {{INDICATOR}}_{{PARAMS}}

SINGLE-WORD INDICATORS:
- RSI with period 14: "RSI_14" (NOT "RSI" or "RSI14")
- SMA with period 20: "SMA_20" (NOT "SMA" or "SMA20")
- EMA with period 50: "EMA_50" (NOT "EMA" or "EMA50")
- ATR with period 14: "ATR_14" (NOT "ATR" or "ATR14")
- Stochastic with period 14: "STOCH_14" (NOT "STOCH" or "Stochastic")

MULTI-WORD INDICATORS:
- Volume MA with period 20: "VOLUME_MA_20" (NOT "Volume_MA" or "VolumeMA")
- Price change % over 1 day: "PRICE_CHANGE_PCT_1" (NOT "Price_Change" or "PriceChange")

BOLLINGER BANDS (period 20, std 2):
- Upper band: "Upper_Band_20" or "BBANDS_20_2_UB"
- Middle band: "Middle_Band_20" or "BBANDS_20_2_MB"
- Lower band: "Lower_Band_20" or "BBANDS_20_2_LB"

MACD (fast 12, slow 26, signal 9):
- MACD line: "MACD_12_26_9" (NOT "MACD")
- Signal line: "MACD_12_26_9_SIGNAL" (NOT "MACD_signal")
- Histogram: "MACD_12_26_9_HIST" (NOT "MACD_hist")

SUPPORT/RESISTANCE:
- Support level: "Support" (simple name)
- Resistance level: "Resistance" (simple name)

OUTPUT ONLY THIS JSON (no other text):
{{
    "code": "data['close'] > indicators['SMA_20']",
    "required_indicators": ["SMA_20"],
    "description": "Price is above 20-period SMA"
}}

RULES FOR CODE GENERATION:
1. Code must be a Python expression that evaluates to boolean or boolean Series
2. Use data['column_name'] to access price/volume data
3. Use indicators['indicator_name'] with EXACT naming as shown above
4. For percentage changes: (data['close'] - data['close'].shift(20)) / data['close'].shift(20) > 0.05
5. For comparisons: use >, <, >=, <=, ==
6. For AND logic: use &
7. For OR logic: use |
8. Always use vectorized pandas operations (no loops)
9. For crossovers: detect when indicator crosses above/below another
   - Bullish crossover: (indicator1 > indicator2) & (indicator1.shift(1) <= indicator2.shift(1))
   - Bearish crossover: (indicator1 < indicator2) & (indicator1.shift(1) >= indicator2.shift(1))

CORRECT EXAMPLES:
"RSI below 30" → {{"code": "indicators['RSI_14'] < 30", "required_indicators": ["RSI_14"], "description": "RSI below 30"}}
"Price above 50-day SMA" → {{"code": "data['close'] > indicators['SMA_50']", "required_indicators": ["SMA_50"], "description": "Price above 50-day SMA"}}
"20-day price change > 5%" → {{"code": "(data['close'] - data['close'].shift(20)) / data['close'].shift(20) > 0.05", "required_indicators": [], "description": "20-day price change greater than 5%"}}
"Volume above 20-day average" → {{"code": "data['volume'] > indicators['VOLUME_MA_20']", "required_indicators": ["VOLUME_MA_20"], "description": "Volume above 20-day average"}}
"MACD crosses above signal line" → {{"code": "(indicators['MACD_12_26_9'] > indicators['MACD_12_26_9_SIGNAL']) & (indicators['MACD_12_26_9'].shift(1) <= indicators['MACD_12_26_9_SIGNAL'].shift(1))", "required_indicators": ["MACD_12_26_9", "MACD_12_26_9_SIGNAL"], "description": "MACD crosses above signal line"}}
"Price crosses below lower Bollinger Band" → {{"code": "(data['close'] < indicators['Lower_Band_20']) & (data['close'].shift(1) >= indicators['Lower_Band_20'].shift(1))", "required_indicators": ["Lower_Band_20"], "description": "Price crosses below lower Bollinger Band"}}
"Price below lower Bollinger Band" → {{"code": "data['close'] < indicators['Lower_Band_20']", "required_indicators": ["Lower_Band_20"], "description": "Price below lower Bollinger Band"}}

INCORRECT EXAMPLES (DO NOT USE):
❌ "indicators['RSI']" - Missing period
❌ "indicators['SMA']" - Missing period
❌ "indicators['BB_L_20']" - Wrong format, use "Lower_Band_20"
❌ "indicators['MACD']" - Missing parameters
❌ "indicators['Volume_MA']" - Missing period
❌ "MACD crosses signal" without shift() - This detects state, not crossover

Now interpret the rule above and output JSON:"""
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self._call_ollama(prompt, use_code_model=True)
                
                # Parse JSON response
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if not json_match:
                    raise ValueError("No JSON found in response")
                
                json_str = json_match.group(0)
                result = json.loads(json_str)
                
                # Validate required fields
                if "code" not in result or "required_indicators" not in result:
                    raise ValueError("Missing required fields in response")
                
                logger.info(f"Interpreted rule: {rule} -> {result['code']}")
                return result
                
            except Exception as e:
                logger.warning(f"Failed to interpret rule on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise ValueError(f"Failed to interpret rule after {max_retries} attempts: {e}")
        
        raise ValueError("Failed to interpret trading rule")
    
    def generate_indicator_code(self, indicator_name: str, description: str, 
                               parameters: Dict[str, Any]) -> str:
        """
        Generate Python code for a custom technical indicator.
        
        Args:
            indicator_name: Name of the indicator (e.g., "Custom_RSI", "My_Momentum")
            description: Natural language description of what the indicator calculates
            parameters: Indicator parameters (e.g., {"period": 14, "smoothing": 2})
        
        Returns:
            Python function code as string that takes DataFrame and returns Series
        
        Raises:
            ConnectionError: If Ollama is unavailable
            ValueError: If code cannot be generated after retries
        """
        params_str = ", ".join(f"{k}={v}" for k, v in parameters.items())
        
        prompt = f"""You are a technical indicator code generator. Generate Python code for custom indicators.

INDICATOR TO GENERATE:
- Name: {indicator_name}
- Description: {description}
- Parameters: {params_str}

OUTPUT ONLY PYTHON CODE (no markdown, no explanations):

def {indicator_name.lower()}(data: pd.DataFrame, {params_str}) -> pd.Series:
    \"\"\"
    {description}
    
    Args:
        data: OHLCV DataFrame with columns: open, high, low, close, volume
        {params_str}
    
    Returns:
        pd.Series with indicator values
    \"\"\"
    # Your implementation here
    pass

REQUIREMENTS:
1. Use pandas vectorized operations (no loops)
2. Handle edge cases (NaN, insufficient data)
3. Return pd.Series with same index as input data
4. Use .fillna() or .dropna() appropriately
5. Include proper error handling
6. Use numpy for mathematical operations
7. Follow pandas best practices

EXAMPLES:

def simple_momentum(data: pd.DataFrame, period=14) -> pd.Series:
    \"\"\"Calculate simple momentum as price change over period.\"\"\"
    return data['close'] - data['close'].shift(period)

def custom_rsi(data: pd.DataFrame, period=14) -> pd.Series:
    \"\"\"Calculate RSI with custom period.\"\"\"
    delta = data['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

Now generate the code for {indicator_name}:"""
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self._call_ollama(prompt, use_code_model=True)
                
                # Extract Python code from response - try multiple patterns
                # Pattern 1: Look for code in markdown code blocks first
                code_match = re.search(r'```python\s*(def\s+.*?)```', response, re.DOTALL)
                if not code_match:
                    code_match = re.search(r'```\s*(def\s+.*?)```', response, re.DOTALL)
                
                # Pattern 2: Look for def statement to next def/class or double newline
                if not code_match:
                    code_match = re.search(r'(def\s+\w+[^:]*:.*?)(?=\n\n|\ndef\s+|\nclass\s+|$)', 
                                          response, re.DOTALL)
                
                # Pattern 3: Just get everything from def onwards
                if not code_match:
                    code_match = re.search(r'(def\s+\w+.*)', response, re.DOTALL)
                
                if not code_match:
                    raise ValueError("No function definition found in response")
                
                code = code_match.group(1).strip()
                
                # Clean up the code - remove any trailing incomplete lines
                lines = code.split('\n')
                cleaned_lines = []
                for line in lines:
                    # Stop if we hit an incomplete line or non-Python content
                    if line.strip() and not line.strip().startswith('#'):
                        # Check if line looks like Python code
                        if any(keyword in line for keyword in ['def ', 'return', '=', 'if ', 'for ', 'while ', 'import', 'from']):
                            cleaned_lines.append(line)
                        elif line.strip().startswith(('"""', "'''")):
                            cleaned_lines.append(line)
                        elif cleaned_lines and (line.startswith('    ') or line.startswith('\t')):
                            # Indented line following valid code
                            cleaned_lines.append(line)
                    elif line.strip().startswith('#'):
                        cleaned_lines.append(line)
                
                code = '\n'.join(cleaned_lines)
                
                # Basic validation: check if it's valid Python syntax
                try:
                    compile(code, '<string>', 'exec')
                except SyntaxError as e:
                    # Try to fix common issues
                    # If there's an unclosed string or parenthesis, truncate at that point
                    logger.warning(f"Syntax error in generated code: {e}, attempting to fix")
                    raise ValueError(f"Generated code has syntax error: {e}")
                
                logger.info(f"Generated indicator code for {indicator_name}")
                return code
                
            except Exception as e:
                logger.warning(f"Failed to generate indicator code on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise ValueError(f"Failed to generate indicator code after {max_retries} attempts: {e}")
        
        raise ValueError("Failed to generate indicator code")
    
    def generate_rule_evaluation_code(self, rule: str, available_indicators: List[str]) -> str:
        """
        Generate Python code to evaluate a trading rule against market data.
        
        Args:
            rule: Natural language rule description
            available_indicators: List of available indicator names
        
        Returns:
            Python code string that evaluates to boolean Series
        
        Raises:
            ConnectionError: If Ollama is unavailable
            ValueError: If code cannot be generated after retries
        """
        indicators_str = ", ".join(available_indicators)
        
        prompt = f"""You are a trading rule code generator. Generate Python code to evaluate trading rules.

RULE: "{rule}"
AVAILABLE INDICATORS: {indicators_str}

OUTPUT ONLY PYTHON CODE (single line expression, no function definition):

REQUIREMENTS:
1. Code must be a single Python expression
2. Returns boolean or boolean Series
3. Use data['column'] for OHLCV data
4. Use indicators['name'] for indicator values
5. Use pandas vectorized operations
6. Use & for AND, | for OR
7. No loops, no function calls except pandas/numpy

EXAMPLES:
Rule: "RSI below 30 and price above SMA"
Code: (indicators['RSI_14'] < 30) & (data['close'] > indicators['SMA_20'])

Rule: "Volume spike above 2x average"
Code: data['volume'] > (indicators['Volume_SMA_20'] * 2)

Rule: "Price breaks above upper Bollinger Band"
Code: data['close'] > indicators['BB_upper']

Now generate code for the rule above (single line only):"""
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self._call_ollama(prompt, use_code_model=True)
                
                # Extract code (should be single line)
                lines = [line.strip() for line in response.split('\n') if line.strip()]
                # Find the line that looks like code (contains operators or brackets)
                code_line = None
                for line in lines:
                    if any(op in line for op in ['>', '<', '&', '|', '[', '(', 'data', 'indicators']):
                        code_line = line
                        break
                
                if not code_line:
                    raise ValueError("No code expression found in response")
                
                # Basic validation
                try:
                    compile(code_line, '<string>', 'eval')
                except SyntaxError as e:
                    raise ValueError(f"Generated code has syntax error: {e}")
                
                logger.info(f"Generated rule evaluation code: {code_line}")
                return code_line
                
            except Exception as e:
                logger.warning(f"Failed to generate rule code on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise ValueError(f"Failed to generate rule code after {max_retries} attempts: {e}")
        
        raise ValueError("Failed to generate rule evaluation code")
    
    def _call_ollama(self, prompt: str, use_code_model: bool = False, temperature: float = 0.3) -> str:
        """
        Call Ollama API to generate response.
        
        Args:
            prompt: Formatted prompt
            use_code_model: If True, use the larger code generation model
            temperature: Temperature for generation (0.0-1.0). Higher = more random/creative
        
        Returns:
            Generated text response
        
        Raises:
            ConnectionError: If Ollama is unavailable
        """
        try:
            import time
            import random
            
            # Select model based on task type
            model = self.code_model if use_code_model else self.model
            
            # Use more random seed to prevent identical outputs
            seed = random.randint(0, 2147483647)
            
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json" if not use_code_model else None,  # JSON format for strategy, free-form for code
                "options": {
                    "temperature": temperature,  # Use provided temperature
                    "top_p": 0.9,
                    "seed": seed,  # Random seed to prevent caching
                    "num_predict": 1000 if use_code_model else 500,  # More tokens for code generation
                },
                "keep_alive": 0  # Don't keep model in memory (prevents caching)
            }
            
            response = requests.post(self.api_url, json=payload, timeout=120)  # Increase timeout
            response.raise_for_status()
            
            result = response.json()
            return result.get("response", "")
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama API call failed: {e}")
            raise ConnectionError(f"Failed to connect to Ollama: {e}")
    
    def _repair_json(self, json_str: str) -> str:
        """
        Repair common JSON syntax errors from LLM responses.
        Enhanced to handle trading-specific structures.
        
        Args:
            json_str: Potentially malformed JSON string
        
        Returns:
            Repaired JSON string
        """
        # Remove control characters (newlines, tabs in strings)
        json_str = json_str.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
        
        # Remove trailing commas before closing braces/brackets
        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
        
        # Fix missing commas between array elements
        json_str = re.sub(r'"\s+"', '", "', json_str)
        
        # Fix missing commas between object properties
        json_str = re.sub(r'"\s+"([^"]+)":', '", "\1":', json_str)
        
        # Remove comments (some LLMs add them)
        json_str = re.sub(r'//.*?(?=\n|$)', '', json_str)
        json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
        
        # Fix single quotes to double quotes (if any)
        json_str = re.sub(r"(?<!\\)'", '"', json_str)
        
        # Remove multiple spaces
        json_str = re.sub(r'\s+', ' ', json_str)
        
        # Fix common array/object formatting issues
        json_str = re.sub(r'\[\s*\]', '[]', json_str)
        json_str = re.sub(r'\{\s*\}', '{}', json_str)
        
        # Fix common trading-specific issues
        # Fix percentage values that might be written as "5%" instead of 0.05
        json_str = re.sub(r'"(\d+(?:\.\d+)?)%"', lambda m: str(float(m.group(1)) / 100), json_str)
        
        # Fix indicator names that might have spaces
        json_str = re.sub(r'"([A-Z]+)\s+(\d+)"', r'"\1_\2"', json_str)  # "RSI 14" -> "RSI_14"
        
        # Ensure numeric values are not quoted (except in specific fields)
        # This is tricky, so we'll be conservative
        
        return json_str.strip()
    
    def parse_response(self, response: str) -> StrategyDefinition:
        """
        Parse LLM response into structured strategy definition.
        
        Args:
            response: Raw LLM response text
        
        Returns:
            StrategyDefinition with parsed data
        
        Raises:
            ValueError: If response cannot be parsed
        """
        try:
            # Extract JSON from response (handle cases where LLM adds extra text)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in response")
            
            json_str = json_match.group(0)
            
            # Try to parse JSON, with repair if needed
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"Initial JSON parse failed: {e}. Attempting repair...")
                # Attempt to repair common JSON errors
                repaired_json = self._repair_json(json_str)
                try:
                    data = json.loads(repaired_json)
                    logger.info("Successfully repaired and parsed JSON")
                except json.JSONDecodeError as e2:
                    logger.error(f"JSON repair failed: {e2}")
                    logger.debug(f"Original JSON: {json_str[:500]}...")
                    logger.debug(f"Repaired JSON: {repaired_json[:500]}...")
                    raise ValueError(f"Failed to parse JSON even after repair: {e2}")
            
            # Extract required fields
            name = data.get("name", "")
            description = data.get("description", "")
            rules = data.get("rules", {})
            symbols = data.get("symbols", [])
            risk_params_data = data.get("risk_params", {})
            
            # Create RiskConfig from risk_params
            risk_params = RiskConfig(
                max_position_size_pct=risk_params_data.get("max_position_size_pct", 0.1),
                stop_loss_pct=risk_params_data.get("stop_loss_pct", 0.02),
                take_profit_pct=risk_params_data.get("take_profit_pct", 0.04)
            )
            
            # Capture reasoning metadata if present
            reasoning = None
            if "reasoning" in data:
                reasoning = self.capture_reasoning(data["reasoning"], response)
            
            strategy_def = StrategyDefinition(
                name=name,
                description=description,
                rules=rules,
                symbols=symbols,
                risk_params=risk_params,
                reasoning=reasoning,
                metadata={"raw_response": response}
            )
            
            logger.info(f"Parsed strategy: {name}")
            return strategy_def
        
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.debug(f"Response was: {response}")
            raise ValueError(f"Failed to parse strategy from LLM response: {e}")
    
    def capture_reasoning(self, reasoning_data: Dict[str, Any], llm_response: str) -> StrategyReasoning:
        """
        Extract reasoning metadata from LLM response.
        
        Args:
            reasoning_data: Parsed reasoning section from JSON
            llm_response: Raw LLM response for reference
        
        Returns:
            StrategyReasoning with hypothesis, alpha sources, assumptions
        
        Raises:
            ValueError: If reasoning data is incomplete
        """
        try:
            # Handle None or invalid input
            if not reasoning_data or not isinstance(reasoning_data, dict):
                logger.error("Invalid reasoning data provided")
                return StrategyReasoning(
                    hypothesis="Failed to parse reasoning",
                    alpha_sources=[AlphaSource(type="unknown", weight=1.0, description="Parsing failed")],
                    market_assumptions=["Failed to parse assumptions"],
                    signal_logic="Failed to parse signal logic",
                    llm_response=llm_response
                )
            
            # Extract hypothesis
            hypothesis = reasoning_data.get("hypothesis", "")
            if not hypothesis:
                logger.warning("Missing hypothesis in reasoning data")
                hypothesis = "No hypothesis provided"
            
            # Extract alpha sources
            alpha_sources = []
            alpha_sources_data = reasoning_data.get("alpha_sources", [])
            for source_data in alpha_sources_data:
                if isinstance(source_data, dict):
                    alpha_source = AlphaSource(
                        type=source_data.get("type", "unknown"),
                        weight=float(source_data.get("weight", 0.5)),
                        description=source_data.get("description", "")
                    )
                    alpha_sources.append(alpha_source)
            
            # If no alpha sources provided, create a default one
            if not alpha_sources:
                logger.warning("No alpha sources in reasoning data, creating default")
                alpha_sources.append(AlphaSource(
                    type="unspecified",
                    weight=1.0,
                    description="Alpha source not specified by LLM"
                ))
            
            # Extract market assumptions
            market_assumptions = reasoning_data.get("market_assumptions", [])
            if not market_assumptions:
                logger.warning("No market assumptions in reasoning data")
                market_assumptions = ["No assumptions specified"]
            
            # Extract signal logic
            signal_logic = reasoning_data.get("signal_logic", "")
            if not signal_logic:
                logger.warning("Missing signal logic in reasoning data")
                signal_logic = "No signal logic provided"
            
            # Extract confidence factors
            confidence_factors = reasoning_data.get("confidence_factors", {})
            
            reasoning = StrategyReasoning(
                hypothesis=hypothesis,
                alpha_sources=alpha_sources,
                market_assumptions=market_assumptions,
                signal_logic=signal_logic,
                confidence_factors=confidence_factors,
                llm_response=llm_response
            )
            
            logger.info(f"Captured reasoning with {len(alpha_sources)} alpha sources")
            return reasoning
        
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Failed to capture reasoning: {e}")
            # Return a minimal reasoning object rather than failing
            return StrategyReasoning(
                hypothesis="Failed to parse reasoning",
                alpha_sources=[AlphaSource(type="unknown", weight=1.0, description="Parsing failed")],
                market_assumptions=["Failed to parse assumptions"],
                signal_logic="Failed to parse signal logic",
                llm_response=llm_response
            )
    
    def validate_strategy(self, strategy: StrategyDefinition) -> ValidationResult:
        """
        Validate strategy completeness and correctness.
        
        Args:
            strategy: Strategy definition to validate
        
        Returns:
            ValidationResult with validation status and errors
        """
        errors = []
        warnings = []
        
        # Validate required fields
        if not strategy.name or not strategy.name.strip():
            errors.append("Strategy name is required")
        
        if not strategy.description or not strategy.description.strip():
            errors.append("Strategy description is required")
        
        if not strategy.symbols or len(strategy.symbols) == 0:
            errors.append("At least one symbol is required")
        
        # Validate rules structure
        if not strategy.rules:
            errors.append("Strategy rules are required")
        else:
            if "entry_conditions" not in strategy.rules:
                errors.append("Entry conditions are required in rules")
            elif not strategy.rules["entry_conditions"]:
                errors.append("At least one entry condition is required")
            
            if "exit_conditions" not in strategy.rules:
                errors.append("Exit conditions are required in rules")
            elif not strategy.rules["exit_conditions"]:
                errors.append("At least one exit condition is required")
        
        # Validate symbols format
        for symbol in strategy.symbols:
            if not isinstance(symbol, str) or not symbol.strip():
                errors.append(f"Invalid symbol: {symbol}")
            elif not re.match(r'^[A-Z0-9\-]+$', symbol.upper()):
                warnings.append(f"Symbol '{symbol}' may not be valid (expected uppercase alphanumeric)")
        
        # Validate risk parameters
        if strategy.risk_params.max_position_size_pct <= 0 or strategy.risk_params.max_position_size_pct > 1:
            errors.append("max_position_size_pct must be between 0 and 1")
        
        if strategy.risk_params.stop_loss_pct <= 0 or strategy.risk_params.stop_loss_pct > 1:
            errors.append("stop_loss_pct must be between 0 and 1")
        
        if strategy.risk_params.take_profit_pct <= 0 or strategy.risk_params.take_profit_pct > 1:
            errors.append("take_profit_pct must be between 0 and 1")
        
        # Validate indicator consistency between rules and indicators list
        if strategy.rules and "indicators" in strategy.rules:
            indicators_list = strategy.rules.get("indicators", [])
            
            # Normalize indicator names for comparison
            normalized_indicators = set()
            for ind in indicators_list:
                if isinstance(ind, str):
                    normalized_indicators.add(ind.upper().replace(" ", "_"))
            
            # Check entry conditions
            entry_conditions = strategy.rules.get("entry_conditions", [])
            for condition in entry_conditions:
                if isinstance(condition, str):
                    # Check for common indicator references
                    condition_upper = condition.upper()
                    
                    # Check for Bollinger Bands references
                    if any(bb_ref in condition_upper for bb_ref in ["LOWER_BAND", "UPPER_BAND", "MIDDLE_BAND", "BOLLINGER"]):
                        if not any(ind in ["BOLLINGER_BANDS", "BBANDS", "BOLLINGER BANDS"] for ind in normalized_indicators):
                            errors.append(f"Entry condition references Bollinger Bands but 'Bollinger Bands' not in indicators list: {condition}")
                    
                    # Check for MACD references
                    if "MACD" in condition_upper and "MACD" not in normalized_indicators:
                        errors.append(f"Entry condition references MACD but 'MACD' not in indicators list: {condition}")
                    
                    # Check for Stochastic references
                    if any(stoch_ref in condition_upper for stoch_ref in ["STOCH", "%K", "%D"]):
                        if not any(ind in ["STOCHASTIC", "STOCH", "STOCHASTIC_OSCILLATOR"] for ind in normalized_indicators):
                            errors.append(f"Entry condition references Stochastic but 'Stochastic' not in indicators list: {condition}")
            
            # Check exit conditions
            exit_conditions = strategy.rules.get("exit_conditions", [])
            for condition in exit_conditions:
                if isinstance(condition, str):
                    condition_upper = condition.upper()
                    
                    # Check for Bollinger Bands references
                    if any(bb_ref in condition_upper for bb_ref in ["LOWER_BAND", "UPPER_BAND", "MIDDLE_BAND", "BOLLINGER"]):
                        if not any(ind in ["BOLLINGER_BANDS", "BBANDS", "BOLLINGER BANDS"] for ind in normalized_indicators):
                            errors.append(f"Exit condition references Bollinger Bands but 'Bollinger Bands' not in indicators list: {condition}")
                    
                    # Check for MACD references
                    if "MACD" in condition_upper and "MACD" not in normalized_indicators:
                        errors.append(f"Exit condition references MACD but 'MACD' not in indicators list: {condition}")
                    
                    # Check for Stochastic references
                    if any(stoch_ref in condition_upper for stoch_ref in ["STOCH", "%K", "%D"]):
                        if not any(ind in ["STOCHASTIC", "STOCH", "STOCHASTIC_OSCILLATOR"] for ind in normalized_indicators):
                            errors.append(f"Exit condition references Stochastic but 'Stochastic' not in indicators list: {condition}")
        
        is_valid = len(errors) == 0
        
        if is_valid:
            logger.info(f"Strategy '{strategy.name}' validated successfully")
        else:
            logger.warning(f"Strategy validation failed: {errors}")
        
        return ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)
    
    def translate_vibe_code(self, natural_language: str) -> TradingCommand:
        """
        Translate natural language trading command to executable action.
        
        Args:
            natural_language: Natural language trading command
        
        Returns:
            TradingCommand with structured action
        
        Raises:
            ConnectionError: If Ollama is unavailable
            ValueError: If command cannot be parsed
        """
        # Extract quantity directly from input text before LLM processing
        # This prevents LLM hallucination of quantities
        extracted_quantity = self._extract_quantity_from_text(natural_language)
        has_dollar_amount = extracted_quantity is not None
        
        # Check if user specified units/shares
        import re
        unit_pattern = r'(\d+(?:\.\d+)?)\s*(unit|share|coin)s?'
        unit_match = re.search(unit_pattern, natural_language, re.IGNORECASE)
        
        # If we extracted a quantity, inject it into the prompt to guide the LLM
        if extracted_quantity is not None:
            prompt = self._format_vibe_code_prompt(natural_language, extracted_quantity)
        else:
            prompt = self._format_vibe_code_prompt(natural_language)
        
        try:
            response = self._call_ollama(prompt)
            command = self._parse_trading_command(response)
            
            # ALWAYS override LLM quantity if we extracted a dollar amount
            # If no dollar amount was found (units/shares), convert to dollars
            if has_dollar_amount:
                logger.info(f"Overriding LLM quantity {command.quantity} with extracted {extracted_quantity}")
                command.quantity = extracted_quantity
            elif unit_match:
                # User specified units/shares - need to convert to dollars
                # Get the number of units
                num_units = float(unit_match.group(1))
                logger.info(f"User specified {num_units} units/shares of {command.symbol}, converting to dollars")
                
                # Get current market price to convert
                try:
                    from src.api.etoro_client import EToroAPIClient
                    from src.core.config import get_config
                    from src.models.enums import TradingMode
                    
                    config = get_config()
                    # Try demo credentials first, fall back to live
                    try:
                        credentials = config.load_credentials(TradingMode.DEMO)
                    except Exception as _cred_err:
                        # DEMO credentials not configured — this is expected when
                        # running live-only. Log at DEBUG and fall back.
                        logger.debug(
                            f"DEMO credentials unavailable ({_cred_err}); "
                            f"falling back to LIVE credentials"
                        )
                        credentials = config.load_credentials(TradingMode.LIVE)
                    
                    if credentials and credentials.get("public_key") and credentials.get("user_key"):
                        etoro_client = EToroAPIClient(
                            public_key=credentials["public_key"],
                            user_key=credentials["user_key"],
                            mode=TradingMode.DEMO
                        )
                        market_data = etoro_client.get_market_data(command.symbol)
                        dollar_amount = num_units * market_data.close
                        
                        # Enforce minimum of $10
                        if dollar_amount < 10.0:
                            logger.warning(f"Calculated amount ${dollar_amount:.2f} below minimum, adjusting to $10.00")
                            dollar_amount = 10.0
                        
                        logger.info(f"Converted {num_units} units of {command.symbol} to ${dollar_amount:.2f} at price ${market_data.close:.2f}")
                        command.quantity = dollar_amount
                    else:
                        # No credentials available, default to $10 minimum
                        logger.warning(f"Cannot convert units to dollars (no credentials), defaulting to $10")
                        command.quantity = 10.0
                except Exception as e:
                    logger.error(f"Failed to convert units to dollars: {e}, defaulting to $10")
                    command.quantity = 10.0
            else:
                # No dollar amount or units found - default to minimum
                logger.info(f"No dollar amount or units found, defaulting to $10 minimum")
                command.quantity = 10.0
                command.reason = natural_language
            
            logger.info(f"Translated vibe code: {natural_language} -> {command.action} {command.symbol} ${command.quantity}")
            return command
        
        except Exception as e:
            logger.error(f"Failed to translate vibe code: {e}")
            raise
    
    def _extract_quantity_from_text(self, text: str) -> Optional[float]:
        """
        Extract dollar quantity directly from input text using regex.
        This prevents LLM hallucination of quantities.
        
        Args:
            text: Natural language input
            
        Returns:
            Extracted quantity or None if not found
        """
        import re
        
        # Pattern to match dollar amounts: $800, $1000, 500 dollars, etc.
        patterns = [
            r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',  # $800, $1,000, $1000.50
            r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*dollars?',  # 800 dollars, 1000 dollar
            r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*worth',  # 500 worth
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Extract number and remove commas
                amount_str = match.group(1).replace(',', '')
                amount = float(amount_str)
                
                # Enforce minimum of $10
                if amount < 10.0:
                    logger.warning(f"Extracted quantity ${amount:.2f} below minimum, adjusting to $10.00")
                    amount = 10.0
                
                logger.info(f"Extracted quantity from text: ${amount:.2f}")
                return amount
        
        # Check for "unit" or "share" patterns - these should return None
        # so the LLM can interpret them (but we'll note it in the log)
        unit_pattern = r'(\d+)\s*(unit|share|coin)s?'
        unit_match = re.search(unit_pattern, text, re.IGNORECASE)
        if unit_match:
            logger.info(f"Found unit/share pattern: {unit_match.group(0)} - letting LLM interpret")
            return None
        
        logger.info("No dollar amount found in text")
        return None
    
    def _format_vibe_code_prompt(self, natural_language: str, extracted_quantity: Optional[float] = None) -> str:
        """Format prompt for vibe-coding translation."""
        
        # Add timestamp to make each prompt unique (prevents caching)
        import time
        timestamp = int(time.time() * 1000)
        
        # If we extracted a quantity, tell the LLM exactly what it is
        quantity_hint = ""
        if extracted_quantity is not None:
            quantity_hint = f"\nIMPORTANT: The dollar amount in this command is EXACTLY ${extracted_quantity:.2f}. Use this exact number for quantity."
        
        return f"""You are a trading command interpreter. Convert this command to JSON format. [Request ID: {timestamp}]

COMMAND: "{natural_language}"{quantity_hint}

OUTPUT ONLY THIS JSON (no other text):
{{
    "action": "ENTER_LONG",
    "symbol": "AAPL",
    "quantity": 800,
    "price": null,
    "reason": "Buy $800 of Apple stock"
}}

RULES:
1. action MUST be exactly one of: ENTER_LONG, ENTER_SHORT, EXIT_LONG, EXIT_SHORT
   - buy/purchase/long → ENTER_LONG
   - sell/short → ENTER_SHORT
   - close/exit → EXIT_LONG or EXIT_SHORT

2. symbol: Extract ticker (AAPL, GOOGL, TSLA, BTC, ETH, etc.)
   - "Bitcoin" or "BTC" → "BTC"
   - "Apple" → "AAPL"
   - "Tesla" → "TSLA"

3. quantity: Extract the EXACT dollar amount as a number
   - "$800" → 800
   - "$100" → 100
   - "500 dollars" → 500
   - "1 unit" or "1 share" → null (system will calculate)
   - No amount → null (will default to $10)
   - DO NOT add zeros or change the number
   - Minimum is 10

4. price: Only if "at $X" or "limit $X" specified, otherwise null

5. reason: Describe what the command does
   - If dollar amount: "Buy $800 of BTC"
   - If units/shares: "Buy 1 unit of BTC"

EXAMPLES:
"buy $800 of BTC" → {{"action": "ENTER_LONG", "symbol": "BTC", "quantity": 800, "price": null, "reason": "Buy $800 of BTC"}}
"buy $100 of Bitcoin" → {{"action": "ENTER_LONG", "symbol": "BTC", "quantity": 100, "price": null, "reason": "Buy $100 of Bitcoin"}}
"buy 1 unit of BTC" → {{"action": "ENTER_LONG", "symbol": "BTC", "quantity": null, "price": null, "reason": "Buy 1 unit of BTC"}}
"purchase $500 worth of TSLA" → {{"action": "ENTER_LONG", "symbol": "TSLA", "quantity": 500, "price": null, "reason": "Purchase $500 worth of TSLA"}}

Now convert the command above to JSON:"""
    
    def _parse_trading_command(self, response: str) -> TradingCommand:
        """Parse LLM response into trading command."""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in response")
            
            json_str = json_match.group(0)
            data = json.loads(json_str)
            
            # Parse action with fallback mapping for common variations
            action_str = data.get("action", "").upper().replace(" ", "_")
            
            # Map common action variations to valid SignalAction values
            action_mapping = {
                "BUY": "ENTER_LONG",
                "SELL": "ENTER_SHORT",
                "LONG": "ENTER_LONG",
                "SHORT": "ENTER_SHORT",
                "BUY_LONG": "ENTER_LONG",
                "SELL_SHORT": "ENTER_SHORT",
                "CLOSE": "EXIT_LONG",
                "EXIT": "EXIT_LONG",
            }
            
            # Apply mapping if needed
            if action_str in action_mapping:
                logger.info(f"Mapping action '{action_str}' to '{action_mapping[action_str]}'")
                action_str = action_mapping[action_str]
            
            try:
                action = SignalAction[action_str]
            except KeyError:
                raise ValueError(f"Invalid action: {action_str}")
            
            symbol = data.get("symbol", "").upper()
            if not symbol:
                raise ValueError("Symbol is required")
            
            # Parse quantity and enforce minimum
            quantity = data.get("quantity")
            if quantity is not None:
                quantity = float(quantity)
                # Enforce eToro minimum of $10
                if quantity < 10.0:
                    logger.warning(f"Quantity ${quantity:.2f} below minimum, adjusting to $10.00")
                    quantity = 10.0
            
            command = TradingCommand(
                action=action,
                symbol=symbol,
                quantity=quantity,
                price=data.get("price"),
                reason=data.get("reason", ""),
                metadata={"raw_response": response}
            )
            
            return command
        
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse trading command: {e}")
            logger.debug(f"Response was: {response}")
            raise ValueError(f"Failed to parse trading command from LLM response: {e}")
