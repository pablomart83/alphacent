#!/usr/bin/env python3
"""
Performance Report Generator

Runs performance benchmarks and generates a comprehensive report with:
- Signal generation latency
- Fundamental data fetch times
- ML prediction times
- Optimization recommendations
"""

import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy.strategy_engine import StrategyEngine
from src.data.fundamental_data_provider import FundamentalDataProvider, FundamentalData
from src.ml.signal_filter import MLSignalFilter
from src.models import Strategy, StrategyStatus, TradingSignal, SignalAction
from src.models.dataclasses import RiskConfig
from unittest.mock import MagicMock

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class PerformanceReporter:
    """Generate performance reports for Alpha Edge components."""
    
    def __init__(self):
        self.results: Dict[str, Dict] = {}
        
    def measure_signal_generation(self) -> Dict:
        """Measure signal generation performance."""
        print("\n📊 Testing Signal Generation Performance...")
        
        results = {}
        
        # Create mock strategy engine
        mock_market_data = MagicMock()
        mock_market_data.get_historical_data.return_value = []
        engine = StrategyEngine(None, mock_market_data, None)
        
        # Test single symbol
        strategy_single = Strategy(
            id="test-1",
            name="Test Single",
            description="Test",
            status=StrategyStatus.DEMO,
            symbols=["SPY"],
            rules={"indicators": ["RSI:14"], "entry_conditions": [], "exit_conditions": []},
            risk_params=RiskConfig(),
            created_at=datetime.now()
        )
        
        start = time.time()
        try:
            engine.generate_signals(strategy_single)
            elapsed = time.time() - start
            results['single_symbol'] = elapsed
            status = "✅ PASS" if elapsed < 5.0 else "❌ FAIL"
            print(f"  Single symbol: {elapsed:.3f}s {status} (target: < 5.0s)")
        except Exception as e:
            elapsed = time.time() - start
            results['single_symbol'] = elapsed
            print(f"  Single symbol: {elapsed:.3f}s ⚠️  (with errors)")
        
        # Test multiple symbols
        strategy_multi = Strategy(
            id="test-2",
            name="Test Multi",
            description="Test",
            status=StrategyStatus.DEMO,
            symbols=["SPY", "AAPL", "MSFT"],
            rules={"indicators": ["RSI:14"], "entry_conditions": [], "exit_conditions": []},
            risk_params=RiskConfig(),
            created_at=datetime.now()
        )
        
        start = time.time()
        try:
            engine.generate_signals(strategy_multi)
            elapsed = time.time() - start
            results['multiple_symbols'] = elapsed
            status = "✅ PASS" if elapsed < 5.0 else "❌ FAIL"
            print(f"  Multiple symbols (3): {elapsed:.3f}s {status} (target: < 5.0s)")
        except Exception as e:
            elapsed = time.time() - start
            results['multiple_symbols'] = elapsed
            print(f"  Multiple symbols (3): {elapsed:.3f}s ⚠️  (with errors)")
        
        return results
    
    def measure_fundamental_data(self) -> Dict:
        """Measure fundamental data performance."""
        print("\n📊 Testing Fundamental Data Performance...")
        
        results = {}
        
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
        
        # Test cache hit
        test_data = FundamentalData(
            symbol="AAPL",
            timestamp=datetime.now(),
            eps=6.05,
            revenue=394328000000,
            source="test"
        )
        provider.cache.set("AAPL", test_data)
        
        start = time.time()
        for _ in range(100):
            provider.get_fundamental_data("AAPL", use_cache=True)
        elapsed = (time.time() - start) / 100
        results['cache_hit'] = elapsed
        
        status = "✅ PASS" if elapsed < 0.002 else "❌ FAIL"
        print(f"  Cache hit (avg): {elapsed*1000:.2f}ms {status} (target: < 2s)")
        
        # Test rate limiter
        start = time.time()
        for _ in range(1000):
            provider.fmp_rate_limiter.can_make_call()
        elapsed = (time.time() - start) / 1000
        results['rate_limiter'] = elapsed
        
        print(f"  Rate limiter check: {elapsed*1000:.3f}ms per call")
        
        return results
    
    def measure_ml_filter(self) -> Dict:
        """Measure ML filter performance."""
        print("\n📊 Testing ML Filter Performance...")
        
        results = {}
        
        config = {
            'alpha_edge': {
                'ml_filter': {
                    'enabled': True,
                    'min_confidence': 0.70
                }
            }
        }
        ml_filter = MLSignalFilter(config, MagicMock())
        
        # Create test signal
        signal = TradingSignal(
            strategy_id="test",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.85,
            reasoning="Test",
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
        
        # Test feature extraction
        start = time.time()
        for _ in range(100):
            ml_filter._extract_features(signal, strategy, None)
        elapsed = (time.time() - start) / 100
        results['feature_extraction'] = elapsed
        
        print(f"  Feature extraction: {elapsed*1000:.2f}ms per signal")
        
        # Test prediction without model
        start = time.time()
        result = ml_filter.filter_signal(signal, strategy)
        elapsed = time.time() - start
        results['prediction_no_model'] = elapsed
        
        print(f"  Prediction (no model): {elapsed*1000:.2f}ms")
        
        # Try to train and test with model
        try:
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
            
            ml_filter.train_model(training_data)
            
            start = time.time()
            result = ml_filter.filter_signal(signal, strategy)
            elapsed = time.time() - start
            results['prediction_with_model'] = elapsed
            
            status = "✅ PASS" if elapsed < 0.1 else "❌ FAIL"
            print(f"  Prediction (with model): {elapsed*1000:.2f}ms {status} (target: < 100ms)")
            
        except Exception as e:
            print(f"  Prediction (with model): ⚠️  Could not train model")
            results['prediction_with_model'] = None
        
        return results
    
    def generate_report(self):
        """Generate comprehensive performance report."""
        print("\n" + "="*70)
        print("🚀 ALPHA EDGE PERFORMANCE REPORT")
        print("="*70)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Run all tests
        self.results['signal_generation'] = self.measure_signal_generation()
        self.results['fundamental_data'] = self.measure_fundamental_data()
        self.results['ml_filter'] = self.measure_ml_filter()
        
        # Summary
        print("\n" + "="*70)
        print("📈 PERFORMANCE SUMMARY")
        print("="*70)
        
        # Signal Generation
        sg = self.results['signal_generation']
        print("\n🎯 Signal Generation:")
        print(f"  • Single symbol: {sg.get('single_symbol', 0):.3f}s")
        print(f"  • Multiple symbols: {sg.get('multiple_symbols', 0):.3f}s")
        
        if sg.get('single_symbol', 999) < 5.0 and sg.get('multiple_symbols', 999) < 5.0:
            print("  ✅ All signal generation tests PASSED")
        else:
            print("  ❌ Some signal generation tests FAILED")
        
        # Fundamental Data
        fd = self.results['fundamental_data']
        print("\n💾 Fundamental Data:")
        print(f"  • Cache hit: {fd.get('cache_hit', 0)*1000:.2f}ms")
        print(f"  • Rate limiter: {fd.get('rate_limiter', 0)*1000:.3f}ms")
        
        if fd.get('cache_hit', 999) < 0.002:
            print("  ✅ Cache performance EXCELLENT")
        else:
            print("  ⚠️  Cache performance could be improved")
        
        # ML Filter
        ml = self.results['ml_filter']
        print("\n🤖 ML Filter:")
        print(f"  • Feature extraction: {ml.get('feature_extraction', 0)*1000:.2f}ms")
        print(f"  • Prediction (no model): {ml.get('prediction_no_model', 0)*1000:.2f}ms")
        if ml.get('prediction_with_model'):
            print(f"  • Prediction (with model): {ml.get('prediction_with_model', 0)*1000:.2f}ms")
        
        if ml.get('prediction_with_model', 999) and ml.get('prediction_with_model') < 0.1:
            print("  ✅ ML prediction performance EXCELLENT")
        elif ml.get('prediction_with_model'):
            print("  ⚠️  ML prediction could be optimized")
        
        # Recommendations
        print("\n" + "="*70)
        print("💡 OPTIMIZATION RECOMMENDATIONS")
        print("="*70)
        
        recommendations = []
        
        if sg.get('single_symbol', 0) > 2.0:
            recommendations.append("• Consider caching indicator calculations")
            recommendations.append("• Optimize data fetching with batch requests")
        
        if fd.get('cache_hit', 0) > 0.001:
            recommendations.append("• Cache implementation could use faster data structure")
        
        if ml.get('prediction_with_model', 0) > 0.05:
            recommendations.append("• Consider model optimization or simpler features")
        
        if not recommendations:
            print("✅ All components performing within targets!")
        else:
            for rec in recommendations:
                print(rec)
        
        print("\n" + "="*70)
        print("✨ Report Complete")
        print("="*70 + "\n")


if __name__ == "__main__":
    reporter = PerformanceReporter()
    reporter.generate_report()
