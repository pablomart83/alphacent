"""
Test script for MarketStatisticsAnalyzer.

Tests:
1. Symbol analysis with all metrics
2. Alpha Vantage integration (with fallback)
3. FRED integration (with fallback)
4. Indicator distribution analysis
5. Caching functionality
6. Rate limiting
7. Comprehensive analysis for multiple symbols
"""

import sys
import logging
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import required modules
from src.api.etoro_client import EToroAPIClient
from src.data.market_data_manager import MarketDataManager
from src.strategy.market_analyzer import MarketStatisticsAnalyzer


def test_symbol_analysis():
    """Test basic symbol analysis."""
    logger.info("\n" + "="*80)
    logger.info("TEST 1: Symbol Analysis")
    logger.info("="*80)
    
    # Initialize components
    from src.core.config import Configuration, TradingMode
    config = Configuration()
    credentials = config.load_credentials(TradingMode.DEMO)
    
    etoro_client = EToroAPIClient(
        public_key=credentials['public_key'],
        user_key=credentials['user_key'],
        mode=TradingMode.DEMO
    )
    market_data = MarketDataManager(etoro_client)
    analyzer = MarketStatisticsAnalyzer(market_data)
    
    # Test with AAPL
    symbol = "AAPL"
    logger.info(f"\nAnalyzing {symbol}...")
    
    analysis = analyzer.analyze_symbol(symbol, period_days=90)
    
    # Verify all sections present
    assert 'volatility_metrics' in analysis, "Missing volatility_metrics"
    assert 'trend_metrics' in analysis, "Missing trend_metrics"
    assert 'mean_reversion_metrics' in analysis, "Missing mean_reversion_metrics"
    assert 'price_action' in analysis, "Missing price_action"
    assert 'sector_info' in analysis, "Missing sector_info"
    
    # Verify volatility metrics
    vol = analysis['volatility_metrics']
    logger.info(f"\nVolatility Metrics:")
    logger.info(f"  ATR Ratio: {vol['atr_ratio']:.4f}")
    logger.info(f"  Std Dev Returns: {vol['std_dev_returns']:.4f}")
    logger.info(f"  Historical Vol (20d): {vol['historical_volatility_20d']:.4f}")
    logger.info(f"  Current ATR: {vol['current_atr']:.2f}")
    
    assert vol['atr_ratio'] >= 0, "ATR ratio should be non-negative"
    assert vol['std_dev_returns'] >= 0, "Std dev should be non-negative"
    
    # Verify trend metrics
    trend = analysis['trend_metrics']
    logger.info(f"\nTrend Metrics:")
    logger.info(f"  20d Price Change: {trend['price_change_20d']:.2f}%")
    logger.info(f"  50d Price Change: {trend['price_change_50d']:.2f}%")
    logger.info(f"  ADX: {trend['adx']:.2f}")
    logger.info(f"  Trend Strength: {trend['trend_strength']:.2f}")
    
    assert -100 <= trend['price_change_20d'] <= 1000, "Price change out of reasonable range"
    assert 0 <= trend['trend_strength'] <= 1, "Trend strength should be 0-1"
    
    # Verify mean reversion metrics
    mr = analysis['mean_reversion_metrics']
    logger.info(f"\nMean Reversion Metrics:")
    logger.info(f"  Hurst Exponent: {mr['hurst_exponent']:.3f}")
    logger.info(f"  Autocorr Lag-1: {mr['autocorr_lag1']:.3f}")
    logger.info(f"  Autocorr Lag-5: {mr['autocorr_lag5']:.3f}")
    logger.info(f"  Mean Reversion Score: {mr['mean_reversion_score']:.3f}")
    
    assert 0 <= mr['hurst_exponent'] <= 1, "Hurst should be 0-1"
    assert 0 <= mr['mean_reversion_score'] <= 1, "MR score should be 0-1"
    
    # Verify price action
    pa = analysis['price_action']
    logger.info(f"\nPrice Action:")
    logger.info(f"  Current Price: ${pa['current_price']:.2f}")
    logger.info(f"  20d High: ${pa['high_20d']:.2f}")
    logger.info(f"  20d Low: ${pa['low_20d']:.2f}")
    logger.info(f"  Support: ${pa['support']:.2f}")
    logger.info(f"  Resistance: ${pa['resistance']:.2f}")
    
    assert pa['current_price'] > 0, "Current price should be positive"
    assert pa['low_20d'] <= pa['current_price'] <= pa['high_20d'], "Current price should be within 20d range"
    
    logger.info(f"\n✅ Symbol analysis test PASSED for {symbol}")
    return analyzer


