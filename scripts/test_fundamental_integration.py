#!/usr/bin/env python3
"""
Test script for fundamental data integration.

Tests the complete flow:
1. Load configuration
2. Initialize FundamentalDataProvider
3. Fetch fundamental data for test symbols
4. Initialize FundamentalFilter
5. Filter symbols based on fundamentals
6. Display results
"""

import sys
import os
import yaml
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.data.fundamental_data_provider import FundamentalDataProvider
from src.strategy.fundamental_filter import FundamentalFilter

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from YAML file."""
    config_path = project_root / 'config' / 'autonomous_trading.yaml'
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def test_fundamental_data_provider(config):
    """Test FundamentalDataProvider."""
    logger.info("=" * 80)
    logger.info("Testing FundamentalDataProvider")
    logger.info("=" * 80)
    
    provider = FundamentalDataProvider(config)
    
    # Test symbols
    test_symbols = ['AAPL', 'MSFT', 'GOOGL']
    
    for symbol in test_symbols:
        logger.info(f"\nFetching fundamental data for {symbol}...")
        data = provider.get_fundamental_data(symbol, use_cache=False)
        
        if data:
            logger.info(f"✓ Successfully fetched data for {symbol}")
            logger.info(f"  Source: {data.source}")
            logger.info(f"  EPS: {data.eps}")
            logger.info(f"  Revenue: ${data.revenue:,.0f}" if data.revenue else "  Revenue: N/A")
            logger.info(f"  Revenue Growth: {data.revenue_growth*100:.1f}%" if data.revenue_growth else "  Revenue Growth: N/A")
            logger.info(f"  ROE: {data.roe*100:.1f}%" if data.roe else "  ROE: N/A")
            logger.info(f"  P/E Ratio: {data.pe_ratio:.1f}" if data.pe_ratio else "  P/E Ratio: N/A")
            logger.info(f"  Market Cap: ${data.market_cap:,.0f}" if data.market_cap else "  Market Cap: N/A")
            logger.info(f"  Debt/Equity: {data.debt_to_equity:.2f}" if data.debt_to_equity else "  Debt/Equity: N/A")
        else:
            logger.error(f"✗ Failed to fetch data for {symbol}")
    
    # Check API usage
    usage = provider.get_api_usage()
    logger.info(f"\nAPI Usage:")
    logger.info(f"  FMP: {usage['fmp']['calls_made']}/{usage['fmp']['max_calls']} "
               f"({usage['fmp']['usage_percent']:.1f}%)")
    logger.info(f"  Cache size: {usage['cache_size']} symbols")
    
    return provider


def test_fundamental_filter(config, provider):
    """Test FundamentalFilter."""
    logger.info("\n" + "=" * 80)
    logger.info("Testing FundamentalFilter")
    logger.info("=" * 80)
    
    filter_instance = FundamentalFilter(config, provider)
    
    # Test symbols (mix of good and bad)
    test_symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA']
    
    logger.info(f"\nFiltering {len(test_symbols)} symbols...")
    logger.info(f"Minimum checks required: {filter_instance.min_checks_passed}/5")
    
    results = filter_instance.filter_symbols(test_symbols)
    
    passed_symbols = []
    failed_symbols = []
    
    for symbol, report in results.items():
        logger.info(f"\n{symbol}:")
        logger.info(f"  Status: {'✓ PASSED' if report.passed else '✗ FAILED'}")
        logger.info(f"  Checks: {report.checks_passed}/{report.checks_total}")
        
        for result in report.results:
            status = "✓" if result.passed else "✗"
            logger.info(f"    {status} {result.check_name}: {result.reason}")
        
        if report.passed:
            passed_symbols.append(symbol)
        else:
            failed_symbols.append(symbol)
    
    logger.info(f"\n" + "=" * 80)
    logger.info(f"Summary:")
    logger.info(f"  Passed: {len(passed_symbols)} symbols - {', '.join(passed_symbols)}")
    logger.info(f"  Failed: {len(failed_symbols)} symbols - {', '.join(failed_symbols)}")
    logger.info("=" * 80)
    
    return results


def test_cache_performance(provider):
    """Test cache performance."""
    logger.info("\n" + "=" * 80)
    logger.info("Testing Cache Performance")
    logger.info("=" * 80)
    
    import time
    
    symbol = 'AAPL'
    
    # First call (no cache)
    logger.info(f"\nFirst call for {symbol} (no cache)...")
    start = time.time()
    data1 = provider.get_fundamental_data(symbol, use_cache=False)
    time1 = time.time() - start
    logger.info(f"  Time: {time1:.2f}s")
    
    # Second call (with cache)
    logger.info(f"\nSecond call for {symbol} (with cache)...")
    start = time.time()
    data2 = provider.get_fundamental_data(symbol, use_cache=True)
    time2 = time.time() - start
    logger.info(f"  Time: {time2:.2f}s")
    
    speedup = time1 / time2 if time2 > 0 else float('inf')
    logger.info(f"\nCache speedup: {speedup:.1f}x faster")
    
    if data1 and data2:
        logger.info(f"Data consistency: {'✓ Same data' if data1.eps == data2.eps else '✗ Different data'}")


def main():
    """Main test function."""
    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = load_config()
        
        # Test FundamentalDataProvider
        provider = test_fundamental_data_provider(config)
        
        # Test FundamentalFilter
        test_fundamental_filter(config, provider)
        
        # Test cache performance
        test_cache_performance(provider)
        
        logger.info("\n" + "=" * 80)
        logger.info("✓ All tests completed successfully!")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"\n✗ Test failed with error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
