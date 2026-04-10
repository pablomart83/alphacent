"""
Tests for partial exit execution (Task 11.8.7).

Tests the _check_partial_exits() method in MonitoringService that
checks open positions for partial exit opportunities and submits
partial close orders when profit thresholds are met.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.orm import Base, PositionORM, StrategyORM, RiskConfigORM, OrderORM
from src.models.enums import (
    PositionSide, OrderStatus, OrderSide, OrderType,
    StrategyStatus, TradingMode,
)
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
    client.place_order.return_value = {"order_id": "etoro_partial_123"}
    client.get_circuit_breaker_states.return_value = {}
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


def _create_strategy(session, strategy_id="strat_1", partial_exit_enabled=True,
                     partial_exit_levels=None):
    """Helper to create a test strategy with risk_params containing partial exit config."""
    if partial_exit_levels is None:
        partial_exit_levels = [{"profit_pct": 0.05, "exit_pct": 0.5}]

    risk_params = {
        "max_position_size_pct": 0.05,
        "max_exposure_pct": 0.50,
        "stop_loss_pct": 0.04,
        "take_profit_pct": 0.10,
        "partial_exit_enabled": partial_exit_enabled,
        "partial_exit_levels": partial_exit_levels,
    }

    strategy = StrategyORM(
        id=strategy_id,
        name="Test Strategy",
        description="Test",
        status=StrategyStatus.DEMO,
        rules={"entry_conditions": [], "exit_conditions": []},
        symbols=["AAPL"],
        allocation_percent=2.0,
        risk_params=risk_params,
        created_at=datetime.now() - timedelta(days=30),
        performance={"total_return": 0.0},
    )
    session.add(strategy)
    session.commit()
    return strategy


def _create_position(session, pos_id="pos_1", strategy_id="strat_1",
                     symbol="AAPL", side=PositionSide.LONG,
                     entry_price=100.0, current_price=110.0,
                     quantity=100.0, partial_exits=None, closed_at=None):
    """Helper to create a test position."""
    pos = PositionORM(
        id=pos_id,
        strategy_id=strategy_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        current_price=current_price,
        unrealized_pnl=(current_price - entry_price) * quantity,
        realized_pnl=0.0,
        opened_at=datetime.now() - timedelta(days=5),
        etoro_position_id=f"etoro_{pos_id}",
        partial_exits=partial_exits or [],
        closed_at=closed_at,
    )
    session.add(pos)
    session.commit()
    return pos


def _create_global_risk_config(session, partial_exit_enabled=True,
                                partial_exit_levels=None):
    """Helper to create a global risk config in the DB."""
    if partial_exit_levels is None:
        partial_exit_levels = [{"profit_pct": 0.05, "exit_pct": 0.5}]

    config = RiskConfigORM(
        mode=TradingMode.DEMO,
        max_position_size_pct=0.05,
        max_exposure_pct=0.50,
        max_daily_loss_pct=0.03,
        max_drawdown_pct=0.10,
        position_risk_pct=0.02,
        stop_loss_pct=0.04,
        take_profit_pct=0.10,
        partial_exit_enabled=1 if partial_exit_enabled else 0,
        partial_exit_levels=partial_exit_levels,
    )
    session.add(config)
    session.commit()
    return config


class TestCheckPartialExits:
    """Tests for _check_partial_exits()."""

    def test_no_open_positions(self, monitoring_service, in_memory_db):
        """Returns zeros when no open positions exist."""
        result = monitoring_service._check_partial_exits()
        assert result["checked"] == 0
        assert result["triggered"] == 0

    def test_partial_exit_triggered_long_position(self, monitoring_service, in_memory_db):
        """Triggers partial exit when long position profit exceeds threshold."""
        session = in_memory_db.get_session()
        _create_strategy(session, partial_exit_levels=[
            {"profit_pct": 0.05, "exit_pct": 0.5}
        ])
        _create_position(session, entry_price=100.0, current_price=106.0, quantity=100.0)

        result = monitoring_service._check_partial_exits()

        assert result["triggered"] == 1
        assert result["failed"] == 0

        # Verify order was created
        orders = session.query(OrderORM).all()
        assert len(orders) == 1
        assert orders[0].quantity == 50.0  # 100 * 0.5
        assert orders[0].side == OrderSide.SELL
        assert orders[0].status == OrderStatus.PENDING

        # Verify partial exit recorded on position
        pos = session.query(PositionORM).filter_by(id="pos_1").first()
        assert len(pos.partial_exits) == 1
        assert pos.partial_exits[0]["level_pct"] == 0.05
        assert pos.partial_exits[0]["exit_pct"] == 0.5
        assert pos.partial_exits[0]["quantity"] == 50.0
        # Position quantity reduced
        assert pos.quantity == 50.0

    def test_partial_exit_triggered_short_position(self, monitoring_service, in_memory_db):
        """Triggers partial exit when short position profit exceeds threshold."""
        session = in_memory_db.get_session()
        _create_strategy(session, partial_exit_levels=[
            {"profit_pct": 0.05, "exit_pct": 0.5}
        ])
        _create_position(
            session, entry_price=100.0, current_price=94.0,
            quantity=100.0, side=PositionSide.SHORT,
        )

        result = monitoring_service._check_partial_exits()

        assert result["triggered"] == 1

        orders = session.query(OrderORM).all()
        assert len(orders) == 1
        assert orders[0].side == OrderSide.BUY  # Opposite of SHORT
        assert orders[0].quantity == 50.0

    def test_no_trigger_when_profit_below_threshold(self, monitoring_service, in_memory_db):
        """Does not trigger when profit is below the threshold."""
        session = in_memory_db.get_session()
        _create_strategy(session, partial_exit_levels=[
            {"profit_pct": 0.10, "exit_pct": 0.5}  # 10% threshold
        ])
        _create_position(session, entry_price=100.0, current_price=105.0)  # Only 5% profit

        result = monitoring_service._check_partial_exits()

        assert result["triggered"] == 0
        orders = session.query(OrderORM).all()
        assert len(orders) == 0

    def test_does_not_retrigger_same_level(self, monitoring_service, in_memory_db):
        """Does not trigger the same level twice."""
        session = in_memory_db.get_session()
        _create_strategy(session, partial_exit_levels=[
            {"profit_pct": 0.05, "exit_pct": 0.5}
        ])
        _create_position(
            session, entry_price=100.0, current_price=106.0, quantity=100.0,
            partial_exits=[{
                "level_pct": 0.05,
                "exit_pct": 0.5,
                "quantity": 50.0,
                "price": 105.5,
                "timestamp": datetime.now().isoformat(),
                "order_id": "old_order",
                "profit_level": "0.0500",
            }],
        )

        result = monitoring_service._check_partial_exits()

        assert result["triggered"] == 0
        assert result["skipped"] == 1
        orders = session.query(OrderORM).all()
        assert len(orders) == 0

    def test_multiple_levels_triggered(self, monitoring_service, in_memory_db):
        """Triggers multiple levels when profit exceeds all thresholds."""
        session = in_memory_db.get_session()
        _create_strategy(session, partial_exit_levels=[
            {"profit_pct": 0.05, "exit_pct": 0.33},
            {"profit_pct": 0.10, "exit_pct": 0.50},
        ])
        _create_position(session, entry_price=100.0, current_price=112.0, quantity=100.0)

        result = monitoring_service._check_partial_exits()

        assert result["triggered"] == 2
        orders = session.query(OrderORM).all()
        assert len(orders) == 2

        pos = session.query(PositionORM).filter_by(id="pos_1").first()
        assert len(pos.partial_exits) == 2

    def test_partial_exit_disabled_on_strategy(self, monitoring_service, in_memory_db):
        """Skips positions whose strategy has partial exits disabled."""
        session = in_memory_db.get_session()
        _create_strategy(session, partial_exit_enabled=False)
        _create_position(session, entry_price=100.0, current_price=120.0)

        result = monitoring_service._check_partial_exits()

        assert result["triggered"] == 0

    def test_falls_back_to_global_risk_config(self, monitoring_service, in_memory_db):
        """Falls back to global RiskConfigORM when strategy has no partial exit config."""
        session = in_memory_db.get_session()
        # Strategy without partial exit config in risk_params
        strategy = StrategyORM(
            id="strat_1",
            name="Test Strategy",
            description="Test",
            status=StrategyStatus.DEMO,
            rules={"entry_conditions": [], "exit_conditions": []},
            symbols=["AAPL"],
            allocation_percent=2.0,
            risk_params={"stop_loss_pct": 0.04, "take_profit_pct": 0.10},
            created_at=datetime.now(),
            performance={},
        )
        session.add(strategy)
        session.commit()

        _create_global_risk_config(session, partial_exit_enabled=True,
                                    partial_exit_levels=[{"profit_pct": 0.05, "exit_pct": 0.5}])
        _create_position(session, entry_price=100.0, current_price=106.0, quantity=100.0)

        result = monitoring_service._check_partial_exits()

        assert result["triggered"] == 1

    def test_closed_positions_skipped(self, monitoring_service, in_memory_db):
        """Closed positions are not checked (filtered by query)."""
        session = in_memory_db.get_session()
        _create_strategy(session)
        _create_position(session, entry_price=100.0, current_price=120.0,
                         closed_at=datetime.now())

        result = monitoring_service._check_partial_exits()

        assert result["checked"] == 0

    def test_etoro_api_failure_records_failed_order(self, monitoring_service, in_memory_db):
        """When eToro API fails, order is marked FAILED and failure counted."""
        from src.api.etoro_client import EToroAPIError

        session = in_memory_db.get_session()
        _create_strategy(session)
        _create_position(session, entry_price=100.0, current_price=106.0)

        monitoring_service.etoro_client.place_order.side_effect = EToroAPIError("API down")

        result = monitoring_service._check_partial_exits()

        assert result["triggered"] == 0
        assert result["failed"] == 1

        orders = session.query(OrderORM).all()
        assert len(orders) == 1
        assert orders[0].status == OrderStatus.FAILED
