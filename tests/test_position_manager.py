"""Unit tests for PositionManager trailing stop-loss logic."""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

from src.execution.position_manager import PositionManager
from src.models.dataclasses import Position, RiskConfig
from src.models.enums import PositionSide, OrderSide, OrderType, OrderStatus
from src.api.etoro_client import EToroAPIError


@pytest.fixture
def mock_etoro_client():
    """Create mock eToro client."""
    client = Mock()
    client.update_position_stop_loss = Mock(return_value={"success": True})
    return client


@pytest.fixture
def risk_config_trailing_enabled():
    """Create risk config with trailing stops enabled."""
    return RiskConfig(
        trailing_stop_enabled=True,
        trailing_stop_activation_pct=0.05,  # 5% profit to activate
        trailing_stop_distance_pct=0.03     # 3% trailing distance
    )


@pytest.fixture
def risk_config_trailing_disabled():
    """Create risk config with trailing stops disabled."""
    return RiskConfig(
        trailing_stop_enabled=False
    )


class TestPositionManagerTrailingStops:
    """Test trailing stop-loss functionality."""

    def test_trailing_stops_disabled(self, mock_etoro_client, risk_config_trailing_disabled):
        """Test that trailing stops are skipped when disabled."""
        manager = PositionManager(mock_etoro_client, risk_config_trailing_disabled)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=110.0,  # 10% profit
                unrealized_pnl=100.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                stop_loss=95.0,
                take_profit=120.0,
                closed_at=None
            )
        ]
        
        orders = manager.check_trailing_stops(positions)
        
        assert len(orders) == 0
        mock_etoro_client.update_position_stop_loss.assert_not_called()

    def test_trailing_stop_not_activated_insufficient_profit(
        self, mock_etoro_client, risk_config_trailing_enabled
    ):
        """Test that trailing stop is not activated when profit is below threshold."""
        manager = PositionManager(mock_etoro_client, risk_config_trailing_enabled)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=102.0,  # 2% profit (below 3% ETF threshold)
                unrealized_pnl=20.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                stop_loss=95.0,
                take_profit=120.0,
                closed_at=None
            )
        ]
        
        orders = manager.check_trailing_stops(positions)
        
        assert len(orders) == 0
        mock_etoro_client.update_position_stop_loss.assert_not_called()

    def test_trailing_stop_activated_long_position(
        self, mock_etoro_client, risk_config_trailing_enabled
    ):
        """Test trailing stop activation for long position with sufficient profit."""
        manager = PositionManager(mock_etoro_client, risk_config_trailing_enabled)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=110.0,  # 10% profit (above 5% threshold)
                unrealized_pnl=100.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                stop_loss=95.0,  # Old stop-loss
                take_profit=120.0,
                closed_at=None
            )
        ]
        
        orders = manager.check_trailing_stops(positions)
        
        # SPY is an ETF → 4% trailing distance
        # Expected new stop-loss: 110 * (1 - 0.04) = 105.6
        expected_stop = 110.0 * 0.96
        
        mock_etoro_client.update_position_stop_loss.assert_called_once_with(
            position_id="etoro_pos1",
            stop_loss_rate=expected_stop
        )
        
        # Position should be updated
        assert positions[0].stop_loss == expected_stop

    def test_trailing_stop_not_updated_when_worse(
        self, mock_etoro_client, risk_config_trailing_enabled
    ):
        """Test that trailing stop is not updated when new stop is worse than current."""
        manager = PositionManager(mock_etoro_client, risk_config_trailing_enabled)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=110.0,  # 10% profit
                unrealized_pnl=100.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                stop_loss=108.0,  # Already has a better stop-loss (110 * 0.97 = 106.7)
                take_profit=120.0,
                closed_at=None
            )
        ]
        
        orders = manager.check_trailing_stops(positions)
        
        # Should not update because new stop (106.7) is worse than current (108.0)
        mock_etoro_client.update_position_stop_loss.assert_not_called()

    def test_trailing_stop_initial_set_no_existing_stop(
        self, mock_etoro_client, risk_config_trailing_enabled
    ):
        """Test that trailing stop is set when position has no existing stop-loss."""
        manager = PositionManager(mock_etoro_client, risk_config_trailing_enabled)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=110.0,  # 10% profit
                unrealized_pnl=100.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                stop_loss=None,  # No existing stop-loss
                take_profit=120.0,
                closed_at=None
            )
        ]
        
        orders = manager.check_trailing_stops(positions)
        
        # Expected new stop-loss: SPY is ETF → 4% distance: 110 * (1 - 0.04) = 105.6
        expected_stop = 110.0 * 0.96
        
        mock_etoro_client.update_position_stop_loss.assert_called_once_with(
            position_id="etoro_pos1",
            stop_loss_rate=expected_stop
        )
        
        assert positions[0].stop_loss == expected_stop

    def test_trailing_stop_short_position(
        self, mock_etoro_client, risk_config_trailing_enabled
    ):
        """Test trailing stop for short position (stop moves down as price falls)."""
        manager = PositionManager(mock_etoro_client, risk_config_trailing_enabled)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.SHORT,
                quantity=10.0,
                entry_price=100.0,
                current_price=90.0,  # 10% profit on short (price fell)
                unrealized_pnl=100.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                stop_loss=105.0,  # Old stop-loss
                take_profit=80.0,
                closed_at=None
            )
        ]
        
        orders = manager.check_trailing_stops(positions)
        
        # Expected new stop-loss for short: SPY is ETF → 4% distance: 90 * (1 + 0.04) = 93.6
        expected_stop = 90.0 * 1.04
        
        mock_etoro_client.update_position_stop_loss.assert_called_once_with(
            position_id="etoro_pos1",
            stop_loss_rate=expected_stop
        )
        
        assert positions[0].stop_loss == expected_stop

    def test_trailing_stop_handles_api_error(
        self, mock_etoro_client, risk_config_trailing_enabled
    ):
        """Test that API errors are handled gracefully and don't stop processing."""
        mock_etoro_client.update_position_stop_loss.side_effect = EToroAPIError("API error")
        
        manager = PositionManager(mock_etoro_client, risk_config_trailing_enabled)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=110.0,
                unrealized_pnl=100.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                stop_loss=95.0,
                take_profit=120.0,
                closed_at=None
            )
        ]
        
        # Should not raise exception
        orders = manager.check_trailing_stops(positions)
        
        # Position should not be updated due to error
        assert positions[0].stop_loss == 95.0

    def test_trailing_stop_skips_closed_positions(
        self, mock_etoro_client, risk_config_trailing_enabled
    ):
        """Test that closed positions are skipped."""
        manager = PositionManager(mock_etoro_client, risk_config_trailing_enabled)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=110.0,
                unrealized_pnl=0.0,
                realized_pnl=100.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                stop_loss=95.0,
                take_profit=120.0,
                closed_at=datetime.now()  # Position is closed
            )
        ]
        
        orders = manager.check_trailing_stops(positions)
        
        mock_etoro_client.update_position_stop_loss.assert_not_called()

    def test_trailing_stop_multiple_positions(
        self, mock_etoro_client, risk_config_trailing_enabled
    ):
        """Test trailing stops for multiple positions."""
        manager = PositionManager(mock_etoro_client, risk_config_trailing_enabled)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=110.0,  # 10% profit - should update
                unrealized_pnl=100.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                stop_loss=95.0,
                take_profit=120.0,
                closed_at=None
            ),
            Position(
                id="pos2",
                strategy_id="strat2",
                symbol="QQQ",
                side=PositionSide.LONG,
                quantity=5.0,
                entry_price=200.0,
                current_price=203.0,  # 1.5% profit - should not update (below 5% threshold)
                unrealized_pnl=15.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos2",
                stop_loss=190.0,
                take_profit=220.0,
                closed_at=None
            ),
            Position(
                id="pos3",
                strategy_id="strat3",
                symbol="AAPL",
                side=PositionSide.LONG,
                quantity=20.0,
                entry_price=150.0,
                current_price=165.0,  # 10% profit - should update
                unrealized_pnl=300.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos3",
                stop_loss=145.0,
                take_profit=180.0,
                closed_at=None
            )
        ]
        
        orders = manager.check_trailing_stops(positions)
        
        # Should update 2 positions (pos1 and pos3)
        assert mock_etoro_client.update_position_stop_loss.call_count == 2
        
        # Verify the calls
        calls = mock_etoro_client.update_position_stop_loss.call_args_list
        assert any(call[1]["position_id"] == "etoro_pos1" for call in calls)
        assert any(call[1]["position_id"] == "etoro_pos3" for call in calls)

    def test_trailing_stop_calculation_precision(
        self, mock_etoro_client, risk_config_trailing_enabled
    ):
        """Test that trailing stop calculations are precise."""
        manager = PositionManager(mock_etoro_client, risk_config_trailing_enabled)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=115.50,  # 15.5% profit
                unrealized_pnl=155.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                stop_loss=100.0,
                take_profit=130.0,
                closed_at=None
            )
        ]
        
        orders = manager.check_trailing_stops(positions)
        
        # Expected: SPY is ETF → 4% distance: 115.50 * 0.96 = 110.88
        expected_stop = 115.50 * 0.96
        
        mock_etoro_client.update_position_stop_loss.assert_called_once()
        call_args = mock_etoro_client.update_position_stop_loss.call_args
        
        assert abs(call_args[1]["stop_loss_rate"] - expected_stop) < 0.01
        assert abs(positions[0].stop_loss - expected_stop) < 0.01



