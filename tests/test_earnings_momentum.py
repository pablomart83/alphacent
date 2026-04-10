"""Tests for Earnings Momentum Strategy."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock
from src.strategy.earnings_momentum import EarningsMomentumStrategy
from src.data.fundamental_data_provider import FundamentalData


@pytest.fixture
def mock_config():
    """Mock configuration."""
    return {
        'alpha_edge': {
            'earnings_momentum': {
                'enabled': True,
                'market_cap_min': 300000000,
                'market_cap_max': 2000000000,
                'earnings_surprise_min': 0.05,
                'revenue_growth_min': 0.10,
                'entry_delay_days': 2,
                'hold_period_days': 45,
                'profit_target': 0.10,
                'stop_loss': 0.05,
                'exit_before_earnings_days': 7
            }
        }
    }


@pytest.fixture
def mock_fundamental_provider():
    """Mock fundamental data provider."""
    provider = Mock()
    return provider


@pytest.fixture
def mock_market_data_manager():
    """Mock market data manager."""
    manager = Mock()
    return manager


@pytest.fixture
def earnings_strategy(mock_config, mock_fundamental_provider, mock_market_data_manager):
    """Create earnings momentum strategy instance."""
    return EarningsMomentumStrategy(
        mock_config,
        mock_fundamental_provider,
        mock_market_data_manager
    )


def test_initialization(earnings_strategy):
    """Test strategy initialization."""
    assert earnings_strategy.enabled is True
    assert earnings_strategy.market_cap_min == 300000000
    assert earnings_strategy.market_cap_max == 2000000000
    assert earnings_strategy.earnings_surprise_min == 0.05
    assert earnings_strategy.revenue_growth_min == 0.10


def test_check_entry_criteria_eligible(earnings_strategy, mock_fundamental_provider):
    """Test entry criteria check for eligible stock."""
    # Mock fundamental data
    fundamental_data = FundamentalData(
        symbol='TEST',
        timestamp=datetime.now(),
        market_cap=500000000,  # $500M - within range
        revenue_growth=0.15,  # 15% - above minimum
        source='test'
    )
    
    # Mock earnings data
    earnings_data = {
        'symbol': 'TEST',
        'last_earnings_date': (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d'),
        'surprise_pct': 0.08,  # 8% - above minimum
        'actual_eps': 1.08,
        'estimated_eps': 1.00
    }
    
    mock_fundamental_provider.get_fundamental_data.return_value = fundamental_data
    mock_fundamental_provider.get_earnings_calendar.return_value = earnings_data
    mock_fundamental_provider.get_days_since_earnings.return_value = 3
    
    result = earnings_strategy.check_entry_criteria('TEST')
    
    assert result['eligible'] is True
    assert 'All entry criteria met' in result['reasons']
    assert result['data']['market_cap'] == 500000000
    assert result['data']['earnings_surprise'] == 0.08
    assert result['data']['revenue_growth'] == 0.15


def test_check_entry_criteria_market_cap_too_low(earnings_strategy, mock_fundamental_provider):
    """Test entry criteria check with market cap too low."""
    fundamental_data = FundamentalData(
        symbol='TEST',
        timestamp=datetime.now(),
        market_cap=200000000,  # $200M - below minimum
        revenue_growth=0.15,
        source='test'
    )
    
    mock_fundamental_provider.get_fundamental_data.return_value = fundamental_data
    
    result = earnings_strategy.check_entry_criteria('TEST')
    
    assert result['eligible'] is False
    assert any('below minimum' in reason for reason in result['reasons'])


def test_check_entry_criteria_earnings_surprise_too_low(earnings_strategy, mock_fundamental_provider):
    """Test entry criteria check with earnings surprise too low."""
    fundamental_data = FundamentalData(
        symbol='TEST',
        timestamp=datetime.now(),
        market_cap=500000000,
        revenue_growth=0.15,
        source='test'
    )
    
    earnings_data = {
        'symbol': 'TEST',
        'last_earnings_date': (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d'),
        'surprise_pct': 0.02,  # 2% - below minimum
        'actual_eps': 1.02,
        'estimated_eps': 1.00
    }
    
    mock_fundamental_provider.get_fundamental_data.return_value = fundamental_data
    mock_fundamental_provider.get_earnings_calendar.return_value = earnings_data
    
    result = earnings_strategy.check_entry_criteria('TEST')
    
    assert result['eligible'] is False
    assert any('Earnings surprise' in reason and 'below minimum' in reason for reason in result['reasons'])


def test_check_entry_criteria_too_soon_after_earnings(earnings_strategy, mock_fundamental_provider):
    """Test entry criteria check when too soon after earnings."""
    fundamental_data = FundamentalData(
        symbol='TEST',
        timestamp=datetime.now(),
        market_cap=500000000,
        revenue_growth=0.15,
        source='test'
    )
    
    earnings_data = {
        'symbol': 'TEST',
        'last_earnings_date': (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
        'surprise_pct': 0.08,
        'actual_eps': 1.08,
        'estimated_eps': 1.00
    }
    
    mock_fundamental_provider.get_fundamental_data.return_value = fundamental_data
    mock_fundamental_provider.get_earnings_calendar.return_value = earnings_data
    mock_fundamental_provider.get_days_since_earnings.return_value = 1
    
    result = earnings_strategy.check_entry_criteria('TEST')
    
    assert result['eligible'] is False
    assert any('days since earnings' in reason for reason in result['reasons'])


def test_check_exit_criteria_profit_target(earnings_strategy):
    """Test exit criteria when profit target is reached."""
    entry_price = 100.0
    current_price = 111.0  # 11% gain - above 10% target
    entry_date = datetime.now() - timedelta(days=10)
    
    result = earnings_strategy.check_exit_criteria('TEST', entry_price, entry_date, current_price)
    
    assert result['should_exit'] is True
    assert result['exit_type'] == 'profit_target'
    assert 'Profit target reached' in result['reason']


def test_check_exit_criteria_stop_loss(earnings_strategy):
    """Test exit criteria when stop loss is triggered."""
    entry_price = 100.0
    current_price = 94.0  # 6% loss - below 5% stop
    entry_date = datetime.now() - timedelta(days=10)
    
    result = earnings_strategy.check_exit_criteria('TEST', entry_price, entry_date, current_price)
    
    assert result['should_exit'] is True
    assert result['exit_type'] == 'stop_loss'
    assert 'Stop loss triggered' in result['reason']


def test_check_exit_criteria_max_hold_period(earnings_strategy):
    """Test exit criteria when max hold period is reached."""
    entry_price = 100.0
    current_price = 105.0  # 5% gain - below target
    entry_date = datetime.now() - timedelta(days=50)  # 50 days - above 45 day limit
    
    result = earnings_strategy.check_exit_criteria('TEST', entry_price, entry_date, current_price)
    
    assert result['should_exit'] is True
    assert result['exit_type'] == 'max_hold_period'
    assert 'Maximum hold period reached' in result['reason']


def test_check_exit_criteria_earnings_approaching(earnings_strategy, mock_fundamental_provider):
    """Test exit criteria when next earnings is approaching."""
    entry_price = 100.0
    current_price = 105.0
    entry_date = datetime.now() - timedelta(days=10)
    
    # Mock 85 days since last earnings (next earnings in ~5 days)
    mock_fundamental_provider.get_days_since_earnings.return_value = 85
    
    result = earnings_strategy.check_exit_criteria('TEST', entry_price, entry_date, current_price)
    
    assert result['should_exit'] is True
    assert result['exit_type'] == 'earnings_approaching'
    assert 'Next earnings approaching' in result['reason']


def test_check_exit_criteria_no_exit(earnings_strategy, mock_fundamental_provider):
    """Test exit criteria when no exit condition is met."""
    entry_price = 100.0
    current_price = 105.0  # 5% gain - below target
    entry_date = datetime.now() - timedelta(days=10)
    
    # Mock 20 days since last earnings (next earnings far away)
    mock_fundamental_provider.get_days_since_earnings.return_value = 20
    
    result = earnings_strategy.check_exit_criteria('TEST', entry_price, entry_date, current_price)
    
    assert result['should_exit'] is False
    assert result['reason'] is None


def test_calculate_position_size(earnings_strategy):
    """Test position size calculation."""
    account_value = 100000.0
    current_price = 50.0
    
    shares = earnings_strategy.calculate_position_size('TEST', account_value, current_price)
    
    # Risk 1% of account = $1000
    # Stop loss is 5% of price = $2.50
    # Position size = $1000 / $2.50 = 400 shares
    # But max position is 5% of account = $5000 / $50 = 100 shares
    assert shares == 100  # Limited by max position size


def test_calculate_position_size_small_account(earnings_strategy):
    """Test position size calculation with small account."""
    account_value = 10000.0
    current_price = 50.0
    
    shares = earnings_strategy.calculate_position_size('TEST', account_value, current_price)
    
    # Risk 1% of account = $100
    # Stop loss is 5% of price = $2.50
    # Position size = $100 / $2.50 = 40 shares
    # Max position is 5% of account = $500 / $50 = 10 shares
    assert shares == 10  # Limited by max position size


def test_get_strategy_metadata(earnings_strategy):
    """Test strategy metadata retrieval."""
    metadata = earnings_strategy.get_strategy_metadata()
    
    assert metadata['strategy_type'] == 'earnings_momentum'
    assert 'market_cap_range' in metadata
    assert 'earnings_surprise_min' in metadata
    assert 'revenue_growth_min' in metadata
    assert metadata['profit_target'] == '10.0%'
    assert metadata['stop_loss'] == '5.0%'


def test_disabled_strategy(mock_config, mock_fundamental_provider, mock_market_data_manager):
    """Test that disabled strategy returns not eligible."""
    mock_config['alpha_edge']['earnings_momentum']['enabled'] = False
    
    strategy = EarningsMomentumStrategy(
        mock_config,
        mock_fundamental_provider,
        mock_market_data_manager
    )
    
    result = strategy.check_entry_criteria('TEST')
    
    assert result['eligible'] is False
    assert 'Strategy is disabled' in result['reasons']



def test_track_post_earnings_drift(earnings_strategy):
    """Test tracking post-earnings drift performance."""
    earnings_date = datetime.now() - timedelta(days=10)
    entry_date = datetime.now() - timedelta(days=7)
    entry_price = 100.0
    current_price = 108.0
    
    result = earnings_strategy.track_post_earnings_drift(
        'TEST', entry_date, entry_price, current_price, earnings_date
    )
    
    assert result['symbol'] == 'TEST'
    assert result['days_since_earnings'] == 10
    assert result['days_held'] == 7
    assert abs(result['return_pct'] - 0.08) < 0.001  # 8% return
    assert result['drift_phase'] == 'short_term'  # 10 days is short-term phase


def test_track_post_earnings_drift_phases(earnings_strategy):
    """Test different drift phases."""
    entry_price = 100.0
    current_price = 105.0
    
    # Immediate phase (0-5 days)
    earnings_date = datetime.now() - timedelta(days=3)
    entry_date = datetime.now() - timedelta(days=1)
    result = earnings_strategy.track_post_earnings_drift(
        'TEST', entry_date, entry_price, current_price, earnings_date
    )
    assert result['drift_phase'] == 'immediate'
    
    # Short-term phase (6-30 days)
    earnings_date = datetime.now() - timedelta(days=20)
    entry_date = datetime.now() - timedelta(days=17)
    result = earnings_strategy.track_post_earnings_drift(
        'TEST', entry_date, entry_price, current_price, earnings_date
    )
    assert result['drift_phase'] == 'short_term'
    
    # Medium-term phase (31-60 days)
    earnings_date = datetime.now() - timedelta(days=45)
    entry_date = datetime.now() - timedelta(days=42)
    result = earnings_strategy.track_post_earnings_drift(
        'TEST', entry_date, entry_price, current_price, earnings_date
    )
    assert result['drift_phase'] == 'medium_term'
    
    # Long-term phase (>60 days)
    earnings_date = datetime.now() - timedelta(days=75)
    entry_date = datetime.now() - timedelta(days=72)
    result = earnings_strategy.track_post_earnings_drift(
        'TEST', entry_date, entry_price, current_price, earnings_date
    )
    assert result['drift_phase'] == 'long_term'


def test_with_historical_earnings_data(earnings_strategy, mock_fundamental_provider):
    """Test strategy with historical earnings data scenario."""
    # Simulate a historical earnings scenario from 6 months ago
    historical_earnings_date = datetime.now() - timedelta(days=180)
    
    # Mock fundamental data for a small-cap stock
    fundamental_data = FundamentalData(
        symbol='SMCAP',
        timestamp=datetime.now(),
        market_cap=800000000,  # $800M - mid-range
        revenue_growth=0.18,  # 18% growth - strong
        source='test'
    )
    
    # Mock historical earnings with strong beat
    earnings_data = {
        'symbol': 'SMCAP',
        'last_earnings_date': historical_earnings_date.strftime('%Y-%m-%d'),
        'surprise_pct': 0.12,  # 12% beat - strong
        'actual_eps': 1.12,
        'estimated_eps': 1.00
    }
    
    mock_fundamental_provider.get_fundamental_data.return_value = fundamental_data
    mock_fundamental_provider.get_earnings_calendar.return_value = earnings_data
    mock_fundamental_provider.get_days_since_earnings.return_value = 180
    
    # Check entry criteria - should fail because too long since earnings
    result = earnings_strategy.check_entry_criteria('SMCAP')
    
    assert result['eligible'] is False
    assert any('too late to enter' in reason for reason in result['reasons'])
    
    # Now test with recent earnings (3 days ago)
    recent_earnings_date = datetime.now() - timedelta(days=3)
    earnings_data['last_earnings_date'] = recent_earnings_date.strftime('%Y-%m-%d')
    mock_fundamental_provider.get_days_since_earnings.return_value = 3
    
    result = earnings_strategy.check_entry_criteria('SMCAP')
    
    assert result['eligible'] is True
    assert result['data']['market_cap'] == 800000000
    assert result['data']['earnings_surprise'] == 0.12
    assert result['data']['revenue_growth'] == 0.18


def test_institutional_ownership_optional(earnings_strategy, mock_fundamental_provider):
    """Test that institutional ownership check is optional."""
    # Enable institutional ownership check
    earnings_strategy.config['check_institutional_ownership'] = True
    
    fundamental_data = FundamentalData(
        symbol='TEST',
        timestamp=datetime.now(),
        market_cap=500000000,
        revenue_growth=0.15,
        source='test'
    )
    
    earnings_data = {
        'symbol': 'TEST',
        'last_earnings_date': (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d'),
        'surprise_pct': 0.08,
        'actual_eps': 1.08,
        'estimated_eps': 1.00
    }
    
    mock_fundamental_provider.get_fundamental_data.return_value = fundamental_data
    mock_fundamental_provider.get_earnings_calendar.return_value = earnings_data
    mock_fundamental_provider.get_days_since_earnings.return_value = 3
    
    # Should still pass even though institutional ownership is not implemented
    result = earnings_strategy.check_entry_criteria('TEST')
    
    assert result['eligible'] is True
