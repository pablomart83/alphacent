"""Tests for Strategy Template Library."""

import pytest

from src.strategy.strategy_proposer import MarketRegime
from src.strategy.strategy_templates import (
    StrategyTemplateLibrary,
    StrategyType,
    StrategyTemplate
)


class TestStrategyTemplateLibrary:
    """Test suite for Strategy Template Library."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.library = StrategyTemplateLibrary()
    
    def test_library_initialization(self):
        """Test that library initializes with templates."""
        assert self.library is not None
        assert len(self.library.templates) > 0
    
    def test_template_count(self):
        """Test that library contains 8-10 templates as specified."""
        count = self.library.get_template_count()
        assert 8 <= count <= 10, f"Expected 8-10 templates, got {count}"
    
    def test_all_templates_have_required_fields(self):
        """Test that all templates have required fields populated."""
        for template in self.library.get_all_templates():
            # Check required string fields
            assert template.name, f"Template missing name"
            assert template.description, f"Template {template.name} missing description"
            assert template.strategy_type, f"Template {template.name} missing strategy_type"
            
            # Check required list fields
            assert len(template.market_regimes) > 0, f"Template {template.name} has no market regimes"
            assert len(template.entry_conditions) > 0, f"Template {template.name} has no entry conditions"
            assert len(template.exit_conditions) > 0, f"Template {template.name} has no exit conditions"
            assert len(template.required_indicators) > 0, f"Template {template.name} has no required indicators"
            
            # Check required dict fields
            assert template.default_parameters is not None, f"Template {template.name} missing default_parameters"
            assert len(template.default_parameters) > 0, f"Template {template.name} has empty default_parameters"
            
            # Check expected characteristics
            assert template.expected_trade_frequency, f"Template {template.name} missing expected_trade_frequency"
            assert template.expected_holding_period, f"Template {template.name} missing expected_holding_period"
            assert template.risk_reward_ratio > 0, f"Template {template.name} has invalid risk_reward_ratio"
    
    def test_mean_reversion_templates(self):
        """Test that mean reversion templates exist and are properly configured."""
        mean_reversion = self.library.get_templates_by_type(StrategyType.MEAN_REVERSION)
        
        # Should have at least 3 mean reversion templates
        assert len(mean_reversion) >= 3, f"Expected at least 3 mean reversion templates, got {len(mean_reversion)}"
        
        # All should be suitable for RANGING markets
        for template in mean_reversion:
            assert MarketRegime.RANGING in template.market_regimes, \
                f"Mean reversion template {template.name} should be suitable for RANGING markets"
    
    def test_trend_following_templates(self):
        """Test that trend following templates exist and are properly configured."""
        trend_following = self.library.get_templates_by_type(StrategyType.TREND_FOLLOWING)
        
        # Should have at least 2 trend following templates
        assert len(trend_following) >= 2, f"Expected at least 2 trend following templates, got {len(trend_following)}"
        
        # All should be suitable for TRENDING markets
        for template in trend_following:
            assert (MarketRegime.TRENDING_UP in template.market_regimes or 
                   MarketRegime.TRENDING_DOWN in template.market_regimes), \
                f"Trend following template {template.name} should be suitable for TRENDING markets"
    
    def test_volatility_templates(self):
        """Test that volatility templates exist and are properly configured."""
        volatility = self.library.get_templates_by_type(StrategyType.VOLATILITY)
        
        # Should have at least 2 volatility templates
        assert len(volatility) >= 2, f"Expected at least 2 volatility templates, got {len(volatility)}"
    
    def test_get_templates_for_regime(self):
        """Test filtering templates by market regime."""
        # Test RANGING regime
        ranging_templates = self.library.get_templates_for_regime(MarketRegime.RANGING)
        assert len(ranging_templates) > 0, "Should have templates for RANGING regime"
        
        # Test TRENDING_UP regime
        trending_up_templates = self.library.get_templates_for_regime(MarketRegime.TRENDING_UP)
        assert len(trending_up_templates) > 0, "Should have templates for TRENDING_UP regime"
        
        # Test TRENDING_DOWN regime
        trending_down_templates = self.library.get_templates_for_regime(MarketRegime.TRENDING_DOWN)
        assert len(trending_down_templates) > 0, "Should have templates for TRENDING_DOWN regime"
    
    def test_get_template_by_name(self):
        """Test retrieving template by name."""
        # Get first template name
        first_template = self.library.get_all_templates()[0]
        
        # Retrieve by name
        retrieved = self.library.get_template_by_name(first_template.name)
        assert retrieved is not None
        assert retrieved.name == first_template.name
        
        # Test non-existent template
        non_existent = self.library.get_template_by_name("Non-Existent Template")
        assert non_existent is None
    
    def test_regime_coverage(self):
        """Test that all market regimes have template coverage."""
        coverage = self.library.get_regime_coverage()
        
        # All regimes should have at least one template
        for regime in MarketRegime:
            assert coverage[regime] > 0, f"No templates available for {regime}"
    
    def test_rsi_mean_reversion_template(self):
        """Test RSI Mean Reversion template specifics."""
        template = self.library.get_template_by_name("RSI Mean Reversion")
        assert template is not None
        
        # Check strategy type
        assert template.strategy_type == StrategyType.MEAN_REVERSION
        
        # Check market regime
        assert MarketRegime.RANGING in template.market_regimes
        
        # Check indicators
        assert "RSI_14" in template.required_indicators
        
        # Check parameters
        assert "rsi_period" in template.default_parameters
        assert "oversold_threshold" in template.default_parameters
        assert "overbought_threshold" in template.default_parameters
        
        # Check thresholds are reasonable
        assert template.default_parameters["oversold_threshold"] <= 35
        assert template.default_parameters["overbought_threshold"] >= 65
    
    def test_bollinger_band_bounce_template(self):
        """Test Bollinger Band Bounce template specifics."""
        template = self.library.get_template_by_name("Bollinger Band Bounce")
        assert template is not None
        
        # Check strategy type
        assert template.strategy_type == StrategyType.MEAN_REVERSION
        
        # Check indicators - should have all 3 bands
        assert "Lower_Band_20" in template.required_indicators
        assert "Middle_Band_20" in template.required_indicators
        assert "Upper_Band_20" in template.required_indicators
        
        # Check parameters
        assert "bb_period" in template.default_parameters
        assert "bb_std" in template.default_parameters
    
    def test_moving_average_crossover_template(self):
        """Test Moving Average Crossover template specifics."""
        template = self.library.get_template_by_name("Moving Average Crossover")
        assert template is not None
        
        # Check strategy type
        assert template.strategy_type == StrategyType.TREND_FOLLOWING
        
        # Check market regimes - should work for both trending directions
        assert MarketRegime.TRENDING_UP in template.market_regimes
        assert MarketRegime.TRENDING_DOWN in template.market_regimes
        
        # Check indicators
        assert "SMA_20" in template.required_indicators
        assert "SMA_50" in template.required_indicators
        
        # Check parameters
        assert "fast_period" in template.default_parameters
        assert "slow_period" in template.default_parameters
        assert template.default_parameters["fast_period"] < template.default_parameters["slow_period"]
    
    def test_macd_momentum_template(self):
        """Test MACD Momentum template specifics."""
        template = self.library.get_template_by_name("MACD Momentum")
        assert template is not None
        
        # Check strategy type
        assert template.strategy_type == StrategyType.TREND_FOLLOWING
        
        # Check indicators
        assert "MACD_12_26_9" in template.required_indicators
        assert "MACD_12_26_9_SIGNAL" in template.required_indicators
    
    def test_atr_breakout_template(self):
        """Test ATR Volatility Breakout template specifics."""
        template = self.library.get_template_by_name("ATR Volatility Breakout")
        assert template is not None
        
        # Check strategy type
        assert template.strategy_type == StrategyType.VOLATILITY
        
        # Check indicators
        assert "ATR_14" in template.required_indicators
        assert "SMA_20" in template.required_indicators
        
        # Check parameters
        assert "atr_period" in template.default_parameters
        assert "atr_multiplier" in template.default_parameters
        assert template.default_parameters["atr_multiplier"] >= 1.5
    
    def test_template_names_are_unique(self):
        """Test that all template names are unique."""
        names = [t.name for t in self.library.get_all_templates()]
        assert len(names) == len(set(names)), "Template names must be unique"
    
    def test_indicator_naming_convention(self):
        """Test that all indicators follow the naming convention."""
        for template in self.library.get_all_templates():
            for indicator in template.required_indicators:
                # Check that indicator names follow standard format
                # Should be like: RSI_14, SMA_20, MACD_12_26_9, etc.
                # Or simple names like: Support, Resistance
                assert indicator, f"Template {template.name} has empty indicator name"
                
                # If it contains underscore, should have period number
                if "_" in indicator and indicator not in ["MACD_12_26_9_SIGNAL", "MACD_12_26_9_HIST"]:
                    parts = indicator.split("_")
                    # Last part should be numeric (period) or band identifier
                    last_part = parts[-1]
                    assert last_part.isdigit() or last_part in ["20", "UB", "MB", "LB"], \
                        f"Indicator {indicator} in template {template.name} doesn't follow naming convention"
    
    def test_entry_exit_conditions_not_empty(self):
        """Test that entry and exit conditions are meaningful."""
        for template in self.library.get_all_templates():
            # Entry conditions should not be empty strings
            for condition in template.entry_conditions:
                assert condition.strip(), f"Template {template.name} has empty entry condition"
                assert len(condition) > 10, f"Template {template.name} has suspiciously short entry condition"
            
            # Exit conditions should not be empty strings
            for condition in template.exit_conditions:
                assert condition.strip(), f"Template {template.name} has empty exit condition"
                assert len(condition) > 10, f"Template {template.name} has suspiciously short exit condition"
    
    def test_risk_reward_ratios_reasonable(self):
        """Test that risk/reward ratios are reasonable."""
        for template in self.library.get_all_templates():
            # Risk/reward should be between 1.0 and 5.0
            assert 1.0 <= template.risk_reward_ratio <= 5.0, \
                f"Template {template.name} has unreasonable risk/reward ratio: {template.risk_reward_ratio}"
    
    def test_template_diversity(self):
        """Test that templates provide good diversity."""
        templates = self.library.get_all_templates()
        
        # Should have multiple strategy types
        strategy_types = set(t.strategy_type for t in templates)
        assert len(strategy_types) >= 3, "Should have at least 3 different strategy types"
        
        # Should cover all market regimes
        all_regimes = set()
        for template in templates:
            all_regimes.update(template.market_regimes)
        
        assert MarketRegime.RANGING in all_regimes
        assert MarketRegime.TRENDING_UP in all_regimes
        assert MarketRegime.TRENDING_DOWN in all_regimes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
