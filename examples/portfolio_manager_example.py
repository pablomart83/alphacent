"""Example usage of Portfolio Manager for autonomous strategy management."""

from datetime import datetime

from src.models.dataclasses import (
    BacktestResults,
    PerformanceMetrics,
    RiskConfig,
    Strategy,
)
from src.models.enums import StrategyStatus
from src.strategy.portfolio_manager import PortfolioManager
from src.strategy.strategy_engine import StrategyEngine


def example_evaluate_and_activate():
    """Example: Evaluate backtest results and auto-activate strategy."""
    # Initialize components (in real usage, these would be properly configured)
    # strategy_engine = StrategyEngine(llm_service, market_data, websocket_manager)
    # portfolio_manager = PortfolioManager(strategy_engine)

    # Create a sample strategy
    strategy = Strategy(
        id="momentum-strategy-1",
        name="RSI Momentum Strategy",
        description="Buy when RSI < 30, sell when RSI > 70",
        status=StrategyStatus.BACKTESTED,
        rules={"entry": ["RSI < 30"], "exit": ["RSI > 70"]},
        symbols=["AAPL", "GOOGL", "MSFT"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
    )

    # Backtest results from strategy evaluation
    backtest_results = BacktestResults(
        total_return=0.28,
        sharpe_ratio=2.1,  # > 1.5 ✓
        sortino_ratio=2.8,
        max_drawdown=0.12,  # < 0.15 ✓
        win_rate=0.62,  # > 0.5 ✓
        avg_win=0.035,
        avg_loss=-0.018,
        total_trades=45,  # > 20 ✓
    )

    # Evaluate for activation
    # should_activate = portfolio_manager.evaluate_for_activation(strategy, backtest_results)

    # if should_activate:
    #     # Auto-activate in DEMO mode with calculated allocation
    #     portfolio_manager.auto_activate_strategy(strategy)
    #     print(f"✓ Strategy {strategy.name} activated in DEMO mode")

    print("Example: Strategy meets all activation criteria")
    print(f"  Sharpe Ratio: {backtest_results.sharpe_ratio:.2f} (threshold: > 1.5)")
    print(f"  Max Drawdown: {backtest_results.max_drawdown:.2%} (threshold: < 15%)")
    print(f"  Win Rate: {backtest_results.win_rate:.2%} (threshold: > 50%)")
    print(f"  Total Trades: {backtest_results.total_trades} (threshold: > 20)")


def example_monitor_and_retire():
    """Example: Monitor active strategy and auto-retire if underperforming."""
    # Initialize components
    # strategy_engine = StrategyEngine(llm_service, market_data, websocket_manager)
    # portfolio_manager = PortfolioManager(strategy_engine)

    # Active strategy with poor performance
    strategy = Strategy(
        id="failing-strategy-1",
        name="Underperforming Strategy",
        description="Strategy that is no longer working",
        status=StrategyStatus.DEMO,
        rules={"entry": ["Price > SMA_20"], "exit": ["Price < SMA_20"]},
        symbols=["AAPL"],
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        performance=PerformanceMetrics(
            total_return=-0.08,
            sharpe_ratio=0.3,  # < 0.5 with 30+ trades
            max_drawdown=0.18,  # > 0.15
            win_rate=0.35,  # < 0.4 with 50+ trades
            total_trades=55,
        ),
    )

    # Check retirement triggers
    # retirement_reason = portfolio_manager.check_retirement_triggers(strategy)

    # if retirement_reason:
    #     # Auto-retire the strategy
    #     portfolio_manager.auto_retire_strategy(strategy, retirement_reason)
    #     print(f"✗ Strategy {strategy.name} retired: {retirement_reason}")

    print("\nExample: Strategy triggers retirement")
    print(f"  Sharpe Ratio: {strategy.performance.sharpe_ratio:.2f} (threshold: < 0.5 with 30+ trades)")
    print(f"  Max Drawdown: {strategy.performance.max_drawdown:.2%} (threshold: > 15%)")
    print(f"  Win Rate: {strategy.performance.win_rate:.2%} (threshold: < 40% with 50+ trades)")
    print(f"  Total Trades: {strategy.performance.total_trades}")


def example_portfolio_lifecycle():
    """Example: Complete portfolio lifecycle management."""
    print("\n" + "=" * 60)
    print("PORTFOLIO MANAGER LIFECYCLE EXAMPLE")
    print("=" * 60)

    print("\n1. STRATEGY PROPOSAL & EVALUATION")
    print("   - Market regime detected: TRENDING_UP")
    print("   - Proposed 5 momentum strategies")
    print("   - Backtested all proposals")

    print("\n2. AUTO-ACTIVATION")
    print("   - Strategy A: Sharpe 2.1, Drawdown 12%, Win Rate 62% → ACTIVATED")
    print("   - Strategy B: Sharpe 1.8, Drawdown 10%, Win Rate 58% → ACTIVATED")
    print("   - Strategy C: Sharpe 1.2, Drawdown 8%, Win Rate 55% → REJECTED (low Sharpe)")
    print("   - Strategy D: Sharpe 2.0, Drawdown 18%, Win Rate 60% → REJECTED (high drawdown)")
    print("   - Strategy E: Sharpe 1.9, Drawdown 11%, Win Rate 48% → REJECTED (low win rate)")

    print("\n3. PORTFOLIO STATUS")
    print("   - Active Strategies: 2")
    print("   - Allocation: 50% each")
    print("   - Portfolio Sharpe: 1.95")

    print("\n4. CONTINUOUS MONITORING")
    print("   - Strategy A: Performance stable")
    print("   - Strategy B: Sharpe dropped to 0.4 after 35 trades → RETIRED")

    print("\n5. REBALANCING")
    print("   - Strategy A: Allocation increased to 100%")
    print("   - New proposals evaluated for diversification")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    example_evaluate_and_activate()
    example_monitor_and_retire()
    example_portfolio_lifecycle()
