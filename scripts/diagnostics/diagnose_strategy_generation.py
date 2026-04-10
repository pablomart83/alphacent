"""Diagnostic script to understand why we're not generating more trades."""

import logging
from src.api.etoro_client import EToroAPIClient
from src.data.market_data_manager import MarketDataManager
from src.strategy.strategy_engine import StrategyEngine
from src.strategy.market_analyzer import MarketStatisticsAnalyzer
from src.strategy.strategy_proposer import StrategyProposer
from src.strategy.strategy_templates import StrategyTemplateLibrary, MarketRegime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    print("=" * 80)
    print("STRATEGY GENERATION DIAGNOSTIC")
    print("=" * 80)
    
    # Initialize components
    from src.core.config import ConfigManager
    config_manager = ConfigManager()
    etoro = EToroAPIClient(
        mode='DEMO',
        public_key=config_manager.get_etoro_public_key(),
        user_key=config_manager.get_etoro_user_key()
    )
    market_data = MarketDataManager(etoro)
    strategy_engine = StrategyEngine(llm_service=None, market_data=market_data)
    market_analyzer = MarketStatisticsAnalyzer(market_data)
    
    # Detect current market regime
    sub_regime, confidence, data_quality, metrics = market_analyzer.detect_sub_regime()
    print(f"\nCurrent Market Regime: {sub_regime.value}")
    print(f"Confidence: {confidence:.2f}")
    print(f"Data Quality: {data_quality}")
    print(f"Metrics: {metrics}")
    
    # Get template library
    template_lib = StrategyTemplateLibrary()
    print(f"\nTotal templates in library: {len(template_lib.templates)}")
    
    # Count templates by regime
    regime_counts = {}
    for template in template_lib.templates:
        for regime in template.market_regimes:
            regime_counts[regime] = regime_counts.get(regime, 0) + 1
    
    print("\nTemplates by regime:")
    for regime, count in sorted(regime_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {regime.value}: {count} templates")
    
    # Check templates for current regime
    matching_templates = [t for t in template_lib.templates if sub_regime in t.market_regimes]
    print(f"\nTemplates matching current regime ({sub_regime.value}): {len(matching_templates)}")
    
    # Initialize proposer
    proposer = StrategyProposer(
        llm_service=None,
        market_data=market_data,
        trading_symbols=None  # Will use default
    )
    
    print(f"\nTrading symbols: {len(proposer._trading_symbols)}")
    print(f"Symbols: {proposer._trading_symbols[:10]}... (showing first 10)")
    
    # Try to generate strategies WITHOUT walk-forward validation
    print("\n" + "=" * 80)
    print("GENERATING STRATEGIES (NO WALK-FORWARD)")
    print("=" * 80)
    
    strategies_no_wf = proposer.propose_strategies(
        count=20,
        use_walk_forward=False,
        strategy_engine=strategy_engine
    )
    
    print(f"\nGenerated {len(strategies_no_wf)} strategies without walk-forward validation")
    for i, s in enumerate(strategies_no_wf[:5], 1):
        print(f"  {i}. {s.name} - {s.symbols}")
    
    # Try to generate strategies WITH walk-forward validation
    print("\n" + "=" * 80)
    print("GENERATING STRATEGIES (WITH WALK-FORWARD)")
    print("=" * 80)
    
    strategies_with_wf = proposer.propose_strategies(
        count=20,
        use_walk_forward=True,
        strategy_engine=strategy_engine
    )
    
    print(f"\nGenerated {len(strategies_with_wf)} strategies with walk-forward validation")
    for i, s in enumerate(strategies_with_wf[:5], 1):
        wf_train = s.metadata.get('wf_train_sharpe', 'N/A')
        wf_test = s.metadata.get('wf_test_sharpe', 'N/A')
        print(f"  {i}. {s.name} - {s.symbols} (train={wf_train}, test={wf_test})")
    
    print("\n" + "=" * 80)
    print("DIAGNOSIS COMPLETE")
    print("=" * 80)
    
    print("\nKey Findings:")
    print(f"1. Current regime: {sub_regime.value}")
    print(f"2. Templates for regime: {len(matching_templates)}")
    print(f"3. Strategies without WF: {len(strategies_no_wf)}")
    print(f"4. Strategies with WF: {len(strategies_with_wf)}")
    print(f"5. WF rejection rate: {(1 - len(strategies_with_wf)/max(len(strategies_no_wf), 1))*100:.1f}%")

if __name__ == "__main__":
    main()