class TestPositionManagerPartialExits:
    """Test partial exit functionality."""

    def test_partial_exits_disabled(self, mock_etoro_client):
        """Test that partial exits are skipped when disabled."""
        risk_config = RiskConfig(partial_exit_enabled=False)
        manager = PositionManager(mock_etoro_client, risk_config)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=110.0,  # 10% profit
                unrealized_pnl=100.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                stop_loss=95.0,
                take_profit=120.0,
                closed_at=None,
                partial_exits=[]
            )
        ]
        
        orders = manager.check_partial_exits(positions)
        
        assert len(orders) == 0

    def test_partial_exit_no_levels_configured(self, mock_etoro_client):
        """Test that partial exits are skipped when no levels configured."""
        risk_config = RiskConfig(
            partial_exit_enabled=True,
            partial_exit_levels=[]
        )
        manager = PositionManager(mock_etoro_client, risk_config)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=110.0,
                unrealized_pnl=100.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                closed_at=None,
                partial_exits=[]
            )
        ]
        
        orders = manager.check_partial_exits(positions)
        
        assert len(orders) == 0

    def test_partial_exit_profit_threshold_not_met(self, mock_etoro_client):
        """Test that partial exit is not triggered when profit threshold not met."""
        risk_config = RiskConfig(
            partial_exit_enabled=True,
            partial_exit_levels=[{"profit_pct": 0.10, "exit_pct": 0.5}]  # 10% profit threshold
        )
        manager = PositionManager(mock_etoro_client, risk_config)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=105.0,  # 5% profit (below 10% threshold)
                unrealized_pnl=50.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                closed_at=None,
                partial_exits=[]
            )
        ]
        
        orders = manager.check_partial_exits(positions)
        
        assert len(orders) == 0

    def test_partial_exit_triggered_long_position(self, mock_etoro_client):
        """Test partial exit is triggered for long position with sufficient profit."""
        risk_config = RiskConfig(
            partial_exit_enabled=True,
            partial_exit_levels=[{"profit_pct": 0.05, "exit_pct": 0.5}]  # 5% profit -> 50% exit
        )
        manager = PositionManager(mock_etoro_client, risk_config)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=110.0,  # 10% profit (above 5% threshold)
                unrealized_pnl=100.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                closed_at=None,
                partial_exits=[]
            )
        ]
        
        orders = manager.check_partial_exits(positions)
        
        assert len(orders) == 1
        order = orders[0]
        
        # Verify order details
        assert order.strategy_id == "strat1"
        assert order.symbol == "SPY"
        assert order.side == OrderSide.SELL  # Opposite of LONG position
        assert order.order_type == OrderType.MARKET
        assert order.quantity == 5.0  # 50% of 10.0
        assert order.status == OrderStatus.PENDING
        assert order.price == 110.0
        
        # Verify partial exit was recorded
        assert len(positions[0].partial_exits) == 1
        exit_record = positions[0].partial_exits[0]
        assert exit_record["profit_level"] == "0.0500"
        assert exit_record["exit_pct"] == 0.5
        assert exit_record["exit_quantity"] == 5.0
        assert exit_record["exit_price"] == 110.0
        
        # Verify position quantity was updated
        assert positions[0].quantity == 5.0  # 10.0 - 5.0

    def test_partial_exit_triggered_short_position(self, mock_etoro_client):
        """Test partial exit for short position (profit when price falls)."""
        risk_config = RiskConfig(
            partial_exit_enabled=True,
            partial_exit_levels=[{"profit_pct": 0.05, "exit_pct": 0.5}]
        )
        manager = PositionManager(mock_etoro_client, risk_config)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.SHORT,
                quantity=10.0,
                entry_price=100.0,
                current_price=90.0,  # 10% profit on short (price fell)
                unrealized_pnl=100.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                closed_at=None,
                partial_exits=[]
            )
        ]
        
        orders = manager.check_partial_exits(positions)
        
        assert len(orders) == 1
        order = orders[0]
        
        # For short position, partial exit is a BUY order
        assert order.side == OrderSide.BUY
        assert order.quantity == 5.0
        assert order.price == 90.0

    def test_partial_exit_not_retriggered(self, mock_etoro_client):
        """Test that partial exit is not triggered again for same level."""
        risk_config = RiskConfig(
            partial_exit_enabled=True,
            partial_exit_levels=[{"profit_pct": 0.05, "exit_pct": 0.5}]
        )
        manager = PositionManager(mock_etoro_client, risk_config)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=110.0,  # 10% profit
                unrealized_pnl=100.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                closed_at=None,
                partial_exits=[
                    {
                        "profit_level": "0.0500",  # Already triggered at 5% level
                        "profit_pct": 0.08,
                        "exit_pct": 0.5,
                        "exit_quantity": 5.0,
                        "exit_price": 108.0,
                        "timestamp": datetime.now().isoformat()
                    }
                ]
            )
        ]
        
        orders = manager.check_partial_exits(positions)
        
        # Should not create another order for same level
        assert len(orders) == 0

    def test_partial_exit_multiple_levels(self, mock_etoro_client):
        """Test multiple partial exit levels."""
        risk_config = RiskConfig(
            partial_exit_enabled=True,
            partial_exit_levels=[
                {"profit_pct": 0.05, "exit_pct": 0.3},  # 5% profit -> 30% exit
                {"profit_pct": 0.10, "exit_pct": 0.5},  # 10% profit -> 50% exit
            ]
        )
        manager = PositionManager(mock_etoro_client, risk_config)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=115.0,  # 15% profit (triggers both levels)
                unrealized_pnl=150.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                closed_at=None,
                partial_exits=[]
            )
        ]
        
        orders = manager.check_partial_exits(positions)
        
        # Should create 2 orders (one for each level)
        assert len(orders) == 2
        
        # First order: 30% of 10.0 = 3.0
        assert orders[0].quantity == 3.0
        
        # Second order: 50% of 10.0 = 5.0
        assert orders[1].quantity == 5.0
        
        # Verify both exits were recorded
        assert len(positions[0].partial_exits) == 2

    def test_partial_exit_skips_closed_positions(self, mock_etoro_client):
        """Test that closed positions are skipped."""
        risk_config = RiskConfig(
            partial_exit_enabled=True,
            partial_exit_levels=[{"profit_pct": 0.05, "exit_pct": 0.5}]
        )
        manager = PositionManager(mock_etoro_client, risk_config)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=110.0,
                unrealized_pnl=0.0,
                realized_pnl=100.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                closed_at=datetime.now(),  # Position is closed
                partial_exits=[]
            )
        ]
        
        orders = manager.check_partial_exits(positions)
        
        assert len(orders) == 0

    def test_partial_exit_invalid_level_configuration(self, mock_etoro_client):
        """Test that invalid level configurations are skipped."""
        risk_config = RiskConfig(
            partial_exit_enabled=True,
            partial_exit_levels=[
                {"profit_pct": 0.0, "exit_pct": 0.5},    # Invalid: profit_pct = 0
                {"profit_pct": 0.05, "exit_pct": 0.0},   # Invalid: exit_pct = 0
                {"profit_pct": 0.05, "exit_pct": 1.5},   # Invalid: exit_pct > 1.0
                {"profit_pct": 0.10, "exit_pct": 0.5},   # Valid
            ]
        )
        manager = PositionManager(mock_etoro_client, risk_config)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=115.0,  # 15% profit
                unrealized_pnl=150.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                closed_at=None,
                partial_exits=[]
            )
        ]
        
        orders = manager.check_partial_exits(positions)
        
        # Should only create 1 order (for the valid level)
        assert len(orders) == 1
        assert orders[0].quantity == 5.0  # 50% of 10.0

    def test_partial_exit_multiple_positions(self, mock_etoro_client):
        """Test partial exits for multiple positions."""
        risk_config = RiskConfig(
            partial_exit_enabled=True,
            partial_exit_levels=[{"profit_pct": 0.05, "exit_pct": 0.5}]
        )
        manager = PositionManager(mock_etoro_client, risk_config)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=110.0,  # 10% profit - should trigger
                unrealized_pnl=100.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                closed_at=None,
                partial_exits=[]
            ),
            Position(
                id="pos2",
                strategy_id="strat2",
                symbol="QQQ",
                side=PositionSide.LONG,
                quantity=5.0,
                entry_price=200.0,
                current_price=203.0,  # 1.5% profit - should not trigger
                unrealized_pnl=15.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos2",
                closed_at=None,
                partial_exits=[]
            ),
            Position(
                id="pos3",
                strategy_id="strat3",
                symbol="AAPL",
                side=PositionSide.LONG,
                quantity=20.0,
                entry_price=150.0,
                current_price=165.0,  # 10% profit - should trigger
                unrealized_pnl=300.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos3",
                closed_at=None,
                partial_exits=[]
            )
        ]
        
        orders = manager.check_partial_exits(positions)
        
        # Should create 2 orders (pos1 and pos3)
        assert len(orders) == 2
        
        # Verify orders are for correct positions
        order_symbols = {order.symbol for order in orders}
        assert order_symbols == {"SPY", "AAPL"}

    def test_partial_exit_quantity_calculation(self, mock_etoro_client):
        """Test that exit quantity is calculated correctly."""
        risk_config = RiskConfig(
            partial_exit_enabled=True,
            partial_exit_levels=[
                {"profit_pct": 0.05, "exit_pct": 0.25},  # 25% exit
                {"profit_pct": 0.10, "exit_pct": 0.33},  # 33% exit
            ]
        )
        manager = PositionManager(mock_etoro_client, risk_config)
        
        positions = [
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=100.0,
                entry_price=100.0,
                current_price=115.0,  # 15% profit
                unrealized_pnl=1500.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                closed_at=None,
                partial_exits=[]
            )
        ]
        
        orders = manager.check_partial_exits(positions)
        
        assert len(orders) == 2
        
        # First order: 25% of 100.0 = 25.0
        assert orders[0].quantity == 25.0
        
        # Second order: 33% of 100.0 = 33.0
        assert orders[1].quantity == 33.0
        
        # Position quantity should be reduced by total exits
        assert positions[0].quantity == 42.0  # 100.0 - 25.0 - 33.0
