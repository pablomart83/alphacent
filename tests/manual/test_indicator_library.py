"""
Tests for Indicator Library

Tests all 10 essential indicators and caching functionality.
"""

import pytest
import pandas as pd
import numpy as np
from src.strategy.indicator_library import IndicatorLibrary, CacheKey


@pytest.fixture
def sample_data():
    """Create sample OHLCV data for testing."""
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    
    # Generate realistic price data
    close_prices = 100 + np.cumsum(np.random.randn(100) * 2)
    
    data = pd.DataFrame({
        'open': close_prices + np.random.randn(100) * 0.5,
        'high': close_prices + abs(np.random.randn(100) * 1.5),
        'low': close_prices - abs(np.random.randn(100) * 1.5),
        'close': close_prices,
        'volume': np.random.randint(1000000, 10000000, 100)
    }, index=dates)
    
    return data


@pytest.fixture
def indicator_lib():
    """Create IndicatorLibrary instance."""
    return IndicatorLibrary()


class TestIndicatorLibrary:
    """Test suite for IndicatorLibrary."""
    
    def test_list_indicators(self, indicator_lib):
        """Test that all 10 indicators are listed."""
        indicators = indicator_lib.list_indicators()
        
        assert len(indicators) == 10
        assert 'SMA' in indicators
        assert 'EMA' in indicators
        assert 'RSI' in indicators
        assert 'MACD' in indicators
        assert 'BBANDS' in indicators
        assert 'ATR' in indicators
        assert 'VOLUME_MA' in indicators
        assert 'PRICE_CHANGE_PCT' in indicators
        assert 'SUPPORT_RESISTANCE' in indicators
        assert 'STOCH' in indicators
    
    def test_sma_calculation(self, indicator_lib, sample_data):
        """Test Simple Moving Average calculation."""
        sma = indicator_lib.calculate('SMA', sample_data, symbol='TEST', period=20)
        
        assert isinstance(sma, pd.Series)
        assert len(sma) == len(sample_data)
        # First 19 values should be NaN
        assert sma.iloc[:19].isna().all()
        # Remaining values should be valid
        assert not sma.iloc[19:].isna().all()
    
    def test_ema_calculation(self, indicator_lib, sample_data):
        """Test Exponential Moving Average calculation."""
        ema = indicator_lib.calculate('EMA', sample_data, symbol='TEST', period=20)
        
        assert isinstance(ema, pd.Series)
        assert len(ema) == len(sample_data)
        # EMA should have some valid values
        assert not ema.isna().all()
    
    def test_rsi_calculation(self, indicator_lib, sample_data):
        """Test RSI calculation."""
        rsi = indicator_lib.calculate('RSI', sample_data, symbol='TEST', period=14)
        
        assert isinstance(rsi, pd.Series)
        assert len(rsi) == len(sample_data)
        # RSI values should be between 0 and 100
        valid_rsi = rsi.dropna()
        assert (valid_rsi >= 0).all()
        assert (valid_rsi <= 100).all()
    
    def test_macd_calculation(self, indicator_lib, sample_data):
        """Test MACD calculation."""
        macd = indicator_lib.calculate('MACD', sample_data, symbol='TEST',
                                       fast_period=12, slow_period=26, signal_period=9)
        
        assert isinstance(macd, pd.Series)
        assert len(macd) == len(sample_data)
        # MACD should have some valid values
        assert not macd.isna().all()
    
    def test_bollinger_bands_calculation(self, indicator_lib, sample_data):
        """Test Bollinger Bands calculation."""
        bbands = indicator_lib.calculate('BBANDS', sample_data, symbol='TEST',
                                         period=20, std_dev=2.0)
        
        assert isinstance(bbands, pd.Series)
        assert len(bbands) == len(sample_data)
        # Should return middle band (SMA)
        assert not bbands.isna().all()
    
    def test_atr_calculation(self, indicator_lib, sample_data):
        """Test ATR calculation."""
        atr = indicator_lib.calculate('ATR', sample_data, symbol='TEST', period=14)
        
        assert isinstance(atr, pd.Series)
        assert len(atr) == len(sample_data)
        # ATR should be positive
        valid_atr = atr.dropna()
        assert (valid_atr >= 0).all()
    
    def test_volume_ma_calculation(self, indicator_lib, sample_data):
        """Test Volume MA calculation."""
        vol_ma = indicator_lib.calculate('VOLUME_MA', sample_data, symbol='TEST', period=20)
        
        assert isinstance(vol_ma, pd.Series)
        assert len(vol_ma) == len(sample_data)
        # Volume MA should be positive
        valid_vol_ma = vol_ma.dropna()
        assert (valid_vol_ma > 0).all()
    
    def test_price_change_pct_calculation(self, indicator_lib, sample_data):
        """Test Price Change % calculation."""
        price_change = indicator_lib.calculate('PRICE_CHANGE_PCT', sample_data,
                                               symbol='TEST', period=1)
        
        assert isinstance(price_change, pd.Series)
        assert len(price_change) == len(sample_data)
        # Should have some valid values
        assert not price_change.isna().all()
    
    def test_support_resistance_calculation(self, indicator_lib, sample_data):
        """Test Support/Resistance calculation."""
        sr = indicator_lib.calculate('SUPPORT_RESISTANCE', sample_data,
                                     symbol='TEST', period=20)
        
        assert isinstance(sr, pd.Series)
        assert len(sr) == len(sample_data)
        # Should return midpoint values
        assert not sr.isna().all()
    
    def test_stochastic_calculation(self, indicator_lib, sample_data):
        """Test Stochastic Oscillator calculation."""
        stoch = indicator_lib.calculate('STOCH', sample_data, symbol='TEST',
                                        k_period=14, d_period=3)
        
        assert isinstance(stoch, pd.Series)
        assert len(stoch) == len(sample_data)
        # Stochastic should be between 0 and 100
        valid_stoch = stoch.dropna()
        assert (valid_stoch >= 0).all()
        assert (valid_stoch <= 100).all()
    
    def test_caching_functionality(self, indicator_lib, sample_data):
        """Test that caching works correctly."""
        # Calculate indicator first time
        sma1 = indicator_lib.calculate('SMA', sample_data, symbol='TEST', period=20)
        
        # Calculate same indicator again
        sma2 = indicator_lib.calculate('SMA', sample_data, symbol='TEST', period=20)
        
        # Should return the same cached result
        assert sma1 is sma2  # Same object reference
        pd.testing.assert_series_equal(sma1, sma2)
    
    def test_cache_different_params(self, indicator_lib, sample_data):
        """Test that different parameters create different cache entries."""
        sma20 = indicator_lib.calculate('SMA', sample_data, symbol='TEST', period=20)
        sma50 = indicator_lib.calculate('SMA', sample_data, symbol='TEST', period=50)
        
        # Should be different results
        assert not sma20.equals(sma50)
    
    def test_cache_different_symbols(self, indicator_lib, sample_data):
        """Test that different symbols create different cache entries."""
        sma_test1 = indicator_lib.calculate('SMA', sample_data, symbol='TEST1', period=20)
        sma_test2 = indicator_lib.calculate('SMA', sample_data, symbol='TEST2', period=20)
        
        # Should create separate cache entries (even if data is same)
        assert sma_test1 is not sma_test2
    
    def test_clear_cache_all(self, indicator_lib, sample_data):
        """Test clearing entire cache."""
        # Calculate some indicators
        indicator_lib.calculate('SMA', sample_data, symbol='TEST', period=20)
        indicator_lib.calculate('RSI', sample_data, symbol='TEST', period=14)
        
        # Cache should have entries
        assert len(indicator_lib._cache) > 0
        
        # Clear cache
        indicator_lib.clear_cache()
        
        # Cache should be empty
        assert len(indicator_lib._cache) == 0
    
    def test_clear_cache_by_symbol(self, indicator_lib, sample_data):
        """Test clearing cache for specific symbol."""
        # Calculate indicators for different symbols
        indicator_lib.calculate('SMA', sample_data, symbol='TEST1', period=20)
        indicator_lib.calculate('SMA', sample_data, symbol='TEST2', period=20)
        
        # Cache should have 2 entries
        assert len(indicator_lib._cache) == 2
        
        # Clear cache for TEST1 only
        indicator_lib.clear_cache(symbol='TEST1')
        
        # Cache should have 1 entry
        assert len(indicator_lib._cache) == 1
        
        # Remaining entry should be for TEST2
        remaining_key = list(indicator_lib._cache.keys())[0]
        assert remaining_key.symbol == 'TEST2'
    
    def test_unknown_indicator_raises_error(self, indicator_lib, sample_data):
        """Test that unknown indicator raises ValueError."""
        with pytest.raises(ValueError, match="Unknown indicator"):
            indicator_lib.calculate('UNKNOWN_INDICATOR', sample_data, symbol='TEST')
    
    def test_get_indicator_info(self, indicator_lib):
        """Test getting indicator metadata."""
        info = indicator_lib.get_indicator_info('RSI')
        
        assert 'description' in info
        assert 'parameters' in info
        assert 'Relative Strength Index' in info['description']
        assert 'period' in info['parameters']
    
    def test_cache_key_equality(self):
        """Test CacheKey equality and hashing."""
        key1 = CacheKey(symbol='TEST', indicator='SMA', params='{"period": 20}')
        key2 = CacheKey(symbol='TEST', indicator='SMA', params='{"period": 20}')
        key3 = CacheKey(symbol='TEST', indicator='SMA', params='{"period": 50}')
        
        # Same keys should be equal
        assert key1 == key2
        assert hash(key1) == hash(key2)
        
        # Different keys should not be equal
        assert key1 != key3
        assert hash(key1) != hash(key3)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
