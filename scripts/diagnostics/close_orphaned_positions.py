"""
Close all eToro positions that have no matching open record in our DB.
Runs the diff, then calls close_position for each orphan.
Also creates a stub closed position record in DB so the P&L is tracked.
"""
import sys, subprocess, uuid
from datetime import datetime, timezone
sys.path.insert(0, '/home/ubuntu/alphacent')

from src.core.config import get_config
from src.api.etoro_client import EToroAPIClient
from src.models.enums import TradingMode
from src.utils.symbol_normalizer import normalize_symbol
from src.utils.instrument_mappings import SYMBOL_TO_INSTRUMENT_ID

config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)
client = EToroAPIClient(
    public_key=credentials["public_key"],
    user_key=credentials["user_key"],
    mode=TradingMode.DEMO
)

# Fetch eToro positions
print("Fetching eToro positions...")
etoro_positions = client.get_positions()
etoro_by_id = {str(p.etoro_position_id): p for p in etoro_positions}
print(f"eToro open: {len(etoro_by_id)}")

# Fetch DB open positions via psql
result = subprocess.run(
    ["sudo", "-u", "postgres", "psql", "alphacent", "-t", "-A", "-c",
     "SELECT etoro_position_id FROM positions WHERE closed_at IS NULL;"],
    capture_output=True, text=True
)
db_open_ids = set()
for line in result.stdout.strip().splitlines():
    line = line.strip()
    if line:
        db_open_ids.add(line)
print(f"DB open:    {len(db_open_ids)}")

# Find orphans: on eToro but not in DB
orphans = {eid: p for eid, p in etoro_by_id.items() if eid not in db_open_ids}
print(f"\nOrphans to close: {len(orphans)}")

if not orphans:
    print("Nothing to do.")
    sys.exit(0)

now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

for eid, pos in sorted(orphans.items(), key=lambda x: normalize_symbol(x[1].symbol)):
    sym = normalize_symbol(pos.symbol)
    instrument_id = SYMBOL_TO_INSTRUMENT_ID.get(sym)
    entry = float(pos.entry_price or 0)
    current = float(pos.current_price or entry)
    invested = float(pos.invested_amount or 0)
    side_str = str(pos.side).upper() if pos.side else 'LONG'
    is_long = 'LONG' in side_str or 'BUY' in side_str
    if entry > 0 and invested > 0:
        pnl = invested * (current - entry) / entry if is_long else invested * (entry - current) / entry
    else:
        pnl = float(pos.unrealized_pnl or 0)

    print(f"  Closing {sym:10s} etoro_id={eid} pnl=${pnl:.2f} ... ", end="", flush=True)
    try:
        client.close_position(eid, instrument_id=instrument_id)
        print("OK", end="")
    except Exception as e:
        print(f"FAILED: {e}", end="")

    # Insert stub closed position in DB so P&L is tracked
    pos_id = str(uuid.uuid4())
    insert_sql = (
        f"INSERT INTO positions (id, strategy_id, symbol, side, quantity, entry_price, "
        f"current_price, unrealized_pnl, realized_pnl, opened_at, closed_at, "
        f"etoro_position_id, invested_amount, closure_reason) VALUES ("
        f"'{pos_id}', 'etoro_position', '{sym}', '{side_str}', "
        f"{float(pos.quantity or 0)}, {entry}, {current}, 0.0, {round(pnl, 4)}, "
        f"'{pos.opened_at.strftime('%Y-%m-%d %H:%M:%S') if pos.opened_at else now_str}', "
        f"'{now_str}', '{eid}', {invested}, 'orphaned_position_closed_by_reconciliation');"
    )
    r2 = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "alphacent", "-t", "-A", "-c", insert_sql],
        capture_output=True, text=True
    )
    if r2.returncode == 0:
        print(f" [DB recorded pnl=${pnl:.2f}]")
    else:
        print(f" [DB insert failed: {r2.stderr.strip()[:80]}]")

print("\nDone. Run etoro_position_diff.py again to verify.")
