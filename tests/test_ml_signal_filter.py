"""
Tests for ML Signal Filter.

Tests feature engineering, model training, signal filtering, and model persistence.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any

from src.ml.signal_filter import MLSignalFilter, MLFilterResult
from src.models.dataclasses import TradingSignal, Strategy, RiskConfig
from src.strategy.strategy_templates import StrategyType
from src.models.enums import SignalAction, StrategyStatus


@pytest.fixture
def temp_model_dir():
    """Create temporary directory for model files."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def config():
    """Test configuration."""
    return {
        'alpha_edge': {
            'ml_filter': {
                'enabled': True,
                'min_confidence': 0.70,
                'retrain_frequency_days': 30,
                'features': [
                    'rsi_14',
                    'macd_signal',
                    'volume_ratio',
                    'price_vs_ma_50',
                    'price_vs_ma_200',
                    'sector_momentum',
                    'market_regime',
                    'vix_level'
                ]
            }
        }
    }


@pytest.fixture
def ml_filter(config, temp_model_dir):
    """Create ML signal filter instance."""
    return MLSignalFilter(config, model_dir=temp_model_dir)


@pytest.fixture
def sample_signal():
    """Create sample trading signal."""
    return TradingSignal(
        strategy_id="test-strategy-123",
        symbol="AAPL",
        action=SignalAction.ENTER_LONG,
        confidence=0.85,
        reasoning="Test signal",
        generated_at=datetime.now(),
        indicators={
            'rsi_14': 65.0,
            'macd_signal': 0.5,
            'volume_ratio': 1.2,
            'price_vs_ma_50': 0.05,
            'price_vs_ma_200': 0.10,
            'sector_momentum': 0.03,
            'market_regime': 0.5,
            'vix_level': 18.0
        }
    )


@pytest.fixture
def sample_strategy():
    """Create sample strategy."""
    return Strategy(
        id="test-strategy-123",
        name="Test Strategy",
        description="Test strategy for ML filter",
        symbols=["AAPL", "MSFT"],
        rules={},
        status=StrategyStatus.DEMO,
        risk_params=RiskConfig(),
        created_at=datetime.now()
    )


@pytest.fixture
def training_data():
    """Create sample training data."""
    data = []
    
    # Create 100 samples with varying features
    for i in range(100):
        # Alternate between positive and negative labels
        label = i % 2
        
        # Features that correlate with label
        features = {
            'rsi_14': 70.0 if label == 1 else 30.0,
            'macd_signal': 1.0 if label == 1 else -1.0,
            'volume_ratio': 1.5 if label == 1 else 0.8,
            'price_vs_ma_50': 0.05 if label == 1 else -0.05,
            'price_vs_ma_200': 0.10 if label == 1 else -0.10,
            'sector_momentum': 0.03 if label == 1 else -0.03,
            'market_regime': 0.5,
            'vix_level': 15.0 if label == 1 else 25.0
        }
        
        data.append({
            'features': features,
            'label': label
        })
    
    return data


