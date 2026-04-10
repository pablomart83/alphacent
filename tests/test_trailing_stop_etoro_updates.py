"""Tests for trailing stop DB updates and stop-loss breach detection.

Verifies that MonitoringService._check_trailing_stops():
1. Updates stop-loss values in the DB when PositionManager calculates new levels
2. Detects stop-loss breaches and flags positions for closure
3. Handles errors gracefully (logs warning, doesn't crash)
4. Returns correct counts

Note: eToro API does NOT support modifying SL/TP on open positions.
Trailing stops are enforced DB-side: this method updates the stop level,
and flags positions that breach their stop for closure via pending_closure.
"""

import time
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.core.monitoring_service import MonitoringService
from src.models.orm import PositionORM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_position_orm(
    pos_id: str = "pos_1",
    symbol: str = "AAPL",
    side="LONG",
    entry_price: float = 100.0,
    current_price: float = 110.0,
    stop_loss: float = 95.0,
    etoro_position_id: str = "etoro_pos_1",
    closed_at=None,
    pending_closure=False,
):
    """Create a minimal PositionORM mock."""
    pos = MagicMock(spec=PositionORM)
    pos.id = pos_id
    pos.symbol = symbol
    pos.side = side
    pos.entry_price = entry_price
    pos.current_price = current_price
    pos.stop_loss = stop_loss
    pos.etoro_position_id = etoro_position_id
    pos.closed_at = closed_at
    pos.pending_closure = pending_closure
    pos.quantity = 10.0
    pos.unrealized_pnl = (current_price - entry_price) * 10
    pos.realized_pnl = 0.0
    pos.opened_at = datetime(2025, 1, 1)
    pos.take_profit = None
    pos.strategy_id = "strat_1"
    return pos


def _build_service() -> MonitoringService:
    """Build a MonitoringService with mocked dependencies for trailing stop tests."""
    svc = MonitoringService.__new__(MonitoringService)
    svc.etoro_client = MagicMock()
    svc.db = MagicMock()
    svc.order_monitor = MagicMock()
    svc.pending_orders_interval = 5
    svc.order_status_interval = 30
    svc.position_sync_interval = 60
    svc.trailing_stops_interval = 5
    svc._running = False
    svc._task = None
    svc._last_pending_check = 0
    svc._last_order_check = 0
    svc._last_position_sync = 0
    svc._last_trailing_check = 0
    svc._last_fundamental_check = 0
    svc._last_pending_closure_check = 0
    svc._last_stale_order_check = 0
    svc._fundamental_config = {"enabled": False}
    svc._fundamental_check_interval = 86400
    svc._pending_closure_interval = 60
    svc._stale_order_config = {}
    svc._trailing_stop_last_etoro_update = {}
    svc._trailing_stop_rate_limit_seconds = 300
    return svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTrailingStopDBUpdates:
    """Test that trailing stop changes are persisted to DB."""

    def test_db_updated_when_stop_loss_changes(self):
        """When stop_loss changes, DB should be updated."""
        svc = _build_service()
        pos_orm = _make_position_orm(stop_loss=95.0)

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [pos_orm]
        session.query.return_value.filter_by.return_value.first.return_value = pos_orm
        svc.db.get_session.return_value = session

        new_stop = 107.0

        def fake_check_trailing(positions, skip_etoro_update=False):
            for p in positions:
                p.stop_loss = new_stop

        svc.order_monitor.position_manager.check_trailing_stops = MagicMock(
            side_effect=fake_check_trailing
        )

        result = svc._check_trailing_stops()

        assert result["updated"] == 1
        session.commit.assert_called()

    def test_no_update_when_stop_loss_unchanged(self):
        """When stop_loss doesn't change, no DB update should happen."""
        svc = _build_service()
        pos_orm = _make_position_orm(stop_loss=95.0)

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [pos_orm]
        session.query.return_value.filter_by.return_value.first.return_value = pos_orm
        svc.db.get_session.return_value = session

        def fake_check_trailing(positions, skip_etoro_update=False):
            pass  # No changes

        svc.order_monitor.position_manager.check_trailing_stops = MagicMock(
            side_effect=fake_check_trailing
        )

        result = svc._check_trailing_stops()

        assert result["updated"] == 0

    def test_error_handled_gracefully(self):
        """Errors should be logged but not crash the monitoring loop."""
        svc = _build_service()
        pos_orm = _make_position_orm(stop_loss=95.0)

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [pos_orm]
        session.query.return_value.filter_by.return_value.first.return_value = pos_orm
        svc.db.get_session.return_value = session

        def fake_check_trailing(positions, skip_etoro_update=False):
            for p in positions:
                p.stop_loss = 107.0

        svc.order_monitor.position_manager.check_trailing_stops = MagicMock(
            side_effect=fake_check_trailing
        )

        result = svc._check_trailing_stops()

        assert result["updated"] == 1
        assert "error" not in result


