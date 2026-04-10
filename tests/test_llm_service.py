"""Unit tests for LLM Service."""

import json
from unittest.mock import Mock, patch

import pytest

from src.llm.llm_service import (
    LLMService,
    StrategyDefinition,
    TradingCommand,
    ValidationResult,
)
from src.models.dataclasses import RiskConfig
from src.models.enums import SignalAction


class TestLLMService:
    """Test LLM Service functionality."""
    
    @patch('src.llm.llm_service.requests.get')
    def test_initialization_with_available_ollama(self, mock_get):
        """Test LLM service initializes when Ollama is available."""
        mock_get.return_value.status_code = 200
        
        service = LLMService()
        
        assert service.model == "llama3.2:1b"
        assert service.base_url == "http://localhost:11434"
        mock_get.assert_called_once()
    
    @patch('src.llm.llm_service.requests.get')
    def test_initialization_with_unavailable_ollama(self, mock_get):
        """Test LLM service handles Ollama unavailable gracefully."""
        import requests
        mock_get.side_effect = requests.exceptions.RequestException("Connection refused")
        
        # Should not raise, just log warning
        service = LLMService()
        
        assert service.model == "llama3.2:1b"
    
    def test_parse_response_valid_json(self):
        """Test parsing valid JSON response."""
        service = LLMService()
        response = json.dumps({
            "name": "Momentum Strategy",
            "description": "Buy on momentum, sell on reversal",
            "rules": {
                "entry_conditions": ["RSI > 70"],
                "exit_conditions": ["RSI < 30"],
                "indicators": ["RSI"],
                "timeframe": "1d"
            },
            "symbols": ["AAPL", "MSFT"],
            "risk_params": {
                "max_position_size_pct": 0.1,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04
            }
        })
        
        strategy = service.parse_response(response)
        
        assert strategy.name == "Momentum Strategy"
        assert strategy.description == "Buy on momentum, sell on reversal"
        assert "entry_conditions" in strategy.rules
        assert strategy.symbols == ["AAPL", "MSFT"]
        assert strategy.risk_params.max_position_size_pct == 0.1
    
    def test_parse_response_with_extra_text(self):
        """Test parsing JSON embedded in extra text."""
        service = LLMService()
        response = """Here is the strategy:
        
        {
            "name": "Test Strategy",
            "description": "A test strategy",
            "rules": {
                "entry_conditions": ["Price > MA"],
                "exit_conditions": ["Price < MA"]
            },
            "symbols": ["BTC"],
            "risk_params": {
                "max_position_size_pct": 0.05,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.06
            }
        }
        
        This should work well."""
        
        strategy = service.parse_response(response)
        
        assert strategy.name == "Test Strategy"
        assert strategy.symbols == ["BTC"]
    
    def test_parse_response_invalid_json(self):
        """Test parsing invalid JSON raises error."""
        service = LLMService()
        response = "This is not JSON at all"
        
        with pytest.raises(ValueError, match="No JSON found"):
            service.parse_response(response)
    
    def test_validate_strategy_valid(self):
        """Test validation of valid strategy."""
        service = LLMService()
        strategy = StrategyDefinition(
            name="Valid Strategy",
            description="A valid strategy",
            rules={
                "entry_conditions": ["Condition 1"],
                "exit_conditions": ["Condition 2"]
            },
            symbols=["AAPL"],
            risk_params=RiskConfig()
        )
        
        result = service.validate_strategy(strategy)
        
        assert result.is_valid
        assert len(result.errors) == 0
    
    def test_validate_strategy_missing_name(self):
        """Test validation fails for missing name."""
        service = LLMService()
        strategy = StrategyDefinition(
            name="",
            description="A strategy",
            rules={
                "entry_conditions": ["Condition 1"],
                "exit_conditions": ["Condition 2"]
            },
            symbols=["AAPL"],
            risk_params=RiskConfig()
        )
        
        result = service.validate_strategy(strategy)
        
        assert not result.is_valid
        assert any("name" in error.lower() for error in result.errors)
    
    def test_validate_strategy_missing_symbols(self):
        """Test validation fails for missing symbols."""
        service = LLMService()
        strategy = StrategyDefinition(
            name="Strategy",
            description="A strategy",
            rules={
                "entry_conditions": ["Condition 1"],
                "exit_conditions": ["Condition 2"]
            },
            symbols=[],
            risk_params=RiskConfig()
        )
        
        result = service.validate_strategy(strategy)
        
        assert not result.is_valid
        assert any("symbol" in error.lower() for error in result.errors)
    
    def test_validate_strategy_missing_entry_conditions(self):
        """Test validation fails for missing entry conditions."""
        service = LLMService()
        strategy = StrategyDefinition(
            name="Strategy",
            description="A strategy",
            rules={
                "exit_conditions": ["Condition 2"]
            },
            symbols=["AAPL"],
            risk_params=RiskConfig()
        )
        
        result = service.validate_strategy(strategy)
        
        assert not result.is_valid
        assert any("entry" in error.lower() for error in result.errors)
    
    def test_validate_strategy_invalid_risk_params(self):
        """Test validation fails for invalid risk parameters."""
        service = LLMService()
        strategy = StrategyDefinition(
            name="Strategy",
            description="A strategy",
            rules={
                "entry_conditions": ["Condition 1"],
                "exit_conditions": ["Condition 2"]
            },
            symbols=["AAPL"],
            risk_params=RiskConfig(max_position_size_pct=1.5)  # Invalid: > 1
        )
        
        result = service.validate_strategy(strategy)
        
        assert not result.is_valid
        assert any("max_position_size_pct" in error for error in result.errors)
    
    @patch('src.llm.llm_service.requests.post')
    @patch('src.llm.llm_service.requests.get')
    def test_generate_strategy_success(self, mock_get, mock_post):
        """Test successful strategy generation."""
        mock_get.return_value.status_code = 200
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "response": json.dumps({
                "name": "Generated Strategy",
                "description": "LLM generated strategy",
                "rules": {
                    "entry_conditions": ["Buy signal"],
                    "exit_conditions": ["Sell signal"]
                },
                "symbols": ["AAPL"],
                "risk_params": {
                    "max_position_size_pct": 0.1,
                    "stop_loss_pct": 0.02,
                    "take_profit_pct": 0.04
                }
            })
        }
        
        service = LLMService()
        strategy = service.generate_strategy(
            "Create a momentum strategy",
            {"risk_config": RiskConfig(), "available_symbols": ["AAPL", "MSFT"]}
        )
        
        assert strategy.name == "Generated Strategy"
        assert strategy.symbols == ["AAPL"]
    
    @patch('src.llm.llm_service.requests.post')
    @patch('src.llm.llm_service.requests.get')
    def test_generate_strategy_retry_on_invalid(self, mock_get, mock_post):
        """Test strategy generation retries on invalid response."""
        mock_get.return_value.status_code = 200
        
        # First call returns invalid strategy (missing entry conditions)
        # Second call returns valid strategy
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.side_effect = [
            {
                "response": json.dumps({
                    "name": "Invalid Strategy",
                    "description": "Missing entry conditions",
                    "rules": {
                        "exit_conditions": ["Sell signal"]
                    },
                    "symbols": ["AAPL"],
                    "risk_params": {
                        "max_position_size_pct": 0.1,
                        "stop_loss_pct": 0.02,
                        "take_profit_pct": 0.04
                    }
                })
            },
            {
                "response": json.dumps({
                    "name": "Valid Strategy",
                    "description": "Now with entry conditions",
                    "rules": {
                        "entry_conditions": ["Buy signal"],
                        "exit_conditions": ["Sell signal"]
                    },
                    "symbols": ["AAPL"],
                    "risk_params": {
                        "max_position_size_pct": 0.1,
                        "stop_loss_pct": 0.02,
                        "take_profit_pct": 0.04
                    }
                })
            }
        ]
        
        service = LLMService()
        strategy = service.generate_strategy(
            "Create a strategy",
            {"risk_config": RiskConfig()}
        )
        
        assert strategy.name == "Valid Strategy"
        assert mock_post.call_count == 2
    
    def test_parse_trading_command_buy(self):
        """Test parsing buy command."""
        service = LLMService()
        response = json.dumps({
            "action": "ENTER_LONG",
            "symbol": "AAPL",
            "quantity": 10,
            "price": None,
            "reason": "User wants to buy AAPL"
        })
        
        command = service._parse_trading_command(response)
        
        assert command.action == SignalAction.ENTER_LONG
        assert command.symbol == "AAPL"
        assert command.quantity == 10
    
    def test_parse_trading_command_sell(self):
        """Test parsing sell command."""
        service = LLMService()
        response = json.dumps({
            "action": "EXIT_LONG",
            "symbol": "MSFT",
            "quantity": None,
            "price": 350.0,
            "reason": "User wants to exit MSFT position"
        })
        
        command = service._parse_trading_command(response)
        
        assert command.action == SignalAction.EXIT_LONG
        assert command.symbol == "MSFT"
        assert command.price == 350.0
    
    def test_parse_trading_command_invalid_action(self):
        """Test parsing command with invalid action."""
        service = LLMService()
        response = json.dumps({
            "action": "INVALID_ACTION",
            "symbol": "AAPL",
            "reason": "Test"
        })
        
        with pytest.raises(ValueError, match="Invalid action"):
            service._parse_trading_command(response)
    
    def test_parse_trading_command_missing_symbol(self):
        """Test parsing command with missing symbol."""
        service = LLMService()
        response = json.dumps({
            "action": "ENTER_LONG",
            "symbol": "",
            "reason": "Test"
        })
        
        with pytest.raises(ValueError, match="Symbol is required"):
            service._parse_trading_command(response)
    
    @patch('src.llm.llm_service.requests.post')
    @patch('src.llm.llm_service.requests.get')
    def test_translate_vibe_code(self, mock_get, mock_post):
        """Test vibe code translation."""
        mock_get.return_value.status_code = 200
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "response": json.dumps({
                "action": "ENTER_LONG",
                "symbol": "BTC",
                "quantity": None,
                "price": None,
                "reason": "User wants to buy Bitcoin"
            })
        }
        
        service = LLMService()
        command = service.translate_vibe_code("buy some bitcoin")
        
        assert command.action == SignalAction.ENTER_LONG
        assert command.symbol == "BTC"
