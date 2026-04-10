#!/usr/bin/env python3
"""
CLI script for bootstrapping initial trading strategies.

This script generates 2-3 sample strategies with different trading approaches,
automatically backtests each strategy, and optionally activates strategies
that meet minimum performance thresholds.

Usage:
    python -m src.cli.bootstrap_strategies
    python -m src.cli.bootstrap_strategies --auto-activate --min-sharpe 0.5
    python -m src.cli.bootstrap_strategies --strategy-types momentum mean_reversion
"""

import argparse
import logging
import sys
from typing import List

from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.strategy.bootstrap_service import STRATEGY_TEMPLATES, BootstrapService
from src.strategy.strategy_engine import StrategyEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.
    
    Returns:
        Parsed arguments namespace
    
    Validates: Requirement 6.5 (CLI support)
    """
    parser = argparse.ArgumentParser(
        description='Bootstrap initial trading strategies for AlphaCent platform',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate all strategy types without activation
  python -m src.cli.bootstrap_strategies
  
  # Generate and auto-activate strategies with Sharpe >= 1.0
  python -m src.cli.bootstrap_strategies --auto-activate
  
  # Generate and auto-activate with custom Sharpe threshold
  python -m src.cli.bootstrap_strategies --auto-activate --min-sharpe 0.5
  
  # Generate only specific strategy types
  python -m src.cli.bootstrap_strategies --strategy-types momentum breakout
  
  # Custom backtest period (120 days)
  python -m src.cli.bootstrap_strategies --backtest-days 120
        """
    )
    
    parser.add_argument(
        '--auto-activate',
        action='store_true',
        help='Automatically activate strategies that meet minimum performance thresholds'
    )
    
    parser.add_argument(
        '--min-sharpe',
        type=float,
        default=1.0,
        help='Minimum Sharpe ratio for auto-activation (default: 1.0)'
    )
    
    parser.add_argument(
        '--strategy-types',
        nargs='+',
        choices=list(STRATEGY_TEMPLATES.keys()),
        default=None,
        help=f'Strategy types to generate (default: all). Choices: {", ".join(STRATEGY_TEMPLATES.keys())}'
    )
    
    parser.add_argument(
        '--backtest-days',
        type=int,
        default=90,
        help='Number of days to backtest (default: 90)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    return parser.parse_args()


def main() -> int:
    """
    Main entry point for bootstrap CLI.
    
    Returns:
        Exit code (0 for success, 1 for error)
    
    Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
    """
    args = parse_arguments()
    
    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print("=" * 70)
    print("AlphaCent Strategy Bootstrap")
    print("=" * 70)
    print()
    
    try:
        # Initialize services
        print("Initializing services...")
        logger.info("Initializing MarketDataManager, LLMService, and StrategyEngine")
        
        # Import required modules
        from src.core.config import get_config
        from src.api.etoro_client import EToroAPIClient
        from src.models import TradingMode
        
        # Load configuration
        config = get_config()
        
        # Initialize eToro client (use DEMO mode for bootstrap)
        try:
            creds = config.load_credentials(TradingMode.DEMO)
            etoro_client = EToroAPIClient(
                public_key=creds["public_key"],
                user_key=creds["user_key"],
                mode=TradingMode.DEMO
            )
        except Exception as e:
            logger.warning(f"Could not load credentials: {e}. Using mock client.")
            # Create a mock client for testing
            from unittest.mock import Mock
            etoro_client = Mock()
        
        market_data = MarketDataManager(etoro_client)
        llm_service = LLMService()
        # WebSocket manager is optional for CLI - pass None
        strategy_engine = StrategyEngine(llm_service, market_data, websocket_manager=None)
        bootstrap_service = BootstrapService(strategy_engine, llm_service, market_data)
        
        print("✓ Services initialized")
        print()
        
        # Display configuration
        print("Configuration:")
        print(f"  Strategy types: {args.strategy_types or 'all'}")
        print(f"  Auto-activate: {args.auto_activate}")
        if args.auto_activate:
            print(f"  Min Sharpe ratio: {args.min_sharpe}")
        print(f"  Backtest period: {args.backtest_days} days")
        print()
        
        # Run bootstrap
        print("Starting bootstrap process...")
        print()
        
        results = bootstrap_service.bootstrap_strategies(
            strategy_types=args.strategy_types,
            auto_activate=args.auto_activate,
            min_sharpe=args.min_sharpe,
            backtest_days=args.backtest_days
        )
        
        # Display results
        print()
        print("=" * 70)
        print("Bootstrap Results")
        print("=" * 70)
        print()
        
        summary = results['summary']
        print(f"Strategies generated: {summary['total_generated']}")
        print(f"Strategies backtested: {summary['total_backtested']}")
        print(f"Strategies activated: {summary['total_activated']}")
        print()
        
        # Display strategy details
        if results['strategies']:
            print("Strategy Details:")
            print("-" * 70)
            
            for strategy in results['strategies']:
                print(f"\n{strategy.name} (ID: {strategy.id})")
                print(f"  Status: {strategy.status.value}")
                print(f"  Symbols: {', '.join(strategy.symbols)}")
                
                # Display backtest results if available
                if strategy.id in results['backtest_results']:
                    bt_results = results['backtest_results'][strategy.id]
                    print(f"  Backtest Results:")
                    print(f"    Total Return: {bt_results.total_return:.2%}")
                    print(f"    Sharpe Ratio: {bt_results.sharpe_ratio:.2f}")
                    print(f"    Sortino Ratio: {bt_results.sortino_ratio:.2f}")
                    print(f"    Max Drawdown: {bt_results.max_drawdown:.2%}")
                    print(f"    Win Rate: {bt_results.win_rate:.2%}")
                    print(f"    Total Trades: {bt_results.total_trades}")
                    
                    # Indicate if activated
                    if strategy.id in results['activated']:
                        print(f"  ✓ ACTIVATED in DEMO mode")
                    elif args.auto_activate:
                        print(f"  ✗ Not activated (Sharpe {bt_results.sharpe_ratio:.2f} < {args.min_sharpe})")
        
        # Display errors if any
        if summary['errors']:
            print()
            print("Errors:")
            print("-" * 70)
            for error in summary['errors']:
                print(f"  ✗ {error}")
        
        print()
        print("=" * 70)
        
        # Determine exit code
        if summary['total_generated'] == 0:
            print("✗ Bootstrap failed: No strategies generated")
            return 1
        elif summary['errors']:
            print(f"⚠ Bootstrap completed with {len(summary['errors'])} error(s)")
            return 0  # Partial success
        else:
            print("✓ Bootstrap completed successfully")
            return 0
    
    except KeyboardInterrupt:
        print()
        print("Bootstrap interrupted by user")
        return 1
    
    except Exception as e:
        print()
        print("=" * 70)
        print("✗ Bootstrap failed with error:")
        print(f"  {type(e).__name__}: {e}")
        print("=" * 70)
        logger.exception("Bootstrap failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