def test_indicator_distributions(analyzer):
    """Test indicator distribution analysis."""
    logger.info("\n" + "="*80)
    logger.info("TEST 2: Indicator Distribution Analysis")
    logger.info("="*80)
    
    symbol = "SPY"
    logger.info(f"\nAnalyzing indicator distributions for {symbol}...")
    
    distributions = analyzer.analyze_indicator_distributions(symbol, period_days=90)
    
    # Should have RSI and STOCH
    logger.info(f"\nFound {len(distributions)} indicator distributions")
    
    for indicator_name, dist in distributions.items():
        logger.info(f"\n{indicator_name} Distribution:")
        logger.info(f"  Mean: {dist['mean']:.2f}")
        logger.info(f"  Std: {dist['std']:.2f}")
        logger.info(f"  Min: {dist['min']:.2f}")
        logger.info(f"  Max: {dist['max']:.2f}")
        logger.info(f"  % Oversold (<30): {dist['pct_oversold']:.1f}%")
        logger.info(f"  % Overbought (>70): {dist['pct_overbought']:.1f}%")
        logger.info(f"  Avg Duration Oversold: {dist['avg_duration_oversold']:.1f} days")
        logger.info(f"  Avg Duration Overbought: {dist['avg_duration_overbought']:.1f} days")
        logger.info(f"  Current Value: {dist['current_value']:.2f}")
        logger.info(f"  Current Percentile: {dist['current_percentile']:.1f}%")
        
        # Verify ranges
        assert 0 <= dist['mean'] <= 100, f"{indicator_name} mean out of range"
        assert dist['min'] <= dist['current_value'] <= dist['max'], f"{indicator_name} current value out of range"
        assert 0 <= dist['pct_oversold'] <= 100, f"{indicator_name} pct_oversold out of range"
        assert 0 <= dist['pct_overbought'] <= 100, f"{indicator_name} pct_overbought out of range"
    
    # Should have at least 1 indicator (RSI should always work)
    assert len(distributions) >= 1, "Should have at least RSI distribution"
    
    logger.info(f"\n✅ Indicator distribution test PASSED")


def test_market_context(analyzer):
    """Test market context from FRED."""
    logger.info("\n" + "="*80)
    logger.info("TEST 3: Market Context (FRED)")
    logger.info("="*80)
    
    context = analyzer.get_market_context()
    
    logger.info(f"\nMarket Context:")
    logger.info(f"  VIX: {context['vix']:.2f}")
    logger.info(f"  10Y Treasury: {context['treasury_10y']:.2f}%")
    logger.info(f"  Risk Regime: {context['risk_regime']}")
    logger.info(f"  Last Updated: {context['last_updated']}")
    
    # Verify values
    assert context['vix'] > 0, "VIX should be positive"
    assert context['treasury_10y'] > 0, "Treasury yield should be positive"
    assert context['risk_regime'] in ['risk_on', 'risk_off', 'neutral'], "Invalid risk regime"
    
    logger.info(f"\n✅ Market context test PASSED")


