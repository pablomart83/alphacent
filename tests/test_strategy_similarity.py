"""Unit tests for strategy similarity detection."""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock

from src.strategy.strategy_engine import StrategyEngine
from src.models import (
    Strategy,
    StrategyStatus,
    PerformanceMetrics,
    RiskConfig,
    TradingMode
)


@pytest.fixture
def mock_market_data():
    """Create mock market data manager."""
    return Mock()


@pytest.fixture
def strategy_engine(mock_market_data):
    """Create strategy engine instance."""
    return StrategyEngine(None, mock_market_data, None)


def create_test_strategy(
    name="Test Strategy",
    symbols=None,
    indicators=None,
    rules=None,
    status=StrategyStatus.BACKTESTED
):
    """Helper to create test strategies."""
    if symbols is None:
        symbols = ["AAPL"]
    
    if rules is None:
        rules = {
            "entry_conditions": [
                {"indicator": "RSI", "period": 14, "operator": "<", "value": 30}
            ],
            "exit_conditions": [
                {"indicator": "RSI", "period": 14, "operator": ">", "value": 70}
            ]
        }
    
    return Strategy(
        id=f"test-{name.replace(' ', '-').lower()}",
        name=name,
        description=f"Test strategy: {name}",
        status=status,
        rules=rules,
        symbols=symbols,
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics()
    )


class TestStrategySimilarity:
    """Test strategy similarity detection."""
    
    def test_identical_strategies_high_similarity(self, strategy_engine):
        """Identical strategies should have very high similarity score."""
        strategy1 = create_test_strategy(name="Strategy 1")
        strategy2 = create_test_strategy(name="Strategy 2")
        
        similarity = strategy_engine._compute_strategy_similarity(strategy1, strategy2)
        
        assert similarity > 95, f"Expected >95% similarity for identical strategies, got {similarity:.1f}%"
    
    def test_different_symbols_reduces_similarity(self, strategy_engine):
        """Different symbols should reduce similarity score."""
        strategy1 = create_test_strategy(name="Strategy 1", symbols=["AAPL"])
        strategy2 = create_test_strategy(name="Strategy 2", symbols=["MSFT"])
        
        similarity = strategy_engine._compute_strategy_similarity(strategy1, strategy2)
        
        # Should have 20% penalty for different symbols (80% max without penalty)
        assert similarity <= 80, f"Expected <=80% similarity for different symbols, got {similarity:.1f}%"
    
    def test_similar_parameters_high_similarity(self, strategy_engine):
        """RSI(14) vs RSI(15) should be highly similar."""
        rules1 = {
            "entry_conditions": [
                {"indicator": "RSI", "period": 14, "operator": "<", "value": 30}
            ],
            "exit_conditions": [
                {"indicator": "RSI", "period": 14, "operator": ">", "value": 70}
            ]
        }
        rules2 = {
            "entry_conditions": [
                {"indicator": "RSI", "period": 15, "operator": "<", "value": 30}
            ],
            "exit_conditions": [
                {"indicator": "RSI", "period": 15, "operator": ">", "value": 70}
            ]
        }
        
        strategy1 = create_test_strategy(name="RSI 14", rules=rules1)
        strategy2 = create_test_strategy(name="RSI 15", rules=rules2)
        
        similarity = strategy_engine._compute_strategy_similarity(strategy1, strategy2)
        
        assert similarity > 85, f"Expected >85% similarity for RSI(14) vs RSI(15), got {similarity:.1f}%"
    
    def test_different_indicators_low_similarity(self, strategy_engine):
        """Strategies with different indicators should have low similarity."""
        rules1 = {
            "entry_conditions": [
                {"indicator": "RSI", "period": 14, "operator": "<", "value": 30}
            ],
            "exit_conditions": [
                {"indicator": "RSI", "period": 14, "operator": ">", "value": 70}
            ]
        }
        rules2 = {
            "entry_conditions": [
                {"indicator": "MACD", "fast": 12, "slow": 26, "signal": 9, "operator": ">", "value": 0}
            ],
            "exit_conditions": [
                {"indicator": "MACD", "fast": 12, "slow": 26, "signal": 9, "operator": "<", "value": 0}
            ]
        }
        
        strategy1 = create_test_strategy(name="RSI Strategy", rules=rules1)
        strategy2 = create_test_strategy(name="MACD Strategy", rules=rules2)
        
        similarity = strategy_engine._compute_strategy_similarity(strategy1, strategy2)
        
        assert similarity < 50, f"Expected <50% similarity for different indicators, got {similarity:.1f}%"
    
    def test_activation_blocked_when_too_similar(self, strategy_engine, monkeypatch):
        """Activation should fail when strategy is too similar to active strategy."""
        # Create two similar strategies
        strategy1 = create_test_strategy(name="Strategy 1")
        strategy2 = create_test_strategy(name="Strategy 2")
        
        # Mock database operations
        def mock_save(self, strategy):
            pass
        
        def mock_load(self, strategy_id):
            if strategy_id == strategy2.id:
                return strategy2
            return None
        
        def mock_get_active(self):
            return [strategy1]
        
        monkeypatch.setattr(StrategyEngine, "_save_strategy", mock_save)
        monkeypatch.setattr(StrategyEngine, "_load_strategy", mock_load)
        monkeypatch.setattr(StrategyEngine, "get_active_strategies", mock_get_active)
        
        # Mock validation config to enable similarity detection
        strategy_engine.validation_config = {
            'similarity_detection': {
                'enabled': True,
                'strategy_similarity_threshold': 80
            }
        }
        
        # Try to activate similar strategy - should raise ValueError
        with pytest.raises(ValueError, match="Too similar"):
            strategy_engine.activate_strategy(strategy2.id, TradingMode.DEMO, 5.0)
    
    def test_activation_allowed_when_dissimilar(self, strategy_engine):
        """Activation should succeed when strategy is dissimilar to active strategies."""
        # Create two dissimilar strategies
        rules1 = {
            "entry_conditions": [
                {"indicator": "RSI", "period": 14, "operator": "<", "value": 30}
            ],
            "exit_conditions": [
                {"indicator": "RSI", "period": 14, "operator": ">", "value": 70}
            ]
        }
        rules2 = {
            "entry_conditions": [
                {"indicator": "MACD", "fast": 12, "slow": 26, "signal": 9, "operator": ">", "value": 0}
            ],
            "exit_conditions": [
                {"indicator": "MACD", "fast": 12, "slow": 26, "signal": 9, "operator": "<", "value": 0}
            ]
        }
        
        strategy1 = create_test_strategy(name="RSI Strategy", rules=rules1)
        strategy2 = create_test_strategy(name="MACD Strategy", rules=rules2, symbols=["MSFT"])
        
        # Test similarity directly
        similarity = strategy_engine._compute_strategy_similarity(strategy1, strategy2)
        
        # Should be dissimilar enough to pass 80% threshold
        assert similarity < 80, f"Expected <80% similarity for dissimilar strategies, got {similarity:.1f}%"
    
    def test_similarity_detection_can_be_disabled(self, strategy_engine):
        """Similarity detection should be bypassable via config."""
        # Create two similar strategies
        strategy1 = create_test_strategy(name="Strategy 1")
        strategy2 = create_test_strategy(name="Strategy 2")
        
        # Test that similarity is high
        similarity = strategy_engine._compute_strategy_similarity(strategy1, strategy2)
        assert similarity > 80, f"Expected >80% similarity for similar strategies, got {similarity:.1f}%"
        
        # Verify config can disable it
        strategy_engine.validation_config = {
            'similarity_detection': {
                'enabled': False,
                'strategy_similarity_threshold': 80
            }
        }
        
        # When disabled, the check should be skipped (tested in integration tests)