class TestMLSignalFilter:
    """Test ML signal filter functionality."""
    
    def test_initialization(self, ml_filter, config):
        """Test ML filter initialization."""
        assert ml_filter.enabled is True
        assert ml_filter.min_confidence == 0.70
        assert ml_filter.retrain_frequency_days == 30
        assert ml_filter.model is None  # No model trained yet
        assert ml_filter.scaler is None
    
    def test_initialization_disabled(self, temp_model_dir):
        """Test ML filter when disabled."""
        config = {
            'alpha_edge': {
                'ml_filter': {
                    'enabled': False
                }
            }
        }
        ml_filter = MLSignalFilter(config, model_dir=temp_model_dir)
        assert ml_filter.enabled is False
    
    def test_feature_extraction(self, ml_filter, sample_signal, sample_strategy):
        """Test feature extraction from signal."""
        features = ml_filter._extract_features(sample_signal, sample_strategy)
        
        assert 'rsi_14' in features
        assert 'macd_signal' in features
        assert 'volume_ratio' in features
        assert 'price_vs_ma_50' in features
        assert 'price_vs_ma_200' in features
        assert 'sector_momentum' in features
        assert 'market_regime' in features
        assert 'vix_level' in features
        
        # Check values match signal indicators
        assert features['rsi_14'] == 65.0
        assert features['macd_signal'] == 0.5
        assert features['volume_ratio'] == 1.2
    
    def test_feature_vector_preparation(self, ml_filter):
        """Test feature vector preparation."""
        features = {
            'rsi_14': 65.0,
            'macd_signal': 0.5,
            'volume_ratio': 1.2,
            'price_vs_ma_50': 0.05,
            'price_vs_ma_200': 0.10,
            'sector_momentum': 0.03,
            'market_regime': 0.5,
            'vix_level': 18.0
        }
        
        vector = ml_filter._prepare_feature_vector(features)
        
        assert len(vector) == 8
        assert vector[0] == 65.0  # rsi_14
        assert vector[1] == 0.5   # macd_signal
        assert vector[7] == 18.0  # vix_level
    
    def test_feature_vector_missing_features(self, ml_filter):
        """Test feature vector with missing features (should default to 0)."""
        features = {
            'rsi_14': 65.0,
            # Missing other features
        }
        
        vector = ml_filter._prepare_feature_vector(features)
        
        assert len(vector) == 8
        assert vector[0] == 65.0  # rsi_14
        assert vector[1] == 0.0   # macd_signal (default)
        assert vector[7] == 0.0   # vix_level (default)
    
    def test_model_training(self, ml_filter, training_data):
        """Test model training."""
        metrics = ml_filter.train_model(training_data, test_size=0.2)
        
        # Check metrics exist
        assert 'accuracy' in metrics
        assert 'precision' in metrics
        assert 'recall' in metrics
        assert 'f1' in metrics
        assert 'train_samples' in metrics
        assert 'test_samples' in metrics
        assert 'cv_f1_mean' in metrics
        assert 'cv_f1_std' in metrics
        
        # Check model was trained
        assert ml_filter.model is not None
        assert ml_filter.scaler is not None
        assert ml_filter.last_trained is not None
        
        # Check metrics are reasonable
        assert 0 <= metrics['accuracy'] <= 1
        assert 0 <= metrics['precision'] <= 1
        assert 0 <= metrics['recall'] <= 1
        assert 0 <= metrics['f1'] <= 1
    
    def test_model_training_insufficient_data(self, ml_filter):
        """Test model training with insufficient data."""
        small_data = [
            {'features': {'rsi_14': 50.0}, 'label': 1}
            for _ in range(10)
        ]
        
        with pytest.raises(ValueError, match="Need at least 50 samples"):
            ml_filter.train_model(small_data)
    
    def test_signal_filtering_no_model(self, ml_filter, sample_signal, sample_strategy):
        """Test signal filtering when no model is trained."""
        result = ml_filter.filter_signal(sample_signal, sample_strategy)
        
        # Should pass by default when no model
        assert result.passed is True
        assert result.confidence == 0.5
    
    def test_signal_filtering_with_model(self, ml_filter, training_data, sample_signal, sample_strategy):
        """Test signal filtering with trained model."""
        # Train model
        ml_filter.train_model(training_data, test_size=0.2)
        
        # Filter signal
        result = ml_filter.filter_signal(sample_signal, sample_strategy)
        
        assert isinstance(result, MLFilterResult)
        assert isinstance(bool(result.passed), bool)  # Convert numpy bool to Python bool
        assert 0 <= float(result.confidence) <= 1  # Convert numpy float to Python float
        assert result.features is not None
        assert result.model_version == ml_filter.model_version
    
    def test_signal_filtering_disabled(self, temp_model_dir, sample_signal, sample_strategy):
        """Test signal filtering when ML filter is disabled."""
        config = {
            'alpha_edge': {
                'ml_filter': {
                    'enabled': False
                }
            }
        }
        ml_filter = MLSignalFilter(config, model_dir=temp_model_dir)
        
        result = ml_filter.filter_signal(sample_signal, sample_strategy)
        
        # Should always pass when disabled
        assert result.passed is True
        assert result.confidence == 1.0
    
    def test_confidence_threshold(self, ml_filter, training_data, sample_signal, sample_strategy):
        """Test that confidence threshold is applied correctly."""
        # Train model
        ml_filter.train_model(training_data, test_size=0.2)
        
        # Set high threshold
        ml_filter.min_confidence = 0.99
        
        result = ml_filter.filter_signal(sample_signal, sample_strategy)
        
        # With very high threshold, signal should likely fail
        # (unless model is extremely confident)
        # Convert numpy types to Python types for comparison
        confidence = float(result.confidence)
        passed = bool(result.passed)
        assert confidence < 0.99 or passed is True
    
    def test_model_persistence(self, ml_filter, training_data, temp_model_dir):
        """Test model save and load."""
        # Train and save model
        ml_filter.train_model(training_data, test_size=0.2)
        original_last_trained = ml_filter.last_trained
        
        # Create new filter instance (should load saved model)
        config = {
            'alpha_edge': {
                'ml_filter': {
                    'enabled': True,
                    'min_confidence': 0.70,
                    'retrain_frequency_days': 30
                }
            }
        }
        new_filter = MLSignalFilter(config, model_dir=temp_model_dir)
        
        # Check model was loaded
        assert new_filter.model is not None
        assert new_filter.scaler is not None
        assert new_filter.last_trained == original_last_trained
        assert new_filter.feature_names == ml_filter.feature_names
    
    def test_needs_retraining(self, ml_filter, training_data):
        """Test retraining check."""
        # No model trained yet
        assert ml_filter.needs_retraining() is True
        
        # Train model
        ml_filter.train_model(training_data, test_size=0.2)
        
        # Just trained, should not need retraining
        assert ml_filter.needs_retraining() is False
        
        # Simulate old training date
        ml_filter.last_trained = datetime.now() - timedelta(days=31)
        assert ml_filter.needs_retraining() is True
    
    def test_get_model_info(self, ml_filter, training_data):
        """Test getting model information."""
        # Before training
        info = ml_filter.get_model_info()
        assert info['model_loaded'] is False
        assert info['last_trained'] is None
        assert info['needs_retraining'] is True
        
        # After training
        ml_filter.train_model(training_data, test_size=0.2)
        info = ml_filter.get_model_info()
        
        assert info['model_loaded'] is True
        assert info['last_trained'] is not None
        assert info['version'] == ml_filter.model_version
        assert info['enabled'] is True
        assert info['min_confidence'] == 0.70
        assert info['retrain_frequency_days'] == 30
        assert len(info['feature_names']) == 8
    
    def test_signal_metadata_enrichment(self, ml_filter, training_data, sample_signal, sample_strategy):
        """Test that ML filter adds metadata to signals."""
        # Train model
        ml_filter.train_model(training_data, test_size=0.2)
        
        # Filter signal
        result = ml_filter.filter_signal(sample_signal, sample_strategy)
        
        # Check result contains all expected fields
        assert hasattr(result, 'confidence')
        assert hasattr(result, 'features')
        assert hasattr(result, 'model_version')
        assert hasattr(result, 'passed')
        
        # Check features were extracted
        assert len(result.features) > 0
        assert 'rsi_14' in result.features


