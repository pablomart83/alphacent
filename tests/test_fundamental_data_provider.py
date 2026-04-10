"""
Tests for FundamentalDataProvider.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from src.data.fundamental_data_provider import (
    FundamentalData,
    RateLimiter,
    FundamentalDataCache,
    FundamentalDataProvider
)


class TestRateLimiter:
    """Tests for RateLimiter."""
    
    def test_allows_calls_within_limit(self):
        """Test that calls are allowed within the limit."""
        limiter = RateLimiter(max_calls=5, period_seconds=60)
        
        for i in range(5):
            assert limiter.can_make_call()
            limiter.record_call()
        
        # 6th call should be blocked
        assert not limiter.can_make_call()
    
    def test_usage_statistics(self):
        """Test usage statistics."""
        limiter = RateLimiter(max_calls=10, period_seconds=60)
        
        for i in range(3):
            limiter.record_call()
        
        usage = limiter.get_usage()
        assert usage['calls_made'] == 3
        assert usage['max_calls'] == 10
        assert usage['usage_percent'] == 30.0
        assert usage['calls_remaining'] == 7
    
    def test_calls_expire_after_period(self):
        """Test that old calls are removed after the period."""
        limiter = RateLimiter(max_calls=2, period_seconds=1)
        
        # Make 2 calls
        limiter.record_call()
        limiter.record_call()
        assert not limiter.can_make_call()
        
        # Wait for period to expire
        import time
        time.sleep(1.1)
        
        # Should be able to make calls again
        assert limiter.can_make_call()


class TestFundamentalDataCache:
    """Tests for FundamentalDataCache."""
    
    def test_cache_stores_and_retrieves_data(self):
        """Test basic cache operations."""
        cache = FundamentalDataCache(ttl_seconds=60)
        
        data = FundamentalData(
            symbol="AAPL",
            timestamp=datetime.now(),
            eps=6.05,
            revenue=394328000000,
            source="test"
        )
        
        cache.set("AAPL", data)
        retrieved = cache.get("AAPL")
        
        assert retrieved is not None
        assert retrieved.symbol == "AAPL"
        assert retrieved.eps == 6.05
    
    def test_cache_expires_after_ttl(self):
        """Test that cached data expires after TTL."""
        cache = FundamentalDataCache(ttl_seconds=1)
        
        data = FundamentalData(
            symbol="AAPL",
            timestamp=datetime.now() - timedelta(seconds=2),  # Already expired
            eps=6.05,
            source="test"
        )
        
        cache.set("AAPL", data)
        retrieved = cache.get("AAPL")
        
        # Should be None because it's expired
        assert retrieved is None
    
    def test_cache_clear(self):
        """Test cache clearing."""
        cache = FundamentalDataCache(ttl_seconds=60)
        
        data = FundamentalData(symbol="AAPL", timestamp=datetime.now(), source="test")
        cache.set("AAPL", data)
        
        assert cache.get("AAPL") is not None
        
        cache.clear()
        assert cache.get("AAPL") is None


class TestFundamentalDataProvider:
    """Tests for FundamentalDataProvider."""
    
    @pytest.fixture
    def config(self):
        """Test configuration."""
        return {
            'data_sources': {
                'financial_modeling_prep': {
                    'enabled': True,
                    'api_key': 'test_fmp_key',
                    'rate_limit': 250,
                    'cache_duration': 86400
                },
                'alpha_vantage': {
                    'enabled': True,
                    'api_key': 'test_av_key'
                }
            }
        }
    
    @pytest.fixture
    def provider(self, config):
        """Create provider instance."""
        return FundamentalDataProvider(config)
    
    def test_initialization(self, provider):
        """Test provider initialization."""
        assert provider.fmp_enabled is True
        assert provider.fmp_api_key == 'test_fmp_key'
        assert provider.av_enabled is True
        assert provider.av_api_key == 'test_av_key'
    
    def test_uses_cache_when_available(self, provider):
        """Test that cached data is used when available."""
        # Pre-populate cache
        cached_data = FundamentalData(
            symbol="AAPL",
            timestamp=datetime.now(),
            eps=6.05,
            source="cache"
        )
        provider.cache.set("AAPL", cached_data)
        
        # Should return cached data without making API call
        result = provider.get_fundamental_data("AAPL", use_cache=True)
        
        assert result is not None
        assert result.source == "cache"
        assert result.eps == 6.05
    
    @patch('requests.get')
    def test_fetches_from_fmp(self, mock_get, provider):
        """Test fetching from FMP API."""
        # Mock FMP API responses
        mock_response = Mock()
        mock_response.json.side_effect = [
            [{'eps': 6.05, 'revenue': 394328000000, 'revenueGrowth': 0.08}],  # income statement
            [{'totalDebt': 100000000000, 'totalStockholdersEquity': 50000000000}],  # balance sheet
            [{'roe': 0.15, 'peRatio': 28.5, 'marketCap': 2800000000000}],  # key metrics
            [{'mktCap': 2800000000000}]  # profile
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = provider.get_fundamental_data("AAPL", use_cache=False)
        
        assert result is not None
        assert result.symbol == "AAPL"
        assert result.eps == 6.05
        assert result.revenue == 394328000000
        assert result.revenue_growth == 0.08
        assert result.roe == 0.15
        assert result.pe_ratio == 28.5
        assert result.source == "FMP"
    
    @patch('requests.get')
    def test_falls_back_to_alpha_vantage(self, mock_get, provider):
        """Test fallback to Alpha Vantage when FMP fails."""
        # Disable FMP
        provider.fmp_enabled = False
        
        # Mock Alpha Vantage response
        mock_response = Mock()
        mock_response.json.return_value = {
            'Symbol': 'AAPL',
            'EPS': '6.05',
            'RevenueTTM': '394328000000',
            'QuarterlyRevenueGrowthYOY': '0.08',
            'ReturnOnEquityTTM': '0.15',
            'PERatio': '28.5',
            'MarketCapitalization': '2800000000000'
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = provider.get_fundamental_data("AAPL", use_cache=False)
        
        assert result is not None
        assert result.symbol == "AAPL"
        assert result.eps == 6.05
        assert result.source == "AlphaVantage"
    
    def test_respects_rate_limit(self, provider):
        """Test that rate limiting is enforced."""
        # Set very low rate limit
        provider.fmp_rate_limiter = RateLimiter(max_calls=2, period_seconds=60)
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.side_effect = [
                [{'eps': 6.05}], [{}], [{}], [{}]  # income, balance, metrics, profile
            ]
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            # First call should succeed
            result1 = provider.get_fundamental_data("AAPL", use_cache=False)
            assert result1 is not None
            
            # Second call should succeed
            result2 = provider.get_fundamental_data("MSFT", use_cache=False)
            assert result2 is not None
            
            # Third call should fail due to rate limit
            result3 = provider.get_fundamental_data("GOOGL", use_cache=False)
            assert result3 is None
    
    def test_api_usage_tracking(self, provider):
        """Test API usage tracking."""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.side_effect = [
                [{'eps': 6.05}], [{}], [{}], [{}]
            ]
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            provider.get_fundamental_data("AAPL", use_cache=False)
            
            usage = provider.get_api_usage()
            assert usage['fmp']['calls_made'] == 1
            assert usage['fmp']['max_calls'] == 250
    
    def test_handles_missing_data_gracefully(self, provider):
        """Test handling of missing data fields."""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.side_effect = [
                [{}],  # Empty income statement
                [{}],  # Empty balance sheet
                [{}],  # Empty key metrics
                [{}]   # Empty profile
            ]
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            result = provider.get_fundamental_data("AAPL", use_cache=False)
            
            assert result is not None
            assert result.eps is None
            assert result.revenue is None
            assert result.roe is None


    @patch('requests.get')
    def test_get_earnings_calendar_fmp(self, mock_get, provider):
        """Test fetching earnings calendar from FMP."""
        # Mock FMP earnings calendar response
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                'date': '2024-01-15',
                'eps': 1.08,
                'epsEstimated': 1.00,
                'revenue': 100000000,
                'revenueEstimated': 95000000,
                'fiscalDateEnding': '2023-12-31'
            },
            {
                'date': '2023-10-15',
                'eps': 0.95,
                'epsEstimated': 0.90,
                'revenue': 90000000,
                'revenueEstimated': 88000000,
                'fiscalDateEnding': '2023-09-30'
            }
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = provider.get_earnings_calendar("AAPL")
        
        assert result is not None
        assert result['symbol'] == "AAPL"
        assert result['last_earnings_date'] == '2024-01-15'
        assert result['actual_eps'] == 1.08
        assert result['estimated_eps'] == 1.00
        assert abs(result['surprise_pct'] - 0.08) < 0.001  # Allow for floating point precision
        assert result['source'] == 'FMP'
    
    @patch('requests.get')
    def test_get_earnings_calendar_alpha_vantage(self, mock_get, provider):
        """Test fetching earnings calendar from Alpha Vantage."""
        # Disable FMP
        provider.fmp_enabled = False
        
        # Mock Alpha Vantage earnings response
        mock_response = Mock()
        mock_response.json.return_value = {
            'quarterlyEarnings': [
                {
                    'reportedDate': '2024-01-15',
                    'reportedEPS': '1.08',
                    'estimatedEPS': '1.00',
                    'surprise': '0.08',
                    'surprisePercentage': '8.0',
                    'fiscalDateEnding': '2023-12-31'
                }
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = provider.get_earnings_calendar("AAPL")
        
        assert result is not None
        assert result['symbol'] == "AAPL"
        assert result['last_earnings_date'] == '2024-01-15'
        assert result['actual_eps'] == 1.08
        assert result['estimated_eps'] == 1.00
        assert abs(result['surprise_pct'] - 0.08) < 0.001  # Allow for floating point precision
        assert result['source'] == 'AlphaVantage'
    
    @patch('requests.get')
    def test_calculate_earnings_surprise(self, mock_get, provider):
        """Test calculating earnings surprise percentage."""
        # Mock FMP earnings calendar response
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                'date': '2024-01-15',
                'eps': 1.10,
                'epsEstimated': 1.00,
                'revenue': 100000000,
                'fiscalDateEnding': '2023-12-31'
            }
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        surprise = provider.calculate_earnings_surprise("AAPL")
        
        assert surprise is not None
        assert abs(surprise - 0.10) < 0.001  # Allow for floating point precision
    
    @patch('requests.get')
    def test_get_days_since_earnings(self, mock_get, provider):
        """Test calculating days since earnings."""
        # Mock earnings 5 days ago
        five_days_ago = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                'date': five_days_ago,
                'eps': 1.08,
                'epsEstimated': 1.00,
                'revenue': 100000000,
                'fiscalDateEnding': '2023-12-31'
            }
        ]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        days_since = provider.get_days_since_earnings("AAPL")
        
        assert days_since is not None
        assert days_since == 5
    
    def test_store_earnings_history(self, provider):
        """Test storing earnings history in database."""
        from src.models.orm import EarningsHistoryORM
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        # Create in-memory database
        engine = create_engine('sqlite:///:memory:')
        from src.models.orm import Base
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        earnings_data = {
            'symbol': 'AAPL',
            'last_earnings_date': '2024-01-15',
            'fiscal_period': '2023-12-31',
            'actual_eps': 1.08,
            'estimated_eps': 1.00,
            'surprise_pct': 0.08,
            'revenue': 100000000,
            'estimated_revenue': 95000000,
            'source': 'FMP'
        }
        
        provider.store_earnings_history(earnings_data, session)
        
        # Verify it was stored
        stored = session.query(EarningsHistoryORM).filter_by(symbol='AAPL').first()
        assert stored is not None
        assert stored.symbol == 'AAPL'
        assert stored.actual_eps == 1.08
        assert stored.estimated_eps == 1.00
        assert stored.surprise_pct == 0.08
        assert stored.source == 'FMP'
        
        session.close()
    
    def test_store_earnings_history_duplicate(self, provider):
        """Test that duplicate earnings records are not stored."""
        from src.models.orm import EarningsHistoryORM
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        # Create in-memory database
        engine = create_engine('sqlite:///:memory:')
        from src.models.orm import Base
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        earnings_data = {
            'symbol': 'AAPL',
            'last_earnings_date': '2024-01-15',
            'fiscal_period': '2023-12-31',
            'actual_eps': 1.08,
            'estimated_eps': 1.00,
            'surprise_pct': 0.08,
            'revenue': 100000000,
            'estimated_revenue': 95000000,
            'source': 'FMP'
        }
        
        # Store once
        provider.store_earnings_history(earnings_data, session)
        
        # Try to store again
        provider.store_earnings_history(earnings_data, session)
        
        # Verify only one record exists
        count = session.query(EarningsHistoryORM).filter_by(symbol='AAPL').count()
        assert count == 1
        
        session.close()
