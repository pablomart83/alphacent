"""Example demonstrating configuration loading in AutonomousStrategyManager."""

import sys
sys.path.insert(0, '.')

from unittest.mock import Mock
from src.strategy.autonomous_strategy_manager import AutonomousStrategyManager


def main():
    """Demonstrate configuration loading."""
    
    # Create mock dependencies
    llm_service = Mock()
    market_data = Mock()
    strategy_engine = Mock()
    
    print("=" * 70)
    print("Configuration Loading Example")
    print("=" * 70)
    
    # Example 1: Load from default config file
    print("\n1. Loading from default config file (config/autonomous_trading.yaml):")
    print("-" * 70)
    
    manager = AutonomousStrategyManager(
        llm_service=llm_service,
        market_data=market_data,
        strategy_engine=strategy_engine
    )
    
    print(f"✓ LLM Model: {manager.config['llm']['model']}")
    print(f"✓ LLM Temperature: {manager.config['llm']['temperature']}")
    print(f"✓ Autonomous Enabled: {manager.config['autonomous']['enabled']}")
    print(f"✓ Proposal Frequency: {manager.config['autonomous']['proposal_frequency']}")
    print(f"✓ Max Active Strategies: {manager.config['autonomous']['max_active_strategies']}")
    print(f"✓ Min Sharpe Ratio (Activation): {manager.config['activation_thresholds']['min_sharpe']}")
    print(f"✓ Max Sharpe Ratio (Retirement): {manager.config['retirement_thresholds']['max_sharpe']}")
    
    # Example 2: Override with custom config
    print("\n2. Overriding with custom configuration:")
    print("-" * 70)
    
    custom_config = {
        'autonomous': {
            'enabled': False,
            'max_active_strategies': 15,
            'proposal_frequency': 'daily'
        },
        'activation_thresholds': {
            'min_sharpe': 2.0
        }
    }
    
    manager2 = AutonomousStrategyManager(
        llm_service=llm_service,
        market_data=market_data,
        strategy_engine=strategy_engine,
        config=custom_config
    )
    
    print(f"✓ Autonomous Enabled: {manager2.config['autonomous']['enabled']}")
    print(f"✓ Max Active Strategies: {manager2.config['autonomous']['max_active_strategies']}")
    print(f"✓ Proposal Frequency: {manager2.config['autonomous']['proposal_frequency']}")
    print(f"✓ Min Sharpe Ratio: {manager2.config['activation_thresholds']['min_sharpe']}")
    
    # Example 3: Load from custom config file path
    print("\n3. Loading from custom config file path:")
    print("-" * 70)
    
    manager3 = AutonomousStrategyManager(
        llm_service=llm_service,
        market_data=market_data,
        strategy_engine=strategy_engine,
        config_path="config/autonomous_trading.yaml"
    )
    
    print(f"✓ Configuration loaded from custom path")
    print(f"✓ LLM Model: {manager3.config['llm']['model']}")
    
    print("\n" + "=" * 70)
    print("Configuration loading examples completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    main()
