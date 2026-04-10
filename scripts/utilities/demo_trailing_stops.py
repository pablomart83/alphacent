#!/usr/bin/env python3
"""
Demo script to show trailing stop-loss functionality.

This script demonstrates how trailing stops work with example positions.
"""

from datetime import datetime
from unittest.mock import Mock

from src.execution.position_manager import PositionManager
from src.models.dataclasses import Position, RiskConfig
from src.models.enums import PositionSide


def demo_trailing_stops():
    """Demonstrate trailing stop-loss logic."""
    print("=" * 70)
    print("TRAILING STOP-LOSS DEMONSTRATION")
    print("=" * 70)
    print()
    
    # Create mock eToro client
    mock_client = Mock()
    mock_client.update_position_stop_loss = Mock(return_value={"success": True})
    
    # Create risk config with trailing stops enabled
    risk_config = RiskConfig(
        trailing_stop_enabled=True,
        trailing_stop_activation_pct=0.05,  # 5% profit to activate
        trailing_stop_distance_pct=0.03     # 3% trailing distance
    )
    
    print("Risk Configuration:")
    print(f"  Trailing Stop Enabled: {risk_config.trailing_stop_enabled}")
    print(f"  Activation Threshold: {risk_config.trailing_stop_activation_pct * 100}%")
    print(f"  Trailing Distance: {risk_config.trailing_stop_distance_pct * 100}%")
    print()
    
    # Create position manager
    manager = PositionManager(mock_client, risk_config)
    
    # Example 1: Long position with sufficient profit
    print("-" * 70)
    print("Example 1: Long Position with 10% Profit")
    print("-" * 70)
    
    position1 = Position(
        id="pos1",
        strategy_id="momentum_strategy",
        symbol="SPY",
        side=PositionSide.LONG,
        quantity=10.0,
        entry_price=100.0,
        current_price=110.0,  # 10% profit
        unrealized_pnl=100.0,
        realized_pnl=0.0,
        opened_at=datetime.now(),
        etoro_position_id="etoro_pos1",
        stop_loss=95.0,  # Old stop-loss at -5%
        take_profit=120.0,
        closed_at=None
    )
    
    print(f"  Symbol: {position1.symbol}")
    print(f"  Entry Price: ${position1.entry_price:.2f}")
    print(f"  Current Price: ${position1.current_price:.2f}")
    print(f"  Profit: {((position1.current_price - position1.entry_price) / position1.entry_price) * 100:.1f}%")
    print(f"  Old Stop-Loss: ${position1.stop_loss:.2f}")
    
    manager.check_trailing_stops([position1])
    
    new_stop = position1.current_price * (1 - risk_config.trailing_stop_distance_pct)
    print(f"  New Stop-Loss: ${new_stop:.2f} (3% below current price)")
    print(f"  Protection: ${new_stop - position1.entry_price:.2f} profit locked in")
    print()
    
    # Example 2: Position with insufficient profit
    print("-" * 70)
    print("Example 2: Long Position with 3% Profit (Below Threshold)")
    print("-" * 70)
    
    position2 = Position(
        id="pos2",
        strategy_id="mean_reversion_strategy",
        symbol="QQQ",
        side=PositionSide.LONG,
        quantity=5.0,
        entry_price=200.0,
        current_price=206.0,  # 3% profit (below 5% threshold)
        unrealized_pnl=30.0,
        realized_pnl=0.0,
        opened_at=datetime.now(),
        etoro_position_id="etoro_pos2",
        stop_loss=190.0,
        take_profit=220.0,
        closed_at=None
    )
    
    print(f"  Symbol: {position2.symbol}")
    print(f"  Entry Price: ${position2.entry_price:.2f}")
    print(f"  Current Price: ${position2.current_price:.2f}")
    print(f"  Profit: {((position2.current_price - position2.entry_price) / position2.entry_price) * 100:.1f}%")
    print(f"  Stop-Loss: ${position2.stop_loss:.2f}")
    print(f"  Result: No update (profit below 5% activation threshold)")
    print()
    
    # Example 3: Short position with profit
    print("-" * 70)
    print("Example 3: Short Position with 10% Profit")
    print("-" * 70)
    
    position3 = Position(
        id="pos3",
        strategy_id="short_strategy",
        symbol="TSLA",
        side=PositionSide.SHORT,
        quantity=10.0,
        entry_price=100.0,
        current_price=90.0,  # 10% profit on short (price fell)
        unrealized_pnl=100.0,
        realized_pnl=0.0,
        opened_at=datetime.now(),
        etoro_position_id="etoro_pos3",
        stop_loss=105.0,  # Old stop-loss
        take_profit=80.0,
        closed_at=None
    )
    
    print(f"  Symbol: {position3.symbol}")
    print(f"  Entry Price: ${position3.entry_price:.2f}")
    print(f"  Current Price: ${position3.current_price:.2f}")
    print(f"  Profit: {((position3.entry_price - position3.current_price) / position3.entry_price) * 100:.1f}%")
    print(f"  Old Stop-Loss: ${position3.stop_loss:.2f}")
    
    manager.check_trailing_stops([position3])
    
    new_stop_short = position3.current_price * (1 + risk_config.trailing_stop_distance_pct)
    print(f"  New Stop-Loss: ${new_stop_short:.2f} (3% above current price)")
    print(f"  Protection: ${position3.entry_price - new_stop_short:.2f} profit locked in")
    print()
    
    # Example 4: Position moving higher - multiple updates
    print("-" * 70)
    print("Example 4: Position Moving Higher - Multiple Updates")
    print("-" * 70)
    
    position4 = Position(
        id="pos4",
        strategy_id="trend_following",
        symbol="AAPL",
        side=PositionSide.LONG,
        quantity=20.0,
        entry_price=150.0,
        current_price=165.0,  # 10% profit
        unrealized_pnl=300.0,
        realized_pnl=0.0,
        opened_at=datetime.now(),
        etoro_position_id="etoro_pos4",
        stop_loss=145.0,
        take_profit=180.0,
        closed_at=None
    )
    
    print(f"  Symbol: {position4.symbol}")
    print(f"  Entry Price: ${position4.entry_price:.2f}")
    print()
    
    # Simulate price moving up
    prices = [165.0, 170.0, 175.0, 180.0]
    for price in prices:
        position4.current_price = price
        profit_pct = ((price - position4.entry_price) / position4.entry_price) * 100
        
        old_stop = position4.stop_loss
        manager.check_trailing_stops([position4])
        
        print(f"  Price: ${price:.2f} ({profit_pct:.1f}% profit)")
        print(f"    Stop-Loss: ${old_stop:.2f} → ${position4.stop_loss:.2f}")
        print(f"    Locked Profit: ${position4.stop_loss - position4.entry_price:.2f}")
        print()
    
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    print("Trailing stops automatically protect profits by:")
    print("  1. Activating when position reaches 5% profit")
    print("  2. Moving stop-loss to 3% below current price")
    print("  3. Only moving stop-loss in favorable direction")
    print("  4. Locking in profits as price moves favorably")
    print()
    print("Benefits:")
    print("  ✓ Automatic profit protection")
    print("  ✓ No manual intervention required")
    print("  ✓ Lets winners run while protecting gains")
    print("  ✓ Works for both long and short positions")
    print()


if __name__ == "__main__":
    demo_trailing_stops()
