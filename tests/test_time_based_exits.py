"""
Tests for time-based exit enforcement for DSL strategies (Task 11.8.8).

Tests the _check_time_based_exits() method in MonitoringService that
flags positions exceeding max_holding_period_days for closure.
Alpha Edge strategies are skipped (they have their own hold period logic).
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.orm import Base, PositionORM, StrategyORM
from src.models.enums import PositionSide, StrategyStatus
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


def _create_strategy(session, strat_id="strat_1", category=None):
    """Helper to create a test strategy with optional category metadata."""
    metadata = {}
    if category:
        metadata["strategy_category"] = category
    strategy = StrategyORM(
        id=strat_id,
        name=f"Test Strategy {strat_id}",
        description="Test",
        status=StrategyStatus.DEMO,
        rules={"entry_conditions": []},
        symbols=["AAPL"],
        allocation_percent=2.0,
        risk_params={},
        created_at=datetime.utcnow(),
        performance={},
        strategy_metadata=metadata,
    )
    session.add(strategy)
    session.commit()
    return strategy


def _create_position(session, pos_id="pos_1", symbol="AAPL", strategy_id="strat_1",
                     days_held=70, pending=False, closed_at=None):
    """Helper to create a test position opened `days_held` days ago."""
    pos = PositionORM(
        id=pos_id,
        strategy_id=strategy_id,
        symbol=symbol,
        side=PositionSide.LONG,
        quantity=100.0,
        entry_price=150.0,
        current_price=145.0,
        unrealized_pnl=-500.0,
        realized_pnl=0.0,
        opened_at=datetime.utcnow() - timedelta(days=days_held),
        etoro_position_id=f"etoro_{pos_id}",
        pending_closure=pending,
        closure_reason=None,
        closed_at=closed_at,
    )
    session.add(pos)
    session.commit()
    return pos


YAML_CONFIG = {
    "position_management": {
        "max_holding_period_days": 60,
    },
    "alpha_edge": {
        "fundamental_monitoring": {},
    },
}


class TestCheckTimeBasedExits:
    """Tests for _check_time_based_exits()."""

    def _patch_yaml(self):
        """Return a patch for yaml.safe_load returning our test config."""
        return patch("builtins.open", create=True), patch(
            "yaml.safe_load", return_value=YAML_CONFIG
        )

    def test_no_open_positions(self, monitoring_service, in_memory_db):
        """Should return zeros when no open positions exist."""
        with patch("builtins.open", MagicMock()), patch("yaml.safe_load", return_value=YAML_CONFIG):
            result = monitoring_service._check_time_based_exits()
        assert result["checked"] == 0
        assert result["flagged"] == 0

    def test_flags_position_exceeding_max_hold(self, monitoring_service, in_memory_db):
        """Position held 70 days should be flagged when max is 60."""
        session = in_memory_db.get_session()
        _create_strategy(session, "strat_1", category=None)
        _create_position(session, "pos_1", days_held=70, strategy_id="strat_1")

        with patch("builtins.open", MagicMock()), patch("yaml.safe_load", return_value=YAML_CONFIG):
            result = monitoring_service._check_time_based_exits()

        assert result["checked"] == 1
        assert result["flagged"] == 1

        pos = session.query(PositionORM).get("pos_1")
        assert pos.pending_closure is True
        assert "70 days" in pos.closure_reason
        assert "limit: 60" in pos.closure_reason

    def test_does_not_flag_position_within_limit(self, monitoring_service, in_memory_db):
        """Position held 30 days should NOT be flagged when max is 60."""
        session = in_memory_db.get_session()
        _create_strategy(session, "strat_1", category=None)
        _create_position(session, "pos_1", days_held=30, strategy_id="strat_1")

        with patch("builtins.open", MagicMock()), patch("yaml.safe_load", return_value=YAML_CONFIG):
            result = monitoring_service._check_time_based_exits()

        assert result["checked"] == 1
        assert result["flagged"] == 0

        pos = session.query(PositionORM).get("pos_1")
        assert pos.pending_closure is False

    def test_skips_alpha_edge_strategies(self, monitoring_service, in_memory_db):
        """Alpha Edge positions should be skipped entirely."""
        session = in_memory_db.get_session()
        _create_strategy(session, "strat_ae", category="alpha_edge")
        _create_position(session, "pos_ae", days_held=90, strategy_id="strat_ae")

        with patch("builtins.open", MagicMock()), patch("yaml.safe_load", return_value=YAML_CONFIG):
            result = monitoring_service._check_time_based_exits()

        assert result["checked"] == 0
        assert result["flagged"] == 0
        assert result["skipped_alpha_edge"] == 1

        pos = session.query(PositionORM).get("pos_ae")
        assert pos.pending_closure is False

    def test_skips_already_pending_closure(self, monitoring_service, in_memory_db):
        """Positions already pending closure should not be checked."""
        session = in_memory_db.get_session()
        _create_strategy(session, "strat_1", category=None)
        _create_position(session, "pos_1", days_held=90, strategy_id="strat_1", pending=True)

        with patch("builtins.open", MagicMock()), patch("yaml.safe_load", return_value=YAML_CONFIG):
            result = monitoring_service._check_time_based_exits()

        assert result["checked"] == 0
        assert result["flagged"] == 0

    def test_skips_closed_positions(self, monitoring_service, in_memory_db):
        """Closed positions should not be checked."""
        session = in_memory_db.get_session()
        _create_strategy(session, "strat_1", category=None)
        _create_position(session, "pos_1", days_held=90, strategy_id="strat_1",
                         closed_at=datetime.utcnow())

        with patch("builtins.open", MagicMock()), patch("yaml.safe_load", return_value=YAML_CONFIG):
            result = monitoring_service._check_time_based_exits()

        assert result["checked"] == 0
        assert result["flagged"] == 0

    def test_mixed_positions(self, monitoring_service, in_memory_db):
        """Test with a mix of DSL (over limit), DSL (under limit), and Alpha Edge."""
        session = in_memory_db.get_session()
        _create_strategy(session, "strat_dsl", category=None)
        _create_strategy(session, "strat_ae", category="alpha_edge")

        # DSL position over limit
        _create_position(session, "pos_over", days_held=65, strategy_id="strat_dsl", symbol="MSFT")
        # DSL position under limit
        _create_position(session, "pos_under", days_held=10, strategy_id="strat_dsl", symbol="GOOGL")
        # Alpha Edge position over limit (should be skipped)
        _create_position(session, "pos_ae", days_held=100, strategy_id="strat_ae", symbol="AAPL")

        with patch("builtins.open", MagicMock()), patch("yaml.safe_load", return_value=YAML_CONFIG):
            result = monitoring_service._check_time_based_exits()

        assert result["checked"] == 2
        assert result["flagged"] == 1
        assert result["skipped_alpha_edge"] == 1

        pos_over = session.query(PositionORM).get("pos_over")
        assert pos_over.pending_closure is True

        pos_under = session.query(PositionORM).get("pos_under")
        assert pos_under.pending_closure is False

    def test_boundary_exactly_at_limit(self, monitoring_service, in_memory_db):
        """Position held exactly max_holding_period_days should NOT be flagged (> not >=)."""
        session = in_memory_db.get_session()
        _create_strategy(session, "strat_1", category=None)
        _create_position(session, "pos_1", days_held=60, strategy_id="strat_1")

        with patch("builtins.open", MagicMock()), patch("yaml.safe_load", return_value=YAML_CONFIG):
            result = monitoring_service._check_time_based_exits()

        assert result["flagged"] == 0

    def test_uses_default_when_config_missing(self, monitoring_service, in_memory_db):
        """Should default to 60 days when config key is missing."""
        session = in_memory_db.get_session()
        _create_strategy(session, "strat_1", category=None)
        _create_position(session, "pos_1", days_held=65, strategy_id="strat_1")

        empty_config = {"position_management": {}}
        with patch("builtins.open", MagicMock()), patch("yaml.safe_load", return_value=empty_config):
            result = monitoring_service._check_time_based_exits()

        assert result["flagged"] == 1

    def test_handles_strategy_not_found(self, monitoring_service, in_memory_db):
        """Position with no matching strategy should still be checked (not Alpha Edge)."""
        session = in_memory_db.get_session()
        # Create position without a strategy record
        _create_position(session, "pos_orphan", days_held=70, strategy_id="nonexistent")

        with patch("builtins.open", MagicMock()), patch("yaml.safe_load", return_value=YAML_CONFIG):
            result = monitoring_service._check_time_based_exits()

        assert result["checked"] == 1
        assert result["flagged"] == 1
