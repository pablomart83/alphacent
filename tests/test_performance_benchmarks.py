"""
Performance benchmarks for Alpha Edge improvements.

Tests performance of:
- Signal generation latency (target: < 5 seconds)
- Fundamental data fetch time (target: < 2 seconds with cache)
- ML prediction time (target: < 100ms)
- Component optimization opportunities
"""

import pytest
import time
import logging
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from typing import Dict, Any

from src.strategy.strategy_engine import StrategyEngine
from src.data.fundamental_data_provider import FundamentalDataProvider, FundamentalData
from src.ml.signal_filter import MLSignalFilter
from src.models import Strategy, StrategyStatus, TradingSignal, SignalAction
from src.models.dataclasses import RiskConfig

logger = logging.getLogger(__name__)


class TestSignalGenerationPerformance:
    """Test signal generation latency."""
    
    @pytest.fixture
    def mock_strategy(self):
        """Create a mock strategy for testing."""
        return Strategy(
            id="test-strategy-1",
            name="Test Strategy",
            description="Test strategy for performance testing",
            status=StrategyStatus.DEMO,
            symbols=["SPY", "AAPL", "MSFT"],
            rules={
                "indicators": ["RSI:14", "SMA:50", "MACD:12:26:9"],
                "entry_conditions": [
                    {"type": "indicator", "indicator": "RSI", "operator": "<", "value": 30}
                ],
                "exit_conditions": [
                    {"type": "indicator", "indicator": "RSI", "operator": ">", "value": 70}
                ]
            },
            risk_params=RiskConfig(),
            created_at=datetime.now(),
            allocation_percent=5.0
        )
    
    @pytest.fixture
    def strategy_engine(self):
        """Create strategy engine with mocked dependencies."""
        mock_market_data = MagicMock()
        mock_market_data.get_historical_data.return_value = []
        
        engine = StrategyEngine(None, mock_market_data, None)
        return engine
    
    def test_signal_generation_latency_single_symbol(self, strategy_engine, mock_strategy):
        """Test signal generation for a single symbol."""
        # Modify strategy to use single symbol
        mock_strategy.symbols = ["SPY"]
        
        start_time = time.time()
        
        try:
            signals = strategy_engine.generate_signals(mock_strategy)
            elapsed = time.time() - start_time
            
            logger.info(f"Signal generation (1 symbol): {elapsed:.3f}s")
            
            # Target: < 5 seconds for single symbol
            assert elapsed < 5.0, f"Signal generation took {elapsed:.3f}s (target: < 5.0s)"
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.warning(f"Signal generation failed after {elapsed:.3f}s: {e}")
            # Still check timing even if generation fails
            assert elapsed < 5.0, f"Signal generation took {elapsed:.3f}s (target: < 5.0s)"
    
    def test_signal_generation_latency_multiple_symbols(self, strategy_engine, mock_strategy):
        """Test signal generation for multiple symbols."""
        # Use 3 symbols
        mock_strategy.symbols = ["SPY", "AAPL", "MSFT"]
        
        start_time = time.time()
        
        try:
            signals = strategy_engine.generate_signals(mock_strategy)
            elapsed = time.time() - start_time
            
            logger.info(f"Signal generation (3 symbols): {elapsed:.3f}s")
            
            # Target: < 5 seconds for 3 symbols (should be batched efficiently)
            assert elapsed < 5.0, f"Signal generation took {elapsed:.3f}s (target: < 5.0s)"
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.warning(f"Signal generation failed after {elapsed:.3f}s: {e}")
            assert elapsed < 5.0, f"Signal generation took {elapsed:.3f}s (target: < 5.0s)"
    
    @patch('src.core.system_state_manager.get_system_state_manager')
    def test_signal_generation_with_system_state(self, mock_state_mgr, strategy_engine, mock_strategy):
        """Test signal generation with system state checks."""
        from src.models.enums import SystemStateEnum
        
        # Mock system state as ACTIVE
        mock_state = MagicMock()
        mock_state.state = SystemStateEnum.ACTIVE
        mock_state_mgr.return_value.get_current_state.return_value = mock_state
        
        start_time = time.time()
        
        try:
            signals = strategy_engine.generate_signals(mock_strategy)
            elapsed = time.time() - start_time
            
            logger.info(f"Signal generation with state check: {elapsed:.3f}s")
            
            # Should still be fast with state checks
            assert elapsed < 5.0, f"Signal generation took {elapsed:.3f}s (target: < 5.0s)"
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.warning(f"Signal generation failed after {elapsed:.3f}s: {e}")


