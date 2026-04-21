"""Flag losing weak-watchlist positions for pending_closure.

These positions were opened on symbols that had insufficient WF evidence
(S<0.2 or t<3 for same-class, or cross-asset with no validation).
They are currently losing money and tying up ~$82K of capital.
Winners from the same group are left to run to TP.
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

# Exact IDs from the audit query — losing weak-watchlist positions only
position_ids = [
    "635977c1-f963-42d4-b902-0178e2af568f",  # COIN   -148
    "ddcc781d-b67f-4831-8f1d-43abfbfe9471",  # INTC   -103
    "3496758667",                              # RIO     -58
    "9e56d8dd-1157-42b9-95c7-482ad01c2d7a",  # SCCO    -55
    "d7b77164-294c-4f13-a37f-ad4dbd2102a4",  # BTC     -50
    "2b2e0a49-92d3-480d-968f-e614cf86a455",  # LRCX    -48
    "ac457d46-8055-4827-952b-491f5830922b",  # SCCO    -47
    "d2e0fb3f-1d7f-49f2-9da6-2f9eddfcdeb4",  # HWM     -46
    "06b4ca96-0edb-467b-ab5e-f94489a7d601",  # XOM     -45
    "fa2df7d4-0535-404d-ac11-57edee639ed0",  # ITW     -41
    "dc1342c4-f0be-4c23-80e6-03958d4f5456",  # VTI     -28
    "1473c607-b4ae-43ac-bcac-b4633417c9eb",  # CVX     -27
    "ec1ff692-00a1-43aa-a321-152d3390a200",  # BABA    -26
    "61c08eed-6a12-44cd-8028-d2eb635181c8",  # GS      -16
    "9e56d8dd-1157-42b9-95c7-482ad01c2d7a",  # SCCO (dup check)
    "cffbef5d-91a6-4dc3-bb7e-d1ee9d1f8c2a",  # CAT     -16
    "510bbf19-61b5-49d6-b034-d3665b88a0e6",  # AMAT    -15
    "c5a7df0b-4d6a-41bd-8325-69bdd525eef8",  # VOO     -14
    "c8099b6c-76d7-4a11-9e50-46f4b1736d46",  # PYPL    -10
    "666a3323-eb5e-4ca8-9646-8eeb372d2a43",  # AUDUSD  -10
    "e7d41da8-e067-4dea-a8d7-ba80445129b3",  # USDCAD   -9
    "81642b27-f5f3-4c7a-8df4-d71b51234d56",  # GBPUSD   -9
    "e76f7b4c-2b71-4c0e-a693-d330bc35d8c2",  # SPY      -8
    "15483e83-84d3-484b-8664-b2eb3516ba5b",  # GEV      -7
    "7129c0a0-5fc6-4cd2-aeb8-8f18de9d22a9",  # ALB      -5
    "41c3523b-3ffc-4dbe-a9ce-6fd838497b48",  # NZDUSD   -3
    "fb8ab6aa-a5f8-48d2-89a8-4d8800eb44c2",  # MSFT     -2
    "7b5239ca-b4af-4773-98d1-62a41935e1a2",  # LOW      -2
]

# Also include eToro-ID positions (numeric IDs from the query)
etoro_style_ids = [
    "3497145622",   # ETH    -113
    "3492776879",   # ITA     -72
    "3499109583",   # BTC     -16
    "3499109524",   # CAT     -16
    "3496619696",   # COP     -13
    "3498232352",   # GS      -11
]

with engine.connect() as conn:
    # For UUID-style IDs
    uuid_ids = [i for i in position_ids if "-" in i]
    updated = 0

    for pid in set(uuid_ids):  # deduplicate
        result = conn.execute(text(
            "UPDATE positions SET pending_closure = true, "
            "closure_reason = 'weak_watchlist_loser: opened on symbol with insufficient WF evidence (cross-asset or S<threshold). Flagged for closure by manual audit.' "
            "WHERE id = :pid AND closed_at IS NULL AND unrealized_pnl < 0 "
            "RETURNING id, symbol"
        ), {"pid": pid})
        row = result.fetchone()
        if row:
            print(f"  Flagged: {row[1]} ({row[0]})")
            updated += 1

    # For eToro-style numeric IDs — match by etoro_position_id
    for eid in etoro_style_ids:
        result = conn.execute(text(
            "UPDATE positions SET pending_closure = true, "
            "closure_reason = 'weak_watchlist_loser: opened on symbol with insufficient WF evidence (cross-asset or S<threshold). Flagged for closure by manual audit.' "
            "WHERE etoro_position_id = :eid AND closed_at IS NULL AND unrealized_pnl < 0 "
            "RETURNING id, symbol, etoro_position_id"
        ), {"eid": eid})
        row = result.fetchone()
        if row:
            print(f"  Flagged: {row[1]} (eToro: {row[2]})")
            updated += 1

    conn.commit()

print(f"\nDone: {updated} positions flagged for pending_closure.")
print("These will be closed by the monitoring service's pending closure processor.")
