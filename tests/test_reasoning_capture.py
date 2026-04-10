"""Unit tests for reasoning capture functionality."""

import json
import pytest

from src.llm.llm_service import (
    AlphaSource,
    LLMService,
    StrategyReasoning,
)
from src.models.dataclasses import RiskConfig


class TestReasoningCapture:
    """Test reasoning capture functionality."""
    
    def test_parse_response_with_reasoning(self):
        """Test parsing response with reasoning metadata."""
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
            },
            "reasoning": {
                "hypothesis": "Stocks with strong momentum tend to continue trending",
                "alpha_sources": [
                    {
                        "type": "momentum",
                        "weight": 0.8,
                        "description": "Price momentum drives returns"
                    },
                    {
                        "type": "mean_reversion",
                        "weight": 0.2,
                        "description": "Exit on reversal signals"
                    }
                ],
                "market_assumptions": [
                    "Markets exhibit momentum in trending conditions",
                    "RSI is a reliable momentum indicator"
                ],
                "signal_logic": "Enter when RSI exceeds 70, exit when RSI drops below 30",
                "confidence_factors": {
                    "trend_strength": 0.8,
                    "volume_confirmation": 0.6
                }
            }
        })
        
        strategy = service.parse_response(response)
        
        assert strategy.name == "Momentum Strategy"
        assert strategy.reasoning is not None
        assert strategy.reasoning.hypothesis == "Stocks with strong momentum tend to continue trending"
        assert len(strategy.reasoning.alpha_sources) == 2
        assert strategy.reasoning.alpha_sources[0].type == "momentum"
        assert strategy.reasoning.alpha_sources[0].weight == 0.8
        assert len(strategy.reasoning.market_assumptions) == 2
        assert strategy.reasoning.signal_logic == "Enter when RSI exceeds 70, exit when RSI drops below 30"
        assert strategy.reasoning.confidence_factors["trend_strength"] == 0.8
    
    def test_parse_response_without_reasoning(self):
        """Test parsing response without reasoning metadata."""
        service = LLMService()
        response = json.dumps({
            "name": "Simple Strategy",
            "description": "A simple strategy",
            "rules": {
                "entry_conditions": ["Buy signal"],
                "exit_conditions": ["Sell signal"]
            },
            "symbols": ["BTC"],
            "risk_params": {
                "max_position_size_pct": 0.1,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04
            }
        })
        
        strategy = service.parse_response(response)
        
        assert strategy.name == "Simple Strategy"
        assert strategy.reasoning is None
    
    def test_capture_reasoning_complete(self):
        """Test capturing complete reasoning data."""
        service = LLMService()
        reasoning_data = {
            "hypothesis": "Test hypothesis",
            "alpha_sources": [
                {
                    "type": "momentum",
                    "weight": 0.7,
                    "description": "Momentum alpha"
                }
            ],
            "market_assumptions": ["Assumption 1", "Assumption 2"],
            "signal_logic": "Test signal logic",
            "confidence_factors": {"factor1": 0.8}
        }
        
        reasoning = service.capture_reasoning(reasoning_data, "raw response")
        
        assert reasoning.hypothesis == "Test hypothesis"
        assert len(reasoning.alpha_sources) == 1
        assert reasoning.alpha_sources[0].type == "momentum"
        assert len(reasoning.market_assumptions) == 2
        assert reasoning.signal_logic == "Test signal logic"
        assert reasoning.llm_response == "raw response"
    
    def test_capture_reasoning_missing_fields(self):
        """Test capturing reasoning with missing fields uses defaults."""
        service = LLMService()
        reasoning_data = {
            "hypothesis": "Test hypothesis"
            # Missing alpha_sources, market_assumptions, signal_logic
        }
        
        reasoning = service.capture_reasoning(reasoning_data, "raw response")
        
        assert reasoning.hypothesis == "Test hypothesis"
        assert len(reasoning.alpha_sources) == 1  # Default alpha source
        assert reasoning.alpha_sources[0].type == "unspecified"
        assert len(reasoning.market_assumptions) == 1  # Default assumption
        assert reasoning.signal_logic == "No signal logic provided"
    
    def test_capture_reasoning_invalid_data(self):
        """Test capturing reasoning with invalid data returns minimal object."""
        service = LLMService()
        reasoning_data = None  # Invalid
        
        reasoning = service.capture_reasoning(reasoning_data, "raw response")
        
        assert reasoning.hypothesis == "Failed to parse reasoning"
        assert len(reasoning.alpha_sources) == 1
        assert reasoning.alpha_sources[0].type == "unknown"
    
    def test_alpha_source_dataclass(self):
        """Test AlphaSource dataclass."""
        alpha_source = AlphaSource(
            type="momentum",
            weight=0.75,
            description="Price momentum"
        )
        
        assert alpha_source.type == "momentum"
        assert alpha_source.weight == 0.75
        assert alpha_source.description == "Price momentum"
    
    def test_strategy_reasoning_dataclass(self):
        """Test StrategyReasoning dataclass."""
        alpha_sources = [
            AlphaSource(type="momentum", weight=0.6, description="Momentum alpha"),
            AlphaSource(type="mean_reversion", weight=0.4, description="Mean reversion alpha")
        ]
        
        reasoning = StrategyReasoning(
            hypothesis="Test hypothesis",
            alpha_sources=alpha_sources,
            market_assumptions=["Assumption 1"],
            signal_logic="Test logic",
            confidence_factors={"factor1": 0.8},
            llm_prompt="Test prompt",
            llm_response="Test response"
        )
        
        assert reasoning.hypothesis == "Test hypothesis"
        assert len(reasoning.alpha_sources) == 2
        assert reasoning.alpha_sources[0].weight == 0.6
        assert reasoning.market_assumptions == ["Assumption 1"]
        assert reasoning.signal_logic == "Test logic"
        assert reasoning.confidence_factors["factor1"] == 0.8
        assert reasoning.llm_prompt == "Test prompt"
        assert reasoning.llm_response == "Test response"
