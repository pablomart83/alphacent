"""Unit tests for OrderExecutor."""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch
import uuid

from src.execution.order_executor import OrderExecutor, OrderExecutionError, Fill
from src.api.etoro_client import EToroAPIClient, EToroAPIError
from src.data.market_hours_manager import MarketHoursManager, AssetClass
from src.models import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    SignalAction,
    TradingSignal,
    TradingMode,
)


@pytest.fixture
def mock_etoro_client():
    """Create mock eToro client."""
    client = Mock(spec=EToroAPIClient)
    client.mode = TradingMode.DEMO
    return client


@pytest.fixture
def mock_market_hours():
    """Create mock market hours manager."""
    manager = Mock(spec=MarketHoursManager)
    manager.is_market_open.return_value = True  # Default to market open
    return manager


@pytest.fixture
def order_executor(mock_etoro_client, mock_market_hours):
    """Create OrderExecutor instance."""
    return OrderExecutor(
        etoro_client=mock_etoro_client,
        market_hours=mock_market_hours,
        poll_interval=0.1,  # Fast polling for tests
        max_poll_attempts=10
    )


@pytest.fixture
def sample_signal():
    """Create sample trading signal."""
    return TradingSignal(
        strategy_id="test_strategy",
        symbol="AAPL",
        action=SignalAction.ENTER_LONG,
        confidence=0.8,
        reasoning="Test signal",
        generated_at=datetime.now(),
        metadata={}
    )


