"""Tests for the durable WF-validation ledger (2026-06-19).

The ledger persists the walk-forward test Sharpe per (template, symbol) so it
survives BACKTESTED-TTL deletion of the strategy versions that carried it. This
prevents the graduation gate from transiently fail-closing a pair whose WF edge
WAS established when every surviving version of its template momentarily lacks a
wf_test_sharpe (deleted + not-yet-re-validated).

Same class of fix as the trade-history loss (commit 1a373bd): metadata recovered
from a store that outlives version deletion.
"""
from contextlib import contextmanager
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.orm import Base, WfValidationLedgerORM
from src.strategy import wf_ledger
from src.strategy.graduation_gate import is_qualified


@pytest.fixture
def db_session():
    """In-memory SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def mock_db(db_session):
    """A fake Database exposing get_session + session_scope over the test session.

    Patched in for `src.models.database.get_database` so the ledger writes land
    in the in-memory SQLite DB.
    """
    @contextmanager
    def _scope():
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise

    fake = Mock()
    fake.get_session.return_value = db_session
    fake.session_scope.side_effect = _scope
    with patch("src.models.database.get_database", return_value=fake):
        yield fake


# ── record_wf_validation ───────────────────────────────────────────────────

def test_record_creates_row(db_session, mock_db):
    wf_ledger.record_wf_validation("RSI Dip Buy", "AAPL", 1.42, wf_test_trades=12)
    rows = db_session.query(WfValidationLedgerORM).all()
    assert len(rows) == 1
    r = rows[0]
    assert r.template_name == "RSI Dip Buy"
    assert r.symbol == "AAPL"
    assert r.wf_test_sharpe == pytest.approx(1.42)
    assert r.wf_test_trades == 12
    assert r.best_wf_test_sharpe == pytest.approx(1.42)
    assert r.validation_count == 1
    assert r.source == "proposer"


def test_record_upserts_latest_and_tracks_best_and_count(db_session, mock_db):
    wf_ledger.record_wf_validation("T", "MU", 2.0, wf_test_trades=8)
    # Re-validation with a LOWER sharpe — latest wins, best stays high, count bumps.
    wf_ledger.record_wf_validation("T", "MU", 1.1, wf_test_trades=20)
    rows = db_session.query(WfValidationLedgerORM).all()
    assert len(rows) == 1  # upsert, not duplicate
    r = rows[0]
    assert r.wf_test_sharpe == pytest.approx(1.1)        # latest reflects current edge
    assert r.best_wf_test_sharpe == pytest.approx(2.0)   # max ever retained
    assert r.wf_test_trades == 20
    assert r.validation_count == 2


def test_record_ignores_non_positive_and_none(db_session, mock_db):
    wf_ledger.record_wf_validation("T", "X", 0.0)
    wf_ledger.record_wf_validation("T", "Y", -1.5)
    wf_ledger.record_wf_validation("T", "Z", None)
    wf_ledger.record_wf_validation(None, "Q", 1.0)
    wf_ledger.record_wf_validation("T", None, 1.0)
    assert db_session.query(WfValidationLedgerORM).count() == 0


def test_record_never_raises_on_db_error():
    # No patch → import inside the function will still resolve get_database, so
    # force a failure by patching it to raise. Must be swallowed.
    with patch("src.models.database.get_database", side_effect=RuntimeError("boom")):
        wf_ledger.record_wf_validation("T", "S", 1.0)  # should not raise


# ── load_wf_ledger ───────────────────────────────────────────────────────────

def test_load_returns_pair_map(db_session, mock_db):
    wf_ledger.record_wf_validation("Tmpl A", "AAPL", 1.5)
    wf_ledger.record_wf_validation("Tmpl A", "MSFT", 0.9)
    wf_ledger.record_wf_validation("Tmpl B", "MU", 2.1)
    loaded = wf_ledger.load_wf_ledger(db_session)
    assert loaded[("Tmpl A", "AAPL")] == pytest.approx(1.5)
    assert loaded[("Tmpl A", "MSFT")] == pytest.approx(0.9)
    assert loaded[("Tmpl B", "MU")] == pytest.approx(2.1)
    assert len(loaded) == 3


def test_load_empty_when_no_rows(db_session):
    assert wf_ledger.load_wf_ledger(db_session) == {}


# ── end-to-end intent: recovery feeds the qualification gate ─────────────────

_GOOD = dict(paper_trades=20, paper_sharpe=2.0, paper_win_rate=0.60, paper_total_pnl=800.0)


def test_recovered_wf_sharpe_lets_established_pair_qualify():
    """The whole point: a pair with no current-version WF Sharpe but a ledger
    entry recovers it and qualifies, instead of fail-closing."""
    # Simulate the gate's recovery order: row.wf_sharpe missing, template max 0,
    # ledger supplies the established value.
    wf_by_pair = {("Trend X", "XLK"): 1.5}
    recovered = wf_by_pair.get(("Trend X", "XLK"), 0.0) or None
    ok, reasons = is_qualified(_GOOD, recovered, interval="4h", strategy_type="trend_following")
    assert ok is True, reasons


def test_without_ledger_established_pair_fails_closed():
    """Control: no ledger entry and no other WF source → fail-closed (the bug)."""
    wf_by_pair = {}
    recovered = wf_by_pair.get(("Trend X", "XLK"), 0.0) or None
    ok, reasons = is_qualified(_GOOD, recovered, interval="4h", strategy_type="trend_following")
    assert ok is False
    assert any("wf_sharpe" in r and "fail-closed" in r for r in reasons)
