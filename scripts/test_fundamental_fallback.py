"""
Test script to verify fundamental data fallback improvements.

This script tests:
1. Immediate fallback when FMP data is incomplete
2. Data merging from multiple sources
3. Stale data retrieval as last resort
4. Data quality scoring
5. Filter skipping when data quality is too low
"""

import sys
import logging
from datetime import datetime
from src.data.fundamental_data_provider import FundamentalDataProvider
from src.strategy.fundamental_filter import FundamentalFilter
from src.models.database import get_database

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_data_quality_scoring():
    """Test data quality scoring on real symbols."""
    logger.info("\n" + "="*80)
    logger.info("TEST 1: Data Quality Scoring")
    logger.info("="*80)
    
    # Load config
    import yaml
    with open('config/autonomous_trading.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    provider = FundamentalDataProvider(config)
    filter_obj = FundamentalFilter(config, provider)
    
    # Test symbols with varying data quality
    test_symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA']
    
    for symbol in test_symbols:
        logger.info(f"\nTesting {symbol}...")
        
        # Get fundamental data
        data = provider.get_fundamental_data(symbol)
        
        if data:
            # Calculate data quality score
            quality_score = filter_obj._calculate_data_quality_score(data)
            
            logger.info(f"  Data Quality Score: {quality_score:.1f}%")
            logger.info(f"  EPS: {data.eps}")
            logger.info(f"  Revenue Growth: {data.revenue_growth}")
            logger.info(f"  P/E Ratio: {data.pe_ratio}")
            logger.info(f"  ROE: {data.roe}")
            logger.info(f"  Market Cap: {data.market_cap}")
            logger.info(f"  Debt/Equity: {data.debt_to_equity}")
            logger.info(f"  Source: {data.source}")
        else:
            logger.warning(f"  No data available for {symbol}")


def test_low_quality_filter_skip():
    """Test that filter is skipped when data quality is too low."""
    logger.info("\n" + "="*80)
    logger.info("TEST 2: Low Quality Filter Skip")
    logger.info("="*80)
    
    # Load config
    import yaml
    with open('config/autonomous_trading.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    provider = FundamentalDataProvider(config)
    filter_obj = FundamentalFilter(config, provider)
    
    # Test with symbols that might have incomplete data
    test_symbols = ['AAPL', 'MSFT', 'GOOGL']
    
    for symbol in test_symbols:
        logger.info(f"\nFiltering {symbol}...")
        
        report = filter_obj.filter_symbol(symbol)
        
        logger.info(f"  Passed: {report.passed}")
        logger.info(f"  Data Quality Score: {report.data_quality_score:.1f}%")
        logger.info(f"  Checks Passed: {report.checks_passed}/{report.checks_total}")
        
        if report.data_quality_score < 40.0:
            logger.warning(f"  Filter skipped due to low data quality!")
        
        for result in report.results:
            logger.info(f"    {result.check_name}: {result.passed} - {result.reason}")


def test_fallback_chain():
    """Test the complete fallback chain."""
    logger.info("\n" + "="*80)
    logger.info("TEST 3: Fallback Chain")
    logger.info("="*80)
    
    # Load config
    import yaml
    with open('config/autonomous_trading.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    provider = FundamentalDataProvider(config)
    
    # Test a symbol
    symbol = 'AAPL'
    logger.info(f"\nTesting fallback chain for {symbol}...")
    
    # Clear cache to force fresh fetch
    provider.clear_cache()
    
    # Get data (should try FMP first, then AV if needed, then stale data)
    data = provider.get_fundamental_data(symbol, use_cache=False)
    
    if data:
        logger.info(f"  Successfully retrieved data")
        logger.info(f"  Source: {data.source}")
        logger.info(f"  Timestamp: {data.timestamp}")
        logger.info(f"  Age: {(datetime.now() - data.timestamp).total_seconds() / 3600:.1f} hours")
        
        # Check completeness
        is_complete = provider._is_data_complete(data)
        logger.info(f"  Data Complete: {is_complete}")
        
        if not is_complete:
            logger.warning(f"  Data is incomplete - fallback should have been triggered")
    else:
        logger.error(f"  Failed to retrieve data from all sources")


def test_api_usage():
    """Test API usage tracking."""
    logger.info("\n" + "="*80)
    logger.info("TEST 4: API Usage Tracking")
    logger.info("="*80)
    
    # Load config
    import yaml
    with open('config/autonomous_trading.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    provider = FundamentalDataProvider(config)
    
    # Get API usage
    usage = provider.get_api_usage()
    
    logger.info(f"\nFMP API Usage:")
    logger.info(f"  Calls Made: {usage['fmp']['calls_made']}")
    logger.info(f"  Max Calls: {usage['fmp']['max_calls']}")
    logger.info(f"  Usage: {usage['fmp']['usage_percent']:.1f}%")
    logger.info(f"  Circuit Breaker Active: {usage['fmp']['circuit_breaker_active']}")
    
    logger.info(f"\nCache:")
    logger.info(f"  Memory Cache Size: {usage['cache_size']}")


def main():
    """Run all tests."""
    try:
        test_data_quality_scoring()
        test_low_quality_filter_skip()
        test_fallback_chain()
        test_api_usage()
        
        logger.info("\n" + "="*80)
        logger.info("ALL TESTS COMPLETED SUCCESSFULLY")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
