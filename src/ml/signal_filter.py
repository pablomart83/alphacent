"""
ML Signal Filter - Uses Random Forest to filter trading signals.

Filters signals based on historical performance patterns using machine learning.
Only signals with ML confidence > threshold are traded.
"""

import logging
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

from src.models.dataclasses import TradingSignal, Strategy

logger = logging.getLogger(__name__)


@dataclass
class MLFilterResult:
    """Result from ML signal filtering."""
    passed: bool
    confidence: float  # 0.0 to 1.0
    features: Dict[str, float]
    model_version: str


class MLSignalFilter:
    """
    Machine learning signal filter using Random Forest.
    
    Predicts whether a trading signal will be profitable based on:
    - Technical indicators (RSI, MACD, volume)
    - Price vs moving averages
    - Sector momentum
    - Market regime
    - VIX level
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        database: Any,
        model_dir: str = "models/ml",
        market_analyzer: Optional[Any] = None
    ):
        """
        Initialize ML signal filter.
        
        Args:
            config: Configuration dictionary
            database: Database instance for logging
            model_dir: Directory to save/load models
            market_analyzer: Optional MarketStatisticsAnalyzer instance
        """
        self.config = config
        self.database = database
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.market_analyzer = market_analyzer
        
        # Get ML filter config
        ml_config = config.get('alpha_edge', {}).get('ml_filter', {})
        self.enabled = ml_config.get('enabled', True)
        self.min_confidence = ml_config.get('min_confidence', 0.70)
        self.retrain_frequency_days = ml_config.get('retrain_frequency_days', 30)
        
        # Model components
        self.model: Optional[RandomForestClassifier] = None
        self.scaler: Optional[StandardScaler] = None
        self.feature_names: List[str] = []
        self.model_version: str = "1.0.0"
        self.last_trained: Optional[datetime] = None
        
        # Try to load existing model
        self._load_model()
        
        logger.info(
            f"MLSignalFilter initialized - Enabled: {self.enabled}, "
            f"Min confidence: {self.min_confidence}"
        )
    
    def filter_signal(
        self,
        signal: TradingSignal,
        strategy: Strategy,
        market_data: Optional[Dict[str, Any]] = None
    ) -> MLFilterResult:
        """
        Filter a trading signal using ML model.
        
        Args:
            signal: Trading signal to filter
            strategy: Strategy that generated the signal
            market_data: Optional market data for feature extraction
            
        Returns:
            MLFilterResult with pass/fail and confidence
        """
        if not self.enabled:
            return MLFilterResult(
                passed=True,
                confidence=1.0,
                features={},
                model_version=self.model_version
            )
        
        if self.model is None or self.scaler is None:
            logger.warning("ML model not trained, passing signal by default")
            return MLFilterResult(
                passed=True,
                confidence=0.5,
                features={},
                model_version=self.model_version
            )
        
        try:
            # Extract features
            features = self._extract_features(signal, strategy, market_data)
            
            # Prepare feature vector
            feature_vector = self._prepare_feature_vector(features)
            
            # Scale features
            scaled_features = self.scaler.transform([feature_vector])
            
            # Predict probability
            probabilities = self.model.predict_proba(scaled_features)[0]
            confidence = probabilities[1]  # Probability of positive class
            
            # Check if passes threshold
            passed = confidence >= self.min_confidence
            
            logger.info(
                f"ML filter for {signal.symbol}: confidence={confidence:.3f}, "
                f"passed={passed} (threshold={self.min_confidence})"
            )
            
            result = MLFilterResult(
                passed=passed,
                confidence=confidence,
                features=features,
                model_version=self.model_version
            )
            
            # Log to database
            self._log_filter_result(signal, strategy, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error filtering signal: {e}", exc_info=True)
            # On error, pass signal by default
            return MLFilterResult(
                passed=True,
                confidence=0.5,
                features={},
                model_version=self.model_version
            )
    
    def _log_filter_result(self, signal: TradingSignal, strategy: Strategy, result: MLFilterResult) -> None:
        """Log ML filter result to database."""
        try:
            from src.models.orm import MLFilterLogORM
            from datetime import datetime
            
            log_entry = MLFilterLogORM(
                strategy_id=strategy.id,
                symbol=signal.symbol,
                signal_type=signal.signal_type.value,
                passed=result.passed,
                confidence=result.confidence,
                features=result.features,
                timestamp=datetime.now()
            )
            
            session = self.database.get_session()
            try:
                session.add(log_entry)
                session.commit()
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Failed to log ML filter result: {e}")
    
    def train_model(
        self,
        training_data: List[Dict[str, Any]],
        test_size: float = 0.2,
        random_state: int = 42
    ) -> Dict[str, float]:
        """
        Train Random Forest model on historical signals.
        
        Args:
            training_data: List of dicts with 'features' and 'label' keys
            test_size: Fraction of data to use for testing
            random_state: Random seed for reproducibility
            
        Returns:
            Dict with performance metrics
        """
        if len(training_data) < 50:
            raise ValueError(f"Need at least 50 samples to train, got {len(training_data)}")
        
        logger.info(f"Training ML model with {len(training_data)} samples")
        
        # Prepare data
        X = []
        y = []
        
        for sample in training_data:
            features = sample['features']
            label = sample['label']
            
            feature_vector = self._prepare_feature_vector(features)
            X.append(feature_vector)
            y.append(label)
        
        X = np.array(X)
        y = np.array(y)
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y
        )
        
        # Scale features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train Random Forest
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=random_state,
            n_jobs=-1
        )
        
        self.model.fit(X_train_scaled, y_train)
        
        # Evaluate
        y_pred = self.model.predict(X_test_scaled)
        
        metrics = {
            'accuracy': accuracy_score(y_test, y_pred),
            'precision': precision_score(y_test, y_pred, zero_division=0),
            'recall': recall_score(y_test, y_pred, zero_division=0),
            'f1': f1_score(y_test, y_pred, zero_division=0),
            'train_samples': len(X_train),
            'test_samples': len(X_test)
        }
        
        # Cross-validation
        cv_scores = cross_val_score(
            self.model, X_train_scaled, y_train, cv=5, scoring='f1'
        )
        metrics['cv_f1_mean'] = cv_scores.mean()
        metrics['cv_f1_std'] = cv_scores.std()
        
        self.last_trained = datetime.now()
        
        logger.info(
            f"Model trained - Accuracy: {metrics['accuracy']:.3f}, "
            f"Precision: {metrics['precision']:.3f}, "
            f"Recall: {metrics['recall']:.3f}, "
            f"F1: {metrics['f1']:.3f}"
        )
        
        # Save model
        self._save_model()
        
        return metrics
    
    def needs_retraining(self) -> bool:
        """Check if model needs retraining based on age."""
        if self.last_trained is None:
            return True
        
        days_since_training = (datetime.now() - self.last_trained).days
        return days_since_training >= self.retrain_frequency_days
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the current model.
        
        Returns:
            Dict with model metadata
        """
        return {
            'version': self.model_version,
            'last_trained': self.last_trained.isoformat() if self.last_trained else None,
            'days_since_training': (datetime.now() - self.last_trained).days if self.last_trained else None,
            'needs_retraining': self.needs_retraining(),
            'enabled': self.enabled,
            'min_confidence': self.min_confidence,
            'retrain_frequency_days': self.retrain_frequency_days,
            'feature_names': self.feature_names,
            'model_loaded': self.model is not None
        }
    
    def _extract_features(
        self,
        signal: TradingSignal,
        strategy: Strategy,
        market_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, float]:
        """
        Extract features from signal for ML prediction.
        
        Features:
        - RSI (14-period)
        - MACD signal
        - Volume ratio (current vs average)
        - Price vs 50-day MA
        - Price vs 200-day MA
        - Sector momentum
        - Market regime (encoded)
        - VIX level
        """
        features = {}
        
        # Get indicator values from signal
        indicators = signal.indicators or {}
        
        # Technical indicators
        features['rsi_14'] = indicators.get('rsi_14', 50.0)
        features['macd_signal'] = indicators.get('macd_signal', 0.0)
        features['volume_ratio'] = indicators.get('volume_ratio', 1.0)
        
        # Price vs moving averages
        features['price_vs_ma_50'] = indicators.get('price_vs_ma_50', 0.0)
        features['price_vs_ma_200'] = indicators.get('price_vs_ma_200', 0.0)
        
        # Sector momentum (if available)
        features['sector_momentum'] = indicators.get('sector_momentum', 0.0)
        
        # Market regime and VIX
        if self.market_analyzer:
            try:
                market_context = self.market_analyzer.get_market_context()
                regime = market_context.get('regime', 'unknown')
                vix = market_context.get('vix', 20.0)
                
                # Encode regime as numeric
                regime_map = {
                    'high_volatility': 1.0,
                    'low_volatility': 0.0,
                    'trending': 0.5,
                    'ranging': -0.5,
                    'unknown': 0.0
                }
                features['market_regime'] = regime_map.get(regime, 0.0)
                features['vix_level'] = vix
            except Exception as e:
                logger.warning(f"Error getting market context: {e}")
                features['market_regime'] = 0.0
                features['vix_level'] = 20.0
        else:
            features['market_regime'] = 0.0
            features['vix_level'] = 20.0
        
        return features
    
    def _prepare_feature_vector(self, features: Dict[str, float]) -> List[float]:
        """
        Prepare feature vector in consistent order.
        
        Args:
            features: Dict of feature name -> value
            
        Returns:
            List of feature values in consistent order
        """
        # Define feature order
        if not self.feature_names:
            self.feature_names = [
                'rsi_14',
                'macd_signal',
                'volume_ratio',
                'price_vs_ma_50',
                'price_vs_ma_200',
                'sector_momentum',
                'market_regime',
                'vix_level'
            ]
        
        # Extract values in order
        vector = []
        for name in self.feature_names:
            value = features.get(name, 0.0)
            vector.append(value)
        
        return vector
    
    def _save_model(self) -> None:
        """Save model and scaler to disk."""
        try:
            model_path = self.model_dir / "signal_filter_model.pkl"
            scaler_path = self.model_dir / "signal_filter_scaler.pkl"
            metadata_path = self.model_dir / "signal_filter_metadata.pkl"
            
            with open(model_path, 'wb') as f:
                pickle.dump(self.model, f)
            
            with open(scaler_path, 'wb') as f:
                pickle.dump(self.scaler, f)
            
            metadata = {
                'version': self.model_version,
                'last_trained': self.last_trained,
                'feature_names': self.feature_names,
                'min_confidence': self.min_confidence
            }
            
            with open(metadata_path, 'wb') as f:
                pickle.dump(metadata, f)
            
            logger.info(f"Model saved to {model_path}")
            
        except Exception as e:
            logger.error(f"Error saving model: {e}", exc_info=True)
    
    def _load_model(self) -> bool:
        """
        Load model and scaler from disk.
        
        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            model_path = self.model_dir / "signal_filter_model.pkl"
            scaler_path = self.model_dir / "signal_filter_scaler.pkl"
            metadata_path = self.model_dir / "signal_filter_metadata.pkl"
            
            if not model_path.exists() or not scaler_path.exists():
                logger.info("No saved model found")
                return False
            
            with open(model_path, 'rb') as f:
                self.model = pickle.load(f)
            
            with open(scaler_path, 'rb') as f:
                self.scaler = pickle.load(f)
            
            if metadata_path.exists():
                with open(metadata_path, 'rb') as f:
                    metadata = pickle.load(f)
                    self.model_version = metadata.get('version', '1.0.0')
                    self.last_trained = metadata.get('last_trained')
                    self.feature_names = metadata.get('feature_names', [])
            
            logger.info(f"Model loaded from {model_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading model: {e}", exc_info=True)
            return False
