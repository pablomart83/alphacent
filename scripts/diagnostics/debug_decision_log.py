"""Diagnose the decision_log silent-failure bug.

The `record_batch`/`record_decision` functions in src/analytics/decision_log.py
catch every exception and log at DEBUG level. The logger is configured at
INFO+, so any failure is invisible. This script:

1. Forces logging.DEBUG on decision_log + sqlalchemy
2. Calls record_decision + record_batch with real payloads
3. Prints any exception fully
4. Queries the table to confirm persistence

Run from repo root on the box where the service normally runs (so the
sqlalchemy engine connects to the same Postgres):

    cd /home/ubuntu/alphacent
    venv/bin/python3 scripts/diagnostics/debug_decision_log.py
"""

import logging
import sys
import traceback
from pathlib import Path

# Ensure we can import from repo root regardless of CWD
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Verbose everything
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)


def try_single_write():
    print("\n=== record_decision (single) ===")
    try:
        from src.analytics.decision_log import record_decision

        record_decision(
            stage="diag_single",
            decision="accepted",
            template="DIAG_TEMPLATE",
            symbol="DIAG_SYM",
            direction="long",
            cycle_id="diag_cycle_single",
            market_regime="diag_regime",
            score=1.23,
            reason="diagnostic single-row write",
            metadata={"src": "debug_decision_log.py", "numpy_free": True},
        )
        print("record_decision call returned (no exception surfaced).")
    except Exception:
        traceback.print_exc()


def try_batch_write():
    print("\n=== record_batch (3 rows) ===")
    try:
        from src.analytics.decision_log import record_batch

        rows = [
            {
                "stage": "diag_batch",
                "decision": "accepted",
                "template": "DIAG_TEMPLATE",
                "symbol": f"SYM{i}",
                "direction": "long",
                "cycle_id": "diag_cycle_batch",
                "market_regime": "diag_regime",
                "score": float(i),
                "reason": f"diag batch row {i}",
                "metadata": {"i": i},
            }
            for i in range(3)
        ]
        record_batch(rows)
        print("record_batch call returned (no exception surfaced).")
    except Exception:
        traceback.print_exc()


def try_raw_orm_insert():
    """Bypass the fire-and-forget wrapper and let exceptions bubble up."""
    print("\n=== raw ORM insert (exceptions NOT swallowed) ===")
    try:
        from datetime import datetime

        from src.models.database import get_database
        from src.models.orm import SignalDecisionORM

        db = get_database()
        session = db.get_session()
        try:
            row = SignalDecisionORM(
                timestamp=datetime.now(),
                cycle_id="diag_cycle_raw",
                strategy_id="diag_strategy",
                template_name="DIAG_TEMPLATE",
                symbol="DIAG_RAW",
                direction="long",
                market_regime="diag_regime",
                stage="diag_raw",
                decision="accepted",
                reason="raw insert no wrapper",
                score=9.99,
                decision_metadata={"raw": True},
            )
            session.add(row)
            session.commit()
            print(f"Raw insert committed, row.id={row.id}")
        finally:
            session.close()
    except Exception:
        traceback.print_exc()


def count_rows():
    print("\n=== count after inserts ===")
    try:
        from src.models.database import get_database
        from src.models.orm import SignalDecisionORM

        db = get_database()
        session = db.get_session()
        try:
            total = session.query(SignalDecisionORM).count()
            diag = (
                session.query(SignalDecisionORM)
                .filter(SignalDecisionORM.stage.like("diag_%"))
                .count()
            )
            print(f"total rows: {total}")
            print(f"diag_* rows: {diag}")

            recent = (
                session.query(SignalDecisionORM)
                .filter(SignalDecisionORM.stage.like("diag_%"))
                .all()
            )
            for r in recent:
                print(
                    f"  id={r.id} stage={r.stage} decision={r.decision} "
                    f"template={r.template_name} symbol={r.symbol}"
                )
        finally:
            session.close()
    except Exception:
        traceback.print_exc()


def describe_db_url():
    print("\n=== db config ===")
    try:
        from src.models.database import get_database

        db = get_database()
        print(f"database_url: {db.database_url}")
        print(f"is_postgres: {db.is_postgres}")
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    describe_db_url()
    try_single_write()
    try_batch_write()
    try_raw_orm_insert()
    count_rows()