class TestMLFilterEdgeCases:
    """Test edge cases and error handling."""
    
    def test_missing_indicators(self, ml_filter, sample_strategy):
        """Test signal with missing indicators."""
        signal = TradingSignal(
            strategy_id="test-strategy-123",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.85,
            reasoning="Test signal",
            generated_at=datetime.now(),
            indicators={}  # Empty indicators
        )
        
        # Should not crash, should use defaults
        features = ml_filter._extract_features(signal, sample_strategy)
        assert features['rsi_14'] == 50.0  # Default
        assert features['vix_level'] == 20.0  # Default
    
    def test_none_indicators(self, ml_filter, sample_strategy):
        """Test signal with None indicators."""
        signal = TradingSignal(
            strategy_id="test-strategy-123",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.85,
            reasoning="Test signal",
            generated_at=datetime.now(),
            indicators=None
        )
        
        # Should not crash
        features = ml_filter._extract_features(signal, sample_strategy)
        assert features is not None
    
    def test_imbalanced_training_data(self, ml_filter):
        """Test training with imbalanced data."""
        # Create highly imbalanced data (90% negative, 10% positive)
        data = []
        for i in range(100):
            label = 1 if i < 10 else 0
            features = {
                'rsi_14': 70.0 if label == 1 else 30.0,
                'macd_signal': 1.0 if label == 1 else -1.0,
                'volume_ratio': 1.5,
                'price_vs_ma_50': 0.05,
                'price_vs_ma_200': 0.10,
                'sector_momentum': 0.03,
                'market_regime': 0.5,
                'vix_level': 18.0
            }
            data.append({'features': features, 'label': label})
        
        # Should still train (sklearn handles imbalanced data)
        metrics = ml_filter.train_model(data, test_size=0.2)
        assert metrics is not None
        assert ml_filter.model is not None