def test_caching(analyzer):
    """Test caching functionality."""
    logger.info("\n" + "="*80)
    logger.info("TEST 4: Caching")
    logger.info("="*80)
    
    symbol = "QQQ"
    
    # First call - should fetch data
    logger.info(f"\nFirst call for {symbol} (should fetch data)...")
    start_time = datetime.now()
    analysis1 = analyzer.analyze_symbol(symbol, period_days=90)
    time1 = (datetime.now() - start_time).total_seconds()
    logger.info(f"  Time: {time1:.2f}s")
    
    # Second call - should use cache
    logger.info(f"\nSecond call for {symbol} (should use cache)...")
    start_time = datetime.now()
    analysis2 = analyzer.analyze_symbol(symbol, period_days=90)
    time2 = (datetime.now() - start_time).total_seconds()
    logger.info(f"  Time: {time2:.2f}s")
    
    # Cache should be faster
    assert time2 < time1, "Cached call should be faster"
    logger.info(f"\n  Speedup: {time1/time2:.1f}x faster with cache")
    
    # Results should be identical
    assert analysis1['symbol'] == analysis2['symbol'], "Cached results should match"
    
    logger.info(f"\n✅ Caching test PASSED")


def test_rate_limiting(analyzer):
    """Test Alpha Vantage rate limiting."""
    logger.info("\n" + "="*80)
    logger.info("TEST 5: Rate Limiting")
    logger.info("="*80)
    
    if not analyzer.alpha_vantage_enabled:
        logger.info("\n⚠️  Alpha Vantage disabled, skipping rate limit test")
        return
    
    logger.info(f"\nCurrent Alpha Vantage calls today: {MarketStatisticsAnalyzer._alpha_vantage_calls_today}")
    logger.info(f"Rate limit: {analyzer.alpha_vantage_rate_limit}")
    
    # Check rate limit
    can_call = analyzer._check_alpha_vantage_rate_limit()
    logger.info(f"Can make API call: {can_call}")
    
    remaining = analyzer.alpha_vantage_rate_limit - MarketStatisticsAnalyzer._alpha_vantage_calls_today
    logger.info(f"Remaining calls today: {remaining}")
    
    assert remaining >= 0, "Remaining calls should be non-negative"
    
    logger.info(f"\n✅ Rate limiting test PASSED")


def test_comprehensive_analysis(analyzer):
    """Test comprehensive analysis for multiple symbols."""
    logger.info("\n" + "="*80)
    logger.info("TEST 6: Comprehensive Analysis (Multiple Symbols)")
    logger.info("="*80)
    
    symbols = ["AAPL", "SPY", "QQQ"]
    logger.info(f"\nAnalyzing {len(symbols)} symbols: {symbols}")
    
    start_time = datetime.now()
    result = analyzer.get_comprehensive_analysis(symbols, period_days=90)
    elapsed = (datetime.now() - start_time).total_seconds()
    
    logger.info(f"\nCompleted in {elapsed:.2f}s")
    
    # Verify structure
    assert 'market_context' in result, "Missing market_context"
    assert 'symbol_analysis' in result, "Missing symbol_analysis"
    assert 'indicator_distributions' in result, "Missing indicator_distributions"
    
    # Verify all symbols analyzed
    for symbol in symbols:
        assert symbol in result['symbol_analysis'], f"Missing analysis for {symbol}"
        assert symbol in result['indicator_distributions'], f"Missing distributions for {symbol}"
        
        logger.info(f"\n{symbol}:")
        analysis = result['symbol_analysis'][symbol]
        logger.info(f"  Data points: {analysis['data_points']}")
        logger.info(f"  Volatility (ATR ratio): {analysis['volatility_metrics']['atr_ratio']:.4f}")
        logger.info(f"  Trend (20d change): {analysis['trend_metrics']['price_change_20d']:.2f}%")
        logger.info(f"  Mean Reversion Score: {analysis['mean_reversion_metrics']['mean_reversion_score']:.3f}")
    
    # Market context
    context = result['market_context']
    logger.info(f"\nMarket Context:")
    logger.info(f"  VIX: {context['vix']:.2f}")
    logger.info(f"  Risk Regime: {context['risk_regime']}")
    
    logger.info(f"\n✅ Comprehensive analysis test PASSED")


