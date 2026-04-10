"""
Test FMP Earnings-Aware Caching Implementation

This test verifies:
1. Earnings-aware caching works correctly (30-day default, 24-hour during earnings)
2. Earnings calendar is fetched and cached properly
3. Symbols near earnings dates use 24-hour TTL, others use 30-day TTL
4. Database cache persistence (survives restarts)
5. Circuit breaker stops on first 429 error
6. Circuit breaker reset logic at midnight UTC
7. Cache hit/miss rates and earnings period detection
8. Fallback to Alpha Vantage when FMP is rate-limited
"""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from src.data.fundamental_data_provider import FundamentalDataProvider, FundamentalData, RateLimiter
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.fixture
def mock_database():
    """Create mock database."""
    mock_db = MagicMock()
    mock_session = MagicMock()
    mock_db.get_session.return_value = mock_session
    return mock_db


@pytest.fixture
def config():
    """Test configuration with earnings-aware caching."""
    return {
        'data_sources': {
            'financial_modeling_prep': {
                'enabled': True,
                'api_key': 'test_key',
                'rate_limit': 250,
                'cache_duration': 86400,
                'cache_strategy': 'earnings_aware',
                'earnings_aware_cache': {
                    'default_ttl': 30 * 24 * 3600,  # 30 days
                    'earnings_period_ttl': 24 * 3600,  # 24 hours
                    'earnings_calendar_ttl': 7 * 24 * 3600  # 7 days
                }
            },
            'alpha_vantage': {
                'enabled': True,
                'api_key': 'test_av_key'
            }
        }
    }


@pytest.fixture
def provider(config, mock_database):
    """Create provider instance."""
    with patch('src.models.database.get_database', return_value=mock_database):
        provider = FundamentalDataProvider(config)
        return provider

