"""
Unit tests for autonomous configuration validation logic.

Tests the validation rules without requiring a running server.
"""

import pytest
from typing import Dict, Any, List


def validate_autonomous_config(config: Dict[str, Any]) -> List[str]:
    """
    Validate autonomous configuration.
    
    This is extracted from the endpoint logic for testing purposes.
    
    Args:
        config: Configuration dictionary to validate
        
    Returns:
        List of validation error messages (empty if valid)
    """
    validation_errors = []
    
    # Validate autonomous settings
    if "autonomous" in config:
        auto_config = config["autonomous"]
        
        if "enabled" in auto_config and not isinstance(auto_config["enabled"], bool):
            validation_errors.append("autonomous.enabled must be a boolean")
        
        if "proposal_frequency" in auto_config:
            valid_frequencies = ["daily", "weekly", "monthly"]
            if auto_config["proposal_frequency"] not in valid_frequencies:
                validation_errors.append(
                    f"autonomous.proposal_frequency must be one of: {', '.join(valid_frequencies)}"
                )
        
        if "max_active_strategies" in auto_config:
            max_strat = auto_config["max_active_strategies"]
            if not isinstance(max_strat, int) or max_strat < 1 or max_strat > 50:
                validation_errors.append("autonomous.max_active_strategies must be between 1 and 50")
        
        if "min_active_strategies" in auto_config:
            min_strat = auto_config["min_active_strategies"]
            if not isinstance(min_strat, int) or min_strat < 1:
                validation_errors.append("autonomous.min_active_strategies must be >= 1")
        
        # Check min <= max
        if "min_active_strategies" in auto_config and "max_active_strategies" in auto_config:
            if auto_config["min_active_strategies"] > auto_config["max_active_strategies"]:
                validation_errors.append(
                    "autonomous.min_active_strategies must be <= max_active_strategies"
                )
    
    # Validate activation thresholds
    if "activation_thresholds" in config:
        thresholds = config["activation_thresholds"]
        
        if "min_sharpe" in thresholds:
            if not isinstance(thresholds["min_sharpe"], (int, float)) or thresholds["min_sharpe"] < 0:
                validation_errors.append("activation_thresholds.min_sharpe must be >= 0")
        
        if "max_drawdown" in thresholds:
            dd = thresholds["max_drawdown"]
            if not isinstance(dd, (int, float)) or dd < 0 or dd > 1:
                validation_errors.append("activation_thresholds.max_drawdown must be between 0 and 1")
        
        if "min_win_rate" in thresholds:
            wr = thresholds["min_win_rate"]
            if not isinstance(wr, (int, float)) or wr < 0 or wr > 1:
                validation_errors.append("activation_thresholds.min_win_rate must be between 0 and 1")
        
        if "min_trades" in thresholds:
            if not isinstance(thresholds["min_trades"], int) or thresholds["min_trades"] < 1:
                validation_errors.append("activation_thresholds.min_trades must be >= 1")
    
    # Validate retirement thresholds
    if "retirement_thresholds" in config:
        thresholds = config["retirement_thresholds"]
        
        if "max_sharpe" in thresholds:
            if not isinstance(thresholds["max_sharpe"], (int, float)) or thresholds["max_sharpe"] < 0:
                validation_errors.append("retirement_thresholds.max_sharpe must be >= 0")
        
        if "max_drawdown" in thresholds:
            dd = thresholds["max_drawdown"]
            if not isinstance(dd, (int, float)) or dd < 0 or dd > 1:
                validation_errors.append("retirement_thresholds.max_drawdown must be between 0 and 1")
        
        if "min_win_rate" in thresholds:
            wr = thresholds["min_win_rate"]
            if not isinstance(wr, (int, float)) or wr < 0 or wr > 1:
                validation_errors.append("retirement_thresholds.min_win_rate must be between 0 and 1")
        
        if "min_trades_for_evaluation" in thresholds:
            if not isinstance(thresholds["min_trades_for_evaluation"], int) or thresholds["min_trades_for_evaluation"] < 1:
                validation_errors.append("retirement_thresholds.min_trades_for_evaluation must be >= 1")
    
    # Validate backtest settings
    if "backtest" in config:
        backtest = config["backtest"]
        
        if "days" in backtest:
            if not isinstance(backtest["days"], int) or backtest["days"] < 30 or backtest["days"] > 3650:
                validation_errors.append("backtest.days must be between 30 and 3650")
        
        if "warmup_days" in backtest:
            if not isinstance(backtest["warmup_days"], int) or backtest["warmup_days"] < 0:
                validation_errors.append("backtest.warmup_days must be >= 0")
        
        if "min_trades" in backtest:
            if not isinstance(backtest["min_trades"], int) or backtest["min_trades"] < 1:
                validation_errors.append("backtest.min_trades must be >= 1")
    
    return validation_errors


