"""Test StrategyProposer integration with performance tracking."""

import os
import sys
from datetime import datetime
from unittest.mock import Mock

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.strategy.strategy_proposer import StrategyProposer, MarketRegime
from src.strategy.performance_tracker import StrategyPerformanceTracker
from src.llm.llm_service import LLMService
from src.data.market_data_manager import MarketDataManager
from src.api.etoro_client import EToroAPIClient


def test_proposer_with_performance_history():
    """Test that StrategyProposer includes performance history in prompts."""
    print("=" * 80)
    print("Testing StrategyProposer with Performance History")
    print("=" * 80)
    
    # Clean up any existing test databases
    for db_file in ["test_proposer_perf.db", "test_empty_performance.db"]:
        if os.path.exists(db_file):
            os.remove(db_file)
    
    # Initialize components with mock etoro client and unique database
    llm_service = LLMService()
    mock_etoro = Mock(spec=EToroAPIClient)
    market_data = MarketDataManager(mock_etoro)
    proposer = StrategyProposer(llm_service, market_data)
    
    # Use a unique database for this test
    proposer.performance_tracker = StrategyPerformanceTracker(db_path="test_proposer_perf.db")
    
    print("\n1. Verifying StrategyProposer has performance_tracker...")
    assert hasattr(proposer, 'performance_tracker'), "StrategyProposer should have performance_tracker"
    assert isinstance(proposer.performance_tracker, StrategyPerformanceTracker), "performance_tracker should be StrategyPerformanceTracker instance"
    print("✅ StrategyProposer has performance_tracker")
    
    print("\n2. Adding sample performance data...")
    
    # Add some sample performance data for ranging market
    tracker = proposer.performance_tracker
    
    test_data = [
        # Mean reversion works well in ranging
        ("mean_reversion", "ranging", 1.5, 0.12, 0.55, "SPY"),
        ("mean_reversion", "ranging", 1.2, 0.08, 0.52, "QQQ"),
        ("mean_reversion", "ranging", 0.8, 0.05, 0.48, "DIA"),
        
        # Momentum doesn't work well in ranging
        ("momentum", "ranging", -0.3, -0.02, 0.42, "SPY"),
        ("momentum", "ranging", -0.5, -0.04, 0.38, "QQQ"),
        
        # Breakout mixed results in ranging
        ("breakout", "ranging", 0.6, 0.04, 0.46, "SPY"),
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
    
    print("✅ Added 6 performance records")
    
    print("\n3. Testing prompt generation with performance history...")
    
    # Generate a prompt for ranging market
    prompt = proposer._create_proposal_prompt(
        regime=MarketRegime.RANGING,
        available_indicators=["RSI", "SMA", "Bollinger Bands"],
        symbols=["SPY", "QQQ"],
        strategy_number=1,
        total_strategies=3
    )
    
    print("\n4. Verifying prompt contains performance history...")
    
    # Check that prompt contains performance section
    assert "RECENT STRATEGY PERFORMANCE" in prompt, "Prompt should contain performance section"
    print("✅ Prompt contains 'RECENT STRATEGY PERFORMANCE' section")
    
    # Check that it mentions mean reversion (which performed well)
    assert "mean reversion" in prompt.lower() or "Mean Reversion" in prompt, "Prompt should mention mean reversion"
    print("✅ Prompt mentions mean reversion strategies")
    
    # Check that it shows Sharpe ratios
    assert "Sharpe" in prompt, "Prompt should show Sharpe ratios"
    print("✅ Prompt shows Sharpe ratios")
    
    # Check that it shows success rates
    assert "success rate" in prompt.lower(), "Prompt should show success rates"
    print("✅ Prompt shows success rates")
    
    print("\n5. Displaying performance section from prompt...")
    
    # Extract and display the performance section
    if "RECENT STRATEGY PERFORMANCE" in prompt:
        start_idx = prompt.index("RECENT STRATEGY PERFORMANCE")
        # Find the end of the section (next major section or end)
        end_markers = ["\n\nInclude entry/exit", "\n\nCRITICAL MARKET DATA", "\n\nDesign a strategy"]
        end_idx = len(prompt)
        for marker in end_markers:
            if marker in prompt[start_idx:]:
                end_idx = start_idx + prompt[start_idx:].index(marker)
                break
        
        performance_section = prompt[start_idx:end_idx]
        print("\n" + "-" * 80)
        print(performance_section)
        print("-" * 80)
    
    print("\n6. Testing with no performance history (new system)...")
    
    # Delete the test database file to ensure it's truly empty
    test_db_path = "test_empty_performance.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    
    # Create new proposer with empty tracker
    llm_service2 = LLMService()
    mock_etoro2 = Mock(spec=EToroAPIClient)
    market_data2 = MarketDataManager(mock_etoro2)
    proposer2 = StrategyProposer(llm_service2, market_data2)
    
    # Create a completely new tracker with the empty database
    proposer2.performance_tracker = StrategyPerformanceTracker(db_path=test_db_path)
    
    # Verify the tracker is actually empty
    empty_result = proposer2.performance_tracker.get_recent_performance(days=30, market_regime="ranging")
    print(f"Debug: empty_result = {empty_result}")
    assert empty_result == {}, f"Expected empty dict, got {empty_result}"
    print("✅ Verified tracker is empty")
    
    prompt_empty = proposer2._create_proposal_prompt(
        regime=MarketRegime.RANGING,
        available_indicators=["RSI", "SMA", "Bollinger Bands"],
        symbols=["SPY", "QQQ"],
        strategy_number=1,
        total_strategies=3
    )
    
    # Should still have performance section but with "No historical data" message
    assert "RECENT STRATEGY PERFORMANCE" in prompt_empty, "Prompt should contain performance section even when empty"
    
    # Check for the actual message
    has_no_data_message = (
        "No historical data" in prompt_empty or 
        "first strategies" in prompt_empty
    )
    
    assert has_no_data_message, "Should mention no historical data when tracker is empty"
    print("✅ Prompt handles empty performance history gracefully")
    
    print("\n" + "=" * 80)
    print("✅ All integration tests passed!")
    print("=" * 80)
    
    # Cleanup
    for db_file in ["test_proposer_perf.db", "test_empty_performance.db"]:
        if os.path.exists(db_file):
            os.remove(db_file)
    print("\n🧹 Cleaned up test databases")


if __name__ == "__main__":
    test_proposer_with_performance_history()
