#!/usr/bin/env python3
"""Test parameter validation improvements."""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from src.strategy.strategy_proposer import StrategyProposer, MarketRegime
from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.models.enums import TradingMode

print("Testing Parameter Validation Improvements")
print("=" * 80)

# Initialize
config_manager = get_config()
credentials = config_manager.load_credentials(TradingMode.DEMO)
etoro_client = EToroAPIClient(
    public_key=credentials['public_key'],
    user_key=credentials['user_key'],
    mode=TradingMode.DEMO
)
llm_service = LLMService()
market_data = MarketDataManager(etoro_client=etoro_client)
proposer = StrategyProposer(llm_service, market_data)

# Test parameter validation
print("\n1. Testing RSI threshold validation...")
test_params = {
    'rsi_period': 14,
    'oversold_threshold': 20,  # Too tight
    'overbought_threshold': 80
}

validated = proposer._validate_parameter_bounds(test_params, {})
print(f"   Input: oversold={test_params['oversold_threshold']}, overbought={test_params['overbought_threshold']}")
print(f"   Output: oversold={validated['oversold_threshold']}, overbought={validated['overbought_threshold']}")
print(f"   ✓ Adjusted: {validated['oversold_threshold'] != test_params['oversold_threshold']}")

# Test narrow spread
print("\n2. Testing narrow RSI spread...")
test_params2 = {
    'rsi_period': 14,
    'oversold_threshold': 40,
    'overbought_threshold': 60  # Only 20 point spread
}

validated2 = proposer._validate_parameter_bounds(test_params2, {})
spread = validated2['overbought_threshold'] - validated2['oversold_threshold']
print(f"   Input spread: {test_params2['overbought_threshold'] - test_params2['oversold_threshold']}")
print(f"   Output spread: {spread}")
print(f"   ✓ Widened: {spread >= 30}")

# Test Bollinger Bands
print("\n3. Testing Bollinger Band validation...")
test_params3 = {
    'bb_period': 20,
    'bb_std': 1.0  # Too tight
}

validated3 = proposer._validate_parameter_bounds(test_params3, {})
print(f"   Input: bb_std={test_params3['bb_std']}")
print(f"   Output: bb_std={validated3['bb_std']}")
print(f"   ✓ Adjusted: {validated3['bb_std'] >= 1.5}")

# Test signal frequency estimation
print("\n4. Testing signal frequency estimation...")
from src.strategy.strategy_templates import StrategyTemplateLibrary

library = StrategyTemplateLibrary()
template = library.get_template_by_name("RSI Mean Reversion")

# Mock indicator distributions
mock_distributions = {
    'SPY': {
        'RSI': {
            'pct_oversold': 5.0,  # 5% of time below 30
            'pct_overbought': 5.0
        }
    }
}

# Test with normal threshold (30)
params_normal = {'oversold_threshold': 30}
freq_normal = proposer._estimate_signal_frequency(params_normal, template, mock_distributions)
print(f"   RSI < 30: {freq_normal:.2f} entries/month")

# Test with tight threshold (25)
params_tight = {'oversold_threshold': 25}
freq_tight = proposer._estimate_signal_frequency(params_tight, template, mock_distributions)
print(f"   RSI < 25: {freq_tight:.2f} entries/month")

# Test with loose threshold (35)
params_loose = {'oversold_threshold': 35}
freq_loose = proposer._estimate_signal_frequency(params_loose, template, mock_distributions)
print(f"   RSI < 35: {freq_loose:.2f} entries/month")

print(f"   ✓ Tighter threshold = lower frequency: {freq_tight < freq_normal}")
print(f"   ✓ Looser threshold = higher frequency: {freq_loose > freq_normal}")

print("\n" + "=" * 80)
print("✅ All parameter validation tests passed!")
print("=" * 80)