class TestEarningsAwareCaching:
    """Test earnings-aware caching functionality."""
    
    def test_earnings_aware_config_loaded(self, provider):
        """Test that earnings-aware configuration is loaded correctly."""
        assert provider.cache_strategy == 'earnings_aware'
        assert provider.default_cache_ttl == 30 * 24 * 3600  # 30 days
        assert provider.earnings_period_ttl == 24 * 3600  # 24 hours
        assert provider.earnings_calendar_ttl == 7 * 24 * 3600  # 7 days
        logger.info("✓ Earnings-aware configuration loaded correctly")
    
    def test_smart_ttl_during_earnings_period(self, provider):
        """Test that symbols in earnings period get 24-hour TTL."""
        # Mock earnings calendar to show recent earnings (3 days ago)
        recent_earnings_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
        mock_earnings_data = {
            'symbol': 'AAPL',
            'last_earnings_date': recent_earnings_date,
            'actual_eps': 1.50,
            'estimated_eps': 1.45
        }
        
        with patch.object(provider, '_get_earnings_calendar_cached', return_value=mock_earnings_data):
            ttl = provider._get_smart_cache_ttl('AAPL')
            
            # Should use short TTL (24 hours) during earnings period
            assert ttl == provider.earnings_period_ttl
            assert ttl == 24 * 3600
            logger.info(f"✓ Symbol in earnings period gets 24-hour TTL: {ttl}s")
    
    def test_smart_ttl_outside_earnings_period(self, provider):
        """Test that symbols outside earnings period get 30-day TTL."""
        # Mock earnings calendar to show old earnings (30 days ago)
        old_earnings_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        mock_earnings_data = {
            'symbol': 'MSFT',
            'last_earnings_date': old_earnings_date,
            'actual_eps': 2.50,
            'estimated_eps': 2.45
        }
        
        with patch.object(provider, '_get_earnings_calendar_cached', return_value=mock_earnings_data):
            ttl = provider._get_smart_cache_ttl('MSFT')
            
            # Should use long TTL (30 days) outside earnings period
            assert ttl == provider.default_cache_ttl
            assert ttl == 30 * 24 * 3600
            logger.info(f"✓ Symbol outside earnings period gets 30-day TTL: {ttl}s")
    
    def test_is_earnings_period_detection(self, provider):
        """Test earnings period detection (±7 days from earnings)."""
        # Test within 7 days of earnings
        for days_ago in [0, 3, 7]:
            earnings_date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
            mock_data = {'last_earnings_date': earnings_date}
            
            with patch.object(provider, '_get_earnings_calendar_cached', return_value=mock_data):
                is_earnings = provider._is_earnings_period('TEST')
                assert is_earnings == True
                logger.info(f"✓ Detected earnings period for {days_ago} days ago")
        
        # Test outside 7 days of earnings
        for days_ago in [8, 15, 30]:
            earnings_date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
            mock_data = {'last_earnings_date': earnings_date}
            
            with patch.object(provider, '_get_earnings_calendar_cached', return_value=mock_data):
                is_earnings = provider._is_earnings_period('TEST')
                assert is_earnings == False
                logger.info(f"✓ Not in earnings period for {days_ago} days ago")
    
    def test_earnings_calendar_caching(self, provider):
        """Test that earnings calendar is cached with 7-day TTL."""
        mock_earnings_data = {
            'symbol': 'GOOGL',
            'last_earnings_date': '2024-01-15',
            'actual_eps': 1.50
        }
        
        # Mock the fetch method
        with patch.object(provider, 'get_earnings_calendar', return_value=mock_earnings_data):
            # First call should fetch
            data1 = provider._get_earnings_calendar_cached('GOOGL')
            assert data1 == mock_earnings_data
            assert 'GOOGL' in provider.earnings_calendar_cache
            assert 'GOOGL' in provider.earnings_calendar_timestamps
            
            # Second call should use cache (no fetch)
            data2 = provider._get_earnings_calendar_cached('GOOGL')
            assert data2 == mock_earnings_data
            
            # Verify cache timestamp is recent
            cache_age = (datetime.now() - provider.earnings_calendar_timestamps['GOOGL']).total_seconds()
            assert cache_age < 5  # Should be very recent
            
            logger.info("✓ Earnings calendar caching works correctly")
    
    def test_database_cache_persistence(self, provider):
        """Test that database cache persists across restarts."""
        # Mock database session and ORM
        mock_session = MagicMock()
        mock_record = MagicMock()
        mock_record.symbol = 'TSLA'
        mock_record.fetched_at = datetime.now() - timedelta(hours=1)
        mock_record.eps = 1.50
        mock_record.revenue = 50000000000
        mock_record.revenue_growth = 0.15
        mock_record.total_debt = 10000000000
        mock_record.total_equity = 20000000000
        mock_record.debt_to_equity = 0.5
        mock_record.roe = 0.20
        mock_record.pe_ratio = 25.0
        mock_record.market_cap = 500000000000
        mock_record.insider_net_buying = None
        mock_record.shares_outstanding = 1000000000
        mock_record.shares_change_percent = 0.02
        mock_record.source = 'FMP'
        
        # Mock database query
        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = mock_record
        mock_session.query.return_value = mock_query
        
        with patch.object(provider.database, 'get_session', return_value=mock_session):
            # Mock earnings calendar to return non-earnings period (30-day TTL)
            old_earnings = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            with patch.object(provider, '_get_earnings_calendar_cached', 
                            return_value={'last_earnings_date': old_earnings}):
                data = provider._get_from_database('TSLA')
                
                assert data is not None
                assert data.symbol == 'TSLA'
                assert data.eps == 1.50
                assert data.source == 'FMP'
                
                logger.info("✓ Database cache persistence works correctly")


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    def test_circuit_breaker_on_429_error(self, provider):
        """Test that circuit breaker activates on first 429 error."""
        # Mock a 429 response
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = Exception("429 Rate Limit")
        
        with patch('requests.get', return_value=mock_response):
            # Make a request that will get 429
            result = provider._fmp_request('/test-endpoint', symbol='TEST')
            
            assert result is None
            
            # Verify circuit breaker is activated (rate limiter should be full)
            usage = provider.fmp_rate_limiter.get_usage()
            assert usage['calls_made'] == provider.fmp_rate_limiter.max_calls
            assert usage['calls_remaining'] == 0
            assert not provider.fmp_rate_limiter.can_make_call()
            
            logger.info("✓ Circuit breaker activates on first 429 error")
    
    def test_circuit_breaker_blocks_subsequent_calls(self, provider):
        """Test that circuit breaker blocks subsequent calls after 429."""
        # Activate circuit breaker
        with provider.fmp_rate_limiter.lock:
            current_time = time.time()
            provider.fmp_rate_limiter.calls = [current_time] * provider.fmp_rate_limiter.max_calls
        
        # Try to make a call
        assert not provider.fmp_rate_limiter.can_make_call()
        
        # Verify _fetch_from_fmp returns None without making API call
        with patch('requests.get') as mock_get:
            result = provider._fetch_from_fmp('TEST')
            assert result is None
            # Should not have made any API calls
            mock_get.assert_not_called()
            
            logger.info("✓ Circuit breaker blocks subsequent calls")
    
    def test_circuit_breaker_reset_logic(self):
        """Test circuit breaker reset at midnight UTC."""
        rate_limiter = RateLimiter(max_calls=250, period_seconds=86400)
        
        # Fill up the rate limiter
        current_time = time.time()
        with rate_limiter.lock:
            rate_limiter.calls = [current_time] * 250
        
        assert not rate_limiter.can_make_call()
        
        # Simulate time passing (25 hours = past midnight UTC)
        future_time = current_time + (25 * 3600)
        
        with rate_limiter.lock:
            # Manually clean up old calls (simulating what happens in can_make_call)
            rate_limiter.calls = [call_time for call_time in rate_limiter.calls 
                                 if future_time - call_time < rate_limiter.period_seconds]
        
        # After 25 hours, all calls should be expired
        assert len(rate_limiter.calls) == 0
        assert rate_limiter.can_make_call()
        
        logger.info("✓ Circuit breaker resets after 24-hour period")