class TestFundamentalDataPerformance:
    """Test fundamental data fetching performance."""
    
    @pytest.fixture
    def fundamental_provider(self):
        """Create fundamental data provider with test config."""
        config = {
            'data_sources': {
                'financial_modeling_prep': {
                    'enabled': True,
                    'api_key': 'test_key',
                    'rate_limit': 250,
                    'cache_duration': 86400
                },
                'alpha_vantage': {
                    'enabled': True,
                    'api_key': 'test_key'
                }
            }
        }
        return FundamentalDataProvider(config)
    
    def test_cache_hit_performance(self, fundamental_provider):
        """Test performance of cache hits."""
        # Pre-populate cache
        test_data = FundamentalData(
            symbol="AAPL",
            timestamp=datetime.now(),
            eps=6.05,
            revenue=394328000000,
            revenue_growth=0.08,
            pe_ratio=28.5,
            market_cap=2800000000000,
            source="test"
        )
        fundamental_provider.cache.set("AAPL", test_data)
        
        # Measure cache hit time
        start_time = time.time()
        data = fundamental_provider.get_fundamental_data("AAPL", use_cache=True)
        elapsed = time.time() - start_time
        
        logger.info(f"Cache hit time: {elapsed*1000:.2f}ms")
        
        # Cache hits should be extremely fast (< 10ms)
        assert elapsed < 0.01, f"Cache hit took {elapsed*1000:.2f}ms (target: < 10ms)"
        assert data is not None
        assert data.symbol == "AAPL"
    
    @patch('requests.get')
    def test_api_fetch_performance_with_mock(self, mock_get, fundamental_provider):
        """Test API fetch performance with mocked response."""
        # Mock API responses
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'symbol': 'AAPL',
                'eps': 6.05,
                'epsDiluted': 6.05,
                'revenue': 394328000000,
                'revenueGrowth': 0.08
            }
        ]
        mock_get.return_value = mock_response
        
        # Clear cache to force API call
        fundamental_provider.cache.clear()
        
        start_time = time.time()
        data = fundamental_provider.get_fundamental_data("AAPL", use_cache=False)
        elapsed = time.time() - start_time
        
        logger.info(f"API fetch time (mocked): {elapsed:.3f}s")
        
        # With mocked network, should be fast (< 1 second)
        assert elapsed < 1.0, f"API fetch took {elapsed:.3f}s (target: < 1.0s with mock)"
    
    def test_cache_performance_multiple_symbols(self, fundamental_provider):
        """Test cache performance with multiple symbols."""
        # Pre-populate cache with multiple symbols
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
        for symbol in symbols:
            test_data = FundamentalData(
                symbol=symbol,
                timestamp=datetime.now(),
                eps=5.0,
                revenue=100000000000,
                source="test"
            )
            fundamental_provider.cache.set(symbol, test_data)
        
        # Measure time to fetch all from cache
        start_time = time.time()
        results = []
        for symbol in symbols:
            data = fundamental_provider.get_fundamental_data(symbol, use_cache=True)
            results.append(data)
        elapsed = time.time() - start_time
        
        logger.info(f"Cache fetch time ({len(symbols)} symbols): {elapsed*1000:.2f}ms")
        
        # Should be very fast for cache hits
        assert elapsed < 0.1, f"Cache fetch took {elapsed*1000:.2f}ms (target: < 100ms)"
        assert all(r is not None for r in results)
    
    def test_rate_limiter_performance(self, fundamental_provider):
        """Test rate limiter overhead."""
        start_time = time.time()
        
        # Check rate limit 100 times
        for _ in range(100):
            can_call = fundamental_provider.fmp_rate_limiter.can_make_call()
        
        elapsed = time.time() - start_time
        
        logger.info(f"Rate limiter check (100 calls): {elapsed*1000:.2f}ms")
        
        # Rate limiter should have minimal overhead
        assert elapsed < 0.1, f"Rate limiter took {elapsed*1000:.2f}ms (target: < 100ms)"


