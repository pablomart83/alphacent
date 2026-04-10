"""Example usage of LLM Service for strategy generation and vibe-coding."""

import logging
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llm.llm_service import LLMService
from src.models.dataclasses import RiskConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def example_strategy_generation():
    """Example: Generate a trading strategy using LLM."""
    logger.info("=== Strategy Generation Example ===")
    
    # Initialize LLM service
    llm_service = LLMService(model="qwen2.5-coder:7b")
    
    # Define market context
    market_context = {
        "risk_config": RiskConfig(
            max_position_size_pct=0.1,
            max_exposure_pct=0.8,
            position_risk_pct=0.01,
            stop_loss_pct=0.02,
            take_profit_pct=0.04
        ),
        "available_symbols": ["AAPL", "MSFT", "GOOGL", "TSLA", "BTC", "ETH"]
    }
    
    # Generate strategy
    prompt = "Create a momentum trading strategy for tech stocks that buys on RSI oversold and sells on RSI overbought"
    
    try:
        strategy = llm_service.generate_strategy(prompt, market_context)
        
        logger.info(f"Generated Strategy: {strategy.name}")
        logger.info(f"Description: {strategy.description}")
        logger.info(f"Symbols: {strategy.symbols}")
        logger.info(f"Entry Conditions: {strategy.rules.get('entry_conditions', [])}")
        logger.info(f"Exit Conditions: {strategy.rules.get('exit_conditions', [])}")
        logger.info(f"Risk Parameters:")
        logger.info(f"  - Max Position Size: {strategy.risk_params.max_position_size_pct * 100}%")
        logger.info(f"  - Stop Loss: {strategy.risk_params.stop_loss_pct * 100}%")
        logger.info(f"  - Take Profit: {strategy.risk_params.take_profit_pct * 100}%")
        
    except ConnectionError as e:
        logger.error(f"Ollama is not available: {e}")
        logger.info("Make sure Ollama is running: ollama serve")
    except Exception as e:
        logger.error(f"Failed to generate strategy: {e}")


def example_vibe_coding():
    """Example: Translate natural language to trading commands."""
    logger.info("\n=== Vibe Coding Example ===")
    
    # Initialize LLM service
    llm_service = LLMService(model="qwen2.5-coder:7b")
    
    # Example natural language commands
    commands = [
        "buy 100 shares of Apple",
        "sell my Tesla position",
        "go long on Bitcoin",
        "close all my Microsoft shares"
    ]
    
    for natural_language in commands:
        try:
            command = llm_service.translate_vibe_code(natural_language)
            
            logger.info(f"\nInput: '{natural_language}'")
            logger.info(f"  Action: {command.action.value}")
            logger.info(f"  Symbol: {command.symbol}")
            if command.quantity:
                logger.info(f"  Quantity: {command.quantity}")
            if command.price:
                logger.info(f"  Price: {command.price}")
            logger.info(f"  Reason: {command.reason}")
            
        except ConnectionError as e:
            logger.error(f"Ollama is not available: {e}")
            break
        except Exception as e:
            logger.error(f"Failed to translate command: {e}")


def example_strategy_validation():
    """Example: Validate a strategy definition."""
    logger.info("\n=== Strategy Validation Example ===")
    
    from src.llm.llm_service import StrategyDefinition
    
    llm_service = LLMService()
    
    # Valid strategy
    valid_strategy = StrategyDefinition(
        name="Mean Reversion Strategy",
        description="Buy when price is below moving average, sell when above",
        rules={
            "entry_conditions": ["Price < 20-day MA", "RSI < 30"],
            "exit_conditions": ["Price > 20-day MA", "RSI > 70"],
            "indicators": ["MA", "RSI"],
            "timeframe": "1d"
        },
        symbols=["AAPL", "MSFT"],
        risk_params=RiskConfig()
    )
    
    result = llm_service.validate_strategy(valid_strategy)
    logger.info(f"Valid Strategy: {result.is_valid}")
    if result.errors:
        logger.info(f"Errors: {result.errors}")
    if result.warnings:
        logger.info(f"Warnings: {result.warnings}")
    
    # Invalid strategy (missing entry conditions)
    invalid_strategy = StrategyDefinition(
        name="Incomplete Strategy",
        description="Missing entry conditions",
        rules={
            "exit_conditions": ["Price > target"]
        },
        symbols=["AAPL"],
        risk_params=RiskConfig()
    )
    
    result = llm_service.validate_strategy(invalid_strategy)
    logger.info(f"\nInvalid Strategy: {result.is_valid}")
    if result.errors:
        logger.info(f"Errors: {result.errors}")


if __name__ == "__main__":
    logger.info("LLM Service Examples")
    logger.info("=" * 50)
    logger.info("Note: These examples require Ollama to be running locally")
    logger.info("Start Ollama with: ollama serve")
    logger.info("=" * 50)
    
    # Run examples
    example_strategy_generation()
    example_vibe_coding()
    example_strategy_validation()
    
    logger.info("\n" + "=" * 50)
    logger.info("Examples completed!")
