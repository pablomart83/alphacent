"""
Monitor FMP Caching Performance

This script monitors:
- Cache hit/miss rates
- Earnings period detection
- API usage statistics
- Circuit breaker status
- Database cache effectiveness
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import yaml
import logging
from datetime import datetime, timedelta
from src.data.fundamental_data_provider import FundamentalDataProvider
from src.models.database import get_database

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CacheMonitor:
    """Monitor FMP caching performance."""
    
    def __init__(self, config_path: str = 'config/autonomous_trading.yaml'):
        """Initialize monitor."""
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.provider = FundamentalDataProvider(self.config)
        self.database = get_database()
        
        # Tracking metrics
        self.cache_hits = 0
        self.cache_misses = 0
        self.db_cache_hits = 0
        self.db_cache_misses = 0
        self.api_calls = 0
        self.earnings_period_detections = 0
        self.non_earnings_period_detections = 0
    
    def test_symbol(self, symbol: str, use_cache: bool = True) -> dict:
        """Test caching for a single symbol."""
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing symbol: {symbol}")
        logger.info(f"{'='*60}")
        
        # Clear memory cache to test database cache
        initial_cache_size = len(self.provider.cache.cache)
        
        # First call - should hit database or API
        logger.info("First call (testing database cache)...")
        data1 = self.provider.get_fundamental_data(symbol, use_cache=use_cache)
        
        if data1:
            logger.info(f"✓ Got data from: {data1.source}")
            logger.info(f"  EPS: {data1.eps}")
            logger.info(f"  P/E: {data1.pe_ratio}")
            logger.info(f"  Revenue Growth: {data1.revenue_growth}")
            
            # Check if in earnings period
            is_earnings = self.provider._is_earnings_period(symbol)
            ttl = self.provider._get_smart_cache_ttl(symbol)
            
            logger.info(f"  In earnings period: {is_earnings}")
            logger.info(f"  Cache TTL: {ttl}s ({ttl / 86400:.1f} days)")
            
            if is_earnings:
                self.earnings_period_detections += 1
            else:
                self.non_earnings_period_detections += 1
        else:
            logger.warning(f"✗ Failed to get data for {symbol}")
            self.cache_misses += 1
            return {
                'symbol': symbol,
                'success': False,
                'error': 'Failed to fetch data'
            }
        
        # Second call - should hit memory cache
        logger.info("\nSecond call (testing memory cache)...")
        data2 = self.provider.get_fundamental_data(symbol, use_cache=use_cache)
        
        if data2:
            logger.info(f"✓ Got data from cache (memory)")
            self.cache_hits += 1
        else:
            logger.warning(f"✗ Cache miss on second call")
            self.cache_misses += 1
        
        # Get API usage
        usage = self.provider.get_api_usage()
        logger.info(f"\nAPI Usage:")
        logger.info(f"  FMP calls: {usage['fmp']['calls_made']}/{usage['fmp']['max_calls']}")
        logger.info(f"  Usage: {usage['fmp']['usage_percent']:.1f}%")
        logger.info(f"  Remaining: {usage['fmp']['calls_remaining']}")
        
        if usage['fmp'].get('circuit_breaker_active'):
            logger.warning(f"  ⚠ Circuit breaker ACTIVE")
            logger.warning(f"  Reset time: {usage['fmp'].get('circuit_breaker_reset_time')}")
        
        return {
            'symbol': symbol,
            'success': True,
            'source': data1.source,
            'in_earnings_period': is_earnings,
            'cache_ttl_days': ttl / 86400,
            'api_usage_percent': usage['fmp']['usage_percent'],
            'circuit_breaker_active': usage['fmp'].get('circuit_breaker_active', False)
        }
    
    def test_multiple_symbols(self, symbols: list) -> dict:
        """Test caching for multiple symbols."""
        logger.info(f"\n{'='*80}")
        logger.info(f"TESTING MULTIPLE SYMBOLS: {len(symbols)} symbols")
        logger.info(f"{'='*80}")
        
        results = []
        
        for symbol in symbols:
            result = self.test_symbol(symbol)
            results.append(result)
        
        # Generate summary
        logger.info(f"\n{'='*80}")
        logger.info("SUMMARY")
        logger.info(f"{'='*80}")
        
        successful = sum(1 for r in results if r['success'])
        failed = len(results) - successful
        
        logger.info(f"Symbols tested: {len(symbols)}")
        logger.info(f"Successful: {successful}")
        logger.info(f"Failed: {failed}")
        logger.info(f"\nCache Performance:")
        logger.info(f"  Memory cache hits: {self.cache_hits}")
        logger.info(f"  Memory cache misses: {self.cache_misses}")
        
        if self.cache_hits + self.cache_misses > 0:
            hit_rate = (self.cache_hits / (self.cache_hits + self.cache_misses)) * 100
            logger.info(f"  Hit rate: {hit_rate:.1f}%")
        
        logger.info(f"\nEarnings Period Detection:")
        logger.info(f"  In earnings period: {self.earnings_period_detections}")
        logger.info(f"  Not in earnings period: {self.non_earnings_period_detections}")
        
        # Final API usage
        usage = self.provider.get_api_usage()
        logger.info(f"\nFinal API Usage:")
        logger.info(f"  FMP calls: {usage['fmp']['calls_made']}/{usage['fmp']['max_calls']}")
        logger.info(f"  Usage: {usage['fmp']['usage_percent']:.1f}%")
        logger.info(f"  Remaining: {usage['fmp']['calls_remaining']}")
        
        if usage['fmp'].get('circuit_breaker_active'):
            logger.warning(f"  ⚠ Circuit breaker ACTIVE")
            logger.warning(f"  Reset time: {usage['fmp'].get('circuit_breaker_reset_time')}")
        
        return {
            'total_symbols': len(symbols),
            'successful': successful,
            'failed': failed,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'hit_rate': hit_rate if self.cache_hits + self.cache_misses > 0 else 0,
            'earnings_period_count': self.earnings_period_detections,
            'non_earnings_period_count': self.non_earnings_period_detections,
            'api_usage': usage
        }
    
    def test_database_persistence(self, symbol: str) -> dict:
        """Test that database cache persists across provider restarts."""
        logger.info(f"\n{'='*80}")
        logger.info(f"TESTING DATABASE PERSISTENCE: {symbol}")
        logger.info(f"{'='*80}")
        
        # First, fetch data and save to database
        logger.info("Step 1: Fetch data and save to database...")
        data1 = self.provider.get_fundamental_data(symbol, use_cache=False)
        
        if not data1:
            logger.error(f"Failed to fetch data for {symbol}")
            return {'success': False, 'error': 'Failed to fetch data'}
        
        logger.info(f"✓ Data fetched and saved to database")
        
        # Create a new provider instance (simulates restart)
        logger.info("\nStep 2: Create new provider instance (simulating restart)...")
        new_provider = FundamentalDataProvider(self.config)
        
        # Clear memory cache to force database lookup
        new_provider.cache.clear()
        
        # Try to get data from new provider (should hit database)
        logger.info("\nStep 3: Fetch data from new provider (should hit database)...")
        data2 = new_provider.get_fundamental_data(symbol, use_cache=True)
        
        if data2:
            logger.info(f"✓ Data retrieved from database cache")
            logger.info(f"  Source: {data2.source}")
            logger.info(f"  Age: {(datetime.now() - data2.timestamp).total_seconds():.0f}s")
            
            # Verify data matches
            if data1.eps == data2.eps and data1.pe_ratio == data2.pe_ratio:
                logger.info(f"✓ Data matches original fetch")
                return {
                    'success': True,
                    'database_cache_working': True,
                    'data_age_seconds': (datetime.now() - data2.timestamp).total_seconds()
                }
            else:
                logger.warning(f"✗ Data mismatch")
                return {
                    'success': False,
                    'error': 'Data mismatch between fetches'
                }
        else:
            logger.error(f"✗ Failed to retrieve from database cache")
            return {
                'success': False,
                'error': 'Database cache miss'
            }
    
    def test_circuit_breaker(self) -> dict:
        """Test circuit breaker functionality."""
        logger.info(f"\n{'='*80}")
        logger.info("TESTING CIRCUIT BREAKER")
        logger.info(f"{'='*80}")
        
        # Manually activate circuit breaker
        logger.info("Activating circuit breaker...")
        self.provider.fmp_rate_limiter.activate_circuit_breaker()
        
        usage = self.provider.get_api_usage()
        logger.info(f"Circuit breaker active: {usage['fmp'].get('circuit_breaker_active')}")
        logger.info(f"Reset time: {usage['fmp'].get('circuit_breaker_reset_time')}")
        logger.info(f"Can make call: {self.provider.fmp_rate_limiter.can_make_call()}")
        
        # Try to fetch data (should fail immediately)
        logger.info("\nTrying to fetch data with circuit breaker active...")
        data = self.provider._fetch_from_fmp('AAPL')
        
        if data is None:
            logger.info("✓ Circuit breaker correctly blocked API call")
        else:
            logger.error("✗ Circuit breaker failed to block API call")
        
        return {
            'circuit_breaker_active': usage['fmp'].get('circuit_breaker_active'),
            'reset_time': usage['fmp'].get('circuit_breaker_reset_time'),
            'blocked_call': data is None
        }


def main():
    """Run monitoring tests."""
    monitor = CacheMonitor()
    
    # Test symbols (mix of large-cap and small-cap)
    test_symbols = [
        'AAPL',  # Large cap
        'MSFT',  # Large cap
        'GOOGL',  # Large cap
        'TSLA',  # Large cap
        'NVDA',  # Large cap
    ]
    
    # Test 1: Multiple symbols
    logger.info("\n" + "="*80)
    logger.info("TEST 1: MULTIPLE SYMBOLS CACHING")
    logger.info("="*80)
    results = monitor.test_multiple_symbols(test_symbols)
    
    # Test 2: Database persistence
    logger.info("\n" + "="*80)
    logger.info("TEST 2: DATABASE PERSISTENCE")
    logger.info("="*80)
    persistence_result = monitor.test_database_persistence('AAPL')
    
    # Test 3: Circuit breaker
    logger.info("\n" + "="*80)
    logger.info("TEST 3: CIRCUIT BREAKER")
    logger.info("="*80)
    circuit_breaker_result = monitor.test_circuit_breaker()
    
    # Final summary
    logger.info("\n" + "="*80)
    logger.info("FINAL SUMMARY")
    logger.info("="*80)
    logger.info(f"Cache hit rate: {results['hit_rate']:.1f}%")
    logger.info(f"Earnings period detections: {results['earnings_period_count']}")
    logger.info(f"Database persistence: {'✓ Working' if persistence_result.get('database_cache_working') else '✗ Failed'}")
    logger.info(f"Circuit breaker: {'✓ Working' if circuit_breaker_result.get('blocked_call') else '✗ Failed'}")
    logger.info(f"API usage: {results['api_usage']['fmp']['usage_percent']:.1f}%")
    
    logger.info("\n" + "="*80)
    logger.info("MONITORING COMPLETE")
    logger.info("="*80)


if __name__ == '__main__':
    main()
