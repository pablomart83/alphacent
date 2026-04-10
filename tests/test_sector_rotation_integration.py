"""Integration tests for Sector Rotation Strategy with Strategy Proposer."""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime
import pandas as pd

from src.strategy.strategy_templates import StrategyTemplateLibrary, MarketRegime
from src.strategy.sector_rotation import SectorRotationStrategy


def test_sector_rotation_template_exists():
    """Test that sector rotation template is in the library."""
    library = StrategyTemplateLibrary()
    template = library.get_template_by_name("Sector Rotation")
    
    assert template is not None
    assert template.name == "Sector Rotation"
    assert template.metadata is not None
    assert 'fixed_symbols' in template.metadata
    assert len(template.metadata['fixed_symbols']) == 8
    assert 'XLE' in template.metadata['fixed_symbols']
    assert 'XLK' in template.metadata['fixed_symbols']


def test_sector_rotation_template_has_correct_symbols():
    """Test that sector rotation template has all 8 sector ETFs."""
    library = StrategyTemplateLibrary()
    template = library.get_template_by_name("Sector Rotation")
    
    expected_symbols = ['XLE', 'XLF', 'XLK', 'XLU', 'XLV', 'XLI', 'XLP', 'XLY']
    actual_symbols = template.metadata['fixed_symbols']
    
    assert set(actual_symbols) == set(expected_symbols)


def test_sector_rotation_template_works_in_all_regimes():
    """Test that sector rotation template is available for all market regimes."""
    library = StrategyTemplateLibrary()
    template = library.get_template_by_name("Sector Rotation")
    
    # Should work in all regimes
    assert len(template.market_regimes) >= 9
    assert MarketRegime.TRENDING_UP in template.market_regimes
    assert MarketRegime.TRENDING_DOWN in template.market_regimes
    assert MarketRegime.RANGING in template.market_regimes


def test_sector_rotation_template_metadata():
    """Test that sector rotation template has correct metadata."""
    library = StrategyTemplateLibrary()
    template = library.get_template_by_name("Sector Rotation")
    
    assert template.metadata['requires_macro_data'] is True
    assert template.metadata['strategy_category'] == 'alpha_edge'
    assert template.metadata['uses_sector_etfs'] is True


def test_sector_rotation_strategy_uses_fixed_symbols():
    """Test that sector rotation strategy uses the fixed symbols from config."""
    config = {
        'alpha_edge': {
            'sector_rotation': {
                'enabled': True,
                'max_positions': 3,
                'rebalance_frequency_days': 30,
                'sectors': ['XLE', 'XLF', 'XLK', 'XLU', 'XLV', 'XLI', 'XLP', 'XLY']
            }
        }
    }
    
    mock_analyzer = Mock()
    mock_data_manager = Mock()
    
    strategy = SectorRotationStrategy(config, mock_analyzer, mock_data_manager)
    
    assert len(strategy.sectors) == 8
    assert 'XLE' in strategy.sectors
    assert 'XLK' in strategy.sectors


def test_sector_rotation_integration_with_template():
    """Test that sector rotation strategy can be created from template."""
    library = StrategyTemplateLibrary()
    template = library.get_template_by_name("Sector Rotation")
    
    # Verify template can be used to create strategy
    assert template.default_parameters['max_positions'] == 3
    assert template.default_parameters['rebalance_frequency_days'] == 30
    
    # Verify symbols are in metadata, not in default parameters
    assert 'fixed_symbols' in template.metadata
    assert 'sectors' not in template.default_parameters


def test_sector_rotation_template_parameters():
    """Test that sector rotation template has appropriate parameters."""
    library = StrategyTemplateLibrary()
    template = library.get_template_by_name("Sector Rotation")
    
    params = template.default_parameters
    
    assert params['max_positions'] == 3
    assert params['rebalance_frequency_days'] == 30
    assert params['momentum_lookback_days'] == 60
    assert params['stop_loss_pct'] == 0.08  # Wider stops for ETFs
    assert params['take_profit_pct'] == 0.15  # Higher targets


def test_sector_rotation_no_fundamental_filtering():
    """Test that sector ETFs should not be subject to fundamental filtering."""
    library = StrategyTemplateLibrary()
    template = library.get_template_by_name("Sector Rotation")
    
    # Sector rotation should NOT require fundamental data
    # (it uses macro data instead)
    metadata = template.metadata
    assert metadata.get('requires_fundamental_data') is None or metadata.get('requires_fundamental_data') is False
    assert metadata.get('requires_macro_data') is True


def test_sector_rotation_expected_frequency():
    """Test that sector rotation has appropriate trade frequency."""
    library = StrategyTemplateLibrary()
    template = library.get_template_by_name("Sector Rotation")
    
    # Should rebalance monthly
    assert '1-3' in template.expected_trade_frequency or 'month' in template.expected_trade_frequency
    assert '30-90' in template.expected_holding_period or 'days' in template.expected_holding_period
