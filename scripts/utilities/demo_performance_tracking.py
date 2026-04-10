"""Demo: Strategy Performance Tracking System

This demo shows how the performance tracking system works end-to-end.
"""

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.strategy.performance_tracker import StrategyPerformanceTracker
from src.strategy.strategy_proposer import StrategyProposer, MarketRegime
from src.llm.llm_service import LLMService
from src.data.market_data_manager import MarketDataManager
from src.api.etoro_client import EToroAPIClient


def main():
    print("=" * 80)
    print("DEMO: Strategy Performance Tracking System")
    print("=" * 80)
    
    # Clean up demo database
    demo_db = "demo_performance.db"
    if os.path.exists(demo_db):
        os.remove(demo_db)
    
    # Initialize tracker
    tracker = StrategyPerformanceTracker(db_path=demo_db)
    
    print("\n" + "=" * 80)
    print("SCENARIO 1: Ranging Market - Week 1")
    print("=" * 80)
    
    print("\nBacktesting 3 strategies in ranging market...")
    
    # Week 1: Test different strategies in ranging market
    week1_data = [
        ("mean_reversion", "ranging", 1.8, 0.15, 0.58, "SPY", "RSI Bollinger Mean Reversion"),
        ("momentum", "ranging", -0.4, -0.03, 0.42, "SPY", "Moving Average Crossover"),
        ("breakout", "ranging", 0.2, 0.01, 0.48, "SPY", "Resistance Breakout"),
    ]
    
    for strategy_type, regime, sharpe, ret, win_rate, symbol, name in week1_data:
        tracker.track_performance(strategy_type, regime, sharpe, ret, win_rate, symbol)
        status = "✅ GOOD" if sharpe > 1.0 else "⚠️  POOR" if sharpe > 0 else "❌ BAD"
        print(f"  {status} {name}: Sharpe {sharpe:.2f}, Return {ret:.1%}, Win Rate {win_rate:.0%}")
    
    print("\n📊 Performance Summary (Week 1):")
    week1_perf = tracker.get_recent_performance(days=7, market_regime="ranging")
    for strategy_type, metrics in sorted(week1_perf.items(), key=lambda x: x[1]['avg_sharpe'], reverse=True):
        print(f"  {strategy_type}: Sharpe {metrics['avg_sharpe']:.2f}, Success {metrics['success_rate']:.0%}")
    
    print("\n💡 Insight: Mean reversion works best in ranging markets!")
    
    print("\n" + "=" * 80)
    print("SCENARIO 2: Trending Market - Week 2")
    print("=" * 80)
    
    print("\nMarket regime changed to trending up. Backtesting strategies...")
    
    # Week 2: Market changes to trending
    week2_data = [
        ("mean_reversion", "trending_up", -0.6, -0.05, 0.38, "SPY", "RSI Mean Reversion"),
        ("momentum", "trending_up", 2.2, 0.20, 0.64, "SPY", "MACD Momentum"),
        ("breakout", "trending_up", 1.9, 0.17, 0.61, "SPY", "Resistance Breakout"),
    ]
    
    for strategy_type, regime, sharpe, ret, win_rate, symbol, name in week2_data:
        tracker.track_performance(strategy_type, regime, sharpe, ret, win_rate, symbol)
        status = "✅ GOOD" if sharpe > 1.0 else "⚠️  POOR" if sharpe > 0 else "❌ BAD"
        print(f"  {status} {name}: Sharpe {sharpe:.2f}, Return {ret:.1%}, Win Rate {win_rate:.0%}")
    
    print("\n📊 Performance Summary (Week 2):")
    week2_perf = tracker.get_recent_performance(days=7, market_regime="trending_up")
    for strategy_type, metrics in sorted(week2_perf.items(), key=lambda x: x[1]['avg_sharpe'], reverse=True):
        print(f"  {strategy_type}: Sharpe {metrics['avg_sharpe']:.2f}, Success {metrics['success_rate']:.0%}")
    
    print("\n💡 Insight: Momentum and breakout work best in trending markets!")
    
    print("\n" + "=" * 80)
    print("SCENARIO 3: Strategy Proposer Integration")
    print("=" * 80)
    
    print("\nInitializing StrategyProposer with performance history...")
    
    # Create proposer with our tracker
    llm_service = LLMService()
    mock_etoro = Mock(spec=EToroAPIClient)
    market_data = MarketDataManager(mock_etoro)
    proposer = StrategyProposer(llm_service, market_data)
    proposer.performance_tracker = tracker
    
    print("\n📝 Generating prompt for RANGING market...")
    prompt_ranging = proposer._create_proposal_prompt(
        regime=MarketRegime.RANGING,
        available_indicators=["RSI", "SMA", "Bollinger Bands"],
        symbols=["SPY"],
        strategy_number=1,
        total_strategies=1
    )
    
    # Extract performance section
    if "RECENT STRATEGY PERFORMANCE" in prompt_ranging:
        start = prompt_ranging.index("RECENT STRATEGY PERFORMANCE")
        end = start + 500
        perf_section = prompt_ranging[start:end]
        
        # Find the end of the section
        for marker in ["\n\nInclude entry", "\n\nCRITICAL MARKET"]:
            if marker in perf_section:
                perf_section = perf_section[:perf_section.index(marker)]
        
        print("\n" + "-" * 80)
        print(perf_section)
        print("-" * 80)
    
    print("\n📝 Generating prompt for TRENDING UP market...")
    prompt_trending = proposer._create_proposal_prompt(
        regime=MarketRegime.TRENDING_UP,
        available_indicators=["RSI", "SMA", "MACD"],
        symbols=["SPY"],
        strategy_number=1,
        total_strategies=1
    )
    
    # Extract performance section
    if "RECENT STRATEGY PERFORMANCE" in prompt_trending:
        start = prompt_trending.index("RECENT STRATEGY PERFORMANCE")
        end = start + 500
        perf_section = prompt_trending[start:end]
        
        # Find the end of the section
        for marker in ["\n\nInclude entry", "\n\nCRITICAL MARKET"]:
            if marker in perf_section:
                perf_section = perf_section[:perf_section.index(marker)]
        
        print("\n" + "-" * 80)
        print(perf_section)
        print("-" * 80)
    
    print("\n" + "=" * 80)
    print("SCENARIO 4: Performance by Regime Analysis")
    print("=" * 80)
    
    print("\n📊 Complete Performance Analysis:")
    by_regime = tracker.get_performance_by_regime(days=30)
    
    for regime, strategies in sorted(by_regime.items()):
        print(f"\n{regime.upper().replace('_', ' ')}:")
        for strategy_type, metrics in sorted(strategies.items(), key=lambda x: x[1]['avg_sharpe'], reverse=True):
            print(f"  {strategy_type}:")
            print(f"    Sharpe: {metrics['avg_sharpe']:.2f}")
            print(f"    Success Rate: {metrics['success_rate']:.0%}")
            print(f"    Backtests: {metrics['count']}")
    
    print("\n" + "=" * 80)
    print("KEY INSIGHTS")
    print("=" * 80)
    
    print("\n1. ✅ Mean reversion strategies work best in ranging markets")
    print("   - Ranging: Sharpe 1.80 (100% success)")
    print("   - Trending: Sharpe -0.60 (0% success)")
    
    print("\n2. ✅ Momentum strategies work best in trending markets")
    print("   - Trending: Sharpe 2.20 (100% success)")
    print("   - Ranging: Sharpe -0.40 (0% success)")
    
    print("\n3. ✅ Breakout strategies work in both regimes")
    print("   - Trending: Sharpe 1.90 (100% success)")
    print("   - Ranging: Sharpe 0.20 (100% success, but weak)")
    
    print("\n4. 🎯 LLM receives this data in prompts")
    print("   - Can make informed decisions about strategy types")
    print("   - Adapts to current market regime")
    print("   - Learns from recent successes and failures")
    
    print("\n" + "=" * 80)
    print("✅ DEMO COMPLETE")
    print("=" * 80)
    
    print("\nThe performance tracking system:")
    print("  ✅ Tracks backtest results by strategy type and market regime")
    print("  ✅ Provides performance statistics to StrategyProposer")
    print("  ✅ Enables data-driven strategy generation")
    print("  ✅ Learns from historical successes and failures")
    
    # Cleanup
    if os.path.exists(demo_db):
        os.remove(demo_db)
        print("\n🧹 Cleaned up demo database")


if __name__ == "__main__":
    main()
