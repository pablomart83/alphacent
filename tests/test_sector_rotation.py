"""Tests for Sector Rotation Strategy."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock
import pandas as pd
from src.strategy.sector_rotation import SectorRotationStrategy


@pytest.fixture
def mock_config():
    """Create mock configuration."""
    return {
        'alpha_edge': {
            'sector_rotation': {
                'enabled': True,
                'max_positions': 3,
                'rebalance_frequency_days': 30,
                'sectors': ['XLE', 'XLF', 'XLK', 'XLU', 'XLV', 'XLI', 'XLP', 'XLY']
            }
        }
    }


@pytest.fixture
def mock_market_analyzer():
    """Create mock market analyzer."""
    analyzer = Mock()
    analyzer.get_market_context = Mock(return_value={
        'inflation_rate': 3.0,
        'fed_stance': 'neutral',
        'unemployment_trend': 'stable',
        'macro_regime': 'transitional',
        'vix': 20.0
    })
    return analyzer


@pytest.fixture
def mock_market_data_manager():
    """Create mock market data manager."""
    manager = Mock()
    
    def get_historical_data(symbol, period_days):
        # Create sample price data with correct length
        dates = pd.date_range(end=datetime.now(), periods=250, freq='D')
        
        # Generate different momentum patterns for different sectors
        if symbol == 'XLK':  # Tech - strong momentum
            prices = [100 + i for i in range(len(dates))]
        elif symbol == 'XLE':  # Energy - moderate momentum
            prices = [100 + i * 0.5 for i in range(len(dates))]
        elif symbol == 'XLU':  # Utilities - weak momentum
            prices = [100] * len(dates)
        else:  # Other sectors - neutral
            prices = [100 + i * 0.3 for i in range(len(dates))]
        
        df = pd.DataFrame({
            'close': prices,
            'open': prices,
            'high': [p * 1.01 for p in prices],
            'low': [p * 0.99 for p in prices],
            'volume': [1000000] * len(dates)
        }, index=dates)
        
        return df
    
    manager.get_historical_data = Mock(side_effect=get_historical_data)
    return manager


@pytest.fixture
def sector_strategy(mock_config, mock_market_analyzer, mock_market_data_manager):
    """Create sector rotation strategy instance."""
    return SectorRotationStrategy(
        mock_config,
        mock_market_analyzer,
        mock_market_data_manager
    )


def test_initialization(sector_strategy):
    """Test strategy initialization."""
    assert sector_strategy.enabled is True
    assert sector_strategy.max_positions == 3
    assert sector_strategy.rebalance_frequency_days == 30
    assert len(sector_strategy.sectors) == 8
    assert 'XLE' in sector_strategy.sectors
    assert sector_strategy.last_rebalance_date is None


def test_regime_to_sector_mapping(sector_strategy):
    """Test regime-to-sector mapping returns correct sectors."""
    mapping = sector_strategy.get_regime_to_sector_mapping()
    
    # High inflation + rising rates -> Energy
    assert 'XLE' in mapping['high_inflation_rising_rates']
    
    # Low inflation + falling rates -> Tech
    assert 'XLK' in mapping['low_inflation_falling_rates']
    
    # Recession fears -> Defensive sectors
    assert 'XLU' in mapping['recession_fears']
    assert 'XLP' in mapping['recession_fears']
    assert 'XLV' in mapping['recession_fears']
    
    # Economic expansion -> Cyclical sectors
    assert 'XLF' in mapping['economic_expansion']
    assert 'XLI' in mapping['economic_expansion']
    assert 'XLY' in mapping['economic_expansion']
    
    # Neutral -> Defensive
    assert 'XLV' in mapping['neutral']
    assert 'XLP' in mapping['neutral']


def test_detect_regime_high_inflation_rising_rates(sector_strategy, mock_market_analyzer):
    """Test regime detection for high inflation + rising rates."""
    mock_market_analyzer.get_market_context.return_value = {
        'inflation_rate': 5.0,
        'fed_stance': 'tightening',
        'unemployment_trend': 'stable',
        'macro_regime': 'transitional',
        'vix': 20.0
    }
    
    regime = sector_strategy.detect_current_regime()
    assert regime == 'high_inflation_rising_rates'


def test_detect_regime_low_inflation_falling_rates(sector_strategy, mock_market_analyzer):
    """Test regime detection for low inflation + falling rates."""
    mock_market_analyzer.get_market_context.return_value = {
        'inflation_rate': 2.0,
        'fed_stance': 'accommodative',
        'unemployment_trend': 'stable',
        'macro_regime': 'transitional',
        'vix': 15.0
    }
    
    regime = sector_strategy.detect_current_regime()
    assert regime == 'low_inflation_falling_rates'


def test_detect_regime_recession_fears(sector_strategy, mock_market_analyzer):
    """Test regime detection for recession fears."""
    mock_market_analyzer.get_market_context.return_value = {
        'inflation_rate': 3.0,
        'fed_stance': 'neutral',
        'unemployment_trend': 'rising',
        'macro_regime': 'risk_off',
        'vix': 30.0
    }
    
    regime = sector_strategy.detect_current_regime()
    assert regime == 'recession_fears'


def test_detect_regime_economic_expansion(sector_strategy, mock_market_analyzer):
    """Test regime detection for economic expansion."""
    mock_market_analyzer.get_market_context.return_value = {
        'inflation_rate': 2.5,
        'fed_stance': 'neutral',
        'unemployment_trend': 'falling',
        'macro_regime': 'risk_on',
        'vix': 15.0
    }
    
    regime = sector_strategy.detect_current_regime()
    assert regime == 'economic_expansion'


def test_detect_regime_neutral(sector_strategy, mock_market_analyzer):
    """Test regime detection defaults to neutral."""
    mock_market_analyzer.get_market_context.return_value = {
        'inflation_rate': 3.0,
        'fed_stance': 'neutral',
        'unemployment_trend': 'stable',
        'macro_regime': 'transitional',
        'vix': 20.0
    }
    
    regime = sector_strategy.detect_current_regime()
    assert regime == 'neutral'


def test_calculate_sector_momentum(sector_strategy):
    """Test sector momentum calculation."""
    momentum_scores = sector_strategy.calculate_sector_momentum(lookback_days=60)
    
    # Should have scores for all sectors
    assert len(momentum_scores) == 8
    
    # XLK (Tech) should have highest momentum based on mock data
    assert momentum_scores['XLK'] > momentum_scores['XLU']
    
    # XLE should have moderate momentum
    assert momentum_scores['XLE'] > momentum_scores['XLU']
    
    # All scores should be numeric
    for score in momentum_scores.values():
        assert isinstance(score, (int, float))


def test_should_rebalance_first_time(sector_strategy):
    """Test rebalancing is needed on first run."""
    assert sector_strategy.should_rebalance() is True


def test_should_rebalance_too_soon(sector_strategy):
    """Test rebalancing not needed if done recently."""
    sector_strategy.last_rebalance_date = datetime.now() - timedelta(days=15)
    assert sector_strategy.should_rebalance() is False


def test_should_rebalance_time_elapsed(sector_strategy):
    """Test rebalancing needed after frequency period."""
    sector_strategy.last_rebalance_date = datetime.now() - timedelta(days=35)
    assert sector_strategy.should_rebalance() is True


def test_should_rebalance_disabled(sector_strategy):
    """Test rebalancing returns False when strategy disabled."""
    sector_strategy.enabled = False
    assert sector_strategy.should_rebalance() is False


def test_get_recommended_sectors(sector_strategy, mock_market_analyzer):
    """Test getting recommended sectors."""
    # Set regime to neutral
    mock_market_analyzer.get_market_context.return_value = {
        'inflation_rate': 3.0,
        'fed_stance': 'neutral',
        'unemployment_trend': 'stable',
        'macro_regime': 'transitional',
        'vix': 20.0
    }
    
    recommendations = sector_strategy.get_recommended_sectors()
    
    # Should return recommendations
    assert len(recommendations) > 0
    assert len(recommendations) <= sector_strategy.max_positions
    
    # Each recommendation should have required fields
    for rec in recommendations:
        assert 'symbol' in rec
        assert 'sector_name' in rec
        assert 'momentum_score' in rec
        assert 'regime' in rec
        assert 'reason' in rec
        assert rec['regime'] == 'neutral'


def test_get_recommended_sectors_max_positions(sector_strategy):
    """Test that recommendations respect max_positions limit."""
    recommendations = sector_strategy.get_recommended_sectors()
    assert len(recommendations) <= sector_strategy.max_positions


def test_get_recommended_sectors_sorted_by_momentum(sector_strategy):
    """Test that recommendations are sorted by momentum."""
    recommendations = sector_strategy.get_recommended_sectors()
    
    if len(recommendations) > 1:
        # Check that momentum scores are in descending order
        for i in range(len(recommendations) - 1):
            assert recommendations[i]['momentum_score'] >= recommendations[i + 1]['momentum_score']


def test_generate_rebalancing_signals_add_sectors(sector_strategy):
    """Test rebalancing signals to add new sectors."""
    current_positions = []
    
    signals = sector_strategy.generate_rebalancing_signals(current_positions)
    
    assert 'add' in signals
    assert 'remove' in signals
    assert len(signals['add']) > 0
    assert len(signals['remove']) == 0
    assert sector_strategy.last_rebalance_date is not None


def test_generate_rebalancing_signals_remove_sectors(sector_strategy):
    """Test rebalancing signals to remove sectors."""
    # Set current positions to sectors not in recommendations
    current_positions = ['XLE', 'XLF', 'XLI']
    
    # Force rebalance
    sector_strategy.last_rebalance_date = None
    
    signals = sector_strategy.generate_rebalancing_signals(current_positions)
    
    assert 'add' in signals
    assert 'remove' in signals
    # Some sectors should be removed or added based on regime
    assert len(signals['add']) + len(signals['remove']) > 0


def test_generate_rebalancing_signals_no_rebalance_needed(sector_strategy):
    """Test no rebalancing when not due."""
    sector_strategy.last_rebalance_date = datetime.now()
    current_positions = ['XLV', 'XLP']
    
    signals = sector_strategy.generate_rebalancing_signals(current_positions)
    
    assert signals['add'] == []
    assert signals['remove'] == []


def test_generate_rebalancing_signals_position_limits(sector_strategy):
    """Test that rebalancing respects max position limits."""
    current_positions = []
    
    signals = sector_strategy.generate_rebalancing_signals(current_positions)
    
    # Total positions after rebalancing should not exceed max
    total_after = len(current_positions) + len(signals['add']) - len(signals['remove'])
    assert total_after <= sector_strategy.max_positions


def test_get_strategy_metadata(sector_strategy):
    """Test strategy metadata."""
    metadata = sector_strategy.get_strategy_metadata()
    
    assert metadata['strategy_type'] == 'sector_rotation'
    assert metadata['max_positions'] == 3
    assert metadata['rebalance_frequency_days'] == 30
    assert len(metadata['sectors']) == 8
    assert metadata['enabled'] is True


def test_disabled_strategy(mock_config, mock_market_analyzer, mock_market_data_manager):
    """Test that disabled strategy returns empty recommendations."""
    mock_config['alpha_edge']['sector_rotation']['enabled'] = False
    
    strategy = SectorRotationStrategy(
        mock_config,
        mock_market_analyzer,
        mock_market_data_manager
    )
    
    recommendations = strategy.get_recommended_sectors()
    assert recommendations == []


def test_regime_detection_with_error(sector_strategy, mock_market_analyzer):
    """Test regime detection handles errors gracefully."""
    mock_market_analyzer.get_market_context.side_effect = Exception("API Error")
    
    regime = sector_strategy.detect_current_regime()
    assert regime == 'neutral'  # Should default to neutral on error


def test_momentum_calculation_with_insufficient_data(sector_strategy, mock_market_data_manager):
    """Test momentum calculation handles insufficient data."""
    # Return None for a sector
    original_get_data = mock_market_data_manager.get_historical_data
    
    def get_data_with_none(symbol, period_days):
        if symbol == 'XLE':
            return None
        return original_get_data(symbol, period_days)
    
    mock_market_data_manager.get_historical_data = Mock(side_effect=get_data_with_none)
    
    momentum_scores = sector_strategy.calculate_sector_momentum()
    
    # XLE should have 0 momentum due to missing data
    assert momentum_scores['XLE'] == 0.0
    
    # Other sectors should still have scores
    assert momentum_scores['XLK'] != 0.0


def test_historical_regime_changes(sector_strategy, mock_market_analyzer):
    """Test strategy adapts to regime changes over time."""
    # Start with expansion regime
    mock_market_analyzer.get_market_context.return_value = {
        'inflation_rate': 2.5,
        'fed_stance': 'neutral',
        'unemployment_trend': 'falling',
        'macro_regime': 'risk_on',
        'vix': 15.0
    }
    
    regime1 = sector_strategy.detect_current_regime()
    recs1 = sector_strategy.get_recommended_sectors()
    
    # Change to recession regime
    mock_market_analyzer.get_market_context.return_value = {
        'inflation_rate': 3.0,
        'fed_stance': 'neutral',
        'unemployment_trend': 'rising',
        'macro_regime': 'risk_off',
        'vix': 30.0
    }
    
    regime2 = sector_strategy.detect_current_regime()
    recs2 = sector_strategy.get_recommended_sectors()
    
    # Regimes should be different
    assert regime1 != regime2
    
    # Recommendations should change
    symbols1 = {rec['symbol'] for rec in recs1}
    symbols2 = {rec['symbol'] for rec in recs2}
    assert symbols1 != symbols2
