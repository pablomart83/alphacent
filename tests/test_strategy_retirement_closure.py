"""
Tests for strategy retirement position closure (Task 11.8.2).

Tests the _close_strategy_positions() method in PortfolioManager that
closes all open positions when a strategy is retired, cancels pending orders,
and falls back to pending_closure when no eToro client is available.
"""
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.database import Database
from src.models.enums import (
    OrderSide, OrderStatus, OrderType, PositionSide,
)
from src.models.orm import Base, OrderORM, PositionORM


@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    db = MagicMock(spec=Database)
    db.get_session.side_effect = lambda: Session()
    db._engine = engine
    db._Session = Session
    return db


@pytest.fixture
def mock_strategy_engine(in_memory_db):
    """Create a mock strategy engine with a real DB."""
    se = MagicMock()
    se.db = in_memory_db
    return se


@pytest.fixture
def mock_etoro_client():
    """Create a mock eToro client."""
    client = MagicMock()
    client.place_order.return_value = {"order_id": "etoro_close_123"}
    client.cancel_order.return_value = True
    return client


@pytest.fixture
def portfolio_manager_with_client(mock_strategy_engine, mock_etoro_client):
    """PortfolioManager with eToro client available."""
    from src.strategy.portfolio_manager import PortfolioManager
    return PortfolioManager(
        strategy_engine=mock_strategy_engine,
        etoro_client=mock_etoro_client,
    )


@pytest.fixture
def portfolio_manager_no_client(mock_strategy_engine):
    """PortfolioManager without eToro client (fallback mode)."""
    from src.strategy.portfolio_manager import PortfolioManager
    return PortfolioManager(strategy_engine=mock_strategy_engine)


def _create_position(
    db,
    strategy_id="strat_1",
    pos_id=None,
    symbol="AAPL",
    side=PositionSide.LONG,
    pending=False,
    closed_at=None,
):
    """Helper to insert a PositionORM row."""
    session = db._Session()
    pos = PositionORM(
        id=pos_id or str(uuid.uuid4()),
        strategy_id=strategy_id,
        symbol=symbol,
        side=side,
        quantity=10.0,
        entry_price=150.0,
        current_price=155.0,
        unrealized_pnl=50.0,
        realized_pnl=0.0,
        opened_at=datetime.now(),
        etoro_position_id=f"etoro_{pos_id or 'pos'}",
        pending_closure=pending,
        closed_at=closed_at,
    )
    session.add(pos)
    session.commit()
    session.close()
    return pos


def _create_order(
    db,
    strategy_id="strat_1",
    order_id=None,
    symbol="AAPL",
    status=OrderStatus.PENDING,
    etoro_order_id=None,
):
    """Helper to insert an OrderORM row."""
    session = db._Session()
    order = OrderORM(
        id=order_id or str(uuid.uuid4()),
        strategy_id=strategy_id,
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=status,
        etoro_order_id=etoro_order_id,
    )
    session.add(order)
    session.commit()
    session.close()
    return order


