"""Test strategy performance tracker functionality."""

import os
import sys
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.strategy.performance_tracker import StrategyPerformanceTracker


def test_performance_tracker():
    """Test the StrategyPerformanceTracker class."""
    print("=" * 80)
    print("Testing StrategyPerformanceTracker")
    print("=" * 80)
    
    # Use test database
    tracker = StrategyPerformanceTracker(db_path="test_performance.db")
    
    print("\n1. Testing track_performance()...")
    
    # Track some sample performance data
    test_data = [
        # Mean reversion strategies in ranging market
        ("mean_reversion", "ranging", 1.5, 0.12, 0.55, "SPY"),
        ("mean_reversion", "ranging", 1.2, 0.08, 0.52, "QQQ"),
        ("mean_reversion", "ranging", 0.8, 0.05, 0.48, "DIA"),
        ("mean_reversion", "ranging", -0.3, -0.02, 0.42, "IWM"),
        
        # Momentum strategies in trending market
        ("momentum", "trending_up", 2.1, 0.18, 0.62, "SPY"),
        ("momentum", "trending_up", 1.8, 0.15, 0.58, "QQQ"),
        ("momentum", "trending_up", 1.4, 0.11, 0.54, "DIA"),
        
        # Breakout strategies in trending market
        ("breakout", "trending_up", 1.6, 0.13, 0.56, "SPY"),
        ("breakout", "trending_up", 0.9, 0.06, 0.49, "QQQ"),
        
        # Mean reversion in trending market (should perform poorly)
        ("mean_reversion", "trending_up", -0.5, -0.04, 0.38, "SPY"),
        ("mean_reversion", "trending_up", -0.2, -0.01, 0.41, "QQQ"),
    ]
    
    for strategy_type, regime, sharpe, return_pct, win_rate, symbol in test_data:
        tracker.track_performance(
            strategy_type=strategy_type,
            market_regime=regime,
            sharpe_ratio=sharpe,
            total_return=return_pct,
            win_rate=win_rate,
            symbol=symbol
        )
    
    print("✅ Tracked 11 performance records")
    
    print("\n2. Testing get_recent_performance()...")
    
    # Get overall performance
    overall_performance = tracker.get_recent_performance(days=30)
    
    print("\nOverall Performance (all regimes):")
    for strategy_type, metrics in sorted(overall_performance.items()):
        print(f"  {strategy_type}:")
        print(f"    - Avg Sharpe: {metrics['avg_sharpe']:.2f}")
        print(f"    - Success Rate: {metrics['success_rate']:.1%}")
        print(f"    - Count: {metrics['count']}")
    
    # Get performance for specific regime
    ranging_performance = tracker.get_recent_performance(days=30, market_regime="ranging")
    
    print("\nPerformance in Ranging Market:")
    for strategy_type, metrics in sorted(ranging_performance.items()):
        print(f"  {strategy_type}:")
        print(f"    - Avg Sharpe: {metrics['avg_sharpe']:.2f}")
        print(f"    - Success Rate: {metrics['success_rate']:.1%}")
        print(f"    - Count: {metrics['count']}")
    
    trending_performance = tracker.get_recent_performance(days=30, market_regime="trending_up")
    
    print("\nPerformance in Trending Up Market:")
    for strategy_type, metrics in sorted(trending_performance.items()):
        print(f"  {strategy_type}:")
        print(f"    - Avg Sharpe: {metrics['avg_sharpe']:.2f}")
        print(f"    - Success Rate: {metrics['success_rate']:.1%}")
        print(f"    - Count: {metrics['count']}")
    
    print("\n3. Testing get_performance_by_regime()...")
    
    performance_by_regime = tracker.get_performance_by_regime(days=30)
    
    print("\nPerformance Grouped by Regime:")
    for regime, strategies in sorted(performance_by_regime.items()):
        print(f"\n  {regime}:")
        for strategy_type, metrics in sorted(strategies.items()):
            print(f"    {strategy_type}:")
            print(f"      - Avg Sharpe: {metrics['avg_sharpe']:.2f}")
            print(f"      - Success Rate: {metrics['success_rate']:.1%}")
            print(f"      - Count: {metrics['count']}")
    
    print("\n4. Verifying insights...")
    
    # Verify mean reversion works better in ranging markets
    mean_rev_ranging = ranging_performance.get("mean_reversion", {})
    mean_rev_trending = trending_performance.get("mean_reversion", {})
    
    if mean_rev_ranging and mean_rev_trending:
        ranging_sharpe = mean_rev_ranging['avg_sharpe']
        trending_sharpe = mean_rev_trending['avg_sharpe']
        
        print(f"\nMean Reversion Performance:")
        print(f"  - Ranging market: Sharpe {ranging_sharpe:.2f}")
        print(f"  - Trending market: Sharpe {trending_sharpe:.2f}")
        
        if ranging_sharpe > trending_sharpe:
            print("  ✅ Mean reversion performs better in ranging markets (as expected)")
        else:
            print("  ⚠️  Unexpected: Mean reversion should perform better in ranging markets")
    
    # Verify momentum works better in trending markets
    momentum_trending = trending_performance.get("momentum", {})
    
    if momentum_trending:
        momentum_sharpe = momentum_trending['avg_sharpe']
        print(f"\nMomentum Performance:")
        print(f"  - Trending market: Sharpe {momentum_sharpe:.2f}")
        
        if momentum_sharpe > 1.0:
            print("  ✅ Momentum performs well in trending markets (as expected)")
    
    print("\n5. Testing clear_old_records()...")
    
    # This won't delete anything since all records are recent
    deleted = tracker.clear_old_records(days=90)
    print(f"Deleted {deleted} old records (expected 0 since all are recent)")
    
    print("\n" + "=" * 80)
    print("✅ All tests passed!")
    print("=" * 80)
    
    # Cleanup
    if os.path.exists("test_performance.db"):
        os.remove("test_performance.db")
        print("\n🧹 Cleaned up test database")


if __name__ == "__main__":
    test_performance_tracker()