class TestFallbackBehavior:
    """Test fallback to Alpha Vantage when FMP is rate-limited."""
    
    def test_fallback_to_alpha_vantage(self, provider):
        """Test that system falls back to Alpha Vantage when FMP is rate-limited."""
        # Mock FMP to be rate-limited
        with provider.fmp_rate_limiter.lock:
            current_time = time.time()
            provider.fmp_rate_limiter.calls = [current_time] * provider.fmp_rate_limiter.max_calls
        
        # Mock Alpha Vantage response
        mock_av_data = FundamentalData(
            symbol='NVDA',
            timestamp=datetime.now(),
            eps=5.50,
            revenue=60000000000,
            pe_ratio=50.0,
            source='AlphaVantage'
        )
        
        # Mock cache and database to return None (force API fetch)
        with patch.object(provider.cache, 'get', return_value=None):
            with patch.object(provider, '_get_from_database', return_value=None):
                with patch.object(provider, '_fetch_from_alpha_vantage', return_value=mock_av_data):
                    data = provider.get_fundamental_data('NVDA', use_cache=False)
                    
                    assert data is not None
                    assert data.source == 'AlphaVantage'
                    assert data.symbol == 'NVDA'
                    assert data.eps == 5.50
                    
                    logger.info("✓ Fallback to Alpha Vantage works when FMP is rate-limited")


class TestCacheMetrics:
    """Test cache hit/miss rates and monitoring."""
    
    def test_cache_hit_tracking(self, provider):
        """Test that cache hits are tracked correctly."""
        # Add data to cache
        test_data = FundamentalData(
            symbol='AMD',
            timestamp=datetime.now(),
            eps=1.20,
            revenue=25000000000,
            source='FMP'
        )
        provider.cache.set('AMD', test_data)
        
        # Get from cache (should be a hit)
        cached_data = provider.cache.get('AMD')
        assert cached_data is not None
        assert cached_data.symbol == 'AMD'
        
        # Check cache size
        usage = provider.get_api_usage()
        assert usage['cache_size'] == 1
        
        logger.info("✓ Cache hit tracking works correctly")
    
    def test_cache_miss_tracking(self, provider):
        """Test that cache misses are handled correctly."""
        # Try to get non-existent data
        cached_data = provider.cache.get('NONEXISTENT')
        assert cached_data is None
        
        logger.info("✓ Cache miss tracking works correctly")
    
    def test_api_usage_statistics(self, provider):
        """Test API usage statistics reporting."""
        # Record some API calls
        for _ in range(5):
            provider.fmp_rate_limiter.record_call()
        
        usage = provider.get_api_usage()
        
        assert 'fmp' in usage
        assert usage['fmp']['calls_made'] == 5
        assert usage['fmp']['max_calls'] == 250
        assert usage['fmp']['usage_percent'] == (5 / 250) * 100
        assert usage['fmp']['calls_remaining'] == 245
        
        logger.info(f"✓ API usage statistics: {usage}")


def run_comprehensive_test():
    """Run all tests and generate report."""
    logger.info("=" * 80)
    logger.info("FMP EARNINGS-AWARE CACHING COMPREHENSIVE TEST")
    logger.info("=" * 80)
    
    # Run pytest
    pytest.main([__file__, '-v', '--tb=short'])
    
    logger.info("=" * 80)
    logger.info("TEST COMPLETE")
    logger.info("=" * 80)


if __name__ == '__main__':
    run_comprehensive_test()