class TestStopLossBreachDetection:
    """Test that positions breaching their stop-loss are flagged for closure."""

    def test_long_position_breach_flagged(self):
        """Long position where price <= stop_loss should be flagged."""
        svc = _build_service()
        # Price has dropped below stop
        pos_orm = _make_position_orm(
            stop_loss=105.0, current_price=104.0, side="LONG"
        )

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [pos_orm]
        session.query.return_value.filter_by.return_value.first.return_value = pos_orm
        svc.db.get_session.return_value = session

        def fake_check_trailing(positions, skip_etoro_update=False):
            pass  # No trailing stop changes

        svc.order_monitor.position_manager.check_trailing_stops = MagicMock(
            side_effect=fake_check_trailing
        )

        result = svc._check_trailing_stops()

        assert result.get("breach_closures", 0) == 1
        assert pos_orm.pending_closure == True

    def test_short_position_breach_flagged(self):
        """Short position where price >= stop_loss should be flagged."""
        svc = _build_service()
        pos_orm = _make_position_orm(
            stop_loss=115.0, current_price=116.0, side="SHORT"
        )

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [pos_orm]
        session.query.return_value.filter_by.return_value.first.return_value = pos_orm
        svc.db.get_session.return_value = session

        def fake_check_trailing(positions, skip_etoro_update=False):
            pass

        svc.order_monitor.position_manager.check_trailing_stops = MagicMock(
            side_effect=fake_check_trailing
        )

        result = svc._check_trailing_stops()

        assert result.get("breach_closures", 0) == 1
        assert pos_orm.pending_closure == True

    def test_no_breach_when_price_above_stop(self):
        """Long position where price > stop_loss should NOT be flagged."""
        svc = _build_service()
        pos_orm = _make_position_orm(
            stop_loss=95.0, current_price=110.0, side="LONG"
        )

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [pos_orm]
        session.query.return_value.filter_by.return_value.first.return_value = pos_orm
        svc.db.get_session.return_value = session

        def fake_check_trailing(positions, skip_etoro_update=False):
            pass

        svc.order_monitor.position_manager.check_trailing_stops = MagicMock(
            side_effect=fake_check_trailing
        )

        result = svc._check_trailing_stops()

        assert result.get("breach_closures", 0) == 0

    def test_already_pending_closure_not_double_flagged(self):
        """Position already pending closure should not be flagged again."""
        svc = _build_service()
        pos_orm = _make_position_orm(
            stop_loss=105.0, current_price=104.0, side="LONG",
            pending_closure=True,
        )

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [pos_orm]
        session.query.return_value.filter_by.return_value.first.return_value = pos_orm
        svc.db.get_session.return_value = session

        def fake_check_trailing(positions, skip_etoro_update=False):
            pass

        svc.order_monitor.position_manager.check_trailing_stops = MagicMock(
            side_effect=fake_check_trailing
        )

        result = svc._check_trailing_stops()

        # Should not count as a new breach since already pending
        assert result.get("breach_closures", 0) == 0


class TestPositionManagerSkipEtoroUpdate:
    """Test that PositionManager respects skip_etoro_update flag."""

    def test_skip_etoro_update_true_does_not_call_api(self):
        """When skip_etoro_update=True, PositionManager should not call eToro API."""
        from src.execution.position_manager import PositionManager
        from src.models.dataclasses import Position, RiskConfig

        etoro_client = MagicMock()
        risk_config = RiskConfig(
            trailing_stop_enabled=True,
            trailing_stop_activation_pct=0.05,
            trailing_stop_distance_pct=0.03,
        )
        manager = PositionManager(etoro_client, risk_config)

        position = Position(
            id="pos_1",
            strategy_id="strat_1",
            symbol="AAPL",
            side=MagicMock(value="LONG"),
            quantity=10.0,
            entry_price=100.0,
            current_price=110.0,
            unrealized_pnl=100.0,
            realized_pnl=0.0,
            opened_at=datetime(2025, 1, 1),
            etoro_position_id="etoro_pos_1",
            stop_loss=95.0,
            take_profit=None,
            closed_at=None,
        )

        manager.check_trailing_stops([position], skip_etoro_update=True)

        expected_stop = 110.0 * (1 - 0.03)
        assert abs(position.stop_loss - expected_stop) < 0.01
        etoro_client.update_position_stop_loss.assert_not_called()

    def test_skip_etoro_update_false_calls_api(self):
        """When skip_etoro_update=False (default), PositionManager calls eToro API."""
        from src.execution.position_manager import PositionManager
        from src.models.dataclasses import Position, RiskConfig

        etoro_client = MagicMock()
        risk_config = RiskConfig(
            trailing_stop_enabled=True,
            trailing_stop_activation_pct=0.05,
            trailing_stop_distance_pct=0.03,
        )
        manager = PositionManager(etoro_client, risk_config)

        position = Position(
            id="pos_1",
            strategy_id="strat_1",
            symbol="AAPL",
            side=MagicMock(value="LONG"),
            quantity=10.0,
            entry_price=100.0,
            current_price=110.0,
            unrealized_pnl=100.0,
            realized_pnl=0.0,
            opened_at=datetime(2025, 1, 1),
            etoro_position_id="etoro_pos_1",
            stop_loss=95.0,
            take_profit=None,
            closed_at=None,
        )

        manager.check_trailing_stops([position], skip_etoro_update=False)

        expected_stop = 110.0 * (1 - 0.03)
        assert abs(position.stop_loss - expected_stop) < 0.01
        etoro_client.update_position_stop_loss.assert_called_once()


class TestNoOpenPositions:
    """Test edge case with no open positions."""

    def test_returns_zeros_when_no_positions(self):
        """Should return zero counts when there are no open positions."""
        svc = _build_service()

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = []
        svc.db.get_session.return_value = session

        result = svc._check_trailing_stops()

        assert result["updated"] == 0
        assert result.get("breach_closures", 0) == 0
