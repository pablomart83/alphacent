#!/usr/bin/env python3
"""
Script to retrain ML signal filter model with new data.

This script should be run monthly (or as configured) to retrain the ML model
with the latest trading data. It:
1. Fetches historical signals and their outcomes from the database
2. Labels signals based on whether the stock went up >5% in 30 days
3. Trains a new Random Forest model
4. Evaluates performance and saves the model

Usage:
    python scripts/retrain_ml_model.py [--min-samples 100] [--test-size 0.2]
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ml.signal_filter import MLSignalFilter
from src.models.database import Database
from src.data.market_data_manager import MarketDataManager
import yaml

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file."""
    config_path = Path("config/autonomous_trading.yaml")
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def fetch_historical_signals(
    database: Database,
    lookback_days: int = 180
) -> List[Dict[str, Any]]:
    """
    Fetch historical signals from database.
    
    Args:
        database: Database instance
        lookback_days: How many days back to fetch signals
        
    Returns:
        List of signal records with metadata
    """
    logger.info(f"Fetching signals from last {lookback_days} days")
    
    cutoff_date = datetime.now() - timedelta(days=lookback_days)
    
    with database.get_session() as session:
        # Query signals from database
        # Note: This assumes you have a signals table - adjust as needed
        query = """
            SELECT 
                symbol,
                timestamp,
                signal_type,
                confidence,
                indicators,
                strategy_id
            FROM signals
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
        """
        
        result = session.execute(query, (cutoff_date,))
        signals = []
        
        for row in result:
            signals.append({
                'symbol': row[0],
                'timestamp': row[1],
                'signal_type': row[2],
                'confidence': row[3],
                'indicators': row[4],
                'strategy_id': row[5]
            })
    
    logger.info(f"Fetched {len(signals)} historical signals")
    return signals


def label_signals(
    signals: List[Dict[str, Any]],
    market_data: MarketDataManager,
    profit_threshold: float = 0.05,
    holding_period_days: int = 30
) -> List[Dict[str, Any]]:
    """
    Label signals based on future price movement.
    
    A signal is labeled as 1 (positive) if the stock went up >profit_threshold
    within holding_period_days, otherwise 0 (negative).
    
    Args:
        signals: List of historical signals
        market_data: Market data manager for fetching prices
        profit_threshold: Minimum profit to label as positive (default 5%)
        holding_period_days: Days to hold before checking outcome
        
    Returns:
        List of labeled training samples with features and labels
    """
    logger.info(f"Labeling signals (threshold: {profit_threshold*100}%, period: {holding_period_days} days)")
    
    training_data = []
    labeled_count = 0
    skipped_count = 0
    
    for signal in signals:
        try:
            symbol = signal['symbol']
            entry_date = signal['timestamp']
            exit_date = entry_date + timedelta(days=holding_period_days)
            
            # Skip signals that are too recent (no outcome yet)
            if exit_date > datetime.now():
                skipped_count += 1
                continue
            
            # Fetch price data
            price_data = market_data.get_historical_data(
                symbol,
                entry_date - timedelta(days=1),
                exit_date + timedelta(days=1),
                interval="1d",
                prefer_yahoo=True
            )
            
            if not price_data or len(price_data) < 2:
                skipped_count += 1
                continue
            
            # Get entry and exit prices
            entry_price = price_data[0].close
            exit_price = price_data[-1].close
            
            # Calculate return
            returns = (exit_price - entry_price) / entry_price
            
            # Label: 1 if profitable, 0 otherwise
            label = 1 if returns >= profit_threshold else 0
            
            # Extract features from signal indicators
            import json
            indicators = json.loads(signal['indicators']) if isinstance(signal['indicators'], str) else signal['indicators']
            
            features = {
                'rsi_14': indicators.get('rsi_14', 50.0),
                'macd_signal': indicators.get('macd_signal', 0.0),
                'volume_ratio': indicators.get('volume_ratio', 1.0),
                'price_vs_ma_50': indicators.get('price_vs_ma_50', 0.0),
                'price_vs_ma_200': indicators.get('price_vs_ma_200', 0.0),
                'sector_momentum': indicators.get('sector_momentum', 0.0),
                'market_regime': indicators.get('market_regime', 0.0),
                'vix_level': indicators.get('vix_level', 20.0)
            }
            
            training_data.append({
                'features': features,
                'label': label,
                'symbol': symbol,
                'entry_date': entry_date,
                'returns': returns
            })
            
            labeled_count += 1
            
        except Exception as e:
            logger.warning(f"Error labeling signal for {signal.get('symbol')}: {e}")
            skipped_count += 1
            continue
    
    logger.info(
        f"Labeled {labeled_count} signals, skipped {skipped_count} "
        f"(positive: {sum(1 for d in training_data if d['label'] == 1)}, "
        f"negative: {sum(1 for d in training_data if d['label'] == 0)})"
    )
    
    return training_data