class TestOrderExecutor:
    """Test OrderExecutor functionality."""

    def test_initialization(self, order_executor):
        """Test OrderExecutor initializes correctly."""
        assert order_executor is not None
        assert order_executor._orders == {}
        assert order_executor._positions == {}
        assert order_executor._queued_orders == []

    def test_execute_signal_market_open(self, order_executor, mock_etoro_client, sample_signal):
        """Test executing signal when market is open."""
        # Setup mock response
        mock_etoro_client.place_order.return_value = {
            "order_id": "etoro_123",
            "status": "SUBMITTED"
        }

        # Execute signal
        order = order_executor.execute_signal(sample_signal, position_size=100.0)

        # Verify order created
        assert order is not None
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.MARKET
        assert order.quantity == 100.0
        assert order.status == OrderStatus.PENDING
        assert order.etoro_order_id == "etoro_123"

        # Verify eToro API called
        mock_etoro_client.place_order.assert_called_once()

    def test_execute_signal_market_closed(self, order_executor, mock_etoro_client, mock_market_hours, sample_signal):
        """Test executing signal when market is closed queues order."""
        # Setup market closed
        mock_market_hours.is_market_open.return_value = False

        # Execute signal
        order = order_executor.execute_signal(sample_signal, position_size=100.0)

        # Verify order queued
        assert order.status == OrderStatus.PENDING
        assert order.etoro_order_id is None
        assert len(order_executor._queued_orders) == 1
        assert order_executor._queued_orders[0] == order

        # Verify eToro API not called
        mock_etoro_client.place_order.assert_not_called()

    def test_signal_to_order_params_enter_long(self, order_executor):
        """Test converting ENTER_LONG signal to order params."""
        side, order_type = order_executor._signal_to_order_params(SignalAction.ENTER_LONG)
        assert side == OrderSide.BUY
        assert order_type == OrderType.MARKET

    def test_signal_to_order_params_enter_short(self, order_executor):
        """Test converting ENTER_SHORT signal to order params."""
        side, order_type = order_executor._signal_to_order_params(SignalAction.ENTER_SHORT)
        assert side == OrderSide.SELL
        assert order_type == OrderType.MARKET

    def test_signal_to_order_params_exit_long(self, order_executor):
        """Test converting EXIT_LONG signal to order params."""
        side, order_type = order_executor._signal_to_order_params(SignalAction.EXIT_LONG)
        assert side == OrderSide.SELL
        assert order_type == OrderType.MARKET

    def test_signal_to_order_params_exit_short(self, order_executor):
        """Test converting EXIT_SHORT signal to order params."""
        side, order_type = order_executor._signal_to_order_params(SignalAction.EXIT_SHORT)
        assert side == OrderSide.BUY
        assert order_type == OrderType.MARKET

    def test_determine_asset_class_crypto(self, order_executor):
        """Test determining cryptocurrency asset class."""
        assert order_executor._determine_asset_class("BTC-USD") == AssetClass.CRYPTOCURRENCY
        assert order_executor._determine_asset_class("ETH") == AssetClass.CRYPTOCURRENCY

    def test_determine_asset_class_stock(self, order_executor):
        """Test determining stock asset class."""
        assert order_executor._determine_asset_class("AAPL") == AssetClass.STOCK
        assert order_executor._determine_asset_class("TSLA") == AssetClass.STOCK

    def test_submit_order_success(self, order_executor, mock_etoro_client):
        """Test successful order submission."""
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING
        )

        mock_etoro_client.place_order.return_value = {
            "order_id": "etoro_456",
            "status": "SUBMITTED"
        }

        order_executor._submit_order(order)

        assert order.status == OrderStatus.PENDING
        assert order.etoro_order_id == "etoro_456"
        assert order.submitted_at is not None

    def test_submit_order_failure(self, order_executor, mock_etoro_client):
        """Test order submission failure."""
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING
        )

        mock_etoro_client.place_order.side_effect = EToroAPIError("API error")

        with pytest.raises(OrderExecutionError):
            order_executor._submit_order(order)

        assert order.status == OrderStatus.FAILED

    def test_track_order_immediate_fill(self, order_executor, mock_etoro_client):
        """Test tracking order that fills immediately."""
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_789"
        )
        order_executor._orders[order.id] = order

        mock_etoro_client.get_order_status.return_value = {
            "status": "FILLED",
            "filled_at": datetime.now().isoformat(),
            "filled_price": 150.0,
            "filled_quantity": 100.0,
            "position_id": "pos_123"
        }

        status = order_executor.track_order(order.id, wait_for_fill=True)

        assert status == OrderStatus.FILLED
        assert order.filled_price == 150.0
        assert order.filled_quantity == 100.0

    def test_handle_fill_open_long_position(self, order_executor):
        """Test handling fill that opens long position."""
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.FILLED,
            etoro_order_id="etoro_999"
        )

        fill = Fill(
            order_id=order.id,
            filled_quantity=100.0,
            filled_price=150.0,
            filled_at=datetime.now(),
            etoro_position_id="pos_456"
        )

        order_executor.handle_fill(order, fill)

        # Verify position created
        positions = order_executor.get_open_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"
        assert positions[0].side == PositionSide.LONG
        assert positions[0].quantity == 100.0
        assert positions[0].entry_price == 150.0

    def test_handle_fill_close_long_position(self, order_executor):
        """Test handling fill that closes long position."""
        # Create existing long position
        position = Position(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=100.0,
            entry_price=150.0,
            current_price=150.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="pos_789"
        )
        order_executor._positions[position.id] = position

        # Create sell order to close
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.FILLED,
            etoro_order_id="etoro_close"
        )

        fill = Fill(
            order_id=order.id,
            filled_quantity=100.0,
            filled_price=160.0,
            filled_at=datetime.now()
        )

        order_executor.handle_fill(order, fill)

        # Verify position closed with profit
        assert position.quantity == 0.0
        assert position.closed_at is not None
        assert position.realized_pnl == 1000.0  # (160 - 150) * 100

    def test_attach_stop_loss(self, order_executor, mock_etoro_client):
        """Test attaching stop loss to position."""
        position = Position(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=100.0,
            entry_price=150.0,
            current_price=150.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="pos_sl"
        )

        mock_etoro_client.place_order.return_value = {
            "order_id": "etoro_sl_123",
            "status": "SUBMITTED"
        }

        order_executor.attach_stop_loss(position, stop_price=145.0)

        assert position.stop_loss == 145.0
        mock_etoro_client.place_order.assert_called_once()

    def test_attach_take_profit(self, order_executor, mock_etoro_client):
        """Test attaching take profit to position."""
        position = Position(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=100.0,
            entry_price=150.0,
            current_price=150.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="pos_tp"
        )

        mock_etoro_client.place_order.return_value = {
            "order_id": "etoro_tp_123",
            "status": "SUBMITTED"
        }

        order_executor.attach_take_profit(position, target_price=160.0)

        assert position.take_profit == 160.0
        mock_etoro_client.place_order.assert_called_once()

    def test_close_position(self, order_executor, mock_etoro_client):
        """Test closing a position."""
        position = Position(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=100.0,
            entry_price=150.0,
            current_price=155.0,
            unrealized_pnl=500.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="pos_close"
        )
        order_executor._positions[position.id] = position

        mock_etoro_client.place_order.return_value = {
            "order_id": "etoro_close_123",
            "status": "SUBMITTED"
        }

        order = order_executor.close_position(position.id)

        assert order.side == OrderSide.SELL  # Opposite of long position
        assert order.quantity == 100.0
        assert order.status == OrderStatus.PENDING

    def test_close_all_positions(self, order_executor, mock_etoro_client):
        """Test closing all positions."""
        # Create multiple positions
        for i in range(3):
            position = Position(
                id=str(uuid.uuid4()),
                strategy_id="test",
                symbol=f"STOCK{i}",
                side=PositionSide.LONG,
                quantity=100.0,
                entry_price=150.0,
                current_price=155.0,
                unrealized_pnl=500.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id=f"pos_{i}"
            )
            order_executor._positions[position.id] = position

        mock_etoro_client.place_order.return_value = {
            "order_id": "etoro_close",
            "status": "SUBMITTED"
        }

        orders = order_executor.close_all_positions()

        assert len(orders) == 3
        assert all(o.status == OrderStatus.PENDING for o in orders)

    def test_process_queued_orders(self, order_executor, mock_etoro_client, mock_market_hours):
        """Test processing queued orders when market opens."""
        # Create queued orders
        for i in range(3):
            order = Order(
                id=str(uuid.uuid4()),
                strategy_id="test",
                symbol="AAPL",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=100.0,
                status=OrderStatus.PENDING
            )
            order_executor._queued_orders.append(order)
            order_executor._orders[order.id] = order

        # Market opens
        mock_market_hours.is_market_open.return_value = True
        mock_etoro_client.place_order.return_value = {
            "order_id": "etoro_queued",
            "status": "SUBMITTED"
        }

        processed = order_executor.process_queued_orders()

        assert processed == 3
        assert len(order_executor._queued_orders) == 0

    def test_handle_order_failure(self, order_executor):
        """Test handling order failure."""
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING
        )

        error = EToroAPIError("Order rejected")
        order_executor.handle_order_failure(order, error)

        assert order.status == OrderStatus.FAILED

    def test_get_order(self, order_executor):
        """Test getting order by ID."""
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING
        )
        order_executor._orders[order.id] = order

        retrieved = order_executor.get_order(order.id)
        assert retrieved == order

    def test_get_position(self, order_executor):
        """Test getting position by ID."""
        position = Position(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=100.0,
            entry_price=150.0,
            current_price=155.0,
            unrealized_pnl=500.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="pos_get"
        )
        order_executor._positions[position.id] = position

        retrieved = order_executor.get_position(position.id)
        assert retrieved == position

    def test_get_open_positions(self, order_executor):
        """Test getting only open positions."""
        # Create open position
        open_pos = Position(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=100.0,
            entry_price=150.0,
            current_price=155.0,
            unrealized_pnl=500.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="pos_open"
        )
        order_executor._positions[open_pos.id] = open_pos

        # Create closed position
        closed_pos = Position(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="TSLA",
            side=PositionSide.LONG,
            quantity=50.0,
            entry_price=200.0,
            current_price=210.0,
            unrealized_pnl=0.0,
            realized_pnl=500.0,
            opened_at=datetime.now(),
            etoro_position_id="pos_closed",
            closed_at=datetime.now()
        )
        order_executor._positions[closed_pos.id] = closed_pos

        open_positions = order_executor.get_open_positions()
        assert len(open_positions) == 1
        assert open_positions[0].id == open_pos.id

    def test_auto_attach_stop_loss_take_profit_long(self, order_executor, mock_etoro_client):
        """Test automatic stop loss and take profit attachment for long position."""
        # Setup mock to track calls
        mock_etoro_client.place_order.return_value = {
            "order_id": "etoro_auto",
            "status": "SUBMITTED"
        }

        # Create order that will open a position
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.FILLED,
            etoro_order_id="etoro_999"
        )

        fill = Fill(
            order_id=order.id,
            filled_quantity=100.0,
            filled_price=150.0,
            filled_at=datetime.now(),
            etoro_position_id="pos_auto"
        )

        # Handle fill - should automatically attach stop loss and take profit
        order_executor.handle_fill(order, fill)

        # Verify position created
        positions = order_executor.get_open_positions()
        assert len(positions) == 1
        position = positions[0]

        # Verify stop loss and take profit were set
        assert position.stop_loss is not None
        assert position.take_profit is not None

        # For long position with entry at 150:
        # Stop loss should be below entry (150 * 0.98 = 147)
        # Take profit should be above entry (150 * 1.04 = 156)
        assert position.stop_loss < position.entry_price
        assert position.take_profit > position.entry_price
        assert abs(position.stop_loss - 147.0) < 0.01
        assert abs(position.take_profit - 156.0) < 0.01

        # Verify eToro API was called twice (once for stop loss, once for take profit)
        assert mock_etoro_client.place_order.call_count == 2

    def test_auto_attach_stop_loss_take_profit_short(self, order_executor, mock_etoro_client):
        """Test automatic stop loss and take profit attachment for short position."""
        # Setup mock to track calls
        mock_etoro_client.place_order.return_value = {
            "order_id": "etoro_auto_short",
            "status": "SUBMITTED"
        }

        # Create order that will open a short position
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="TSLA",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=50.0,
            status=OrderStatus.FILLED,
            etoro_order_id="etoro_short"
        )

        fill = Fill(
            order_id=order.id,
            filled_quantity=50.0,
            filled_price=200.0,
            filled_at=datetime.now(),
            etoro_position_id="pos_short_auto"
        )

        # Handle fill - should automatically attach stop loss and take profit
        order_executor.handle_fill(order, fill)

        # Verify position created
        positions = order_executor.get_open_positions()
        assert len(positions) == 1
        position = positions[0]

        # Verify stop loss and take profit were set
        assert position.stop_loss is not None
        assert position.take_profit is not None

        # For short position with entry at 200:
        # Stop loss should be above entry (200 * 1.02 = 204)
        # Take profit should be below entry (200 * 0.96 = 192)
        assert position.stop_loss > position.entry_price
        assert position.take_profit < position.entry_price
        assert abs(position.stop_loss - 204.0) < 0.01
        assert abs(position.take_profit - 192.0) < 0.01

        # Verify eToro API was called twice (once for stop loss, once for take profit)
        assert mock_etoro_client.place_order.call_count == 2

    def test_auto_attach_handles_failure_gracefully(self, order_executor, mock_etoro_client):
        """Test that automatic attachment failure doesn't prevent position creation."""
        # Setup mock to fail on stop loss attachment
        mock_etoro_client.place_order.side_effect = EToroAPIError("API error")

        # Create order that will open a position
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.FILLED,
            etoro_order_id="etoro_fail"
        )

        fill = Fill(
            order_id=order.id,
            filled_quantity=100.0,
            filled_price=150.0,
            filled_at=datetime.now(),
            etoro_position_id="pos_fail"
        )

        # Handle fill - should create position even if attachment fails
        order_executor.handle_fill(order, fill)

        # Verify position was still created
        positions = order_executor.get_open_positions()
        assert len(positions) == 1

        # Stop loss and take profit should be None due to failure
        position = positions[0]
        assert position.stop_loss is None
        assert position.take_profit is None

    def test_partial_fill_tracking(self, order_executor, mock_etoro_client):
        """Test partial fill tracking with remaining quantity calculation."""
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_partial"
        )
        order_executor._orders[order.id] = order

        # Mock partial fill response
        mock_etoro_client.get_order_status.return_value = {
            "status": "PARTIALLY_FILLED",
            "filled_quantity": 60.0,
            "average_fill_price": 150.0,
            "position_id": "pos_partial"
        }

        # Check order status
        status = order_executor._check_order_status(order)

        # Verify partial fill status
        assert status == OrderStatus.PARTIALLY_FILLED
        assert order.filled_quantity == 60.0
        assert order.filled_price == 150.0

        # Verify remaining quantity calculation
        remaining = order_executor.get_remaining_quantity(order.id)
        assert remaining == 40.0

        # Verify position created with partial quantity
        positions = order_executor.get_open_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 60.0

    def test_get_remaining_quantity(self, order_executor):
        """Test getting remaining quantity for orders."""
        # Order with no fills
        order1 = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING
        )
        order_executor._orders[order1.id] = order1
        assert order_executor.get_remaining_quantity(order1.id) == 100.0

        # Order with partial fill
        order2 = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="TSLA",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PARTIALLY_FILLED,
            filled_quantity=60.0
        )
        order_executor._orders[order2.id] = order2
        assert order_executor.get_remaining_quantity(order2.id) == 40.0

        # Order fully filled
        order3 = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="MSFT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.FILLED,
            filled_quantity=100.0
        )
        order_executor._orders[order3.id] = order3
        assert order_executor.get_remaining_quantity(order3.id) == 0.0

    def test_get_remaining_quantity_not_found(self, order_executor):
        """Test getting remaining quantity for non-existent order."""
        with pytest.raises(OrderExecutionError):
            order_executor.get_remaining_quantity("nonexistent")

    def test_handle_order_failure_with_retry(self, order_executor, mock_etoro_client):
        """Test order failure handling with retry logic for transient errors."""
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING
        )
        order_executor._orders[order.id] = order

        # First attempt fails with transient error, second succeeds
        mock_etoro_client.place_order.side_effect = [
            EToroAPIError("Connection timeout"),
            {"order_id": "etoro_retry_success", "status": "SUBMITTED"}
        ]

        # Handle failure - should retry and succeed
        error = EToroAPIError("Connection timeout")
        result = order_executor.handle_order_failure(order, error, retry_count=0)

        # Verify retry was attempted and succeeded
        assert result is True
        assert order.status == OrderStatus.PENDING
        assert order.etoro_order_id == "etoro_retry_success"

    def test_handle_order_failure_max_retries(self, order_executor, mock_etoro_client):
        """Test order failure handling exhausts retries."""
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING
        )
        order_executor._orders[order.id] = order

        # All attempts fail with transient error
        mock_etoro_client.place_order.side_effect = EToroAPIError("Connection timeout")

        # Handle failure - should retry 3 times then give up
        error = EToroAPIError("Connection timeout")
        result = order_executor.handle_order_failure(order, error, retry_count=0)

        # Verify retries exhausted
        assert result is False
        assert order.status == OrderStatus.FAILED

    def test_handle_order_failure_non_transient(self, order_executor, mock_etoro_client):
        """Test order failure handling with non-transient error (no retry)."""
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING
        )
        order_executor._orders[order.id] = order

        # Non-transient error (order rejected)
        error = EToroAPIError("Order rejected: insufficient funds")
        result = order_executor.handle_order_failure(order, error, retry_count=0)

        # Verify no retry attempted
        assert result is False
        assert order.status == OrderStatus.FAILED
        mock_etoro_client.place_order.assert_not_called()

    def test_is_transient_error(self, order_executor):
        """Test transient error detection."""
        # Transient errors
        assert order_executor._is_transient_error(Exception("Connection timeout"))
        assert order_executor._is_transient_error(Exception("Network error"))
        assert order_executor._is_transient_error(Exception("Service temporarily unavailable"))
        assert order_executor._is_transient_error(Exception("Rate limit exceeded"))
        assert order_executor._is_transient_error(Exception("503 Service Unavailable"))
        assert order_executor._is_transient_error(Exception("504 Gateway Timeout"))

        # Non-transient errors
        assert not order_executor._is_transient_error(Exception("Order rejected"))
        assert not order_executor._is_transient_error(Exception("Insufficient funds"))
        assert not order_executor._is_transient_error(Exception("Invalid symbol"))
        assert not order_executor._is_transient_error(Exception("400 Bad Request"))

    def test_track_order_continues_on_partial_fill(self, order_executor, mock_etoro_client):
        """Test that order tracking continues when order is partially filled."""
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_track_partial"
        )
        order_executor._orders[order.id] = order

        # Mock responses: partial fill, then full fill
        mock_etoro_client.get_order_status.side_effect = [
            {
                "status": "PARTIALLY_FILLED",
                "filled_quantity": 60.0,
                "average_fill_price": 150.0,
                "position_id": "pos_track"
            },
            {
                "status": "FILLED",
                "filled_at": datetime.now().isoformat(),
                "filled_price": 150.0,
                "filled_quantity": 100.0,
                "position_id": "pos_track"
            }
        ]

        # Track order - should continue polling after partial fill
        status = order_executor.track_order(order.id, wait_for_fill=True)

        # Verify final status is FILLED
        assert status == OrderStatus.FILLED
        assert order.filled_quantity == 100.0

        # Verify API was called twice (partial, then full)
        assert mock_etoro_client.get_order_status.call_count == 2




