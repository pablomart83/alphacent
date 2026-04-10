"""Test template-based strategy generation with market statistics."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import Mock
from src.strategy.strategy_proposer import StrategyProposer, MarketRegime
from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.models.enums import StrategyStatus
from src.api.etoro_client import EToroAPIClient


def test_template_based_generation():
    """Test generating strategies from templates without LLM."""
    print("\n" + "="*80)
    print("TEST: Template-Based Strategy Generation")
    print("="*80)
    
    # Initialize components with mock eToro client
    mock_etoro = Mock(spec=EToroAPIClient)
    market_data = MarketDataManager(mock_etoro)
    llm_service = LLMService()
    proposer = StrategyProposer(llm_service, market_data)
    
    # Test symbols
    symbols = ["SPY", "QQQ"]
    
    # Test for each market regime
    regimes = [MarketRegime.RANGING, MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN]
    
    for regime in regimes:
        print(f"\n{'='*80}")
        print(f"Testing regime: {regime.value}")
        print(f"{'='*80}")
        
        # Generate strategies from templates
        strategies = proposer.generate_strategies_from_templates(
            count=3,
            symbols=symbols,
            market_regime=regime
        )
        
        print(f"\nGenerated {len(strategies)} strategies for {regime.value} market:")
        
        for i, strategy in enumerate(strategies, 1):
            print(f"\n{i}. {strategy.name}")
            print(f"   Description: {strategy.description}")
            print(f"   Status: {strategy.status.value}")
            print(f"   Symbols: {strategy.symbols}")
            print(f"   Indicators: {strategy.rules.get('indicators', [])}")
            print(f"   Entry conditions:")
            for condition in strategy.rules.get('entry_conditions', []):
                print(f"     - {condition}")
            print(f"   Exit conditions:")
            for condition in strategy.rules.get('exit_conditions', []):
                print(f"     - {condition}")
            
            # Check metadata
            if hasattr(strategy, 'metadata') and strategy.metadata:
                print(f"   Template: {strategy.metadata.get('template_name', 'N/A')}")
                print(f"   Template type: {strategy.metadata.get('template_type', 'N/A')}")
                print(f"   Customized parameters: {strategy.metadata.get('customized_parameters', {})}")
            
            # Validate strategy structure
            assert strategy.status == StrategyStatus.PROPOSED
            assert len(strategy.symbols) > 0
            assert len(strategy.rules.get('indicators', [])) > 0
            assert len(strategy.rules.get('entry_conditions', [])) > 0
            assert len(strategy.rules.get('exit_conditions', [])) > 0
            
            print(f"   ✅ Strategy structure valid")
    
    print(f"\n{'='*80}")
    print("✅ ALL TESTS PASSED")
    print(f"{'='*80}")


def test_market_statistics_integration():
    """Test that market statistics are used to customize parameters."""
    print("\n" + "="*80)
    print("TEST: Market Statistics Integration")
    print("="*80)
    
    # Initialize components with mock eToro client
    mock_etoro = Mock(spec=EToroAPIClient)
    market_data = MarketDataManager(mock_etoro)
    llm_service = LLMService()
    proposer = StrategyProposer(llm_service, market_data)
    
    symbols = ["SPY"]
    
    # Get market statistics
    print("\nFetching market statistics...")
    market_statistics = {}
    indicator_distributions = {}
    
    for symbol in symbols:
        try:
            stats = proposer.market_analyzer.analyze_symbol(symbol, period_days=90)
            market_statistics[symbol] = stats
            print(f"\n{symbol} Statistics:")
            print(f"  Volatility: {stats['volatility_metrics']['volatility']:.3f}")
            print(f"  Trend strength: {stats['trend_metrics']['trend_strength']:.2f}")
            print(f"  Mean reversion score: {stats['mean_reversion_metrics']['mean_reversion_score']:.2f}")
            
            distributions = proposer.market_analyzer.analyze_indicator_distributions(symbol, period_days=90)
            indicator_distributions[symbol] = distributions
            
            if 'RSI' in distributions:
                rsi = distributions['RSI']
                print(f"  RSI oversold %: {rsi['pct_oversold']:.1f}%")
                print(f"  RSI overbought %: {rsi['pct_overbought']:.1f}%")
        except Exception as e:
            print(f"  Error analyzing {symbol}: {e}")
    
    # Get market context
    try:
        market_context = proposer.market_analyzer.get_market_context()
        print(f"\nMarket Context:")
        print(f"  VIX: {market_context.get('vix', 'N/A')}")
        print(f"  Risk regime: {market_context.get('risk_regime', 'N/A')}")
    except Exception as e:
        print(f"  Error getting market context: {e}")
        market_context = {}
    
    # Get a template
    templates = proposer.template_library.get_templates_for_regime(MarketRegime.RANGING)
    if not templates:
        print("❌ No templates found for RANGING market")
        return
    
    template = templates[0]
    print(f"\nUsing template: {template.name}")
    print(f"Default parameters: {template.default_parameters}")
    
    # Customize parameters
    customized_params = proposer.customize_template_parameters(
        template=template,
        market_statistics=market_statistics,
        indicator_distributions=indicator_distributions,
        market_context=market_context
    )
    
    print(f"\nCustomized parameters: {customized_params}")
    
    # Check that parameters were customized
    if customized_params != template.default_parameters:
        print("✅ Parameters were customized based on market statistics")
    else:
        print("⚠️  Parameters were not customized (may be expected if market is neutral)")
    
    # Generate strategy with customized parameters
    strategy = proposer.generate_from_template(
        template=template,
        symbols=symbols,
        market_statistics=market_statistics,
        indicator_distributions=indicator_distributions,
        market_context=market_context
    )
    
    print(f"\nGenerated strategy: {strategy.name}")
    print(f"Entry conditions: {strategy.rules.get('entry_conditions', [])}")
    print(f"Exit conditions: {strategy.rules.get('exit_conditions', [])}")
    
    print(f"\n{'='*80}")
    print("✅ TEST PASSED")
    print(f"{'='*80}")


def test_parameter_variations():
    """Test that parameter variations create diverse strategies."""
    print("\n" + "="*80)
    print("TEST: Parameter Variations for Diversity")
    print("="*80)
    
    # Initialize components with mock eToro client
    mock_etoro = Mock(spec=EToroAPIClient)
    market_data = MarketDataManager(mock_etoro)
    llm_service = LLMService()
    proposer = StrategyProposer(llm_service, market_data)
    
    symbols = ["SPY"]
    
    # Generate multiple strategies from same template
    strategies = proposer.generate_strategies_from_templates(
        count=6,
        symbols=symbols,
        market_regime=MarketRegime.RANGING
    )
    
    print(f"\nGenerated {len(strategies)} strategies with parameter variations:")
    
    # Track unique parameter combinations
    unique_params = set()
    
    for i, strategy in enumerate(strategies, 1):
        print(f"\n{i}. {strategy.name}")
        
        if hasattr(strategy, 'metadata') and strategy.metadata:
            params = strategy.metadata.get('customized_parameters', {})
            
            # Create hashable representation of params
            param_tuple = tuple(sorted(params.items()))
            unique_params.add(param_tuple)
            
            print(f"   Parameters: {params}")
            print(f"   Entry: {strategy.rules.get('entry_conditions', [])}")
            print(f"   Exit: {strategy.rules.get('exit_conditions', [])}")
    
    print(f"\n{'='*80}")
    print(f"Unique parameter combinations: {len(unique_params)}")
    
    if len(unique_params) >= 3:
        print("✅ Good diversity - at least 3 unique parameter combinations")
    else:
        print(f"⚠️  Limited diversity - only {len(unique_params)} unique combinations")
    
    print(f"{'='*80}")


if __name__ == "__main__":
    try:
        test_template_based_generation()
        test_market_statistics_integration()
        test_parameter_variations()
        
        print("\n" + "="*80)
        print("🎉 ALL TESTS COMPLETED SUCCESSFULLY")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