def main():
    """Main retraining script."""
    parser = argparse.ArgumentParser(description='Retrain ML signal filter model')
    parser.add_argument(
        '--min-samples',
        type=int,
        default=100,
        help='Minimum number of samples required for training (default: 100)'
    )
    parser.add_argument(
        '--test-size',
        type=float,
        default=0.2,
        help='Fraction of data to use for testing (default: 0.2)'
    )
    parser.add_argument(
        '--lookback-days',
        type=int,
        default=180,
        help='Days of historical signals to fetch (default: 180)'
    )
    parser.add_argument(
        '--profit-threshold',
        type=float,
        default=0.05,
        help='Profit threshold for positive label (default: 0.05 = 5%%)'
    )
    parser.add_argument(
        '--holding-period',
        type=int,
        default=30,
        help='Holding period in days for outcome evaluation (default: 30)'
    )
    
    args = parser.parse_args()
    
    try:
        # Load config
        logger.info("Loading configuration")
        config = load_config()
        
        # Initialize components
        logger.info("Initializing database and market data manager")
        database = Database()
        market_data = MarketDataManager()
        
        # Fetch historical signals
        signals = fetch_historical_signals(database, args.lookback_days)
        
        if len(signals) < args.min_samples:
            logger.error(
                f"Not enough signals for training: {len(signals)} < {args.min_samples}. "
                f"Need more historical data."
            )
            return 1
        
        # Label signals
        training_data = label_signals(
            signals,
            market_data,
            args.profit_threshold,
            args.holding_period
        )
        
        if len(training_data) < args.min_samples:
            logger.error(
                f"Not enough labeled samples: {len(training_data)} < {args.min_samples}. "
                f"Many signals may be too recent or have missing data."
            )
            return 1
        
        # Initialize ML filter
        logger.info("Initializing ML signal filter")
        ml_filter = MLSignalFilter(config)
        
        # Check if retraining is needed
        if not ml_filter.needs_retraining():
            logger.info(
                f"Model was trained recently ({ml_filter.last_trained}). "
                f"Retraining anyway as requested."
            )
        
        # Train model
        logger.info(f"Training model with {len(training_data)} samples")
        metrics = ml_filter.train_model(training_data, test_size=args.test_size)
        
        # Log results
        logger.info("=" * 60)
        logger.info("MODEL TRAINING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Training samples: {metrics['train_samples']}")
        logger.info(f"Test samples: {metrics['test_samples']}")
        logger.info(f"Accuracy: {metrics['accuracy']:.3f}")
        logger.info(f"Precision: {metrics['precision']:.3f}")
        logger.info(f"Recall: {metrics['recall']:.3f}")
        logger.info(f"F1 Score: {metrics['f1']:.3f}")
        logger.info(f"CV F1 Mean: {metrics['cv_f1_mean']:.3f} ± {metrics['cv_f1_std']:.3f}")
        logger.info("=" * 60)
        
        # Performance check
        if metrics['f1'] < 0.5:
            logger.warning(
                f"Model F1 score ({metrics['f1']:.3f}) is below 0.5. "
                f"Consider collecting more data or adjusting features."
            )
        
        logger.info("Model saved successfully. Retraining complete!")
        return 0
        
    except Exception as e:
        logger.error(f"Error during retraining: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