class TestMarketHoursEnforcement:
    """Test market hours enforcement for orders (Task 7.8)."""

    def test_order_queued_when_stock_market_closed(self, order_executor, mock_etoro_client, mock_market_hours):
        """Test order is queued when stock market is closed."""
        # Setup market closed for stocks
        mock_market_hours.is_market_open.return_value = False

        signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test signal",
            generated_at=datetime.now(),
            metadata={}
        )

        # Execute signal
        order = order_executor.execute_signal(signal, position_size=100.0)

        # Verify order queued, not submitted
        assert order.status == OrderStatus.PENDING
        assert order.etoro_order_id is None
        assert order.submitted_at is None
        assert len(order_executor._queued_orders) == 1
        assert order_executor._queued_orders[0] == order

        # Verify eToro API not called
        mock_etoro_client.place_order.assert_not_called()

    def test_order_submitted_when_stock_market_open(self, order_executor, mock_etoro_client, mock_market_hours):
        """Test order is submitted immediately when stock market is open."""
        # Setup market open for stocks
        mock_market_hours.is_market_open.return_value = True

        mock_etoro_client.place_order.return_value = {
            "order_id": "etoro_123",
            "status": "SUBMITTED"
        }

        signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test signal",
            generated_at=datetime.now(),
            metadata={}
        )

        # Execute signal
        order = order_executor.execute_signal(signal, position_size=100.0)

        # Verify order submitted immediately
        assert order.status == OrderStatus.PENDING
        assert order.etoro_order_id == "etoro_123"
        assert order.submitted_at is not None
        assert len(order_executor._queued_orders) == 0

        # Verify eToro API called
        mock_etoro_client.place_order.assert_called_once()

    def test_cryptocurrency_orders_never_queued(self, order_executor, mock_etoro_client, mock_market_hours):
        """Test cryptocurrency orders are never queued (24/7 market)."""
        # Crypto markets are always open
        mock_market_hours.is_market_open.return_value = True

        mock_etoro_client.place_order.return_value = {
            "order_id": "etoro_crypto",
            "status": "SUBMITTED"
        }

        signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="BTC-USD",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test crypto signal",
            generated_at=datetime.now(),
            metadata={}
        )

        # Execute signal
        order = order_executor.execute_signal(signal, position_size=1.0)

        # Verify order submitted immediately (never queued)
        assert order.status == OrderStatus.PENDING
        assert order.etoro_order_id == "etoro_crypto"
        assert len(order_executor._queued_orders) == 0

        # Verify market hours checked with CRYPTOCURRENCY asset class
        mock_market_hours.is_market_open.assert_called_once()
        call_args = mock_market_hours.is_market_open.call_args[0]
        assert call_args[0] == AssetClass.CRYPTOCURRENCY

    def test_process_queued_orders_at_market_open(self, order_executor, mock_etoro_client, mock_market_hours):
        """Test queued orders are processed when market opens."""
        # Create multiple queued orders
        queued_orders = []
        for i in range(3):
            order = Order(
                id=str(uuid.uuid4()),
                strategy_id="test",
                symbol="AAPL",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=100.0,
                status=OrderStatus.PENDING
            )
            order_executor._queued_orders.append(order)
            order_executor._orders[order.id] = order
            queued_orders.append(order)

        # Market opens
        mock_market_hours.is_market_open.return_value = True
        mock_etoro_client.place_order.return_value = {
            "order_id": "etoro_queued",
            "status": "SUBMITTED"
        }

        # Process queued orders
        processed = order_executor.process_queued_orders()

        # Verify all orders processed
        assert processed == 3
        assert len(order_executor._queued_orders) == 0

        # Verify all orders submitted
        for order in queued_orders:
            assert order.status == OrderStatus.PENDING
            assert order.etoro_order_id == "etoro_queued"
            assert order.submitted_at is not None

        # Verify eToro API called for each order
        assert mock_etoro_client.place_order.call_count == 3

    def test_process_queued_orders_partial_processing(self, order_executor, mock_etoro_client, mock_market_hours):
        """Test queued orders are partially processed when only some markets are open."""
        # Create queued orders for different symbols
        aapl_order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING
        )
        btc_order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="BTC-USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            status=OrderStatus.PENDING
        )

        order_executor._queued_orders.extend([aapl_order, btc_order])
        order_executor._orders[aapl_order.id] = aapl_order
        order_executor._orders[btc_order.id] = btc_order

        # Only crypto market open (stock market closed)
        def market_open_side_effect(asset_class):
            return asset_class == AssetClass.CRYPTOCURRENCY

        mock_market_hours.is_market_open.side_effect = market_open_side_effect
        mock_etoro_client.place_order.return_value = {
            "order_id": "etoro_partial",
            "status": "SUBMITTED"
        }

        # Process queued orders
        processed = order_executor.process_queued_orders()

        # Verify only crypto order processed
        assert processed == 1
        assert len(order_executor._queued_orders) == 1
        assert order_executor._queued_orders[0] == aapl_order

        # Verify crypto order submitted, stock order still queued
        assert btc_order.status == OrderStatus.PENDING
        assert aapl_order.status == OrderStatus.PENDING

    def test_process_queued_orders_handles_submission_failure(self, order_executor, mock_etoro_client, mock_market_hours):
        """Test queued orders that fail submission remain queued for retry."""
        # Create queued orders
        success_order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING
        )
        fail_order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="TSLA",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=50.0,
            status=OrderStatus.PENDING
        )

        order_executor._queued_orders.extend([success_order, fail_order])
        order_executor._orders[success_order.id] = success_order
        order_executor._orders[fail_order.id] = fail_order

        # Market open
        mock_market_hours.is_market_open.return_value = True

        # First order succeeds, second fails
        mock_etoro_client.place_order.side_effect = [
            {"order_id": "etoro_success", "status": "SUBMITTED"},
            EToroAPIError("Order rejected")
        ]

        # Process queued orders
        processed = order_executor.process_queued_orders()

        # Verify one order processed successfully
        assert processed == 1
        # Failed order remains in queue for potential retry
        assert len(order_executor._queued_orders) == 1
        assert order_executor._queued_orders[0] == fail_order

        # Verify success order submitted, fail order marked as failed but still queued
        assert success_order.status == OrderStatus.PENDING
        assert fail_order.status == OrderStatus.FAILED

    def test_multiple_orders_queued_for_same_symbol(self, order_executor, mock_etoro_client, mock_market_hours):
        """Test multiple orders for same symbol can be queued."""
        # Setup market closed
        mock_market_hours.is_market_open.return_value = False

        # Create multiple signals for same symbol
        for i in range(3):
            signal = TradingSignal(
                strategy_id=f"strategy_{i}",
                symbol="AAPL",
                action=SignalAction.ENTER_LONG,
                confidence=0.8,
                reasoning=f"Test signal {i}",
                generated_at=datetime.now(),
                metadata={}
            )
            order_executor.execute_signal(signal, position_size=100.0)

        # Verify all orders queued
        assert len(order_executor._queued_orders) == 3
        assert all(o.symbol == "AAPL" for o in order_executor._queued_orders)
        assert all(o.status == OrderStatus.PENDING for o in order_executor._queued_orders)

    def test_queued_orders_preserve_order_parameters(self, order_executor, mock_etoro_client, mock_market_hours):
        """Test queued orders preserve all order parameters."""
        # Setup market closed
        mock_market_hours.is_market_open.return_value = False

        signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reason="Test signal",
            generated_at=datetime.now(),
            metadata={}
        )

        # Execute signal
        order = order_executor.execute_signal(signal, position_size=150.0)

        # Verify order parameters preserved
        assert order.strategy_id == "test_strategy"
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.MARKET
        assert order.quantity == 150.0
        assert order.status == OrderStatus.PENDING

        # Market opens and process queue
        mock_market_hours.is_market_open.return_value = True
        mock_etoro_client.place_order.return_value = {
            "order_id": "etoro_preserved",
            "status": "SUBMITTED"
        }

        order_executor.process_queued_orders()

        # Verify parameters still correct after submission
        assert order.strategy_id == "test_strategy"
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.MARKET
        assert order.quantity == 150.0
        assert order.status == OrderStatus.PENDING

    def test_asset_class_determination_for_various_symbols(self, order_executor):
        """Test asset class is correctly determined for various symbols."""
        # Cryptocurrency symbols
        crypto_symbols = ["BTC-USD", "ETH", "BTCUSD", "ETHEREUM", "DOGE", "ADA", "SOL"]
        for symbol in crypto_symbols:
            asset_class = order_executor._determine_asset_class(symbol)
            assert asset_class == AssetClass.CRYPTOCURRENCY, f"Failed for {symbol}"

        # Stock symbols
        stock_symbols = ["AAPL", "TSLA", "MSFT", "GOOGL", "AMZN", "SPY", "QQQ"]
        for symbol in stock_symbols:
            asset_class = order_executor._determine_asset_class(symbol)
            assert asset_class == AssetClass.STOCK, f"Failed for {symbol}"

    def test_empty_queue_processing(self, order_executor, mock_etoro_client, mock_market_hours):
        """Test processing empty queue returns zero."""
        # No queued orders
        assert len(order_executor._queued_orders) == 0

        # Process queue
        processed = order_executor.process_queued_orders()

        # Verify no processing occurred
        assert processed == 0
        mock_etoro_client.place_order.assert_not_called()

    def test_queued_order_execution_respects_market_hours_per_symbol(self, order_executor, mock_etoro_client, mock_market_hours):
        """Test queued orders check market hours individually per symbol."""
        # Create orders for different asset classes
        stock_order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING
        )
        crypto_order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test",
            symbol="BTC-USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            status=OrderStatus.PENDING
        )

        order_executor._queued_orders.extend([stock_order, crypto_order])
        order_executor._orders[stock_order.id] = stock_order
        order_executor._orders[crypto_order.id] = crypto_order

        # Track market hours calls
        market_hours_calls = []

        def track_market_hours(asset_class):
            market_hours_calls.append(asset_class)
            # Stock closed, crypto open
            return asset_class == AssetClass.CRYPTOCURRENCY

        mock_market_hours.is_market_open.side_effect = track_market_hours
        mock_etoro_client.place_order.return_value = {
            "order_id": "etoro_test",
            "status": "SUBMITTED"
        }

        # Process queue
        order_executor.process_queued_orders()

        # Verify market hours checked for each order's asset class
        assert AssetClass.STOCK in market_hours_calls
        assert AssetClass.CRYPTOCURRENCY in market_hours_calls
        assert len(market_hours_calls) == 2



    def test_get_queued_orders_count(self, order_executor):
        """Test getting count of queued orders."""
        # Initially empty
        assert order_executor.get_queued_orders_count() == 0

        # Add some orders
        for i in range(5):
            order = Order(
                id=str(uuid.uuid4()),
                strategy_id="test",
                symbol="AAPL",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=100.0,
                status=OrderStatus.PENDING
            )
            order_executor._queued_orders.append(order)

        assert order_executor.get_queued_orders_count() == 5

    def test_get_queued_orders(self, order_executor):
        """Test getting list of queued orders."""
        # Initially empty
        assert order_executor.get_queued_orders() == []

        # Add some orders
        orders = []
        for i in range(3):
            order = Order(
                id=str(uuid.uuid4()),
                strategy_id="test",
                symbol=f"STOCK{i}",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=100.0,
                status=OrderStatus.PENDING
            )
            order_executor._queued_orders.append(order)
            orders.append(order)

        queued = order_executor.get_queued_orders()
        assert len(queued) == 3
        assert all(o in orders for o in queued)




