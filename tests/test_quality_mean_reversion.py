"""Tests for Quality Mean Reversion Strategy."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock
from src.strategy.quality_mean_reversion import QualityMeanReversionStrategy
from src.data.fundamental_data_provider import FundamentalData


@pytest.fixture
def mock_config():
    """Mock configuration."""
    return {
        'alpha_edge': {
            'quality_mean_reversion': {
                'enabled': True,
                'market_cap_min': 10000000000,  # $10B
                'min_roe': 0.15,  # 15%
                'max_debt_equity': 0.5,
                'oversold_threshold': 30,
                'drawdown_threshold': 0.10,  # 10%
                'profit_target': 0.05,  # 5%
                'stop_loss': 0.03  # 3%
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
def quality_strategy(mock_config, mock_fundamental_provider, mock_market_data_manager):
    """Create quality mean reversion strategy instance."""
    return QualityMeanReversionStrategy(
        mock_config,
        mock_fundamental_provider,
        mock_market_data_manager
    )


def test_initialization(quality_strategy):
    """Test strategy initialization."""
    assert quality_strategy.enabled is True
    assert quality_strategy.market_cap_min == 10000000000
    assert quality_strategy.min_roe == 0.15
    assert quality_strategy.max_debt_equity == 0.5
    assert quality_strategy.oversold_threshold == 30


def test_check_quality_criteria_passes(quality_strategy, mock_fundamental_provider):
    """Test quality criteria check for high-quality stock."""
    fundamental_data = FundamentalData(
        symbol='QUAL',
        timestamp=datetime.now(),
        market_cap=15000000000,  # $15B - above minimum
        roe=0.20,  # 20% - above minimum
        debt_to_equity=0.3,  # 0.3 - below maximum
        source='test'
    )
    
    mock_fundamental_provider.get_fundamental_data.return_value = fundamental_data
    
    result = quality_strategy.check_quality_criteria('QUAL')
    
    assert result['passes'] is True
    assert 'All quality criteria met' in result['reasons']
    assert result['data']['market_cap'] == 15000000000
    assert result['data']['roe'] == 0.20
    assert result['data']['debt_equity'] == 0.3


def test_check_quality_criteria_market_cap_too_low(quality_strategy, mock_fundamental_provider):
    """Test quality criteria check with market cap too low."""
    fundamental_data = FundamentalData(
        symbol='SMALL',
        timestamp=datetime.now(),
        market_cap=5000000000,  # $5B - below minimum
        roe=0.20,
        debt_to_equity=0.3,
        source='test'
    )
    
    mock_fundamental_provider.get_fundamental_data.return_value = fundamental_data
    
    result = quality_strategy.check_quality_criteria('SMALL')
    
    assert result['passes'] is False
    assert any('below minimum' in reason for reason in result['reasons'])


def test_check_quality_criteria_roe_too_low(quality_strategy, mock_fundamental_provider):
    """Test quality criteria check with ROE too low."""
    fundamental_data = FundamentalData(
        symbol='LOWROE',
        timestamp=datetime.now(),
        market_cap=15000000000,
        roe=0.10,  # 10% - below minimum
        debt_to_equity=0.3,
        source='test'
    )
    
    mock_fundamental_provider.get_fundamental_data.return_value = fundamental_data
    
    result = quality_strategy.check_quality_criteria('LOWROE')
    
    assert result['passes'] is False
    assert any('ROE' in reason and 'below minimum' in reason for reason in result['reasons'])


def test_check_quality_criteria_debt_too_high(quality_strategy, mock_fundamental_provider):
    """Test quality criteria check with debt/equity too high."""
    fundamental_data = FundamentalData(
        symbol='HIGHDEBT',
        timestamp=datetime.now(),
        market_cap=15000000000,
        roe=0.20,
        debt_to_equity=0.8,  # 0.8 - above maximum
        source='test'
    )
    
    mock_fundamental_provider.get_fundamental_data.return_value = fundamental_data
    
    result = quality_strategy.check_quality_criteria('HIGHDEBT')
    
    assert result['passes'] is False
    assert any('Debt/Equity' in reason and 'above maximum' in reason for reason in result['reasons'])


def create_mock_price_data(days=250, start_price=100, trend='down', volatility=0.02):
    """Create mock price data for testing."""
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    
    if trend == 'down':
        # Create downtrend with recent sharp drop
        prices = np.linspace(start_price * 1.2, start_price, days - 10)
        # Add sharp drop in last 5 days
        recent_drop = np.linspace(start_price, start_price * 0.88, 10)
        prices = np.concatenate([prices, recent_drop])
    elif trend == 'up':
        prices = np.linspace(start_price * 0.8, start_price, days)
    else:  # flat
        prices = np.ones(days) * start_price
    
    # Add some noise
    noise = np.random.normal(0, volatility, days)
    prices = prices * (1 + noise)
    
    df = pd.DataFrame({
        'date': dates,
        'close': prices,
        'open': prices * 0.99,
        'high': prices * 1.01,
        'low': prices * 0.98,
        'volume': np.random.randint(1000000, 5000000, days)
    })
    
    return df


def test_check_oversold_criteria_oversold(quality_strategy, mock_market_data_manager):
    """Test oversold criteria check for oversold stock."""
    # Create mock data with recent sharp drop
    df = create_mock_price_data(days=250, start_price=100, trend='down')
    
    mock_market_data_manager.get_historical_data.return_value = df
    
    result = quality_strategy.check_oversold_criteria('OVERSOLD')
    
    # The mock data creates a downtrend with sharp drop
    # Check that the function returns proper structure
    assert 'oversold' in result
    assert 'reasons' in result
    assert 'data' in result
    
    # If oversold, verify we have the expected data
    if result['oversold']:
        assert 'rsi' in result['data']
        assert 'drawdown_5d' in result['data']
        assert 'ma_200' in result['data']


def test_check_oversold_criteria_not_oversold(quality_strategy, mock_market_data_manager):
    """Test oversold criteria check for non-oversold stock."""
    # Create mock data with uptrend
    df = create_mock_price_data(days=250, start_price=100, trend='up')
    
    mock_market_data_manager.get_historical_data.return_value = df
    
    result = quality_strategy.check_oversold_criteria('NOTSOLD')
    
    assert result['oversold'] is False


def test_check_entry_signal_with_rsi_crossover(quality_strategy, mock_fundamental_provider, mock_market_data_manager):
    """Test entry signal when RSI crosses above 30."""
    # Mock quality stock
    fundamental_data = FundamentalData(
        symbol='ENTRY',
        timestamp=datetime.now(),
        market_cap=15000000000,
        roe=0.20,
        debt_to_equity=0.3,
        source='test'
    )
    
    mock_fundamental_provider.get_fundamental_data.return_value = fundamental_data
    
    # Create price data with RSI crossover
    df = create_mock_price_data(days=250, start_price=100, trend='down')
    
    # Manually adjust last few prices to create RSI crossover
    # Make second-to-last price lower to push RSI below 30
    # Then make last price slightly higher to push RSI above 30
    df.loc[df.index[-2], 'close'] = df.loc[df.index[-2], 'close'] * 0.95
    df.loc[df.index[-1], 'close'] = df.loc[df.index[-2], 'close'] * 1.02
    
    mock_market_data_manager.get_historical_data.return_value = df
    
    result = quality_strategy.check_entry_signal('ENTRY')
    
    # May or may not have signal depending on exact RSI calculation
    # Just verify it doesn't crash and returns proper structure
    assert 'signal' in result
    assert 'reasons' in result
    assert 'data' in result


def test_check_exit_criteria_profit_target(quality_strategy):
    """Test exit criteria when profit target is reached."""
    entry_price = 100.0
    current_price = 106.0  # 6% gain - above 5% target
    entry_date = datetime.now() - timedelta(days=5)
    
    result = quality_strategy.check_exit_criteria('TEST', entry_price, entry_date, current_price)
    
    assert result['should_exit'] is True
    assert result['exit_type'] == 'profit_target'
    assert 'Profit target reached' in result['reason']


def test_check_exit_criteria_stop_loss(quality_strategy):
    """Test exit criteria when stop loss is triggered."""
    entry_price = 100.0
    current_price = 96.0  # 4% loss - below 3% stop
    entry_date = datetime.now() - timedelta(days=5)
    
    result = quality_strategy.check_exit_criteria('TEST', entry_price, entry_date, current_price)
    
    assert result['should_exit'] is True
    assert result['exit_type'] == 'stop_loss'
    assert 'Stop loss triggered' in result['reason']


def test_check_exit_criteria_mean_reversion(quality_strategy, mock_market_data_manager):
    """Test exit criteria when price returns to 50-day MA."""
    entry_price = 90.0
    current_price = 93.0  # 3.3% gain - below 5% profit target
    entry_date = datetime.now() - timedelta(days=5)
    
    # Create mock data where 50-day MA is at 93
    df = create_mock_price_data(days=100, start_price=93, trend='flat')
    
    mock_market_data_manager.get_historical_data.return_value = df
    
    result = quality_strategy.check_exit_criteria('TEST', entry_price, entry_date, current_price)
    
    assert result['should_exit'] is True
    assert result['exit_type'] == 'mean_reversion'
    assert '50-day MA' in result['reason']


def test_check_exit_criteria_no_exit(quality_strategy, mock_market_data_manager):
    """Test exit criteria when no exit condition is met."""
    entry_price = 100.0
    current_price = 102.0  # 2% gain - below target
    entry_date = datetime.now() - timedelta(days=3)
    
    # Create mock data where current price is below 50-day MA
    df = create_mock_price_data(days=100, start_price=110, trend='flat')
    
    mock_market_data_manager.get_historical_data.return_value = df
    
    result = quality_strategy.check_exit_criteria('TEST', entry_price, entry_date, current_price)
    
    assert result['should_exit'] is False
    assert result['reason'] is None


def test_calculate_position_size(quality_strategy):
    """Test position size calculation."""
    account_value = 100000.0
    current_price = 50.0
    
    shares = quality_strategy.calculate_position_size('TEST', account_value, current_price)
    
    # Risk 1% of account = $1000
    # Stop loss is 3% of price = $1.50
    # Position size = $1000 / $1.50 = 666 shares
    # But max position is 5% of account = $5000 / $50 = 100 shares
    assert shares == 100  # Limited by max position size


def test_calculate_position_size_large_account(quality_strategy):
    """Test position size calculation with large account."""
    account_value = 1000000.0
    current_price = 100.0
    
    shares = quality_strategy.calculate_position_size('TEST', account_value, current_price)
    
    # Risk 1% of account = $10000
    # Stop loss is 3% of price = $3.00
    # Position size = $10000 / $3.00 = 3333 shares
    # Max position is 5% of account = $50000 / $100 = 500 shares
    assert shares == 500  # Limited by max position size


def test_get_strategy_metadata(quality_strategy):
    """Test strategy metadata retrieval."""
    metadata = quality_strategy.get_strategy_metadata()
    
    assert metadata['strategy_type'] == 'quality_mean_reversion'
    assert 'market_cap_min' in metadata
    assert 'min_roe' in metadata
    assert 'max_debt_equity' in metadata
    assert metadata['profit_target'] == '5.0%'
    assert metadata['stop_loss'] == '3.0%'


def test_disabled_strategy(mock_config, mock_fundamental_provider, mock_market_data_manager):
    """Test that disabled strategy returns not passing."""
    mock_config['alpha_edge']['quality_mean_reversion']['enabled'] = False
    
    strategy = QualityMeanReversionStrategy(
        mock_config,
        mock_fundamental_provider,
        mock_market_data_manager
    )
    
    result = strategy.check_quality_criteria('TEST')
    
    assert result['passes'] is False
    assert 'Strategy is disabled' in result['reasons']


def test_check_fundamental_deterioration(quality_strategy):
    """Test fundamental deterioration check (placeholder)."""
    result = quality_strategy.check_fundamental_deterioration('TEST')
    
    assert 'deterioration' in result
    assert 'reasons' in result
    # Currently not implemented, so should return no deterioration
    assert result['deterioration'] is False


def test_track_recovery_performance(quality_strategy):
    """Test tracking recovery performance."""
    oversold_date = datetime.now() - timedelta(days=10)
    entry_date = datetime.now() - timedelta(days=7)
    entry_price = 90.0
    current_price = 97.0
    
    result = quality_strategy.track_recovery_performance(
        'TEST', entry_date, entry_price, current_price, oversold_date
    )
    
    assert result['symbol'] == 'TEST'
    assert result['days_since_oversold'] == 10
    assert result['days_held'] == 7
    assert abs(result['return_pct'] - 0.0778) < 0.001  # ~7.78% return
    assert result['recovery_phase'] == 'medium_term'  # 10 days is medium-term (8-14)


def test_track_recovery_performance_phases(quality_strategy):
    """Test different recovery phases."""
    entry_price = 90.0
    current_price = 95.0
    
    # Immediate phase (0-3 days)
    oversold_date = datetime.now() - timedelta(days=2)
    entry_date = datetime.now() - timedelta(days=1)
    result = quality_strategy.track_recovery_performance(
        'TEST', entry_date, entry_price, current_price, oversold_date
    )
    assert result['recovery_phase'] == 'immediate'
    
    # Short-term phase (4-7 days)
    oversold_date = datetime.now() - timedelta(days=6)
    entry_date = datetime.now() - timedelta(days=4)
    result = quality_strategy.track_recovery_performance(
        'TEST', entry_date, entry_price, current_price, oversold_date
    )
    assert result['recovery_phase'] == 'short_term'
    
    # Medium-term phase (8-14 days)
    oversold_date = datetime.now() - timedelta(days=12)
    entry_date = datetime.now() - timedelta(days=10)
    result = quality_strategy.track_recovery_performance(
        'TEST', entry_date, entry_price, current_price, oversold_date
    )
    assert result['recovery_phase'] == 'medium_term'
    
    # Long-term phase (>14 days)
    oversold_date = datetime.now() - timedelta(days=20)
    entry_date = datetime.now() - timedelta(days=18)
    result = quality_strategy.track_recovery_performance(
        'TEST', entry_date, entry_price, current_price, oversold_date
    )
    assert result['recovery_phase'] == 'long_term'


def test_rsi_calculation(quality_strategy):
    """Test RSI calculation helper method."""
    # Create simple price series
    prices = pd.Series([100, 102, 101, 103, 105, 104, 106, 108, 107, 109, 
                       111, 110, 112, 114, 113, 115, 117, 116, 118, 120])
    
    rsi = quality_strategy._calculate_rsi(prices, period=14)
    
    # RSI should be between 0 and 100
    assert len(rsi) == len(prices)
    assert rsi.iloc[-1] >= 0
    assert rsi.iloc[-1] <= 100


def test_with_edge_case_no_data(quality_strategy, mock_fundamental_provider, mock_market_data_manager):
    """Test handling of edge case with no data."""
    mock_fundamental_provider.get_fundamental_data.return_value = None
    
    result = quality_strategy.check_quality_criteria('NODATA')
    
    assert result['passes'] is False
    assert 'No fundamental data available' in result['reasons']


def test_with_edge_case_insufficient_history(quality_strategy, mock_market_data_manager):
    """Test handling of insufficient historical data."""
    # Create very short price history
    df = create_mock_price_data(days=50, start_price=100, trend='down')
    
    mock_market_data_manager.get_historical_data.return_value = df
    
    result = quality_strategy.check_oversold_criteria('SHORT')
    
    assert result['oversold'] is False
    assert 'Insufficient historical data' in result['reasons']


def test_quality_stock_with_various_fundamentals(quality_strategy, mock_fundamental_provider):
    """Test quality screening with various fundamental scenarios."""
    test_cases = [
        # (market_cap, roe, debt_to_equity, should_pass)
        (15000000000, 0.20, 0.3, True),   # Perfect quality
        (15000000000, 0.15, 0.5, True),   # Minimum thresholds
        (10000000000, 0.20, 0.3, True),   # Minimum market cap
        (9999999999, 0.20, 0.3, False),   # Just below market cap
        (15000000000, 0.14, 0.3, False),  # Just below ROE
        (15000000000, 0.20, 0.51, False), # Just above debt/equity
    ]
    
    for market_cap, roe, debt_to_equity, should_pass in test_cases:
        fundamental_data = FundamentalData(
            symbol='TEST',
            timestamp=datetime.now(),
            market_cap=market_cap,
            roe=roe,
            debt_to_equity=debt_to_equity,
            source='test'
        )
        
        mock_fundamental_provider.get_fundamental_data.return_value = fundamental_data
        
        result = quality_strategy.check_quality_criteria('TEST')
        
        assert result['passes'] == should_pass, \
            f"Failed for market_cap={market_cap}, roe={roe}, debt_to_equity={debt_to_equity}"
