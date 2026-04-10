"""Tests for signal decision logging (Task 11.8.13)."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.orm import Base, SignalDecisionLogORM


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestSignalDecisionLogORM:
    """Tests for the SignalDecisionLogORM model."""

    def test_create_accepted_signal(self, db_session):
        """Test creating an accepted signal decision log entry."""
        entry = SignalDecisionLogORM(
            signal_id="sig-001",
            strategy_id="strat-001",
            symbol="AAPL",
            side="BUY",
            signal_type="ENTRY",
            decision="ACCEPTED",
            rejection_reason=None,
            created_at=datetime.now(),
            metadata_json={"confidence": 0.85, "strategy_name": "Test Strategy"},
        )
        db_session.add(entry)
        db_session.commit()

        result = db_session.query(SignalDecisionLogORM).first()
        assert result is not None
        assert result.signal_id == "sig-001"
        assert result.decision == "ACCEPTED"
        assert result.rejection_reason is None

    def test_create_rejected_signal(self, db_session):
        """Test creating a rejected signal decision log entry."""
        entry = SignalDecisionLogORM(
            signal_id="sig-002",
            strategy_id="strat-002",
            symbol="MSFT",
            side="SELL",
            signal_type="ENTRY",
            decision="REJECTED",
            rejection_reason="Portfolio balance: max sector exposure exceeded",
            created_at=datetime.now(),
            metadata_json={"confidence": 0.72},
        )
        db_session.add(entry)
        db_session.commit()

        result = db_session.query(SignalDecisionLogORM).first()
        assert result is not None
        assert result.decision == "REJECTED"
        assert "Portfolio balance" in result.rejection_reason

    def test_to_dict(self, db_session):
        """Test the to_dict method returns all expected fields."""
        now = datetime.now()
        entry = SignalDecisionLogORM(
            signal_id="sig-003",
            strategy_id="strat-003",
            symbol="GOOGL",
            side="BUY",
            signal_type="EXIT",
            decision="ACCEPTED",
            rejection_reason=None,
            created_at=now,
            metadata_json={"confidence": 0.90},
        )
        db_session.add(entry)
        db_session.commit()

        result = db_session.query(SignalDecisionLogORM).first()
        d = result.to_dict()

        assert d["signal_id"] == "sig-003"
        assert d["strategy_id"] == "strat-003"
        assert d["symbol"] == "GOOGL"
        assert d["side"] == "BUY"
        assert d["signal_type"] == "EXIT"
        assert d["decision"] == "ACCEPTED"
        assert d["rejection_reason"] is None
        assert d["created_at"] is not None
        assert d["metadata"] == {"confidence": 0.90}

    def test_query_by_decision(self, db_session):
        """Test querying signals filtered by decision type."""
        for i in range(5):
            db_session.add(SignalDecisionLogORM(
                signal_id=f"sig-a{i}",
                strategy_id="strat-001",
                symbol="AAPL",
                side="BUY",
                signal_type="ENTRY",
                decision="ACCEPTED",
                created_at=datetime.now(),
            ))
        for i in range(3):
            db_session.add(SignalDecisionLogORM(
                signal_id=f"sig-r{i}",
                strategy_id="strat-001",
                symbol="MSFT",
                side="SELL",
                signal_type="ENTRY",
                decision="REJECTED",
                rejection_reason="Risk limit exceeded",
                created_at=datetime.now(),
            ))
        db_session.commit()

        accepted = db_session.query(SignalDecisionLogORM).filter_by(decision="ACCEPTED").count()
        rejected = db_session.query(SignalDecisionLogORM).filter_by(decision="REJECTED").count()
        assert accepted == 5
        assert rejected == 3

    def test_ordering_by_created_at(self, db_session):
        """Test that signals can be ordered by creation time."""
        now = datetime.now()
        for i in range(3):
            db_session.add(SignalDecisionLogORM(
                signal_id=f"sig-{i}",
                strategy_id="strat-001",
                symbol="AAPL",
                side="BUY",
                signal_type="ENTRY",
                decision="ACCEPTED",
                created_at=now - timedelta(minutes=i),
            ))
        db_session.commit()

        results = (
            db_session.query(SignalDecisionLogORM)
            .order_by(SignalDecisionLogORM.created_at.desc())
            .all()
        )
        assert results[0].signal_id == "sig-0"  # Most recent
        assert results[2].signal_id == "sig-2"  # Oldest


class TestRejectionCategorization:
    """Tests for the rejection reason categorization in the signals router."""

    def test_categorize_duplicate(self):
        from src.api.routers.signals import _categorize_rejection
        assert _categorize_rejection("Duplicate: 2 existing LONG position(s) in AAPL") == "Duplicate Position"

    def test_categorize_portfolio_balance(self):
        from src.api.routers.signals import _categorize_rejection
        assert _categorize_rejection("Portfolio balance: max sector exposure exceeded") == "Portfolio Balance"

    def test_categorize_risk_limit(self):
        from src.api.routers.signals import _categorize_rejection
        assert _categorize_rejection("Risk limit: position size too large") == "Risk Limit"

    def test_categorize_correlation(self):
        from src.api.routers.signals import _categorize_rejection
        assert _categorize_rejection("Correlation filter: MSFT correlated with AAPL") == "Correlated Symbol"

    def test_categorize_symbol_limit(self):
        from src.api.routers.signals import _categorize_rejection
        assert _categorize_rejection("Symbol limit reached for AAPL") == "Symbol Limit"

    def test_categorize_pending(self):
        from src.api.routers.signals import _categorize_rejection
        assert _categorize_rejection("Pending order already exists") == "Pending Order Exists"

    def test_categorize_other(self):
        from src.api.routers.signals import _categorize_rejection
        assert _categorize_rejection("Some unknown reason") == "Other"


class TestSignalDecisionLogging:
    """Tests for the _log_signal_decision method in TradingScheduler."""

    def test_log_signal_decision_accepted(self, db_session):
        """Test that _log_signal_decision correctly logs an accepted signal."""
        from src.core.trading_scheduler import TradingScheduler

        scheduler = TradingScheduler()
        scheduler._websocket_manager = None  # No WS for test

        # Create a mock signal
        signal = MagicMock()
        signal.strategy_id = "strat-test"
        signal.symbol = "NVDA"
        signal.confidence = 0.88
        signal.action = MagicMock()
        signal.action.value = "ENTER_LONG"
        signal.reasoning = "Strong momentum"
        signal.id = None

        scheduler._log_signal_decision(
            session=db_session,
            signal=signal,
            strategy_name="Test Momentum",
            decision="ACCEPTED",
            rejection_reason=None,
        )

        result = db_session.query(SignalDecisionLogORM).first()
        assert result is not None
        assert result.decision == "ACCEPTED"
        assert result.symbol == "NVDA"
        assert result.side == "BUY"
        assert result.signal_type == "ENTRY"
        assert result.rejection_reason is None

    def test_log_signal_decision_rejected(self, db_session):
        """Test that _log_signal_decision correctly logs a rejected signal."""
        from src.core.trading_scheduler import TradingScheduler

        scheduler = TradingScheduler()
        scheduler._websocket_manager = None

        signal = MagicMock()
        signal.strategy_id = "strat-test"
        signal.symbol = "TSLA"
        signal.confidence = 0.65
        signal.action = MagicMock()
        signal.action.value = "ENTER_SHORT"
        signal.reasoning = "Bearish divergence"
        signal.id = None

        scheduler._log_signal_decision(
            session=db_session,
            signal=signal,
            strategy_name="Test Short",
            decision="REJECTED",
            rejection_reason="Risk limit: max exposure exceeded",
        )

        result = db_session.query(SignalDecisionLogORM).first()
        assert result is not None
        assert result.decision == "REJECTED"
        assert result.symbol == "TSLA"
        assert result.side == "SELL"
        assert result.signal_type == "ENTRY"
        assert "Risk limit" in result.rejection_reason