class TestOrderCancellation:
    """Test order cancellation functionality (Task 6.5.4)."""

    def test_cancel_pending_order_not_submitted(self, order_executor):
        """Test cancelling a pending order that hasn't been submitted to eToro."""
        # Create pending order
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id=None
        )
        order_executor._orders[order.id] = order
        
        # Cancel order
        success = order_executor.cancel_order(order.id, "Test cancellation")
        
        # Verify
        assert success is True
        assert order.status == OrderStatus.CANCELLED

    def test_cancel_submitted_order_via_etoro(self, order_executor, mock_etoro_client):
        """Test cancelling a submitted order via eToro API."""
        # Create submitted order
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_123"
        )
        order_executor._orders[order.id] = order
        
        # Mock eToro cancel response
        mock_etoro_client.cancel_order.return_value = True
        
        # Cancel order
        success = order_executor.cancel_order(order.id, "Test cancellation")
        
        # Verify
        assert success is True
        assert order.status == OrderStatus.CANCELLED
        mock_etoro_client.cancel_order.assert_called_once_with("etoro_123")

    def test_cancel_order_etoro_api_failure(self, order_executor, mock_etoro_client):
        """Test cancelling order when eToro API returns False."""
        # Create submitted order
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_123"
        )
        order_executor._orders[order.id] = order
        
        # Mock eToro cancel response (failure)
        mock_etoro_client.cancel_order.return_value = False
        
        # Cancel order
        success = order_executor.cancel_order(order.id, "Test cancellation")
        
        # Verify
        assert success is False
        assert order.status == OrderStatus.PENDING  # Status unchanged

    def test_cancel_order_not_found(self, order_executor):
        """Test cancelling non-existent order raises error."""
        with pytest.raises(OrderExecutionError, match="Order .* not found"):
            order_executor.cancel_order("nonexistent_id", "Test cancellation")

    def test_cancel_filled_order_not_allowed(self, order_executor):
        """Test that filled orders cannot be cancelled."""
        # Create filled order
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.FILLED,
            etoro_order_id="etoro_123"
        )
        order_executor._orders[order.id] = order
        
        # Try to cancel
        success = order_executor.cancel_order(order.id, "Test cancellation")
        
        # Verify
        assert success is False
        assert order.status == OrderStatus.FILLED  # Status unchanged

    def test_cancel_queued_order_removes_from_queue(self, order_executor):
        """Test that cancelling a queued order removes it from the queue."""
        # Create queued order
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id=None
        )
        order_executor._orders[order.id] = order
        order_executor._queued_orders.append(order)
        
        # Cancel order
        success = order_executor.cancel_order(order.id, "Test cancellation")
        
        # Verify
        assert success is True
        assert order.status == OrderStatus.CANCELLED
        assert order not in order_executor._queued_orders
        assert len(order_executor._queued_orders) == 0

    def test_cancel_order_etoro_api_exception(self, order_executor, mock_etoro_client):
        """Test cancelling order when eToro API raises exception."""
        # Create submitted order
        order = Order(
            id=str(uuid.uuid4()),
            strategy_id="test_strategy",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_123"
        )
        order_executor._orders[order.id] = order
        
        # Mock eToro cancel to raise exception
        mock_etoro_client.cancel_order.side_effect = EToroAPIError("API error")
        
        # Cancel order
        success = order_executor.cancel_order(order.id, "Test cancellation")
        
        # Verify - should return False on exception
        assert success is False
        assert order.status == OrderStatus.PENDING  # Status unchanged
