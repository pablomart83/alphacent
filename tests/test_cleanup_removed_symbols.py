"""Tests for cleanup_removed_symbols and warm_new_symbols_cache (Task 11.9.4).

Tests the database cleanup functions for removing data associated with
symbols that have been removed from the tradeable instruments list.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.orm import (
    Base, StrategyORM, OrderORM, PositionORM, MarketDataORM,
    TradingSignalORM, HistoricalPriceCacheORM, FundamentalDataORM,
    DataQualityReportORM, EarningsHistoryORM, FundamentalFilterLogORM,
    MLFilterLogORM, ConvictionScoreLogORM, RejectedSignalORM,
    SignalDecisionLogORM,
)
from src.models.enums import (
    StrategyStatus, OrderSide, OrderType, OrderStatus,
    PositionSide, SignalAction,
)
from src.models.database import cleanup_removed_symbols


@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database with all tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    return engine, session


@pytest.fixture
def seeded_db(in_memory_db):
    """Seed the in-memory DB with test data for SQ, DE, and AAPL."""
    engine, session = in_memory_db

    # Historical prices
    for symbol in ["SQ", "DE", "AAPL"]:
        for i in range(3):
            session.add(HistoricalPriceCacheORM(
                symbol=symbol,
                date=datetime.now() - timedelta(days=i),
                open=100.0, high=105.0, low=95.0, close=102.0,
                volume=1000000, source="yahoo_finance",
            ))

    # Fundamental data
    for symbol in ["SQ", "DE", "AAPL"]:
        session.add(FundamentalDataORM(
            symbol=symbol,
            eps=5.0, revenue=1000000.0, revenue_growth=0.1,
            pe_ratio=20.0, market_cap=50000000000.0,
            roe=0.15, debt_to_equity=0.3,
            source="FMP",
            fetched_at=datetime.now(),
        ))

    # Data quality reports
    for symbol in ["SQ", "DE", "AAPL"]:
        session.add(DataQualityReportORM(
            symbol=symbol,
            quality_score=85.0,
            total_points=100,
            issue_count=2,
            error_count=0,
            warning_count=2,
        ))

    # Earnings history
    for symbol in ["SQ", "DE", "AAPL"]:
        session.add(EarningsHistoryORM(
            symbol=symbol,
            earnings_date=datetime.now(),
            actual_eps=2.5,
            estimated_eps=2.3,
            surprise_pct=8.7,
            source="FMP",
        ))

    # Orders
    for symbol in ["SQ", "DE", "AAPL"]:
        session.add(OrderORM(
            id=f"order-{symbol}-1",
            strategy_id="strat-1",
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10.0,
            status=OrderStatus.FILLED,
            submitted_at=datetime.now(),
        ))

    # Positions
    for symbol in ["SQ", "DE", "AAPL"]:
        session.add(PositionORM(
            id=f"pos-{symbol}-1",
            strategy_id="strat-1",
            symbol=symbol,
            side=PositionSide.LONG,
            quantity=10.0,
            entry_price=100.0,
            current_price=105.0,
            unrealized_pnl=50.0,
            realized_pnl=0.0,
            etoro_position_id=f"etoro-{symbol}",
            stop_loss=95.0,
            take_profit=115.0,
            opened_at=datetime.now(),
        ))

    # Strategies — one with only SQ, one with SQ+AAPL, one with only AAPL
    session.add(StrategyORM(
        id="strat-sq-only",
        name="SQ Only Strategy",
        description="Only trades SQ",
        status=StrategyStatus.DEMO,
        rules={"entry_conditions": []},
        symbols=["SQ"],
        allocation_percent=2.0,
        risk_params={},
        created_at=datetime.now(),
        performance={},
    ))
    session.add(StrategyORM(
        id="strat-sq-aapl",
        name="SQ and AAPL Strategy",
        description="Trades SQ and AAPL",
        status=StrategyStatus.DEMO,
        rules={"entry_conditions": []},
        symbols=["SQ", "AAPL"],
        allocation_percent=2.0,
        risk_params={},
        created_at=datetime.now(),
        performance={},
    ))
    session.add(StrategyORM(
        id="strat-aapl-only",
        name="AAPL Only Strategy",
        description="Only trades AAPL",
        status=StrategyStatus.DEMO,
        rules={"entry_conditions": []},
        symbols=["AAPL"],
        allocation_percent=2.0,
        risk_params={},
        created_at=datetime.now(),
        performance={},
    ))

    session.commit()
    return engine, session


class TestCleanupRemovedSymbols:
    """Test cleanup_removed_symbols function."""

    def test_removes_historical_prices_for_removed_symbols(self, seeded_db):
        """Historical price data for removed symbols should be deleted."""
        engine, session = seeded_db

        with patch("src.models.database.get_database") as mock_get_db:
            mock_db = Mock()
            mock_db.get_session.return_value = session
            mock_get_db.return_value = mock_db

            results = cleanup_removed_symbols(["SQ", "DE"])

        assert results["historical_price_cache"] == 6  # 3 per symbol × 2 symbols
        remaining = session.query(HistoricalPriceCacheORM).all()
        assert len(remaining) == 3  # Only AAPL remains
        assert all(r.symbol == "AAPL" for r in remaining)

    def test_removes_fundamental_data_for_removed_symbols(self, seeded_db):
        engine, session = seeded_db

        with patch("src.models.database.get_database") as mock_get_db:
            mock_db = Mock()
            mock_db.get_session.return_value = session
            mock_get_db.return_value = mock_db

            results = cleanup_removed_symbols(["SQ", "DE"])

        assert results["fundamental_data_cache"] == 2
        remaining = session.query(FundamentalDataORM).all()
        assert len(remaining) == 1
        assert remaining[0].symbol == "AAPL"

    def test_removes_orders_and_positions(self, seeded_db):
        engine, session = seeded_db

        with patch("src.models.database.get_database") as mock_get_db:
            mock_db = Mock()
            mock_db.get_session.return_value = session
            mock_get_db.return_value = mock_db

            results = cleanup_removed_symbols(["SQ", "DE"])

        assert results["orders"] == 2
        assert results["positions"] == 2
        remaining_orders = session.query(OrderORM).all()
        assert len(remaining_orders) == 1
        assert remaining_orders[0].symbol == "AAPL"

    def test_retires_strategy_with_only_removed_symbols(self, seeded_db):
        engine, session = seeded_db

        with patch("src.models.database.get_database") as mock_get_db:
            mock_db = Mock()
            mock_db.get_session.return_value = session
            mock_get_db.return_value = mock_db

            results = cleanup_removed_symbols(["SQ"])

        assert results["strategies_retired"] == 1
        strat = session.query(StrategyORM).filter_by(id="strat-sq-only").first()
        assert strat.status == StrategyStatus.RETIRED
        assert strat.retired_at is not None

    def test_updates_strategy_with_mixed_symbols(self, seeded_db):
        engine, session = seeded_db

        with patch("src.models.database.get_database") as mock_get_db:
            mock_db = Mock()
            mock_db.get_session.return_value = session
            mock_get_db.return_value = mock_db

            results = cleanup_removed_symbols(["SQ"])

        assert results["strategies_updated"] == 1
        strat = session.query(StrategyORM).filter_by(id="strat-sq-aapl").first()
        assert strat.symbols == ["AAPL"]
        assert strat.status == StrategyStatus.DEMO  # Not retired

    def test_leaves_unrelated_strategy_untouched(self, seeded_db):
        engine, session = seeded_db

        with patch("src.models.database.get_database") as mock_get_db:
            mock_db = Mock()
            mock_db.get_session.return_value = session
            mock_get_db.return_value = mock_db

            cleanup_removed_symbols(["SQ", "DE"])

        strat = session.query(StrategyORM).filter_by(id="strat-aapl-only").first()
        assert strat.symbols == ["AAPL"]
        assert strat.status == StrategyStatus.DEMO

    def test_empty_symbols_list_is_noop(self):
        results = cleanup_removed_symbols([])
        assert results == {}

    def test_idempotent_second_run(self, seeded_db):
        """Running cleanup twice should be safe — second run deletes 0."""
        engine, session = seeded_db

        with patch("src.models.database.get_database") as mock_get_db:
            mock_db = Mock()
            mock_db.get_session.return_value = session
            mock_get_db.return_value = mock_db

            results1 = cleanup_removed_symbols(["SQ", "DE"])
            results2 = cleanup_removed_symbols(["SQ", "DE"])

        # Second run should find nothing to delete in simple tables
        assert results2["historical_price_cache"] == 0
        assert results2["fundamental_data_cache"] == 0
        assert results2["orders"] == 0
        assert results2["positions"] == 0