class TestCloseStrategyPositions:
    """Tests for _close_strategy_positions()."""

    @pytest.fixture(autouse=True)
    def _fast_verification(self):
        """Patch time functions so the 30s verification loop exits immediately."""
        call_count = 0

        def fast_time():
            nonlocal call_count
            call_count += 1
            # First call sets the deadline, second call exceeds it
            return 1000.0 + (call_count * 31)

        with patch("src.strategy.portfolio_manager.time.sleep"), \
             patch("src.strategy.portfolio_manager.time.time", side_effect=fast_time):
            yield

    def test_no_open_positions(self, portfolio_manager_with_client, in_memory_db):
        """No open positions returns cleanly, no API calls."""
        portfolio_manager_with_client._close_strategy_positions("strat_1")
        portfolio_manager_with_client.etoro_client.place_order.assert_not_called()

    def test_submits_close_order_for_long_position(
        self, portfolio_manager_with_client, in_memory_db, mock_etoro_client
    ):
        """Long position submits SELL close order via eToro."""
        _create_position(in_memory_db, side=PositionSide.LONG)

        portfolio_manager_with_client._close_strategy_positions("strat_1")

        mock_etoro_client.place_order.assert_called_once()
        call_kwargs = mock_etoro_client.place_order.call_args
        assert call_kwargs.kwargs["side"] == OrderSide.SELL
        assert call_kwargs.kwargs["order_type"] == OrderType.MARKET

    def test_submits_close_order_for_short_position(
        self, portfolio_manager_with_client, in_memory_db, mock_etoro_client
    ):
        """Short position submits BUY close order via eToro."""
        _create_position(in_memory_db, side=PositionSide.SHORT)

        portfolio_manager_with_client._close_strategy_positions("strat_1")

        mock_etoro_client.place_order.assert_called_once()
        call_kwargs = mock_etoro_client.place_order.call_args
        assert call_kwargs.kwargs["side"] == OrderSide.BUY

    def test_fallback_to_pending_closure_without_client(
        self, portfolio_manager_no_client, in_memory_db
    ):
        """No eToro client sets pending_closure=True on positions."""
        _create_position(in_memory_db, pos_id="pos_fallback")

        portfolio_manager_no_client._close_strategy_positions("strat_1")

        session = in_memory_db._Session()
        pos = session.query(PositionORM).filter_by(id="pos_fallback").first()
        assert pos.pending_closure is True
        assert pos.closure_reason == "Strategy retired"
        session.close()

    def test_fallback_on_api_error(
        self, portfolio_manager_with_client, in_memory_db, mock_etoro_client
    ):
        """eToro API error falls back to pending_closure for that position."""
        _create_position(in_memory_db, pos_id="pos_api_err")

        mock_etoro_client.place_order.side_effect = Exception("eToro API timeout")

        portfolio_manager_with_client._close_strategy_positions("strat_1")

        session = in_memory_db._Session()
        pos = session.query(PositionORM).filter_by(id="pos_api_err").first()
        assert pos.pending_closure is True
        assert "close order failed" in pos.closure_reason
        session.close()

    def test_cancels_pending_orders(
        self, portfolio_manager_with_client, in_memory_db, mock_etoro_client
    ):
        """Cancels PENDING and SUBMITTED orders for the retiring strategy."""
        _create_order(in_memory_db, order_id="ord_pending", status=OrderStatus.PENDING)
        _create_order(
            in_memory_db,
            order_id="ord_submitted",
            status=OrderStatus.PENDING,
            etoro_order_id="etoro_ord_1",
        )
        # FILLED order should NOT be cancelled
        _create_order(in_memory_db, order_id="ord_filled", status=OrderStatus.FILLED)

        portfolio_manager_with_client._close_strategy_positions("strat_1")

        session = in_memory_db._Session()
        pending = session.query(OrderORM).filter_by(id="ord_pending").first()
        submitted = session.query(OrderORM).filter_by(id="ord_submitted").first()
        filled = session.query(OrderORM).filter_by(id="ord_filled").first()

        assert pending.status == OrderStatus.CANCELLED
        assert submitted.status == OrderStatus.CANCELLED
        assert filled.status == OrderStatus.FILLED
        mock_etoro_client.cancel_order.assert_called_once_with("etoro_ord_1")
        session.close()

    def test_does_not_cancel_other_strategy_orders(
        self, portfolio_manager_with_client, in_memory_db
    ):
        """Orders from other strategies are not cancelled."""
        _create_order(
            in_memory_db,
            strategy_id="other_strat",
            order_id="ord_other",
            status=OrderStatus.PENDING,
        )

        portfolio_manager_with_client._close_strategy_positions("strat_1")

        session = in_memory_db._Session()
        other = session.query(OrderORM).filter_by(id="ord_other").first()
        assert other.status == OrderStatus.PENDING
        session.close()

    def test_skips_already_closed_positions(
        self, portfolio_manager_with_client, in_memory_db, mock_etoro_client
    ):
        """Already-closed positions are not processed."""
        _create_position(in_memory_db, pos_id="pos_closed", closed_at=datetime.now())

        portfolio_manager_with_client._close_strategy_positions("strat_1")
        mock_etoro_client.place_order.assert_not_called()

    def test_creates_order_record_in_db(
        self, portfolio_manager_with_client, in_memory_db, mock_etoro_client
    ):
        """Close order is persisted to the orders table."""
        _create_position(in_memory_db, pos_id="pos_db_check")

        portfolio_manager_with_client._close_strategy_positions("strat_1")

        session = in_memory_db._Session()
        orders = (
            session.query(OrderORM)
            .filter_by(strategy_id="strat_1")
            .all()
        )
        assert len(orders) == 1
        assert orders[0].order_type == OrderType.MARKET
        assert orders[0].side == OrderSide.SELL  # Opposite of LONG
        session.close()

    def test_multiple_positions_all_closed(
        self, portfolio_manager_with_client, in_memory_db, mock_etoro_client
    ):
        """Multiple open positions are all submitted for closure."""
        _create_position(in_memory_db, pos_id="pos_a", symbol="AAPL")
        _create_position(in_memory_db, pos_id="pos_b", symbol="MSFT")
        _create_position(in_memory_db, pos_id="pos_c", symbol="GOOGL")

        portfolio_manager_with_client._close_strategy_positions("strat_1")

        assert mock_etoro_client.place_order.call_count == 3

    def test_close_order_tracks_on_position(
        self, portfolio_manager_with_client, in_memory_db, mock_etoro_client
    ):
        """close_order_id and close_attempts are set on the position."""
        _create_position(in_memory_db, pos_id="pos_track")

        portfolio_manager_with_client._close_strategy_positions("strat_1")

        session = in_memory_db._Session()
        pos = session.query(PositionORM).filter_by(id="pos_track").first()
        assert pos.close_order_id is not None
        assert pos.close_attempts == 1
        session.close()
