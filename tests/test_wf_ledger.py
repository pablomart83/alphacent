"""Tests for the durable WF-validation ledger (2026-06-19).

The ledger persists the walk-forward test Sharpe per (template, symbol) so it
survives BACKTESTED-TTL deletion of the strategy versions that carried it.

NOTE: the paper/WF qualification-ratio graduation gate was removed (same day,
after this ledger shipped) because it compared incompatible Sharpe bases and was
redundant with the upstream WF acceptance + activation min_sharpe=1.0 + MC
bootstrap. The ledger therefore no longer feeds a hard gate — it now supplies the
WF value for INFORMATIONAL paper-vs-WF divergence on the CIO graduation card
(and is the substrate for the planned regime-conditional WF check). The
record/load/backfill behaviour below is still the durable store for that value.
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


# ── end-to-end intent: WF availability is no longer a graduation gate ─────────
# As of 2026-06-19 the paper/WF qualification-ratio gate was removed (broken basis
# + redundant with upstream WF acceptance, activation min_sharpe=1.0 and MC). The
# ledger now serves the WF value for INFORMATIONAL display, not gating — so WF
# presence/absence must NOT change the qualification verdict.

_GOOD = dict(paper_trades=20, paper_sharpe=2.0, paper_win_rate=0.60, paper_total_pnl=800.0)


def test_wf_present_does_not_block_strong_pair():
    """A strong paper pair qualifies regardless of how large the paper/WF ratio is
    (the old max-ratio cap that rejected this is gone)."""
    # paper 2.0 vs wf 0.4 = 5× — would have been rejected by the old cap.
    ok, reasons = is_qualified(_GOOD, 0.4, interval="4h", strategy_type="trend_following")
    assert ok is True, reasons


def test_wf_absent_no_longer_fails_closed():
    """Control: with no WF value at all, a strong paper pair still qualifies — the
    fail-closed-on-missing-WF behaviour was removed with the ratio gate."""
    ok, reasons = is_qualified(_GOOD, None, interval="4h", strategy_type="trend_following")
    assert ok is True, reasons
    assert not any("wf_sharpe" in r for r in reasons)
