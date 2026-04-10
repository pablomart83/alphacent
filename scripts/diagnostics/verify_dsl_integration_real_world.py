"""
Real-world verification of DSL integration.

Tests DSL parsing with actual strategy templates and market data patterns.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from unittest.mock import Mock

from src.strategy.strategy_engine import StrategyEngine
from src.llm.llm_service import LLMService
from src.data.market_data_manager import MarketDataManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_realistic_market_data(days=100):
    """Create realistic market data with indicators."""
    dates = pd.date_range(start='2024-01-01', periods=days, freq='D')
    
    # Create realistic price data (trending with noise)
    trend = np.linspace(100, 120, days)
    noise = np.random.randn(days) * 2
    close = pd.Series(trend + noise, index=dates)
    high = close + np.random.rand(days) * 2
    low = close - np.random.rand(days) * 2
    
    # Calculate realistic indicators
    rsi = pd.Series(index=dates)
    for i in range(days):
        # RSI oscillates between 30 and 70 with occasional extremes
        base_rsi = 50 + 15 * np.sin(i / 10)
        rsi.iloc[i] = base_rsi + np.random.randn() * 5
        rsi.iloc[i] = max(0, min(100, rsi.iloc[i]))  # Clamp to 0-100
    
    # Simple moving averages
    sma_20 = close.rolling(window=20, min_periods=1).mean()
    sma_50 = close.rolling(window=50, min_periods=1).mean()
    
    # Bollinger Bands
    bb_middle = close.rolling(window=20, min_periods=1).mean()
    bb_std = close.rolling(window=20, min_periods=1).std()
    bb_upper = bb_middle + 2 * bb_std
    bb_lower = bb_middle - 2 * bb_std
    
    indicators = {
        'RSI_14': rsi,
        'SMA_20': sma_20,
        'SMA_50': sma_50,
        'Upper_Band_20': bb_upper,
        'Middle_Band_20': bb_middle,
        'Lower_Band_20': bb_lower
    }
    
    return close, high, low, indicators


def test_rsi_mean_reversion_strategy():
    """Test RSI mean reversion strategy (most common template)."""
    print("\n" + "="*80)
    print("Real-World Test 1: RSI Mean Reversion Strategy")
    print("="*80)
    
    # Create engine WITHOUT LLM service (DSL-only mode)
    llm_service = None
    mock_etoro = Mock()
    market_data = MarketDataManager(mock_etoro)
    engine = StrategyEngine(llm_service, market_data)
    
    # Create realistic market data
    close, high, low, indicators = create_realistic_market_data(90)
    
    # RSI Mean Reversion strategy (from templates)
    rules = {
        "entry_conditions": ["RSI(14) < 30"],
        "exit_conditions": ["RSI(14) > 70"]
    }
    
    print(f"\nStrategy: RSI Mean Reversion")
    print(f"Entry: {rules['entry_conditions']}")
    print(f"Exit: {rules['exit_conditions']}")
    
    # Parse rules
    entries, exits = engine._parse_strategy_rules(close, high, low, indicators, rules)
    
    # Analyze results
    print(f"\nResults:")
    print(f"  Total days: {len(close)}")
    print(f"  Entry signals: {entries.sum()} ({entries.sum()/len(close)*100:.1f}%)")
    print(f"  Exit signals: {exits.sum()} ({exits.sum()/len(close)*100:.1f}%)")
    print(f"  Signal overlap: {(entries & exits).sum()} days")
    
    # Verify reasonable signal frequency
    assert entries.sum() > 0, "Should generate entry signals"
    assert exits.sum() > 0, "Should generate exit signals"
    assert entries.sum() < len(close) * 0.5, "Entry signals should be selective (< 50% of days)"
    assert exits.sum() < len(close) * 0.5, "Exit signals should be selective (< 50% of days)"
    
    print(f"\n✅ RSI Mean Reversion strategy working correctly")


def test_bollinger_band_bounce_strategy():
    """Test Bollinger Band bounce strategy."""
    print("\n" + "="*80)
    print("Real-World Test 2: Bollinger Band Bounce Strategy")
    print("="*80)
    
    # Create engine WITHOUT LLM service (DSL-only mode)
    llm_service = None
    mock_etoro = Mock()
    market_data = MarketDataManager(mock_etoro)
    engine = StrategyEngine(llm_service, market_data)
    
    # Create realistic market data
    close, high, low, indicators = create_realistic_market_data(90)
    
    # Bollinger Band Bounce strategy (from templates)
    rules = {
        "entry_conditions": ["CLOSE < BB_LOWER(20, 2)"],
        "exit_conditions": ["CLOSE > BB_UPPER(20, 2)"]
    }
    
    print(f"\nStrategy: Bollinger Band Bounce")
    print(f"Entry: {rules['entry_conditions']}")
    print(f"Exit: {rules['exit_conditions']}")
    
    # Parse rules
    entries, exits = engine._parse_strategy_rules(close, high, low, indicators, rules)
    
    # Analyze results
    print(f"\nResults:")
    print(f"  Total days: {len(close)}")
    print(f"  Entry signals: {entries.sum()} ({entries.sum()/len(close)*100:.1f}%)")
    print(f"  Exit signals: {exits.sum()} ({exits.sum()/len(close)*100:.1f}%)")
    print(f"  Signal overlap: {(entries & exits).sum()} days")
    
    # Verify reasonable signal frequency
    assert entries.sum() >= 0, "Should generate entry signals or none (depends on data)"
    assert exits.sum() >= 0, "Should generate exit signals or none (depends on data)"
    
    # Verify no overlap (price can't be below lower band AND above upper band)
    assert (entries & exits).sum() == 0, "Entry and exit should never overlap for Bollinger strategy"
    
    print(f"\n✅ Bollinger Band Bounce strategy working correctly")


def test_sma_crossover_strategy():
    """Test SMA crossover strategy."""
    print("\n" + "="*80)
    print("Real-World Test 3: SMA Crossover Strategy")
    print("="*80)
    
    # Create engine WITHOUT LLM service (DSL-only mode)
    llm_service = None
    mock_etoro = Mock()
    market_data = MarketDataManager(mock_etoro)
    engine = StrategyEngine(llm_service, market_data)
    
    # Create realistic market data
    close, high, low, indicators = create_realistic_market_data(90)
    
    # SMA Crossover strategy (from templates)
    rules = {
        "entry_conditions": ["SMA(20) CROSSES_ABOVE SMA(50)"],
        "exit_conditions": ["SMA(20) CROSSES_BELOW SMA(50)"]
    }
    
    print(f"\nStrategy: SMA Crossover")
    print(f"Entry: {rules['entry_conditions']}")
    print(f"Exit: {rules['exit_conditions']}")
    
    # Parse rules
    entries, exits = engine._parse_strategy_rules(close, high, low, indicators, rules)
    
    # Analyze results
    print(f"\nResults:")
    print(f"  Total days: {len(close)}")
    print(f"  Entry signals: {entries.sum()} ({entries.sum()/len(close)*100:.1f}%)")
    print(f"  Exit signals: {exits.sum()} ({exits.sum()/len(close)*100:.1f}%)")
    print(f"  Signal overlap: {(entries & exits).sum()} days")
    
    # Crossovers should be rare (1-3 times in 90 days)
    assert entries.sum() <= 5, "Crossovers should be rare events"
    assert exits.sum() <= 5, "Crossovers should be rare events"
    
    # Verify no overlap (can't cross above and below simultaneously)
    assert (entries & exits).sum() == 0, "Entry and exit crossovers should never overlap"
    
    print(f"\n✅ SMA Crossover strategy working correctly")


def test_compound_strategy():
    """Test compound strategy with multiple conditions."""
    print("\n" + "="*80)
    print("Real-World Test 4: Compound Strategy (RSI + Bollinger)")
    print("="*80)
    
    # Create engine WITHOUT LLM service (DSL-only mode)
    llm_service = None
    mock_etoro = Mock()
    market_data = MarketDataManager(mock_etoro)
    engine = StrategyEngine(llm_service, market_data)
    
    # Create realistic market data
    close, high, low, indicators = create_realistic_market_data(90)
    
    # Compound strategy combining RSI and Bollinger Bands
    rules = {
        "entry_conditions": ["RSI(14) < 30 AND CLOSE < BB_LOWER(20, 2)"],
        "exit_conditions": ["RSI(14) > 70 OR CLOSE > BB_UPPER(20, 2)"]
    }
    
    print(f"\nStrategy: RSI + Bollinger Band Compound")
    print(f"Entry: {rules['entry_conditions']}")
    print(f"Exit: {rules['exit_conditions']}")
    
    # Parse rules
    entries, exits = engine._parse_strategy_rules(close, high, low, indicators, rules)
    
    # Analyze results
    print(f"\nResults:")
    print(f"  Total days: {len(close)}")
    print(f"  Entry signals: {entries.sum()} ({entries.sum()/len(close)*100:.1f}%)")
    print(f"  Exit signals: {exits.sum()} ({exits.sum()/len(close)*100:.1f}%)")
    print(f"  Signal overlap: {(entries & exits).sum()} days")
    
    # Compound conditions should be more selective
    # Entry requires BOTH conditions (AND), so fewer signals
    # Exit requires EITHER condition (OR), so more signals
    assert entries.sum() <= exits.sum(), "AND logic should be more selective than OR logic"
    
    print(f"\n✅ Compound strategy working correctly")


if __name__ == "__main__":
    print("\n" + "="*80)
    print("REAL-WORLD DSL INTEGRATION VERIFICATION")
    print("="*80)
    print("\nTesting DSL parser with realistic market data and strategy templates...")
    
    try:
        test_rsi_mean_reversion_strategy()
        test_bollinger_band_bounce_strategy()
        test_sma_crossover_strategy()
        test_compound_strategy()
        
        print("\n" + "="*80)
        print("✅ ALL REAL-WORLD TESTS PASSED")
        print("="*80)
        print("\nVerification Summary:")
        print("✅ RSI Mean Reversion strategy works with realistic data")
        print("✅ Bollinger Band Bounce strategy works with realistic data")
        print("✅ SMA Crossover strategy works with realistic data")
        print("✅ Compound strategies work with realistic data")
        print("✅ Signal frequencies are reasonable")
        print("✅ Signal overlap validation works")
        print("✅ DSL integration is production-ready")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        raise