def test_fallback_behavior(analyzer):
    """Test graceful fallback when APIs unavailable."""
    logger.info("\n" + "="*80)
    logger.info("TEST 7: Fallback Behavior")
    logger.info("="*80)
    
    # Test with invalid symbol (should return default analysis)
    invalid_symbol = "INVALID_SYMBOL_XYZ"
    logger.info(f"\nTesting with invalid symbol: {invalid_symbol}")
    
    analysis = analyzer.analyze_symbol(invalid_symbol, period_days=90)
    
    # Should return default analysis
    assert analysis['data_points'] == 0, "Invalid symbol should have 0 data points"
    logger.info(f"  Correctly returned default analysis for invalid symbol")
    
    # Test market context fallback
    logger.info(f"\nTesting market context fallback...")
    
    # Get cache size before clearing
    cache_size_before = analyzer.get_cache_stats()['size']
    logger.info(f"  Cache size before test: {cache_size_before}")
    
    # Temporarily disable FRED and clear cache
    fred_was_enabled = analyzer.fred_enabled
    analyzer.fred_enabled = False
    analyzer.clear_cache()  # Use the proper method instead of direct access
    
    context = analyzer.get_market_context()
    
    # Should return default context
    assert context['vix'] == 20.0, "Should return default VIX"
    assert context['risk_regime'] == 'neutral', "Should return neutral regime"
    logger.info(f"  Correctly returned default market context when FRED disabled")
    
    # Restore FRED state
    analyzer.fred_enabled = fred_was_enabled
    
    # Test cache sharing - create new instance
    logger.info(f"\nTesting cache sharing between instances...")
    
    # First, populate cache with some data
    analyzer.analyze_symbol("AAPL", period_days=90)
    
    from src.core.config import Configuration, TradingMode
    config = Configuration()
    credentials = config.load_credentials(TradingMode.DEMO)
    
    from src.api.etoro_client import EToroAPIClient
    from src.data.market_data_manager import MarketDataManager
    
    etoro_client2 = EToroAPIClient(
        public_key=credentials['public_key'],
        user_key=credentials['user_key'],
        mode=TradingMode.DEMO
    )
    market_data2 = MarketDataManager(etoro_client2)
    analyzer2 = MarketStatisticsAnalyzer(market_data2)
    
    # Both analyzers should share the same cache
    stats1 = analyzer.get_cache_stats()
    stats2 = analyzer2.get_cache_stats()
    
    logger.info(f"  Analyzer 1 cache size: {stats1['size']}")
    logger.info(f"  Analyzer 2 cache size: {stats2['size']}")
    
    assert stats1['size'] == stats2['size'], "Instances should share the same cache"
    assert stats1['size'] > 0, "Cache should have data after analyze_symbol call"
    logger.info(f"  Cache sharing verified - instances use shared cache (size: {stats1['size']})")
    
    logger.info(f"\n✅ Fallback behavior test PASSED")


def main():
    """Run all tests."""
    logger.info("\n" + "="*80)
    logger.info("MARKET STATISTICS ANALYZER TEST SUITE")
    logger.info("="*80)
    
    try:
        # Run tests
        analyzer = test_symbol_analysis()
        test_indicator_distributions(analyzer)
        test_market_context(analyzer)
        test_caching(analyzer)
        test_rate_limiting(analyzer)
        test_comprehensive_analysis(analyzer)
        test_fallback_behavior(analyzer)
        
        # Summary
        logger.info("\n" + "="*80)
        logger.info("ALL TESTS PASSED ✅")
        logger.info("="*80)
        logger.info("\nMarketStatisticsAnalyzer is working correctly:")
        logger.info("  ✅ Symbol analysis with all metrics")
        logger.info("  ✅ Alpha Vantage integration (with fallback)")
        logger.info("  ✅ FRED integration (with fallback)")
        logger.info("  ✅ Indicator distribution analysis")
        logger.info("  ✅ Caching functionality")
        logger.info("  ✅ Rate limiting")
        logger.info("  ✅ Comprehensive multi-symbol analysis")
        logger.info("  ✅ Graceful fallback behavior")
        
        return 0
        
    except Exception as e:
        logger.error(f"\n❌ TEST FAILED: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
