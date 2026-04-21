"""Retire all BACKTESTED strategies approved via factor_validation with null wf_test_sharpe.

Root cause: FMP insider endpoint returns 403/404 on current plan → 0 backtest trades
→ factor_validation fallback approved them despite in_right_quintile=false.
These have no real WF evidence and should not fire signals.
"""
import sys, os
sys.path.insert(0, "/home/ubuntu/alphacent")
os.chdir("/home/ubuntu/alphacent")

from sqlalchemy import create_engine, text
import subprocess

result = subprocess.run(
    ["grep", "DATABASE_URL", ".env.production"],
    capture_output=True, text=True, cwd="/home/ubuntu/alphacent"
)
db_url = result.stdout.strip().split("=", 1)[1]
engine = create_engine(db_url)

with engine.connect() as conn:
    # First: list what we're about to retire
    rows = conn.execute(text(
        "SELECT id, name FROM strategies "
        "WHERE status = 'BACKTESTED' "
        "AND (strategy_metadata->>'wf_test_sharpe') IS NULL "
        "AND (strategy_metadata->>'activation_approved')::bool = true"
    )).fetchall()

    if not rows:
        print("No matching strategies found.")
        sys.exit(0)

    print(f"Retiring {len(rows)} strategies:")
    for r in rows:
        print(f"  - {r[1]}")

    reason = (
        "null_wf_sharpe: approved via factor_validation fallback with 0 FMP backtest trades. "
        "FMP insider endpoint unavailable (403/404 on current plan). "
        "Factor gate3 in_right_quintile=false not enforced. "
        "Re-propose after FMP plan upgrade or insider proxy fix."
    )

    updated = conn.execute(text(
        "UPDATE strategies "
        "SET status = 'RETIRED', "
        "    retired_at = NOW(), "
        "    strategy_metadata = (strategy_metadata::jsonb || jsonb_build_object("
        "        'activation_approved', false,"
        "        'retirement_reason', :reason,"
        "        'retired_by', 'manual_audit',"
        "        'retired_at', NOW()::text"
        "    ))::json "
        "WHERE status = 'BACKTESTED' "
        "AND (strategy_metadata->>'wf_test_sharpe') IS NULL "
        "AND (strategy_metadata->>'activation_approved')::bool = true "
        "RETURNING name"
    ), {"reason": reason})

    retired = [r[0] for r in updated.fetchall()]
    conn.commit()

print(f"\nDone: {len(retired)} strategies retired.")
for name in retired:
    print(f"  RETIRED: {name}")
