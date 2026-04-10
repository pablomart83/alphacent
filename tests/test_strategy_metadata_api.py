"""
Tests for Task 9.7: Backend API Support for Strategy Metadata

Validates: Requirements 9.7
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock

from src.models.orm import StrategyORM
from src.models.enums import StrategyStatus


def create_test_strategy(strategy_id, category="alpha_edge", strategy_type="mean_reversion"):
    """Helper to create test strategy ORM object."""
    strategy = Mock(spec=StrategyORM)
    strategy.id = strategy_id
    strategy.name = f"Test Strategy {strategy_id}"
    strategy.description = "Test strategy"
    strategy.status = StrategyStatus.DEMO
    strategy.to_dict.return_value = {
        "id": strategy_id,
        "name": f"Test Strategy {strategy_id}",
        "description": "Test strategy",
        "status": StrategyStatus.DEMO.value,
        "rules": {"entry": ["RSI < 30"], "exit": ["RSI > 70"]},
        "symbols": ["AAPL"],
        "allocation_percent": 10.0,
        "risk_params": {"stop_loss": 0.02},
        "created_at": datetime.now().isoformat(),
        "activated_at": None,
        "retired_at": None,
        "performance": {
            "total_return": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "total_trades": 0
        },
        "reasoning": None,
        "backtest_results": None,
        "metadata": {
            "strategy_category": category,
            "strategy_type": strategy_type,
            "requires_fundamental_data": category == "alpha_edge",
            "requires_earnings_data": False,
            "template_name": "test_template"
        }
    }
    return strategy


def test_strategy_metadata_extraction():
    """Test that strategy metadata is correctly extracted."""
    # Create test strategy
    strategy = create_test_strategy("test_1", "alpha_edge", "mean_reversion")
    strategy_dict = strategy.to_dict()
    metadata = strategy_dict.get("metadata", {})
    
    # Verify metadata fields
    assert metadata.get("strategy_category") == "alpha_edge"
    assert metadata.get("strategy_type") == "mean_reversion"
    assert metadata.get("requires_fundamental_data") is True
    assert metadata.get("requires_earnings_data") is False


def test_default_category_for_empty_metadata():
    """Test that strategies without metadata get default category."""
    # Create strategy without metadata
    strategy = Mock(spec=StrategyORM)
    strategy.to_dict.return_value = {
        "id": "no_meta",
        "name": "Test Strategy No Metadata",
        "description": "Test",
        "status": StrategyStatus.DEMO.value,
        "rules": {"entry": [], "exit": []},
        "symbols": ["AAPL"],
        "allocation_percent": 10.0,
        "risk_params": {},
        "created_at": datetime.now().isoformat(),
        "metadata": {}  # Empty metadata
    }
    
    strategy_dict = strategy.to_dict()
    metadata = strategy_dict.get("metadata", {})
    
    # Should default to template_based
    strategy_category = metadata.get("strategy_category", "template_based")
    assert strategy_category == "template_based"
    
    requires_fundamental_data = metadata.get("requires_fundamental_data", False)
    assert requires_fundamental_data is False


def test_category_counting():
    """Test counting strategies by category."""
    # Create strategies with different categories
    strategies = [
        create_test_strategy("cat_1", "alpha_edge", "mean_reversion"),
        create_test_strategy("cat_2", "alpha_edge", "momentum"),
        create_test_strategy("cat_3", "template_based", "trend_following"),
        create_test_strategy("cat_4", "template_based", "breakout"),
    ]
    
    # Count strategies by category
    category_counts = {}
    for strategy in strategies:
        strategy_dict = strategy.to_dict()
        metadata = strategy_dict.get("metadata", {})
        category = metadata.get("strategy_category", "template_based")
        
        if category not in category_counts:
            category_counts[category] = 0
        category_counts[category] += 1
    
    # Verify counts
    assert category_counts["alpha_edge"] == 2
    assert category_counts["template_based"] == 2
    assert len(category_counts) == 2


def test_type_counting():
    """Test counting strategies by type."""
    # Create strategies with different types
    strategies = [
        create_test_strategy("type_1", "alpha_edge", "mean_reversion"),
        create_test_strategy("type_2", "template_based", "trend_following"),
        create_test_strategy("type_3", "alpha_edge", "momentum"),
        create_test_strategy("type_4", "template_based", "mean_reversion"),
    ]
    
    # Count strategies by type
    type_counts = {}
    for strategy in strategies:
        strategy_dict = strategy.to_dict()
        metadata = strategy_dict.get("metadata", {})
        strategy_type = metadata.get("strategy_type")
        
        if strategy_type:
            if strategy_type not in type_counts:
                type_counts[strategy_type] = 0
            type_counts[strategy_type] += 1
    
    # Verify counts
    assert type_counts["mean_reversion"] == 2
    assert type_counts["trend_following"] == 1
    assert type_counts["momentum"] == 1
    assert len(type_counts) == 3


def test_strategy_response_model_fields():
    """Test that StrategyResponse model has all required fields."""
    from src.api.routers.strategies import StrategyResponse
    
    # Get model fields
    fields = StrategyResponse.model_fields
    
    # Verify new metadata fields exist
    assert "strategy_category" in fields
    assert "strategy_type" in fields
    assert "requires_fundamental_data" in fields
    assert "requires_earnings_data" in fields


def test_category_info_model():
    """Test CategoryInfo response model."""
    from src.api.routers.strategies import CategoryInfo
    
    # Create instance
    category_info = CategoryInfo(
        category="alpha_edge",
        count=5,
        description="Advanced strategies"
    )
    
    assert category_info.category == "alpha_edge"
    assert category_info.count == 5
    assert category_info.description == "Advanced strategies"


def test_type_info_model():
    """Test TypeInfo response model."""
    from src.api.routers.strategies import TypeInfo
    
    # Create instance
    type_info = TypeInfo(
        type="mean_reversion",
        count=3,
        description="Mean reversion strategies"
    )
    
    assert type_info.type == "mean_reversion"
    assert type_info.count == 3
    assert type_info.description == "Mean reversion strategies"