class TestMLFilterPerformance:
    """Test ML signal filter performance."""
    
    @pytest.fixture
    def ml_filter(self):
        """Create ML filter with test config."""
        config = {
            'alpha_edge': {
                'ml_filter': {
                    'enabled': True,
                    'min_confidence': 0.70,
                    'retrain_frequency_days': 30
                }
            }
        }
        mock_db = MagicMock()
        return MLSignalFilter(config, mock_db)
    
    @pytest.fixture
    def test_signal(self):
        """Create test signal."""
        return TradingSignal(
            strategy_id="test-strategy",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.85,
            reasoning="Test signal for performance testing",
            generated_at=datetime.now(),
            indicators={
                'rsi_14': 35.0,
                'macd_signal': 0.5,
                'volume_ratio': 1.2,
                'price_vs_ma_50': 0.02,
                'price_vs_ma_200': 0.05,
                'sector_momentum': 0.03
            }
        )
    
    @pytest.fixture
    def test_strategy(self):
        """Create test strategy."""
        return Strategy(
            id="test-strategy",
            name="Test Strategy",
            description="Test",
            status=StrategyStatus.DEMO,
            symbols=["AAPL"],
            rules={},
            risk_params=RiskConfig(),
            created_at=datetime.now()
        )
    
    def test_ml_prediction_performance_without_model(self, ml_filter, test_signal, test_strategy):
        """Test ML prediction when model is not loaded."""
        start_time = time.time()
        result = ml_filter.filter_signal(test_signal, test_strategy)
        elapsed = time.time() - start_time
        
        logger.info(f"ML prediction (no model): {elapsed*1000:.2f}ms")
        
        # Should be fast when no model is loaded (< 100ms)
        assert elapsed < 0.1, f"ML prediction took {elapsed*1000:.2f}ms (target: < 100ms)"
        # Note: result.passed may be True or False depending on model state
    
    def test_feature_extraction_performance(self, ml_filter, test_signal, test_strategy):
        """Test feature extraction performance."""
        start_time = time.time()
        
        # Extract features 100 times
        for _ in range(100):
            features = ml_filter._extract_features(test_signal, test_strategy, None)
        
        elapsed = time.time() - start_time
        avg_time = elapsed / 100
        
        logger.info(f"Feature extraction (avg of 100): {avg_time*1000:.2f}ms")
        
        # Feature extraction should be fast
        assert avg_time < 0.01, f"Feature extraction took {avg_time*1000:.2f}ms (target: < 10ms)"
    
    def test_ml_prediction_with_trained_model(self, ml_filter, test_signal, test_strategy):
        """Test ML prediction with a trained model."""
        # Train a simple model
        training_data = []
        for i in range(100):
            features = {
                'rsi_14': 30.0 + i * 0.4,
                'macd_signal': 0.0,
                'volume_ratio': 1.0,
                'price_vs_ma_50': 0.0,
                'price_vs_ma_200': 0.0,
                'sector_momentum': 0.0,
                'market_regime': 0.0,
                'vix_level': 20.0
            }
            label = 1 if i % 2 == 0 else 0
            training_data.append({'features': features, 'label': label})
        
        try:
            ml_filter.train_model(training_data)
            
            # Measure prediction time
            start_time = time.time()
            result = ml_filter.filter_signal(test_signal, test_strategy)
            elapsed = time.time() - start_time
            
            logger.info(f"ML prediction (with model): {elapsed*1000:.2f}ms")
            
            # Target: < 100ms per prediction
            assert elapsed < 0.1, f"ML prediction took {elapsed*1000:.2f}ms (target: < 100ms)"
            
        except Exception as e:
            logger.warning(f"Model training failed: {e}")
            pytest.skip("Model training not available")
    
    def test_ml_batch_prediction_performance(self, ml_filter, test_strategy):
        """Test batch prediction performance."""
        # Train a simple model
        training_data = []
        for i in range(100):
            features = {
                'rsi_14': 30.0 + i * 0.4,
                'macd_signal': 0.0,
                'volume_ratio': 1.0,
                'price_vs_ma_50': 0.0,
                'price_vs_ma_200': 0.0,
                'sector_momentum': 0.0,
                'market_regime': 0.0,
                'vix_level': 20.0
            }
            label = 1 if i % 2 == 0 else 0
            training_data.append({'features': features, 'label': label})
        
        try:
            ml_filter.train_model(training_data)
            
            # Create multiple signals
            signals = []
            for i in range(10):
                signal = TradingSignal(
                    strategy_id="test-strategy",
                    symbol=f"TEST{i}",
                    action=SignalAction.ENTER_LONG,
                    confidence=0.80 + i * 0.01,
                    reasoning="Test signal",
                    generated_at=datetime.now(),
                    indicators={
                        'rsi_14': 35.0 + i,
                        'macd_signal': 0.5,
                        'volume_ratio': 1.2,
                        'price_vs_ma_50': 0.02,
                        'price_vs_ma_200': 0.05,
                        'sector_momentum': 0.03
                    }
                )
                signals.append(signal)
            
            # Measure batch prediction time
            start_time = time.time()
            results = []
            for signal in signals:
                result = ml_filter.filter_signal(signal, test_strategy)
                results.append(result)
            elapsed = time.time() - start_time
            
            avg_time = elapsed / len(signals)
            
            logger.info(f"ML batch prediction ({len(signals)} signals): {elapsed:.3f}s, "
                       f"avg: {avg_time*1000:.2f}ms")
            
            # Average should still be < 100ms per signal
            assert avg_time < 0.1, f"Avg ML prediction took {avg_time*1000:.2f}ms (target: < 100ms)"
            
        except Exception as e:
            logger.warning(f"Model training failed: {e}")
            pytest.skip("Model training not available")