class TestAutonomousConfigValidation:
    """Test suite for autonomous configuration validation."""
    
    def test_valid_config(self):
        """Test that a valid configuration passes validation."""
        config = {
            "autonomous": {
                "enabled": True,
                "proposal_frequency": "weekly",
                "max_active_strategies": 10,
                "min_active_strategies": 5
            },
            "activation_thresholds": {
                "min_sharpe": 1.5,
                "max_drawdown": 0.15,
                "min_win_rate": 0.5,
                "min_trades": 20
            },
            "retirement_thresholds": {
                "max_sharpe": 0.5,
                "max_drawdown": 0.15,
                "min_win_rate": 0.4,
                "min_trades_for_evaluation": 30
            },
            "backtest": {
                "days": 90,
                "warmup_days": 50,
                "min_trades": 10
            }
        }
        
        errors = validate_autonomous_config(config)
        assert len(errors) == 0, f"Valid config should have no errors, got: {errors}"
    
    def test_invalid_enabled_type(self):
        """Test that non-boolean enabled value fails validation."""
        config = {
            "autonomous": {
                "enabled": "yes"  # Should be boolean
            }
        }
        
        errors = validate_autonomous_config(config)
        assert len(errors) == 1
        assert "autonomous.enabled must be a boolean" in errors[0]
    
    def test_invalid_frequency(self):
        """Test that invalid frequency fails validation."""
        config = {
            "autonomous": {
                "proposal_frequency": "hourly"  # Invalid
            }
        }
        
        errors = validate_autonomous_config(config)
        assert len(errors) == 1
        assert "proposal_frequency must be one of" in errors[0]
    
    def test_invalid_max_strategies_range(self):
        """Test that max_active_strategies outside valid range fails."""
        # Test too low
        config1 = {
            "autonomous": {
                "max_active_strategies": 0
            }
        }
        errors1 = validate_autonomous_config(config1)
        assert len(errors1) == 1
        assert "max_active_strategies must be between 1 and 50" in errors1[0]
        
        # Test too high
        config2 = {
            "autonomous": {
                "max_active_strategies": 100
            }
        }
        errors2 = validate_autonomous_config(config2)
        assert len(errors2) == 1
        assert "max_active_strategies must be between 1 and 50" in errors2[0]
    
    def test_min_greater_than_max_strategies(self):
        """Test that min > max strategies fails validation."""
        config = {
            "autonomous": {
                "min_active_strategies": 15,
                "max_active_strategies": 10
            }
        }
        
        errors = validate_autonomous_config(config)
        assert len(errors) == 1
        assert "min_active_strategies must be <= max_active_strategies" in errors[0]
    
    def test_negative_sharpe_ratio(self):
        """Test that negative Sharpe ratio fails validation."""
        config = {
            "activation_thresholds": {
                "min_sharpe": -1.0
            }
        }
        
        errors = validate_autonomous_config(config)
        assert len(errors) == 1
        assert "min_sharpe must be >= 0" in errors[0]
    
    def test_invalid_drawdown_range(self):
        """Test that drawdown outside 0-1 range fails validation."""
        # Test negative
        config1 = {
            "activation_thresholds": {
                "max_drawdown": -0.1
            }
        }
        errors1 = validate_autonomous_config(config1)
        assert len(errors1) == 1
        assert "max_drawdown must be between 0 and 1" in errors1[0]
        
        # Test > 1
        config2 = {
            "activation_thresholds": {
                "max_drawdown": 1.5
            }
        }
        errors2 = validate_autonomous_config(config2)
        assert len(errors2) == 1
        assert "max_drawdown must be between 0 and 1" in errors2[0]
    
    def test_invalid_win_rate_range(self):
        """Test that win rate outside 0-1 range fails validation."""
        config = {
            "activation_thresholds": {
                "min_win_rate": 1.5
            }
        }
        
        errors = validate_autonomous_config(config)
        assert len(errors) == 1
        assert "min_win_rate must be between 0 and 1" in errors[0]
    
    def test_invalid_min_trades(self):
        """Test that invalid min_trades fails validation."""
        config = {
            "activation_thresholds": {
                "min_trades": 0
            }
        }
        
        errors = validate_autonomous_config(config)
        assert len(errors) == 1
        assert "min_trades must be >= 1" in errors[0]
    
    def test_invalid_backtest_days_range(self):
        """Test that backtest days outside valid range fails."""
        # Test too low
        config1 = {
            "backtest": {
                "days": 10
            }
        }
        errors1 = validate_autonomous_config(config1)
        assert len(errors1) == 1
        assert "backtest.days must be between 30 and 3650" in errors1[0]
        
        # Test too high
        config2 = {
            "backtest": {
                "days": 5000
            }
        }
        errors2 = validate_autonomous_config(config2)
        assert len(errors2) == 1
        assert "backtest.days must be between 30 and 3650" in errors2[0]
    
    def test_multiple_validation_errors(self):
        """Test that multiple validation errors are all reported."""
        config = {
            "autonomous": {
                "enabled": "yes",  # Invalid type
                "proposal_frequency": "hourly",  # Invalid value
                "min_active_strategies": 15,
                "max_active_strategies": 10  # min > max
            },
            "activation_thresholds": {
                "min_sharpe": -1.0,  # Negative
                "max_drawdown": 1.5  # > 1
            }
        }
        
        errors = validate_autonomous_config(config)
        assert len(errors) == 5
    
    def test_partial_config_update(self):
        """Test that partial config updates are validated correctly."""
        # Only updating one field should work
        config = {
            "autonomous": {
                "max_active_strategies": 12
            }
        }
        
        errors = validate_autonomous_config(config)
        assert len(errors) == 0
    
    def test_valid_edge_cases(self):
        """Test valid edge case values."""
        config = {
            "autonomous": {
                "max_active_strategies": 1,  # Minimum valid
                "min_active_strategies": 1
            },
            "activation_thresholds": {
                "min_sharpe": 0.0,  # Minimum valid
                "max_drawdown": 0.0,  # Minimum valid
                "min_win_rate": 0.0,  # Minimum valid
                "min_trades": 1  # Minimum valid
            },
            "backtest": {
                "days": 30,  # Minimum valid
                "warmup_days": 0  # Minimum valid
            }
        }
        
        errors = validate_autonomous_config(config)
        assert len(errors) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
