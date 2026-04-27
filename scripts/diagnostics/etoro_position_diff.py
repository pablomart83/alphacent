"""
One-shot diagnostic: compare eToro open positions vs DB open positions.
Prints what's on eToro but missing from DB, and what's in DB but not on eToro.
"""
import sys, subprocess
sys.path.insert(0, '/home/ubuntu/alphacent')

from src.core.config import get_config
from src.api.etoro_client import EToroAPIClient
from src.models.enums import TradingMode
from src.utils.symbol_normalizer import normalize_symbol

config = get_config()
credentials = config.load_credentials(TradingMode.DEMO)
client = EToroAPIClient(
    public_key=credentials["public_key"],
    user_key=credentials["user_key"],
    mode=TradingMode.DEMO
)

# eToro positions — normalize IDs to string
print("Fetching eToro positions...")
etoro_positions = client.get_positions()
etoro_by_id = {}
for p in etoro_positions:
    eid = str(p.etoro_position_id).strip()
    etoro_by_id[eid] = p
print(f"eToro open: {len(etoro_by_id)}")
print("eToro IDs sample:", list(etoro_by_id.keys())[:5])

# DB open positions via psql — normalize IDs to string
result = subprocess.run(
    ["sudo", "-u", "postgres", "psql", "alphacent", "-t", "-A", "-c",
     "SELECT etoro_position_id, symbol FROM positions WHERE closed_at IS NULL AND etoro_position_id IS NOT NULL;"],
    capture_output=True, text=True
)
db_by_id = {}
for line in result.stdout.strip().splitlines():
    parts = line.strip().split("|")
    if len(parts) == 2:
        eid = str(parts[0]).strip()
        db_by_id[eid] = parts[1]
print(f"DB open:    {len(db_by_id)}")
print("DB IDs sample:", list(db_by_id.keys())[:5])

# DB closed positions with closure_reason
result2 = subprocess.run(
    ["sudo", "-u", "postgres", "psql", "alphacent", "-t", "-A", "-c",
     "SELECT etoro_position_id, symbol, closure_reason FROM positions WHERE closed_at IS NOT NULL AND etoro_position_id IS NOT NULL;"],
    capture_output=True, text=True
)
db_closed_by_id = {}
for line in result2.stdout.strip().splitlines():
    parts = line.strip().split("|", 2)
    if len(parts) == 3:
        db_closed_by_id[str(parts[0]).strip()] = (parts[1], parts[2])

# On eToro but NOT in DB open
only_etoro = {k: v for k, v in etoro_by_id.items() if k not in db_by_id}
print(f"\n=== On eToro but MISSING from DB open ({len(only_etoro)}) ===")
for eid, pos in sorted(only_etoro.items(), key=lambda x: normalize_symbol(x[1].symbol)):
    sym = normalize_symbol(pos.symbol)
    if eid in db_closed_by_id:
        reason = db_closed_by_id[eid][1][:80]
        print(f"  {sym:10s}  etoro_id={eid}  [CLOSED IN DB: {reason}]")
    else:
        print(f"  {sym:10s}  etoro_id={eid}  [NOT IN DB AT ALL — TRUE ORPHAN]")

# In DB open but NOT on eToro
only_db = {k: v for k, v in db_by_id.items() if k not in etoro_by_id}
print(f"\n=== In DB open but NOT on eToro ({len(only_db)}) ===")
for eid, sym in sorted(only_db.items(), key=lambda x: x[1]):
    print(f"  {sym:10s}  etoro_id={eid}")

print("\nDone.")