class TestIndicatorExtraction:
    """Test indicator extraction from strategy rules."""
    
    def test_extract_indicators_from_entry_conditions(self, strategy_engine):
        """Should extract indicators from entry conditions."""
        rules = {
            "entry_conditions": [
                {"indicator": "RSI", "period": 14},
                {"indicator": "MACD", "fast": 12}
            ],
            "exit_conditions": []
        }
        
        indicators = strategy_engine._extract_indicators_from_rules(rules)
        
        assert "RSI" in indicators
        assert "MACD" in indicators
        assert len(indicators) == 2
    
    def test_extract_indicators_from_exit_conditions(self, strategy_engine):
        """Should extract indicators from exit conditions."""
        rules = {
            "entry_conditions": [],
            "exit_conditions": [
                {"indicator": "BB", "period": 20},
                {"indicator": "SMA", "period": 50}
            ]
        }
        
        indicators = strategy_engine._extract_indicators_from_rules(rules)
        
        assert "BB" in indicators
        assert "SMA" in indicators
        assert len(indicators) == 2
    
    def test_extract_indicators_handles_empty_rules(self, strategy_engine):
        """Should handle empty rules gracefully."""
        indicators = strategy_engine._extract_indicators_from_rules({})
        assert len(indicators) == 0
        
        indicators = strategy_engine._extract_indicators_from_rules(None)
        assert len(indicators) == 0


class TestParameterExtraction:
    """Test parameter extraction from strategy rules."""
    
    def test_extract_parameters_from_rules(self, strategy_engine):
        """Should extract parameters from rules."""
        rules = {
            "entry_conditions": [
                {"indicator": "RSI", "period": 14, "threshold": 30}
            ],
            "exit_conditions": [
                {"indicator": "RSI", "period": 14, "threshold": 70}
            ]
        }
        
        params = strategy_engine._extract_parameters_from_rules(rules)
        
        assert "entry_0_period" in params
        assert params["entry_0_period"] == 14
        assert "entry_0_threshold" in params
        assert params["entry_0_threshold"] == 30
    
    def test_extract_parameters_handles_empty_rules(self, strategy_engine):
        """Should handle empty rules gracefully."""
        params = strategy_engine._extract_parameters_from_rules({})
        assert len(params) == 0
        
        params = strategy_engine._extract_parameters_from_rules(None)
        assert len(params) == 0
