"""
Tests for auto-close pending closure positions (Task 11.8.1).

Tests the _process_pending_closures() method in MonitoringService that
automatically submits close orders for positions flagged with pending_closure=True.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.orm import Base, PositionORM, OrderORM
from src.models.enums import PositionSide, OrderStatus, OrderSide, OrderType
from src.models.database import Database


@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    db = MagicMock(spec=Database)
    db.get_session.return_value = Session()
    db._engine = engine
    db._Session = Session
    return db


@pytest.fixture
def mock_etoro_client():
    """Create a mock eToro client."""
    client = MagicMock()
    client.place_order.return_value = {"order_id": "etoro_close_123"}
    return client


@pytest.fixture
def monitoring_service(mock_etoro_client, in_memory_db):
    """Create a MonitoringService with mocked dependencies."""
    from src.core.monitoring_service import MonitoringService
    service = MonitoringService(
        etoro_client=mock_etoro_client,
        db=in_memory_db,
    )
    return service


def _create_position(session, pos_id="pos_1", symbol="AAPL", pending=True,
                     reason="Strategy retired", close_order_id=None,
                     close_attempts=0, closed_at=None, side=PositionSide.LONG):
    """Helper to create a test position."""
    pos = PositionORM(
        id=pos_id,
        strategy_id="strat_1",
        symbol=symbol,
        side=side,
        quantity=100.0,
        entry_price=150.0,
        current_price=155.0,
        unrealized_pnl=500.0,
        realized_pnl=0.0,
        opened_at=datetime.now() - timedelta(days=5),
        etoro_position_id=f"etoro_{pos_id}",
        pending_closure=pending,
        closure_reason=reason,
        close_order_id=close_order_id,
        close_attempts=close_attempts,
        closed_at=closed_at,
    )
    session.add(pos)
    session.commit()
    return pos


class TestProcessPendingClosures:
    """Tests for _process_pending_closures()."""

    def test_no_pending_positions(self, monitoring_service, in_memory_db):
        """No pending positions → returns zeros, no API calls."""
        result = monitoring_service._process_pending_closures()
        assert result["submitted"] == 0
        assert result["failed"] == 0
        assert result["skipped"] == 0
        monitoring_service.etoro_client.place_order.assert_not_called()

    def test_submits_close_order_for_pending_long(self, monitoring_service, in_memory_db):
        """Submits a SELL order to close a LONG position flagged for closure."""
        session = in_memory_db.get_session()
        _create_position(session, side=PositionSide.LONG)

        result = monitoring_service._process_pending_closures()

        assert result["submitted"] == 1
        assert result["failed"] == 0
        monitoring_service.etoro_client.place_order.assert_called_once()
        call_kwargs = monitoring_service.etoro_client.place_order.call_args
        assert call_kwargs.kwargs.get("side") == OrderSide.SELL or call_kwargs[1].get("side") == OrderSide.SELL

        # Verify position was updated
        session2 = in_memory_db._Session()
        pos = session2.query(PositionORM).filter_by(id="pos_1").first()
        assert pos.close_order_id is not None
        assert pos.close_attempts == 1
        session2.close()

    def test_submits_close_order_for_pending_short(self, monitoring_service, in_memory_db):
        """Submits a BUY order to close a SHORT position flagged for closure."""
        session = in_memory_db.get_session()
        _create_position(session, side=PositionSide.SHORT)

        result = monitoring_service._process_pending_closures()

        assert result["submitted"] == 1
        call_kwargs = monitoring_service.etoro_client.place_order.call_args
        assert call_kwargs.kwargs.get("side") == OrderSide.BUY or call_kwargs[1].get("side") == OrderSide.BUY

    def test_skips_already_closed_positions(self, monitoring_service, in_memory_db):
        """Positions with closed_at set are not processed."""
        session = in_memory_db.get_session()
        _create_position(session, closed_at=datetime.now())

        result = monitoring_service._process_pending_closures()
        assert result["total"] == 0
        monitoring_service.etoro_client.place_order.assert_not_called()

    def test_skips_non_pending_positions(self, monitoring_service, in_memory_db):
        """Positions without pending_closure=True are not processed."""
        session = in_memory_db.get_session()
        _create_position(session, pending=False)

        result = monitoring_service._process_pending_closures()
        assert result["total"] == 0

    def test_skips_max_retries_exhausted(self, monitoring_service, in_memory_db):
        """Positions with close_attempts >= 3 are skipped."""
        session = in_memory_db.get_session()
        _create_position(session, close_attempts=3)

        result = monitoring_service._process_pending_closures()
        assert result["skipped"] == 1
        assert result["submitted"] == 0
        monitoring_service.etoro_client.place_order.assert_not_called()

    def test_skips_active_close_order(self, monitoring_service, in_memory_db):
        """Positions with an active (PENDING/SUBMITTED) close order are skipped."""
        session = in_memory_db.get_session()

        # Create an active close order
        order = OrderORM(
            id="close_order_1",
            strategy_id="strat_1",
            symbol="AAPL",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.PENDING,
            submitted_at=datetime.now(),
        )
        session.add(order)
        session.commit()

        _create_position(session, close_order_id="close_order_1", close_attempts=1)

        result = monitoring_service._process_pending_closures()
        assert result["skipped"] == 1
        assert result["submitted"] == 0

    def test_retries_after_failed_close_order(self, monitoring_service, in_memory_db):
        """Positions with a FAILED close order get a new attempt."""
        session = in_memory_db.get_session()

        # Create a failed close order with old submission time (past backoff)
        order = OrderORM(
            id="close_order_old",
            strategy_id="strat_1",
            symbol="AAPL",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=100.0,
            status=OrderStatus.FAILED,
            submitted_at=datetime.now() - timedelta(hours=1),
        )
        session.add(order)
        session.commit()

        _create_position(session, close_order_id="close_order_old", close_attempts=1)

        result = monitoring_service._process_pending_closures()
        assert result["submitted"] == 1

    def test_handles_api_error_gracefully(self, monitoring_service, in_memory_db):
        """API errors increment close_attempts but don't crash."""
        from src.api.etoro_client import EToroAPIError
        monitoring_service.etoro_client.place_order.side_effect = EToroAPIError("Market closed")

        session = in_memory_db.get_session()
        _create_position(session)

        result = monitoring_service._process_pending_closures()
        assert result["failed"] == 1
        assert result["submitted"] == 0

        # Verify attempts incremented
        session2 = in_memory_db._Session()
        pos = session2.query(PositionORM).filter_by(id="pos_1").first()
        assert pos.close_attempts == 1
        session2.close()

    def test_creates_order_in_database(self, monitoring_service, in_memory_db):
        """Close order is persisted to the orders table."""
        session = in_memory_db.get_session()
        _create_position(session)

        monitoring_service._process_pending_closures()

        session2 = in_memory_db._Session()
        pos = session2.query(PositionORM).filter_by(id="pos_1").first()
        order = session2.query(OrderORM).filter_by(id=pos.close_order_id).first()
        assert order is not None
        assert order.status == OrderStatus.PENDING
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.SELL
        assert order.order_type == OrderType.MARKET
        assert order.etoro_order_id == "etoro_close_123"
        session2.close()

    def test_multiple_pending_positions(self, monitoring_service, in_memory_db):
        """Processes multiple pending positions in one cycle."""
        session = in_memory_db.get_session()
        _create_position(session, pos_id="pos_1", symbol="AAPL")
        _create_position(session, pos_id="pos_2", symbol="MSFT")
        _create_position(session, pos_id="pos_3", symbol="GOOGL")

        result = monitoring_service._process_pending_closures()
        assert result["submitted"] == 3
        assert result["total"] == 3
        assert monitoring_service.etoro_client.place_order.call_count == 3


class TestPositionORMNewColumns:
    """Tests for the new close_order_id and close_attempts columns."""

    def test_default_values(self, in_memory_db):
        """New columns have correct defaults."""
        session = in_memory_db.get_session()
        pos = PositionORM(
            id="test_defaults",
            strategy_id="strat_1",
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=10.0,
            entry_price=150.0,
            current_price=150.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro_test",
        )
        session.add(pos)
        session.commit()

        fetched = session.query(PositionORM).filter_by(id="test_defaults").first()
        assert fetched.close_order_id is None
        assert fetched.close_attempts == 0
        session.close()

    def test_to_dict_includes_new_fields(self, in_memory_db):
        """to_dict() includes close_order_id and close_attempts."""
        session = in_memory_db.get_session()
        pos = PositionORM(
            id="test_dict",
            strategy_id="strat_1",
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=10.0,
            entry_price=150.0,
            current_price=150.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro_test",
            close_order_id="order_123",
            close_attempts=2,
        )
        session.add(pos)
        session.commit()

        d = pos.to_dict()
        assert d["close_order_id"] == "order_123"
        assert d["close_attempts"] == 2
        session.close()
