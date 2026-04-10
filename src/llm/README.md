# LLM Service

The LLM Service provides AI-powered strategy generation and natural language trading command translation using a local Ollama instance.

## Features

- **Strategy Generation**: Generate trading strategies from natural language descriptions
- **Strategy Validation**: Validate strategy completeness and correctness
- **Vibe Coding**: Translate natural language commands into structured trading actions
- **Retry Logic**: Automatic retry with clarified prompts for invalid LLM responses
- **Graceful Degradation**: Handles Ollama unavailability without crashing

## Requirements

- Ollama running locally (default: http://localhost:11434)
- Ollama model installed (default: qwen2.5-coder:7b)

## Installation

1. Install Ollama: https://ollama.ai/
2. Pull the model:
   ```bash
   ollama pull qwen2.5-coder:7b
   ```
3. Start Ollama:
   ```bash
   ollama serve
   ```

## Usage

### Strategy Generation

```python
from src.llm.llm_service import LLMService
from src.models.dataclasses import RiskConfig

# Initialize service
llm_service = LLMService(model="qwen2.5-coder:7b")

# Define market context
market_context = {
    "risk_config": RiskConfig(),
    "available_symbols": ["AAPL", "MSFT", "GOOGL"]
}

# Generate strategy
strategy = llm_service.generate_strategy(
    "Create a momentum strategy for tech stocks",
    market_context
)

print(f"Strategy: {strategy.name}")
print(f"Symbols: {strategy.symbols}")
print(f"Entry: {strategy.rules['entry_conditions']}")
```

### Strategy Validation

```python
from src.llm.llm_service import StrategyDefinition
from src.models.dataclasses import RiskConfig

strategy = StrategyDefinition(
    name="My Strategy",
    description="A trading strategy",
    rules={
        "entry_conditions": ["Price > MA"],
        "exit_conditions": ["Price < MA"]
    },
    symbols=["AAPL"],
    risk_params=RiskConfig()
)

result = llm_service.validate_strategy(strategy)
if result.is_valid:
    print("Strategy is valid!")
else:
    print(f"Errors: {result.errors}")
```

### Vibe Coding

```python
# Translate natural language to trading command
command = llm_service.translate_vibe_code("buy 100 shares of Apple")

print(f"Action: {command.action}")  # ENTER_LONG
print(f"Symbol: {command.symbol}")  # AAPL
print(f"Quantity: {command.quantity}")  # 100
```

## Data Models

### StrategyDefinition

Structured strategy definition from LLM:

```python
@dataclass
class StrategyDefinition:
    name: str
    description: str
    rules: Dict[str, Any]  # entry_conditions, exit_conditions, indicators, timeframe
    symbols: List[str]
    risk_params: RiskConfig
    metadata: Dict[str, Any]
```

### TradingCommand

Structured trading command from natural language:

```python
@dataclass
class TradingCommand:
    action: SignalAction  # ENTER_LONG, ENTER_SHORT, EXIT_LONG, EXIT_SHORT
    symbol: str
    quantity: Optional[float]
    price: Optional[float]
    reason: str
    metadata: Dict[str, Any]
```

### ValidationResult

Result of strategy validation:

```python
@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str]
    warnings: List[str]
```

## Error Handling

The service handles errors gracefully:

- **Ollama Unavailable**: Logs warning, raises ConnectionError on API calls
- **Invalid JSON**: Retries with clarified prompt (up to 3 attempts)
- **Invalid Strategy**: Returns validation errors, retries generation
- **Parsing Errors**: Raises ValueError with detailed error message

## Configuration

```python
# Custom model and endpoint
llm_service = LLMService(
    model="mistral:7b",
    base_url="http://custom-host:11434"
)
```

## Examples

See `examples/llm_service_example.py` for complete examples:

```bash
python3 examples/llm_service_example.py
```

## Testing

Run unit tests:

```bash
python3 -m pytest tests/test_llm_service.py -v
```

## Requirements Validation

This implementation satisfies:

- **Requirement 7.1**: Connects to local Ollama instance
- **Requirement 7.2**: Handles Ollama unavailable errors gracefully
- **Requirement 7.3**: Provides market context and constraints in prompts
- **Requirement 7.4**: Parses LLM responses into structured definitions
- **Requirement 7.5**: Retries with clarified prompts on invalid responses
- **Requirement 7.6**: Validates strategy completeness and correctness
- **Requirement 7.7**: Supports vibe-coding translation

## Design Properties

This implementation validates:

- **Property 20**: LLM strategy generation context includes market context and risk constraints
- **Property 21**: LLM responses are parsed into StrategyDefinition with all required fields
- **Property 22**: Generated strategies are validated for completeness and correctness
