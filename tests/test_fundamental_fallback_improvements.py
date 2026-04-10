"""
Test fundamental data fallback logic improvements.

Tests:
1. Immediate fallback to Alpha Vantage when FMP data is incomplete
2. Data merging from multiple sources
3. Stale data retrieval as last resort
4. Data quality score calculation
5. Skipping fundamental filter when data quality is too low
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from src.data.fundamental_data_provider import FundamentalData, FundamentalDataProvider
from src.strategy.fundamental_filter import FundamentalFilter


class TestFundamentalFallbackImprovements:
    """Test fundamental data fallback improvements."""
    
    def test_data_completeness_check(self):
        """Test that incomplete data triggers immediate fallback."""
        config = {
            'data_sources': {
                'financial_modeling_prep': {
                    'enabled': True,
                    'api_key': 'test_key',
                    'rate_limit': 250
                },
                'alpha_vantage': {
                    'enabled': True,
                    'api_key': 'test_key'
                }
            }
        }
        
        provider = FundamentalDataProvider(config)
        
        # Complete data (2 out of 3 critical fields)
        complete_data = FundamentalData(
            symbol='AAPL',
            timestamp=datetime.now(),
            eps=5.0,
            revenue_growth=0.10,
            pe_ratio=None,  # Missing but still complete
            source='fmp'
        )
        assert provider._is_data_complete(complete_data) is True
        
        # Incomplete data (only 1 out of 3 critical fields)
        incomplete_data = FundamentalData(
            symbol='AAPL',
            timestamp=datetime.now(),
            eps=5.0,
            revenue_growth=None,
            pe_ratio=None,
            source='fmp'
        )
        assert provider._is_data_complete(incomplete_data) is False
    
    def test_data_merging(self):
        """Test that data from multiple sources is merged correctly."""
        config = {
            'data_sources': {
                'financial_modeling_prep': {
                    'enabled': True,
                    'api_key': 'test_key',
                    'rate_limit': 250
                },
                'alpha_vantage': {
                    'enabled': True,
                    'api_key': 'test_key'
                }
            }
        }
        
        provider = FundamentalDataProvider(config)
        
        # FMP data (incomplete)
        fmp_data = FundamentalData(
            symbol='AAPL',
            timestamp=datetime.now(),
            eps=5.0,
            revenue_growth=None,  # Missing
            pe_ratio=25.0,
            roe=0.30,
            market_cap=2000000000000,
            source='fmp'
        )
        
        # Alpha Vantage data (has revenue_growth)
        av_data = FundamentalData(
            symbol='AAPL',
            timestamp=datetime.now(),
            eps=4.8,  # Different value
            revenue_growth=0.12,  # Has this
            pe_ratio=None,  # Missing
            roe=None,
            market_cap=None,
            source='alpha_vantage'
        )
        
        # Merge
        merged = provider._merge_fundamental_data(fmp_data, av_data)
        
        # Should prefer FMP values when available
        assert merged.eps == 5.0  # From FMP
        assert merged.pe_ratio == 25.0  # From FMP
        assert merged.roe == 0.30  # From FMP
        assert merged.market_cap == 2000000000000  # From FMP
        
        # Should use AV values when FMP is missing
        assert merged.revenue_growth == 0.12  # From AV
        
        # Source should indicate merge
        assert 'fmp' in merged.source
        assert 'alpha_vantage' in merged.source
    
    def test_stale_data_retrieval(self):
        """Test that stale data is retrieved as last resort."""
        config = {
            'data_sources': {
                'financial_modeling_prep': {
                    'enabled': False  # Disabled
                },
                'alpha_vantage': {
                    'enabled': False  # Disabled
                }
            }
        }
        
        provider = FundamentalDataProvider(config)
        
        # Mock database to return stale data
        with patch.object(provider, '_get_from_database') as mock_db:
            stale_data = FundamentalData(
                symbol='AAPL',
                timestamp=datetime.now() - timedelta(days=10),  # 10 days old
                eps=5.0,
                revenue_growth=0.10,
                pe_ratio=25.0,
                source='fmp'
            )
            
            # First call (normal) returns None (expired)
            # Second call (allow_stale=True) returns stale data
            mock_db.side_effect = [None, stale_data]
            
            # Should get stale data as last resort
            result = provider.get_fundamental_data('AAPL')
            
            # Should have called database twice
            assert mock_db.call_count == 2
            # Second call should have allow_stale=True
            assert mock_db.call_args_list[1][1]['allow_stale'] is True
            
            assert result == stale_data
    
    def test_data_quality_score_calculation(self):
        """Test data quality score calculation."""
        config = {
            'fundamental_filters': {
                'enabled': True,
                'min_checks_passed': 4
            }
        }
        
        mock_provider = Mock()
        filter_obj = FundamentalFilter(config, mock_provider)
        
        # Perfect data (100%)
        perfect_data = FundamentalData(
            symbol='AAPL',
            timestamp=datetime.now(),
            eps=5.0,  # 20%
            revenue_growth=0.10,  # 20%
            pe_ratio=25.0,  # 20%
            roe=0.30,  # 15%
            market_cap=2000000000000,  # 15%
            debt_to_equity=0.5,  # 10%
            source='fmp'
        )
        assert filter_obj._calculate_data_quality_score(perfect_data) == 100.0
        
        # Missing some fields (60%)
        partial_data = FundamentalData(
            symbol='AAPL',
            timestamp=datetime.now(),
            eps=5.0,  # 20%
            revenue_growth=0.10,  # 20%
            pe_ratio=25.0,  # 20%
            roe=None,  # Missing
            market_cap=None,  # Missing
            debt_to_equity=None,  # Missing
            source='fmp'
        )
        assert filter_obj._calculate_data_quality_score(partial_data) == 60.0
        
        # Very poor data (20%)
        poor_data = FundamentalData(
            symbol='AAPL',
            timestamp=datetime.now(),
            eps=5.0,  # 20%
            revenue_growth=None,
            pe_ratio=None,
            roe=None,
            market_cap=None,
            debt_to_equity=None,
            source='fmp'
        )
        assert filter_obj._calculate_data_quality_score(poor_data) == 20.0
    
    def test_skip_filter_on_low_data_quality(self):
        """Test that fundamental filter is skipped when data quality is too low."""
        config = {
            'fundamental_filters': {
                'enabled': True,
                'min_checks_passed': 4,
                'checks': {
                    'profitable': True,
                    'growing': True,
                    'reasonable_valuation': True,
                    'no_dilution': True,
                    'insider_buying': True
                }
            }
        }
        
        mock_provider = Mock()
        filter_obj = FundamentalFilter(config, mock_provider)
        
        # Low quality data (only 20%)
        low_quality_data = FundamentalData(
            symbol='TEST',
            timestamp=datetime.now(),
            eps=5.0,  # Only this field
            revenue_growth=None,
            pe_ratio=None,
            roe=None,
            market_cap=None,
            debt_to_equity=None,
            source='fmp'
        )
        
        mock_provider.get_fundamental_data.return_value = low_quality_data
        
        # Filter should pass by default due to low data quality
        report = filter_obj.filter_symbol('TEST')
        
        assert report.passed is True  # Passed by default
        assert report.data_quality_score == 20.0
        assert len(report.results) == 1
        assert report.results[0].check_name == 'data_quality'
        assert 'insufficient data' in report.results[0].reason.lower()
    
    def test_immediate_fallback_on_incomplete_fmp_data(self):
        """Test that Alpha Vantage is tried immediately when FMP data is incomplete."""
        config = {
            'data_sources': {
                'financial_modeling_prep': {
                    'enabled': True,
                    'api_key': 'test_key',
                    'rate_limit': 250
                },
                'alpha_vantage': {
                    'enabled': True,
                    'api_key': 'test_key'
                }
            }
        }
        
        provider = FundamentalDataProvider(config)
        
        # Mock FMP to return incomplete data
        incomplete_fmp_data = FundamentalData(
            symbol='TEST',
            timestamp=datetime.now(),
            eps=5.0,
            revenue_growth=None,
            pe_ratio=None,
            source='fmp'
        )
        
        # Mock AV to return complete data
        complete_av_data = FundamentalData(
            symbol='TEST',
            timestamp=datetime.now(),
            eps=4.8,
            revenue_growth=0.12,
            pe_ratio=25.0,
            source='alpha_vantage'
        )
        
        # Create a mock for _get_from_database that returns None for all calls
        def mock_get_from_database(symbol, allow_stale=False):
            return None
        
        # Mock all the methods
        with patch.object(provider.cache, 'get', return_value=None):
            with patch.object(provider.cache, 'set'):
                with patch.object(provider, '_save_to_database'):
                    with patch.object(provider, '_get_from_database', side_effect=mock_get_from_database):
                        with patch.object(provider, '_fetch_from_fmp', return_value=incomplete_fmp_data):
                            with patch.object(provider, '_fetch_from_alpha_vantage', return_value=complete_av_data):
                                result = provider.get_fundamental_data('TEST')
                                
                                # Should have merged data
                                assert result is not None, "Result should not be None"
                                assert result.eps == 5.0  # From FMP
                                assert result.revenue_growth == 0.12  # From AV
                                assert result.pe_ratio == 25.0  # From AV
                                assert 'fmp' in result.source
                                assert 'alpha_vantage' in result.source


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