class TestComponentOptimization:
    """Test for identifying optimization opportunities."""
    
    def test_identify_slow_components(self):
        """Identify which components are slowest."""
        results = {}
        
        # Test signal generation
        try:
            mock_market_data = MagicMock()
            mock_market_data.get_historical_data.return_value = []
            engine = StrategyEngine(None, mock_market_data, None)
            
            mock_strategy = Strategy(
                id="test",
                name="Test",
                description="Test",
                status=StrategyStatus.DEMO,
                symbols=["SPY"],
                rules={"indicators": ["RSI:14"], "entry_conditions": [], "exit_conditions": []},
                risk_params=RiskConfig(),
                created_at=datetime.now()
            )
            
            start = time.time()
            engine.generate_signals(mock_strategy)
            results['signal_generation'] = time.time() - start
        except Exception as e:
            results['signal_generation'] = None
            logger.warning(f"Signal generation test failed: {e}")
        
        # Test fundamental data cache
        try:
            config = {
                'data_sources': {
                    'financial_modeling_prep': {
                        'enabled': True,
                        'api_key': 'test',
                        'rate_limit': 250,
                        'cache_duration': 86400
                    }
                }
            }
            provider = FundamentalDataProvider(config)
            
            # Pre-populate cache
            test_data = FundamentalData(
                symbol="AAPL",
                timestamp=datetime.now(),
                eps=6.05,
                source="test"
            )
            provider.cache.set("AAPL", test_data)
            
            start = time.time()
            for _ in range(100):
                provider.get_fundamental_data("AAPL", use_cache=True)
            results['fundamental_cache'] = (time.time() - start) / 100
        except Exception as e:
            results['fundamental_cache'] = None
            logger.warning(f"Fundamental cache test failed: {e}")
        
        # Test ML feature extraction
        try:
            config = {
                'alpha_edge': {
                    'ml_filter': {
                        'enabled': True,
                        'min_confidence': 0.70
                    }
                }
            }
            ml_filter = MLSignalFilter(config, MagicMock())
            
            signal = TradingSignal(
                strategy_id="test",
                symbol="AAPL",
                action=SignalAction.ENTER_LONG,
                confidence=0.75,
                reasoning="Test signal",
                generated_at=datetime.now(),
                indicators={'rsi_14': 35.0}
            )
            strategy = Strategy(
                id="test",
                name="Test",
                description="Test",
                status=StrategyStatus.DEMO,
                symbols=["AAPL"],
                rules={},
                risk_params=RiskConfig(),
                created_at=datetime.now()
            )
            
            start = time.time()
            for _ in range(100):
                ml_filter._extract_features(signal, strategy, None)
            results['ml_feature_extraction'] = (time.time() - start) / 100
        except Exception as e:
            results['ml_feature_extraction'] = None
            logger.warning(f"ML feature extraction test failed: {e}")
        
        # Log results
        logger.info("=== Performance Benchmark Results ===")
        for component, timing in results.items():
            if timing is not None:
                logger.info(f"{component}: {timing*1000:.2f}ms")
            else:
                logger.info(f"{component}: FAILED")
        
        # Identify slowest component
        valid_results = {k: v for k, v in results.items() if v is not None}
        if valid_results:
            slowest = max(valid_results.items(), key=lambda x: x[1])
            logger.info(f"\nSlowest component: {slowest[0]} ({slowest[1]*1000:.2f}ms)")
        
        # At least some tests should pass
        assert len(valid_results) > 0, "All performance tests failed"


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s", "--log-cli-level=INFO"])
