"""Debug test for empty performance history."""

import os
import sys
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.strategy.performance_tracker import StrategyPerformanceTracker
from src.strategy.strategy_proposer import StrategyProposer, MarketRegime
from src.llm.llm_service import LLMService
from src.data.market_data_manager import MarketDataManager
from src.api.etoro_client import EToroAPIClient

# Clean up any existing test db
if os.path.exists("test_debug_empty.db"):
    os.remove("test_debug_empty.db")

# Create empty tracker
tracker = StrategyPerformanceTracker(db_path="test_debug_empty.db")

# Test get_recent_performance with empty database
result = tracker.get_recent_performance(days=30, market_regime="ranging")
print(f"Empty tracker result: {result}")
print(f"Result type: {type(result)}")
print(f"Result is falsy: {not result}")
print(f"Result == {{}}: {result == {}}")

# Now test with proposer
llm_service = LLMService()
mock_etoro = Mock(spec=EToroAPIClient)
market_data = MarketDataManager(mock_etoro)
proposer = StrategyProposer(llm_service, market_data)
proposer.performance_tracker = tracker

prompt = proposer._create_proposal_prompt(
    regime=MarketRegime.RANGING,
    available_indicators=["RSI"],
    symbols=["SPY"],
    strategy_number=1,
    total_strategies=1
)

# Check if prompt contains the no data message
if "No historical data" in prompt:
    print("\n✅ Prompt contains 'No historical data' message")
elif "first strategies" in prompt:
    print("\n✅ Prompt contains 'first strategies' message")
else:
    print("\n❌ Prompt does NOT contain no-data message")
    
    # Find and print the performance section
    if "RECENT STRATEGY PERFORMANCE" in prompt:
        start = prompt.index("RECENT STRATEGY PERFORMANCE")
        end = start + 400
        print(f"\nPerformance section:\n{prompt[start:end]}")

# Cleanup
if os.path.exists("test_debug_empty.db"):
    os.remove("test_debug_empty.db")
